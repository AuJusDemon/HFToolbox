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
    update_thread_numreplies,
    upsert_reply,
    auto_dismiss_by_pid,
    get_unread_count,
)
import db
import integration_db
from .reply_pagination import fetch_changed_thread_posts

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
            client = HFClient(
                token,
                owner_uid=uid,
                feature="posting.fire_due",
                priority=2,
                background=False,
                route_class="high",
                egress_lane="critical",
            )
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

            # Overflow replies — post immediately after thread (up to 2 replies)
            async def _post_overflow(msg, label):
                try:
                    r = await client.write(
                        {"posts": {"_tid": int(tid), "_message": msg}},
                        feature="posting.overflow_reply",
                        priority=2,
                    )
                    if r:
                        rp = r.get("posts") or {}
                        if isinstance(rp, list): rp = rp[0] if rp else {}
                        log.info("Posting: %s posted tid=%s pid=%s", label, tid, rp.get("pid","?"))
                    else:
                        log.warning("Posting: %s empty response tid=%s", label, tid)
                except Exception as oe:
                    log.warning("Posting: %s failed tid=%s: %s", label, tid, oe)

            overflow1 = str(row.get("overflow_message") or "").strip()
            overflow2 = str(row.get("overflow_message_2") or "").strip()
            if overflow1:
                await _post_overflow(overflow1, "reply-1")
            if overflow2:
                await _post_overflow(overflow2, "reply-2")

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
# numreplies hint for queued tids - used to calculate which page to fetch
_reply_check_numreplies:  dict[str, dict[str, int]] = {}  # uid -> {tid -> numreplies}
# tids that were first discovered this crawl cycle - seed cursor without queuing replies
_reply_check_seed_tids:   dict[str, set[str]]       = {}  # uid -> {tid}
_reply_poll_backoff_until: dict[str, int]            = {}

STANLEY_UID = "1337"

_HF_BACKOFF_ERRORS = {
    "global_circuit_open",
    "control_plane_unavailable",
    "upstream_unavailable",
    "token_cooldown",
    "rate_limited",
    "http_403",
    "http_429",
    "http_502_503",
    "html_challenge",
    "cloudflare_challenge",
}


def _is_hf_backoff_error(error: str) -> bool:
    error = (error or "").strip().lower()
    return bool(error) and any(marker in error for marker in _HF_BACKOFF_ERRORS)


def _restore_reply_checks(uid: str, tids: set[str], titles: dict[str, str],
                          numreplies: dict[str, int], seed_tids: set[str]) -> None:
    if tids:
        _reply_check_queue.setdefault(uid, set()).update(tids)
    if titles:
        _reply_check_titles.setdefault(uid, {}).update(titles)
    if numreplies:
        _reply_check_numreplies.setdefault(uid, {}).update(numreplies)
    if seed_tids:
        _reply_check_seed_tids.setdefault(uid, set()).update(seed_tids)


