"""
modules/posting/__init__.py — Posting module.

Called by the unified 5-minute scheduler in main.py.

Handles:
  - Firing scheduled/immediate threads (every tick)
  - Polling reply queues for all users' tracked threads (every 15 min)

Reply queue auto-dismiss logic:
  When we find a new post from the thread owner (uid), we parse the BBCode
  for [quote ... pid='XXXX' ...] tags. Any matching unread reply_queue item
  gets dismissed automatically — user already replied to it elsewhere.
"""

import asyncio
import re
import logging
import time

from .router import router
from .posting_db import (
    init_posting_db,
    get_due_threads,
    mark_thread_sending,
    mark_thread_sent,
    mark_thread_failed,
    add_my_thread,
    get_all_tracked_threads,
    update_thread_last_checked,
    upsert_reply,
    auto_dismiss_by_pid,
    get_unread_count,
)
import db

log = logging.getLogger("posting")

# Regex to pull pid out of BBCode quote tags
# Matches: [quote="user" pid='123' dateline='456'] or [quote='user' pid='123' ...]
_QUOTE_PID_RE = re.compile(r"\[quote[^\]]*pid='(\d+)'", re.IGNORECASE)

# Strip BBCode for message preview
_BBCODE_RE = re.compile(r"\[/?[^\]]*\]")


def _strip_bb(text: str) -> str:
    return _BBCODE_RE.sub("", text or "").strip()


def _extract_quoted_pids(message: str) -> list[str]:
    """Return all PIDs quoted in a BBCode message."""
    return _QUOTE_PID_RE.findall(message or "")


# ── Scheduled thread firer ─────────────────────────────────────────────────────

async def fire_due_threads() -> None:
    """Fire all threads whose fire_at <= now. Called every scheduler tick."""
    from HFClient import HFClient

    due = await asyncio.to_thread(get_due_threads)
    if not due:
        return

    log.info("Posting: %d thread(s) due to fire", len(due))

    for row in due:
        row_id  = row["id"]
        uid     = row["uid"]
        fid     = row["fid"]
        subject = row["subject"]
        message = row["message"]
        title   = row["forum_name"]

        # Mark as 'sending' atomically before API call — prevents double-fire
        # if scheduler somehow overlaps (shouldn't happen, but be safe)
        await asyncio.to_thread(mark_thread_sending, row_id)

        token = await asyncio.to_thread(db.get_token, uid)
        if not token:
            await asyncio.to_thread(mark_thread_failed, row_id, "No token for user")
            log.warning("Posting: no token for uid=%s, row_id=%d", uid, row_id)
            continue

        try:
            client = HFClient(token)
            result = await client.write({
                "threads": {
                    "_fid":     int(fid),
                    "_subject": subject,
                    "_message": message,
                }
            })

            if not result:
                await asyncio.to_thread(mark_thread_failed, row_id, "API returned empty response")
                log.error("Posting: empty API response for row_id=%d uid=%s", row_id, uid)
                continue

            # HF returns the new thread's tid in result["threads"]["tid"]
            threads_result = result.get("threads") or {}
            if isinstance(threads_result, list):
                threads_result = threads_result[0] if threads_result else {}
            tid = str(threads_result.get("tid") or "")

            if not tid:
                await asyncio.to_thread(mark_thread_failed, row_id, "No TID in API response")
                log.error("Posting: no tid in response for row_id=%d — result: %s", row_id, result)
                continue

            await asyncio.to_thread(mark_thread_sent, row_id, tid)
            await asyncio.to_thread(add_my_thread, uid, tid, fid, subject)
            log.info("Posting: fired row_id=%d uid=%s tid=%s fid=%s subject='%s'",
                     row_id, uid, tid, fid, subject[:40])

            # Auto-bump: add to bumper if requested
            if row.get("auto_bump"):
                try:
                    from modules.autobump.autobump_db import add_job, _db as bump_db
                    interval_h = int(row.get("bump_interval_h") or 12)
                    import time as _t2
                    next_bump = int(_t2.time()) + interval_h * 3600
                    def _add_bump_job():
                        job = add_job(uid, tid, interval_h, next_bump_override=next_bump)
                        with bump_db() as conn:
                            conn.execute(
                                "UPDATE bump_jobs SET thread_title=?, fid=? WHERE uid=? AND tid=?",
                                (subject, fid, uid, tid)
                            )
                        return job
                    await asyncio.to_thread(_add_bump_job)
                    log.info("Posting: auto-added tid=%s to bumper (%dh) uid=%s", tid, interval_h, uid)
                except Exception as be:
                    log.warning("Posting: auto-bump add failed tid=%s: %s", tid, be)

        except Exception as e:
            await asyncio.to_thread(mark_thread_failed, row_id, str(e)[:500])
            log.exception("Posting: exception firing row_id=%d uid=%s: %s", row_id, uid, e)


