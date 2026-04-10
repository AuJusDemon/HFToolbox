import asyncio
"""
modules/autobump/__init__.py — Auto-Bump module.

Poll cycle: every 30 minutes.

Timer mode:
  1. Fetch thread data (lastpost, numreplies) for all due jobs — 4 TIDs per API call
  2. Smart skip if someone posted within the interval window
  3. Bump — logs numreplies at time of bump for stats tracking

Page1 mode:
  1. Group due jobs by FID — one API call per forum fetches page 1
  2. Skip if thread is still on page 1 (recheck in 30 min)
  3. Bump when thread falls off page 1

Budget check:
  - If user has a weekly byte budget set, count bumps in the last 7 days
  - Each bump costs ~50 bytes (Stanley fee)
  - Skip all bumps for user if budget exceeded
"""

import time
import logging

from .router import router
from scheduler import on_poll
import db

log = logging.getLogger("autobump")

STANLEY_FEE   = 50
TIDS_PER_CALL = 4
PAGE1_RECHECK = 1800


@on_poll("autobump")
async def poll_autobump(polling_uid: str, polling_token: str) -> None:
    from .autobump_db import (
        get_all_due_jobs, update_after_bump, update_after_skip,
        log_action, init, get_settings, get_weekly_bump_count
    )
    from HFClient import HFClient

    init()

    jobs = await asyncio.to_thread(get_all_due_jobs)
    if not jobs:
        return

    by_uid: dict[str, list[dict]] = {}
    for job in jobs:
        by_uid.setdefault(job["uid"], []).append(job)

    log.info("Autobump poll: %d due jobs across %d users", len(jobs), len(by_uid))

    for uid, user_jobs in by_uid.items():
        token = await asyncio.to_thread(db.get_token, uid)
        if not token:
            log.warning("No token for uid=%s, skipping %d jobs", uid, len(user_jobs))
            continue

        # ── Weekly budget check ────────────────────────────────────────────
        settings = await asyncio.to_thread(get_settings, uid)
        weekly_budget = int(settings.get("weekly_budget") or 0)
        if weekly_budget > 0:
            bump_count_this_week = await asyncio.to_thread(get_weekly_bump_count, uid)
            bytes_spent_this_week = bump_count_this_week * STANLEY_FEE
            if bytes_spent_this_week >= weekly_budget:
                log.info(
                    "Budget exceeded for uid=%s (%d/%d bytes this week) — skipping",
                    uid, bytes_spent_this_week, weekly_budget
                )
                for job in user_jobs:
                    await asyncio.to_thread(
                        log_action, job["id"], uid, str(job["tid"]),
                        "skipped",
                        f"Weekly budget exceeded ({bytes_spent_this_week}/{weekly_budget} bytes)"
                    )
                continue

        client = HFClient(token)

        timer_jobs = [j for j in user_jobs if (j.get("mode") or "timer") == "timer"]
        page1_jobs = [j for j in user_jobs if (j.get("mode") or "timer") == "page1"]

        if timer_jobs:
            await _process_timer_jobs(uid, timer_jobs, client,
                                      update_after_bump, update_after_skip, log_action)
        if page1_jobs:
            await _process_page1_jobs(uid, page1_jobs, client,
                                      update_after_bump, update_after_skip, log_action)


async def _do_bump(uid: str, tid_str: str, job: dict, client,
                   thread_title: str, fid: str, numreplies: int | None,
                   update_after_bump, log_action) -> bool:
    """Execute the actual bump write. Returns True on success."""
    try:
        result = await client.write({"bytes": {"_bump": int(tid_str)}})
        if result is not None:
            await asyncio.to_thread(
                update_after_bump,
                job["id"], job["interval_h"], thread_title, fid,
                int(time.time()), "Stanley", job.get("mode", "timer")
            )
            await asyncio.to_thread(
                log_action, job["id"], uid, tid_str, "bumped", "", numreplies
            )
            log.info("Bumped tid=%s uid=%s mode=%s replies=%s",
                     tid_str, uid, job.get("mode", "timer"), numreplies)
            return True
        else:
            await asyncio.to_thread(log_action, job["id"], uid, tid_str, "error", "Bump returned None")
            return False
    except Exception as e:
        log.exception("Bump failed uid=%s tid=%s: %s", uid, tid_str, e)
        await asyncio.to_thread(log_action, job["id"], uid, tid_str, "error", str(e))
        return False


