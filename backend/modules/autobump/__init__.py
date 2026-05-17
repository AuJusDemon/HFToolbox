import os
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

# Stanley bump fee by group (display + budget tracking only — HF deducts this automatically on _bump)
STANLEY_FEE_DEFAULT = 100   # Regular / L33t
STANLEY_FEE_UBER    = 75    # Ub3r (GID 28)
STANLEY_FEE_VENDOR  = 50    # Vendor (GID 67)
MY_FEE           = 10        # bytes per bump sent to platform owner
MY_UID           = os.getenv("PLATFORM_OWNER_UID", "")  # set in .env — exempt from fee
TIDS_PER_CALL    = 4         # HF API max TIDs per _tid list
PAGE1_RECHECK    = 1800      # seconds between page1 checks when thread is still on page 1
STANLEY_UID      = "1337"    # Stanley bot UID — HF's autobump bot
MIN_BUMP_GAP_SECS = 300      # 5 min absolute hard minimum between bumps per job (safety gate)

# Guard against concurrent poll runs — unified loop calls this once per user,
# but each call must process only that user's jobs and never overlap.
_poll_lock = asyncio.Lock()


@on_poll("autobump")
async def poll_autobump(polling_uid: str, polling_token: str) -> None:
    from .autobump_db import (
        get_due_jobs_for_uid, update_after_bump, update_after_skip,
        log_action, init, get_settings, get_weekly_bump_count
    )
    from HFClient import HFClient

    init()

    if _poll_lock.locked():
        log.info("Autobump poll already running, skipping uid=%s", polling_uid)
        return

    async with _poll_lock:
        uid   = polling_uid
        token = polling_token

        jobs = await asyncio.to_thread(get_due_jobs_for_uid, uid)
        if not jobs:
            return

        log.info("Autobump poll uid=%s: %d due jobs", uid, len(jobs))

        # ── Weekly budget check ────────────────────────────────────────────────
        settings = await asyncio.to_thread(get_settings, uid)
        weekly_budget = int(settings.get("weekly_budget") or 0)
        if weekly_budget > 0:
            bump_count_this_week = await asyncio.to_thread(get_weekly_bump_count, uid)
            # Pick Stanley fee based on user's group for accurate budget tracking
            _ugroups = []
            try:
                _udata = db.get_user(uid)
                if _udata:
                    _ugroups = [str(g) for g in (_udata.get("groups") or [])]
            except Exception:
                pass
            if "67" in _ugroups:
                _stanley = STANLEY_FEE_VENDOR
            elif "28" in _ugroups:
                _stanley = STANLEY_FEE_UBER
            else:
                _stanley = STANLEY_FEE_DEFAULT
            cost_per_bump = _stanley if uid == MY_UID else _stanley + MY_FEE
            bytes_spent_this_week = bump_count_this_week * cost_per_bump
            if bytes_spent_this_week >= weekly_budget:
                log.info(
                    "Budget exceeded for uid=%s (%d/%d bytes this week) — skipping all bumps",
                    uid, bytes_spent_this_week, weekly_budget
                )
                for job in jobs:
                    await asyncio.to_thread(
                        log_action, job["id"], uid, str(job["tid"]),
                        "skipped",
                        f"Weekly budget exceeded ({bytes_spent_this_week}/{weekly_budget} bytes)"
                    )
                return

        # Skip immediately if token is known dead — don't waste API calls
        token_dead = await asyncio.to_thread(db.is_token_dead, uid)
        if token_dead:
            log.warning("Autobump: uid=%s token_dead=1 — skipping all jobs (user must re-login)", uid)
            return

        client = HFClient(token)

        # No separate token probe — the thread batch calls below act as the implicit
        # liveness check. If all chunks return no data, _process_timer_jobs marks the
        # token dead and logs the error for each job. The scheduler-level refresh path
        # in main.py handles token recovery for the next cycle.

        timer_jobs = [j for j in jobs if (j.get("mode") or "timer") == "timer"]
        page1_jobs = [j for j in jobs if (j.get("mode") or "timer") == "page1"]

        if timer_jobs:
            await _process_timer_jobs(uid, timer_jobs, client,
                                      update_after_bump, update_after_skip, log_action)
        if page1_jobs:
            await _process_page1_jobs(uid, page1_jobs, client,
                                      update_after_bump, update_after_skip, log_action)