# ── Reply queue poller ─────────────────────────────────────────────────────────

# In-memory: populated by crawl, consumed by reply poller each cycle.
# Key: uid, Value: set of tids where lastpost changed and lastposter != us/Stanley
_reply_check_queue:       dict[str, set[str]]       = {}
# Thread titles for queued tids
_reply_check_titles:      dict[str, dict[str, str]] = {}  # uid -> {tid -> title}
# numreplies hint for queued tids — used to calculate which page to fetch
_reply_check_numreplies:  dict[str, dict[str, int]] = {}  # uid -> {tid -> numreplies}

STANLEY_UID = "1337"


async def poll_reply_queues(active_uids: set | None = None) -> None:
    """
    Fetch posts ONLY for threads the crawl flagged as having new replies.
    The crawl (every 5 min) compares lastpost vs stored cursor and puts TIDs needing
    a check into _reply_check_queue. This function just drains that queue.

    Cost: 0 calls if nothing flagged. 1 call/thread with new replies + 1 users batch.
    Never polls old/inactive threads. Never polls threads where we or Stanley posted last.
    """
    from HFClient import HFClient

    # Snapshot and clear the queue atomically
    uids_to_process = list(_reply_check_queue.keys())
    if not uids_to_process:
        return

    now = int(time.time())

    for uid in uids_to_process:
        if active_uids is not None and uid not in active_uids:
            continue

        tids       = _reply_check_queue.pop(uid, set())
        titles     = _reply_check_titles.pop(uid, {})
        numreplies = _reply_check_numreplies.pop(uid, {})
        if not tids:
            continue

        token = await asyncio.to_thread(db.get_token, uid)
        if not token:
            continue

        client = HFClient(token)

        # Load last_pid cursors for these specific tids only
        all_tracked = await asyncio.to_thread(get_all_tracked_threads)
        tid_map = {str(t["tid"]): t for t in all_tracked if str(t["uid"]) == uid}

        pending: list[dict] = []
        tid_max_pid: dict[str, str] = {}

        for tid_str in tids:
            tracked  = tid_map.get(tid_str, {})
            last_pid = tracked.get("last_pid")

            # Treat NULL/0 last_pid as 0 — normal processing will queue any
            # non-self posts found. Handles first-time and recovery cases.
            if not last_pid:
                last_pid = "0"

            thread_title  = titles.get(tid_str, tracked.get("title", ""))
            nr            = numreplies.get(tid_str, 0)

            # Calculate which page(s) new replies are likely on.
            # Posts are returned oldest-first, so new replies are at the END.
            # Bug fix: always fetching page 1 was missing replies on threads with >30 posts.
            # Use numreplies (from crawl) to jump to the correct last page.
            # Fetch last page + one before it as a buffer for stale numreplies counts.
            last_pid_int = int(last_pid)
            if nr > 30:
                import math as _math
                last_page = _math.ceil(nr / 30)
                pages_to_fetch = list(dict.fromkeys([
                    max(1, last_page - 1),
                    last_page,
                    last_page + 1,   # one ahead in case numreplies was stale
                ]))
            elif last_pid_int == 0:
                pages_to_fetch = [1, 2]   # first time: grab first two pages
            else:
                pages_to_fetch = [1]

            try:
                collected_posts: list = []
                for fetch_page in pages_to_fetch:
                    page_data = await client.read({
                        "posts": {
                            "_tid":     [int(tid_str)],
                            "_page":    fetch_page,
                            "_perpage": 30,
                            "pid":      True,
                            "uid":      True,
                            "dateline": True,
                            "message":  True,
                            "subject":  True,
                        }
                    })
                    if not page_data:
                        continue
                    page_raw = page_data.get("posts", [])
                    if isinstance(page_raw, dict): page_raw = [page_raw]
                    collected_posts.extend(page_raw or [])

                if not collected_posts:
                    continue

                # Dedupe by pid (pages can overlap at boundaries)
                seen_pids: set[str] = set()
                max_pid   = last_pid
                new_posts = []
                for p in collected_posts:
                    pid_str  = str(p.get("pid") or "")
                    post_uid = str(p.get("uid") or "")
                    if not pid_str or pid_str in seen_pids:
                        continue
                    seen_pids.add(pid_str)
                    if int(pid_str) <= last_pid_int:
                        continue
                    if int(pid_str) > int(max_pid):
                        max_pid = pid_str
                    if post_uid in (uid, STANLEY_UID):
                        continue  # our own post or Stanley bump
                    new_posts.append(p)

                tid_max_pid[tid_str] = max_pid
                for p in new_posts:
                    pending.append({"tid_str": tid_str, "thread_title": thread_title, "post": p})

            except Exception as e:
                log.warning("Reply poll: post fetch failed uid=%s tid=%s: %s", uid, tid_str, e)

        # ── Batch username resolution ────────────────────────────────────────
        username_map: dict[str, str] = {}
        author_uids = list({str(item["post"].get("uid") or "") for item in pending if item["post"].get("uid")})
        if author_uids:
            try:
                u_data    = await client.read({"users": {"_uid": [int(u) for u in author_uids if u], "uid": True, "username": True}})
                users_raw = (u_data or {}).get("users", [])
                if isinstance(users_raw, dict): users_raw = [users_raw]
                for u in (users_raw or []):
                    username_map[str(u.get("uid") or "")] = str(u.get("username") or "")
            except Exception as e:
                log.warning("Reply poll: username batch failed uid=%s: %s", uid, e)

        # ── Queue replies ────────────────────────────────────────────────────
        _QUOTE_BLOCK = re.compile(r'\[quote[^\]]*\][\s\S]*?\[/quote\]', re.IGNORECASE)
        for item in pending:
            tid_str      = item["tid_str"]
            thread_title = item["thread_title"]
            p            = item["post"]
            pid_str      = str(p.get("pid") or "")
            post_uid     = str(p.get("uid") or "")
            post_message = str(p.get("message") or "")
            post_date    = int(p.get("dateline") or 0)
            post_username = username_map.get(post_uid, post_uid)

            clean = _QUOTE_BLOCK.sub('', post_message).strip()
            if not _strip_bb(clean).strip():
                continue
            preview = _strip_bb(clean)[:200]
            await asyncio.to_thread(
                upsert_reply, uid, tid_str, pid_str, thread_title,
                post_uid, post_username, post_date, preview, post_message,
            )

        # ── Update last_pid cursors ──────────────────────────────────────────
        for tid_str, max_pid in tid_max_pid.items():
            await asyncio.to_thread(update_thread_last_checked, uid, tid_str, max_pid, now)

        if pending:
            log.info("Reply poll: uid=%s queued %d new replies from %d threads", uid, len(pending), len(tids))


