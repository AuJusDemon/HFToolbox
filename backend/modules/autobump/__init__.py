import asyncio
"""
modules/autobump/__init__.py — Auto-Bump module.

Poll cycle: every 30 minutes.

Per-user logic:
  1. Collect all due jobs for this user
  2. Batch their TIDs — 4 per read() call (API max for _tid lists)
  3. For each thread: check lastpost against user's interval
     - Within window  → skip, reschedule to lastpost + interval
     - Outside window → charge 10 bytes fee, then bump
  4. Log every action

API cost per cycle:
  - 1 call per 4 threads checked (batched)
  - 1 bytes write (fee) + 1 bytes write (bump) per thread that actually bumps
  - Users with no due jobs cost zero calls
"""

import time
import logging

from .router import router
from scheduler import on_poll
import db

log = logging.getLogger("autobump")

BUMP_FEE     = 10
TIDS_PER_CALL = 4  # HF API max TIDs per _tid list


@on_poll("autobump")
async def poll_autobump(polling_uid: str, polling_token: str) -> None:
    """
    Runs every 30 min. Groups due jobs by user, batches TID lookups 4 at a time.
    Each user's jobs use that user's own token.
    """
    from .autobump_db import (
        get_all_due_jobs, update_after_bump, update_after_skip,
        log_action, init
    )
    from HFClient import HFClient

    init()  # ensure tables exist

    jobs = await asyncio.to_thread(get_all_due_jobs)
    if not jobs:
        return

    # Group by uid
    by_uid: dict[str, list[dict]] = {}
    for job in jobs:
        by_uid.setdefault(job["uid"], []).append(job)

    log.info("Autobump poll: %d due jobs across %d users", len(jobs), len(by_uid))

    for uid, user_jobs in by_uid.items():
        token = db.get_token(uid)
        if not token:
            log.warning("No token for uid=%s, skipping %d jobs", uid, len(user_jobs))
            continue

        client  = HFClient(token)
        now     = int(time.time())

        # Build TID list and a lookup map: tid_str -> job
        job_map  = {str(j["tid"]): j for j in user_jobs}
        tid_list = list(job_map.keys())

        # Batch fetch thread info — 4 TIDs per call
        thread_info: dict[str, dict] = {}

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
                if isinstance(rows, dict):
                    rows = [rows]
                for t in rows:
                    tid_str = str(t.get("tid") or "")
                    if tid_str:
                        thread_info[tid_str] = t
            except Exception as e:
                log.warning("Batch fetch failed for uid=%s chunk=%s: %s", uid, chunk, e)
                continue

        # Process each job using the fetched data
        for tid_str, job in job_map.items():
            thread = thread_info.get(tid_str)

            if not thread:
                await asyncio.to_thread(log_action, job["id"], uid, tid_str, "error", "Thread not found in API response")
                continue

            last_post_ts   = int(thread.get("lastpost")  or 0)
            fid            = str(thread.get("fid")        or "")
            thread_title   = str(thread.get("subject")    or "")
            interval_secs  = job["interval_h"] * 3600
            time_since_last = now - last_post_ts if last_post_ts else interval_secs + 1

            # Smart skip: post is within the interval window
            if last_post_ts and time_since_last < interval_secs:
                next_bump = last_post_ts + interval_secs
                await asyncio.to_thread(update_after_skip, job["id"], next_bump)
                hours_ago = round(time_since_last / 3600, 1)
                await asyncio.to_thread(log_action, job["id"], uid, tid_str, "skipped",
                    f"Post {hours_ago}h ago, within {job['interval_h']}h window")
                log.info("Skipped tid=%s uid=%s (post %sh ago)", tid_str, uid, hours_ago)
                continue

            fee_ok = True  # No platform fee in open-source build

            # Bump
            try:
                result = await client.write({
                    "bytes": {"_bump": int(tid_str)}
                })
                if result is not None:
                    # After bump, last post is NOW by Stanley — update to current time
                    await asyncio.to_thread(update_after_bump, job["id"], job["interval_h"], thread_title, fid,
                        int(time.time()), "Stanley")
                    await asyncio.to_thread(log_action, job["id"], uid, tid_str, "bumped",
                        f"Fee {'ok' if fee_ok else 'failed'}")
                    log.info("Bumped tid=%s uid=%s", tid_str, uid)
                else:
                    await asyncio.to_thread(log_action, job["id"], uid, tid_str, "error", "Bump returned None")
            except Exception as e:
                log.exception("Bump failed uid=%s tid=%s: %s", uid, tid_str, e)
                await asyncio.to_thread(log_action, job["id"], uid, tid_str, "error", str(e))