async def _do_bump(uid: str, tid_str: str, job: dict, client,
                   thread_title: str, fid: str, numreplies: int | None,
                   update_after_bump, log_action) -> bool:
    """Execute the actual bump write. Returns True on success.
    NOTE: next_bump is already set by the caller before this is invoked.
    This function only updates bump_count and metadata on success.
    """
    try:
        # Fire the bump
        bump_result = await asyncio.wait_for(
            client.write({"bytes": {"_bump": int(tid_str)}}),
            timeout=12,
        )

        # Trust the write response — if it returned something, the bump landed.
        # The crawler's next bytes._from fetch will passively confirm it.
        # A separate confirmation read is a wasted call per bump.
        if bump_result is None:
            await asyncio.to_thread(log_action, job["id"], uid, tid_str, "error",
                                    "Bump write returned no response — fee not charged")
            log.warning("Bump write returned None uid=%s tid=%s — skipping fee", uid, tid_str)
            return False

        # Bump accepted — collect the fee
        # Small delay so the relay doesn't drop back-to-back write calls
        await asyncio.sleep(2)
        if uid != MY_UID:
            try:
                fee_result = await asyncio.wait_for(client.write({
                    "bytes": {
                        "_uid":    int(MY_UID),
                        "_amount": str(MY_FEE),
                        "_reason": f"HFToolbox | Bump Fee | TID: {tid_str}",
                    }
                }), timeout=12)
            except asyncio.TimeoutError:
                fee_result = None
                log.warning("Fee write timed out uid=%s tid=%s", uid, tid_str)
            fee_ok = (
                fee_result is not None
                and isinstance(fee_result, dict)
                and "bytes" in fee_result
            )
            if not fee_ok:
                err = repr(fee_result)
                if isinstance(fee_result, dict):
                    err = fee_result.get("error") or fee_result.get("message") or repr(fee_result)
                log.warning("Fee send failed uid=%s tid=%s: %s", uid, tid_str, err)
                await asyncio.to_thread(log_action, job["id"], uid, tid_str, "error",
                                        f"Fee send failed: {err}")
            else:
                log.info("Fee collected: %d bytes from uid=%s tid=%s", MY_FEE, uid, tid_str)

        # next_bump already set — just update bump_count and metadata
        await asyncio.to_thread(
            update_after_bump,
            job["id"], thread_title, fid,
            int(time.time()), "Stanley"
        )
        await asyncio.to_thread(
            log_action, job["id"], uid, tid_str, "bumped", "", numreplies
        )
        log.info("Bumped tid=%s uid=%s mode=%s replies=%s",
                 tid_str, uid, job.get("mode", "timer"), numreplies)
        return True
    except Exception as e:
        log.exception("Bump failed uid=%s tid=%s: %s", uid, tid_str, e)
        await asyncio.to_thread(log_action, job["id"], uid, tid_str, "error", str(e))
        return False