async def poll_reply_queues(active_uids: set | None = None) -> None:
    """
    Fetch posts ONLY for threads the crawl flagged as having new replies.
    The crawl (every 5 min) compares lastpost vs stored cursor and puts TIDs needing
    a check into _reply_check_queue. This function just drains that queue.

    Cost: 0 calls if nothing is flagged. Changed threads use one shared metadata
    lookup plus their final post pages. Owner and Stanley posts are filtered only
    after the changed thread has been inspected.
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
        if now < _reply_poll_backoff_until.get(uid, 0):
            continue

        tids       = _reply_check_queue.pop(uid, set())
        titles     = _reply_check_titles.pop(uid, {})
        numreplies = _reply_check_numreplies.pop(uid, {})
        seed_tids  = _reply_check_seed_tids.pop(uid, set())
        if not tids:
            continue

        token = await asyncio.to_thread(db.get_token, uid)
        if not token:
            continue

        client = HFClient(
            token,
            owner_uid=uid,
            feature="posting.reply_poll",
            priority=7,
            background=True,
            route_class="background",
            egress_lane="background",
        )

        # threads._uid frequently omits numreplies. Resolve changed TIDs through
        # threads._tid in one batch before calculating their final posts pages.
        targeted_counts: dict[str, int | None] = {}
        try:
            meta_data = await client.read({"threads": {
                "_tid": [int(t) for t in tids],
                "tid": True, "numreplies": True,
            }}, feature="posting.reply_poll.metadata", background=True,
                priority=7, cache_ttl=5, stale_ttl=300)
            meta_rows = (meta_data or {}).get("threads", [])
            if isinstance(meta_rows, dict):
                meta_rows = [meta_rows]
            for row in (meta_rows or []):
                meta_tid = str(row.get("tid") or "")
                raw_count = row.get("numreplies")
                if meta_tid:
                    targeted_counts[meta_tid] = int(raw_count) if raw_count is not None else None
            if not meta_rows and _is_hf_backoff_error(getattr(client, "last_error", "")):
                _restore_reply_checks(uid, tids, titles, numreplies, seed_tids)
                _reply_poll_backoff_until[uid] = now + 900
                log.warning(
                    "Reply poll: uid=%s backing off 900s after controller error=%s",
                    uid, getattr(client, "last_error", ""),
                )
                continue
        except Exception as exc:
            log.warning("Reply poll: targeted thread metadata failed uid=%s: %s", uid, exc)

        # Load last_pid cursors for these specific tids only
        all_tracked = await asyncio.to_thread(get_all_tracked_threads)
        tid_map = {str(t["tid"]): t for t in all_tracked if str(t["uid"]) == uid}

        pending: list[dict] = []
        tid_max_pid: dict[str, str] = {}
        failed_tids: set[str] = set()
        stop_due_to_backoff = False

        for tid_str in tids:
            if stop_due_to_backoff:
                failed_tids.add(tid_str)
                continue

            tracked  = tid_map.get(tid_str, {})
            last_pid = tracked.get("last_pid")

            if not last_pid:
                last_pid = "0"
            last_pid_int = int(last_pid)

            # seed_only: true only for threads first discovered this crawl cycle.
            # Existing tracked threads with last_pid=0 due to stale cursors are NOT seed.
            seed_only    = tid_str in seed_tids
            thread_title = titles.get(tid_str, tracked.get("title", ""))

            nr = targeted_counts.get(tid_str)
            if nr == 0 and last_pid_int > 0:
                # A populated cursor and a zero count is the known bad API shape.
                nr = None

            try:
                collected_posts, verified_replies = await fetch_changed_thread_posts(
                    client, tid_str, nr,
                )
                await asyncio.to_thread(
                    update_thread_numreplies, uid, tid_str, verified_replies,
                )

                if not collected_posts:
                    log.info("Reply poll: uid=%s tid=%s - no posts returned", uid, tid_str)
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

                cursor_advanced = int(max_pid) > last_pid_int
                if cursor_advanced:
                    tid_max_pid[tid_str] = max_pid

                log.info(
                    "Reply poll: uid=%s tid=%s replies=%d collected=%d new=%d seed=%s cursor_adv=%s",
                    uid, tid_str, verified_replies, len(collected_posts), len(new_posts),
                    seed_only, cursor_advanced,
                )

                if not seed_only:
                    for p in new_posts:
                        pending.append({"tid_str": tid_str, "thread_title": thread_title, "post": p})

            except Exception as e:
                log.warning("Reply poll: post fetch failed uid=%s tid=%s: %s", uid, tid_str, e)
                failed_tids.add(tid_str)
                if _is_hf_backoff_error(getattr(client, "last_error", "")):
                    stop_due_to_backoff = True

        if failed_tids:
            failed_titles = {t: titles[t] for t in failed_tids if t in titles}
            failed_nr = {t: numreplies[t] for t in failed_tids if t in numreplies}
            failed_seed_tids = {t for t in failed_tids if t in seed_tids}
            _restore_reply_checks(uid, failed_tids, failed_titles, failed_nr, failed_seed_tids)
            if _is_hf_backoff_error(getattr(client, "last_error", "")):
                _reply_poll_backoff_until[uid] = now + 900
                log.warning(
                    "Reply poll: uid=%s parked %d tid(s) for 900s after controller error=%s",
                    uid, len(failed_tids), getattr(client, "last_error", ""),
                )
            else:
                log.info("Reply poll: uid=%s re-queued %d tid(s) for retry (transient HF failure)",
                         uid, len(failed_tids))

        # ── Batch username resolution ────────────────────────────────────────
        username_map: dict[str, str] = {}
        author_uids = list({str(item["post"].get("uid") or "") for item in pending if item["post"].get("uid")})
        if author_uids:
            try:
                u_data    = await client.read({"users": {
                    "_uid": [int(u) for u in author_uids if u],
                    "uid": True, "username": True, "avatar": True,
                    "usertitle": True, "reputation": True,
                    "displaygroup": True, "additionalgroups": True,
                }}, feature="posting.reply_poll.users", background=True,
                    priority=8, cache_ttl=60, stale_ttl=3600)
                users_raw = (u_data or {}).get("users", [])
                if isinstance(users_raw, dict): users_raw = [users_raw]
                uid_profile_map: dict = {}
                for u in (users_raw or []):
                    _u_uid = str(u.get("uid") or "")
                    _u_name = str(u.get("username") or "")
                    if _u_uid:
                        username_map[_u_uid] = _u_name
                        av = str(u.get("avatar", "") or "")
                        if av and not av.startswith("http"):
                            av = "https://hackforums.net/" + av.lstrip("./")
                        uid_profile_map[_u_uid] = {
                            "username":         _u_name,
                            "avatar":           av,
                            "usertitle":        str(u.get("usertitle", "") or ""),
                            "reputation":       int(u.get("reputation") or 0),
                            "displaygroup":     str(u.get("displaygroup") or ""),
                            "additionalgroups": str(u.get("additionalgroups") or ""),
                        }
                if uid_profile_map:
                    await asyncio.to_thread(db.upsert_uid_usernames, uid_profile_map)
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

            clean = post_message
            prev = None
            while prev != clean:
                prev = clean
                clean = _QUOTE_BLOCK.sub('', clean)
            clean = clean.strip()
            if not _strip_bb(clean).strip():
                continue
            preview = _strip_bb(clean)[:200]
            log.info("Reply poll: uid=%s tid=%s inserting pid=%s from_uid=%s",
                     uid, tid_str, pid_str, post_uid)
            await asyncio.to_thread(
                upsert_reply, uid, tid_str, pid_str, thread_title,
                post_uid, post_username, post_date, preview, post_message,
            )
            await asyncio.to_thread(
                integration_db.create_alert_event,
                uid, "reply_tracked_thread", f"pid:{pid_str}",
                f"Reply in: {thread_title or tid_str}",
                f"{post_username}: {preview}" if post_username else preview,
                f"https://hackforums.net/showthread.php?tid={tid_str}&pid={pid_str}#pid{pid_str}",
                "toolbox", None, False,
            )

        # ── Update last_pid cursors ──────────────────────────────────────────
        for tid_str, max_pid in tid_max_pid.items():
            await asyncio.to_thread(update_thread_last_checked, uid, tid_str, max_pid, now)

        if pending:
            log.info("Reply poll: uid=%s queued %d new replies from %d threads", uid, len(pending), len(tids))