async def _process_timer_jobs(uid, user_jobs, client,
                              update_after_bump, update_after_skip, log_action):
    """Timer mode: check lastpost, smart skip or bump."""
    job_map  = {str(j["tid"]): j for j in user_jobs}
    tid_list = list(job_map.keys())
    thread_info: dict[str, dict] = {}
    now = int(time.time())

    for i in range(0, len(tid_list), TIDS_PER_CALL):
        chunk = tid_list[i:i + TIDS_PER_CALL]
        try:
            data = await client.read({
                "threads": {
                    "_tid":       chunk,
                    "tid":        True,
                    "fid":        True,
                    "subject":    True,
                    "lastpost":   True,
                    "numreplies": True,
                }
            })
            if not data:
                continue
            rows = data.get("threads", [])
            if isinstance(rows, dict): rows = [rows]
            for t in rows:
                tid_str = str(t.get("tid") or "")
                if tid_str:
                    thread_info[tid_str] = t
        except Exception as e:
            log.warning("Timer batch fetch failed uid=%s chunk=%s: %s", uid, chunk, e)

    for tid_str, job in job_map.items():
        thread = thread_info.get(tid_str)
        if not thread:
            await asyncio.to_thread(log_action, job["id"], uid, tid_str,
                                    "error", "Thread not found in API response")
            continue

        last_post_ts  = int(thread.get("lastpost")  or 0)
        fid           = str(thread.get("fid")        or "")
        thread_title  = str(thread.get("subject")    or "")
        numreplies    = int(thread.get("numreplies") or 0) or None
        interval_secs = job["interval_h"] * 3600
        time_since    = now - last_post_ts if last_post_ts else interval_secs + 1

        if last_post_ts and time_since < interval_secs:
            next_bump = last_post_ts + interval_secs
            await asyncio.to_thread(update_after_skip, job["id"], next_bump)
            hours_ago = round(time_since / 3600, 1)
            await asyncio.to_thread(
                log_action, job["id"], uid, tid_str, "skipped",
                f"Post {hours_ago}h ago, within {job['interval_h']}h window"
            )
            log.info("Skipped tid=%s uid=%s (post %sh ago)", tid_str, uid, hours_ago)
            continue

        await _do_bump(uid, tid_str, job, client, thread_title, fid, numreplies,
                       update_after_bump, log_action)


async def _process_page1_jobs(uid, user_jobs, client,
                              update_after_bump, update_after_skip, log_action):
    """Page1 mode: bump only when thread has fallen off page 1."""
    now = int(time.time())

    # Group by FID — one forum API call retrieves all threads for that forum
    by_fid: dict[str, list[dict]] = {}
    unfid: list[dict] = []
    for job in user_jobs:
        fid = str(job.get("fid") or "")
        if fid:
            by_fid.setdefault(fid, []).append(job)
        else:
            unfid.append(job)
    # Jobs with no cached FID: skip this cycle (FID populated after first timer bump)
    for job in unfid:
        await asyncio.to_thread(update_after_skip, job["id"], now + PAGE1_RECHECK)
        log.debug("Page1 skip tid=%s uid=%s — no FID cached yet", job["tid"], uid)

    for fid, fid_jobs in by_fid.items():
        try:
            data = await client.read({
                "threads": {
                    "_fid":     [int(fid)],
                    "_page":    1,
                    "_perpage": 30,
                    "tid":      True,
                    "lastpost": True,
                }
            })
            if not data:
                for job in fid_jobs:
                    await asyncio.to_thread(update_after_skip, job["id"], now + PAGE1_RECHECK)
                continue

            page1_rows = data.get("threads", [])
            if isinstance(page1_rows, dict): page1_rows = [page1_rows]
            page1_tids = {str(t.get("tid") or "") for t in (page1_rows or [])}

        except Exception as e:
            log.warning("Page1 forum fetch failed uid=%s fid=%s: %s", uid, fid, e)
            for job in fid_jobs:
                await asyncio.to_thread(update_after_skip, job["id"], now + PAGE1_RECHECK)
            continue

        for job in fid_jobs:
            tid_str = str(job["tid"])
            thread_title = str(job.get("thread_title") or "")

            if tid_str in page1_tids:
                # Still on page 1 — recheck later
                await asyncio.to_thread(update_after_skip, job["id"], now + PAGE1_RECHECK)
                log.info("Page1 skip tid=%s uid=%s — still on page 1", tid_str, uid)
                await asyncio.to_thread(log_action, job["id"], uid, tid_str,
                                        "skipped", "Still on page 1")
            else:
                # Fell off page 1 — bump
                await _do_bump(uid, tid_str, job, client, thread_title, fid, None,
                               update_after_bump, log_action)