async def _process_timer_jobs(uid, user_jobs, client,
                               update_after_bump, update_after_skip, log_action):
    now     = int(time.time())
    job_map = {str(j["tid"]): j for j in user_jobs}
    tid_list = list(job_map.keys())

    thread_info: dict[str, dict] = {}
    total_chunks  = len(range(0, len(tid_list), TIDS_PER_CALL))
    failed_chunks = 0

    for i in range(0, len(tid_list), TIDS_PER_CALL):
        chunk = tid_list[i:i + TIDS_PER_CALL]
        try:
            data = await client.read({
                "threads": {
                    "_tid":         chunk,
                    "tid":          True,
                    "fid":          True,
                    "subject":      True,
                    "lastpost":     True,
                    "lastposteruid": True,
                    "lastposter":   True,
                    "numreplies":   True,
                }
            })
            if not data or "threads" not in data:
                failed_chunks += 1
                log.warning("Batch fetch returned no thread data uid=%s chunk=%s (data=%s) — token may be expired",
                            uid, chunk, repr(data)[:120] if data else None)
                continue
            rows = data.get("threads", [])
            if isinstance(rows, dict):
                rows = [rows]
            for t in rows:
                tid_str = str(t.get("tid") or "")
                if tid_str:
                    thread_info[tid_str] = t
        except Exception as e:
            failed_chunks += 1
            log.warning("Batch fetch failed uid=%s chunk=%s: %s", uid, chunk, e)
            continue

    # If every single chunk returned no data, the token is almost certainly dead.
    # Don't log "Thread not found" for each job — log one meaningful error and bail.
    if failed_chunks == total_chunks and total_chunks > 0:
        log.warning(
            "Autobump: all %d chunk(s) returned no data for uid=%s — token likely expired, marking dead",
            total_chunks, uid,
        )
        await asyncio.to_thread(db.mark_token_dead, uid)
        for tid_str, job in job_map.items():
            await asyncio.to_thread(
                log_action, job["id"], uid, tid_str, "error",
                "Token expired or revoked — user must re-login to HFToolbox"
            )
        return

    for tid_str, job in job_map.items():
        thread = thread_info.get(tid_str)
        if not thread:
            await asyncio.to_thread(log_action, job["id"], uid, tid_str, "error",
                                    "Thread not found in API response")
            continue

        last_post_ts    = int(thread.get("lastpost")       or 0)
        last_poster_uid = str(thread.get("lastposteruid") or "")
        fid             = str(thread.get("fid")            or "")
        thread_title    = str(thread.get("subject")        or "")
        numreplies      = int(thread.get("numreplies")     or 0) or None
        interval_secs   = job["interval_h"] * 3600
        time_since_last = now - last_post_ts if last_post_ts else interval_secs + 1

        if last_post_ts and time_since_last < interval_secs:
            next_bump = last_post_ts + interval_secs
            await asyncio.to_thread(update_after_skip, job["id"], next_bump)
            hours_ago = round(time_since_last / 3600, 1)
            await asyncio.to_thread(log_action, job["id"], uid, tid_str, "skipped",
                f"Post {hours_ago}h ago, within {job['interval_h']}h window")
            log.info("Skipped tid=%s uid=%s (post %sh ago)", tid_str, uid, hours_ago)
            continue

        # ── Safety gate 1: hard last_bumped cooldown ──────────────────────────
        # Even if next_bump says we're due, refuse to fire if last_bumped was less
        # than MIN_BUMP_GAP_SECS ago. Prevents any double-charge scenario regardless
        # of how next_bump ended up in the past (restart, DB glitch, code bug).
        last_bumped = int(job.get("last_bumped") or 0)
        if last_bumped and (now - last_bumped) < MIN_BUMP_GAP_SECS:
            secs_ago = now - last_bumped
            log.warning(
                "Safety gate 1 (last_bumped): tid=%s uid=%s — bumped only %ds ago, refusing",
                tid_str, uid, secs_ago
            )
            await asyncio.to_thread(update_after_skip, job["id"], last_bumped + interval_secs)
            await asyncio.to_thread(log_action, job["id"], uid, tid_str, "error",
                f"Safety gate: last_bumped {secs_ago}s ago (min {MIN_BUMP_GAP_SECS}s) — aborted")
            continue

        # ── Safety gate 2: Stanley just posted ────────────────────────────────
        # If Stanley is the lastposter AND posted within MIN_BUMP_GAP_SECS, a bump
        # likely happened very recently (from a run whose next_bump update didn't
        # persist). Treat this as already-bumped and reschedule from Stanley's post.
        if last_poster_uid == STANLEY_UID and last_post_ts and time_since_last < MIN_BUMP_GAP_SECS:
            log.warning(
                "Safety gate 2 (Stanley recency): tid=%s uid=%s — Stanley posted %ds ago, skipping",
                tid_str, uid, int(time_since_last)
            )
            await asyncio.to_thread(update_after_skip, job["id"], last_post_ts + interval_secs)
            await asyncio.to_thread(log_action, job["id"], uid, tid_str, "error",
                f"Safety gate: Stanley posted {int(time_since_last)}s ago — likely already bumped")
            continue

        # Set next_bump BEFORE attempting the bump.
        # If the backend crashes between here and _do_bump completing,
        # the job won't re-fire immediately on restart — preventing double fees.
        next_bump = now + interval_secs
        await asyncio.to_thread(update_after_skip, job["id"], next_bump)

        await _do_bump(uid, tid_str, job, client, thread_title, fid, numreplies,
                       update_after_bump, log_action)


async def _process_page1_jobs(uid, user_jobs, client,
                               update_after_bump, update_after_skip, log_action):
    now = int(time.time())

    no_fid_jobs  = [j for j in user_jobs if not j.get("fid")]
    has_fid_jobs = [j for j in user_jobs if j.get("fid")]

    if no_fid_jobs:
        tid_list = [str(j["tid"]) for j in no_fid_jobs]
        job_map  = {str(j["tid"]): j for j in no_fid_jobs}
        for i in range(0, len(tid_list), TIDS_PER_CALL):
            chunk = tid_list[i:i + TIDS_PER_CALL]
            try:
                data = await client.read({
                    "threads": {"_tid": chunk, "tid": True, "fid": True, "subject": True}
                })
                if not data:
                    continue
                rows = data.get("threads", [])
                if isinstance(rows, dict):
                    rows = [rows]
                for t in rows:
                    tid_str = str(t.get("tid") or "")
                    if tid_str and tid_str in job_map:
                        job_map[tid_str]["fid"]             = str(t.get("fid")     or "")
                        job_map[tid_str]["_title_resolved"] = str(t.get("subject") or "")
            except Exception as e:
                log.warning("FID resolve failed uid=%s chunk=%s: %s", uid, chunk, e)

        for j in no_fid_jobs:
            if j.get("fid"):
                has_fid_jobs.append(j)
            else:
                await asyncio.to_thread(log_action, j["id"], uid, str(j["tid"]),
                                        "error", "Could not resolve FID for page1 job")

    if not has_fid_jobs:
        return

    by_fid: dict[str, list[dict]] = {}
    for job in has_fid_jobs:
        by_fid.setdefault(str(job["fid"]), []).append(job)

    for fid, fid_jobs in by_fid.items():
        page1_tids:    set[str]         = set()
        page1_replies: dict[str, int]   = {}

        try:
            data = await client.read({
                "threads": {
                    "_fid":       [fid],
                    "_page":      1,
                    "_perpage":   30,
                    "tid":        True,
                    "subject":    True,
                    "numreplies": True,
                    "lastpost":   True,
                }
            })
            if data:
                rows = data.get("threads", [])
                if isinstance(rows, dict):
                    rows = [rows]
                for t in rows:
                    tid_str = str(t.get("tid") or "")
                    if tid_str:
                        page1_tids.add(tid_str)
                        nr = t.get("numreplies")
                        if nr is not None:
                            page1_replies[tid_str] = int(nr)
                log.info("Page1 check fid=%s uid=%s — %d threads on page 1", fid, uid, len(page1_tids))
        except Exception as e:
            log.warning("Page1 FID fetch failed uid=%s fid=%s: %s", uid, fid, e)
            for job in fid_jobs:
                tid_str = str(job["tid"])
                await asyncio.to_thread(update_after_skip, job["id"], now + PAGE1_RECHECK)
                await asyncio.to_thread(log_action, job["id"], uid, tid_str,
                                        "error", f"FID page fetch failed: {e}")
            continue

        for job in fid_jobs:
            tid_str      = str(job["tid"])
            thread_title = job.get("thread_title") or job.get("_title_resolved") or ""
            numreplies   = page1_replies.get(tid_str)

            if tid_str in page1_tids:
                await asyncio.to_thread(update_after_skip, job["id"], now + PAGE1_RECHECK)
                await asyncio.to_thread(log_action, job["id"], uid, tid_str,
                                        "skipped", "Thread still on page 1")
                log.info("Page1 skip tid=%s uid=%s (on page 1)", tid_str, uid)
            else:
                # ── Safety gate 1: hard last_bumped cooldown ──────────────────
                last_bumped = int(job.get("last_bumped") or 0)
                if last_bumped and (now - last_bumped) < MIN_BUMP_GAP_SECS:
                    secs_ago = now - last_bumped
                    log.warning(
                        "Safety gate 1 (last_bumped): tid=%s uid=%s — bumped only %ds ago, refusing",
                        tid_str, uid, secs_ago
                    )
                    await asyncio.to_thread(update_after_skip, job["id"],
                                            last_bumped + job["interval_h"] * 3600)
                    await asyncio.to_thread(log_action, job["id"], uid, tid_str, "error",
                        f"Safety gate: last_bumped {secs_ago}s ago (min {MIN_BUMP_GAP_SECS}s) — aborted")
                    continue
                log.info("Page1 bump tid=%s uid=%s (not on page 1 of fid=%s)", tid_str, uid, fid)
                # Reschedule before bump — crash-safe
                await asyncio.to_thread(update_after_skip, job["id"], now + job["interval_h"] * 3600)
                await _do_bump(uid, tid_str, job, client, thread_title, fid, numreplies,
                               update_after_bump, log_action)
