"""Auto-Bump worker for inactivity and weekly-calendar schedules."""

import os
import asyncio
import time
import logging

from .router import router
from scheduler import on_poll
import db
from hf_thread_stats import thread_reply_count
from .fees import fee_breakdown
from .schedule import calculate_updated_next

log = logging.getLogger("autobump")

MY_UID           = os.getenv("PLATFORM_OWNER_UID", "")  # set in .env — exempt from fee
TIDS_PER_CALL    = 30        # verified live against threads._tid on 2026-09-07
STANLEY_UID      = "1337"    # Stanley bot UID — HF's autobump bot
MIN_BUMP_GAP_SECS = 300      # 5 min absolute hard minimum between bumps per job (safety gate)

# Guard against concurrent poll runs — unified loop calls this once per user,
# but each call must process only that user's jobs and never overlap.
_poll_lock = asyncio.Lock()


@on_poll("autobump")
async def poll_autobump(polling_uid: str, polling_token: str) -> None:
    from .autobump_db import (
        get_due_jobs_for_uid, update_after_bump, update_after_skip,
        log_action, init, get_settings, get_weekly_spend, complete_job
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
        user_data = await asyncio.to_thread(db.get_user, uid) or {}
        user_groups = user_data.get("groups") or []
        fees = fee_breakdown(uid, user_groups, MY_UID)

        runnable_jobs = []
        for job in jobs:
            if job.get("end_mode") == "bytes":
                limit = int(job.get("end_limit") or 0)
                spent = int(job.get("spent_bytes") or 0)
                if limit and spent + int(fees["total_cost"]) > limit:
                    await asyncio.to_thread(complete_job, job["id"])
                    await asyncio.to_thread(
                        log_action, job["id"], uid, str(job["tid"]), "skipped",
                        f"Next successful bump would exceed the {limit} Byte job limit",
                    )
                    continue
            runnable_jobs.append(job)
        jobs = runnable_jobs
        if not jobs:
            return

        if weekly_budget > 0:
            cost_per_bump = int(fees["total_cost"])
            bytes_spent_this_week = await asyncio.to_thread(
                get_weekly_spend, uid, cost_per_bump
            )
            if bytes_spent_this_week + cost_per_bump > weekly_budget:
                log.info(
                    "Budget exceeded for uid=%s (%d/%d bytes this week) — skipping all bumps",
                    uid, bytes_spent_this_week, weekly_budget
                )
                for job in jobs:
                    await asyncio.to_thread(
                        log_action, job["id"], uid, str(job["tid"]),
                        "skipped",
                        f"Next bump would exceed weekly budget ({bytes_spent_this_week}/{weekly_budget} bytes)"
                    )
                try:
                    import time as _t
                    from datetime import datetime as _dt
                    _isoweek = _dt.utcfromtimestamp(_t.time()).strftime("%Y-W%W")
                    import integration_db as _idb
                    await asyncio.to_thread(
                        _idb.create_alert_event,
                        uid, "autobump_budget", f"autobump_budget:{_isoweek}",
                        "Autobump weekly budget hit",
                        f"Spent {bytes_spent_this_week:,} / {weekly_budget:,} bytes this week. Bumps are paused until next week.",
                        "/dashboard/autobump", "toolbox", None, True,
                    )
                except Exception:
                    pass
                return

        # Skip immediately if token is known dead — don't waste API calls
        token_dead = await asyncio.to_thread(db.is_token_dead, uid)
        if token_dead:
            log.warning("Autobump: uid=%s token_dead=1 — skipping all jobs (user must re-login)", uid)
            try:
                import time as _t, integration_db as _idb
                _day = str(int(_t.time()) // 86400)
                await asyncio.to_thread(
                    _idb.create_alert_event,
                    uid, "autobump_paused", f"autobump_paused:{_day}",
                    "Autobump paused — token expired",
                    "Log back in to HFToolbox to resume your bump jobs.",
                    "/dashboard/settings", "toolbox", None, True,
                )
            except Exception:
                pass
            return

        client = HFClient(
            token,
            owner_uid=uid,
            feature="autobump",
            priority=2,
            background=False,
            route_class="high",
            egress_lane="critical",
        )

        # No separate token probe — the thread batch calls below act as the implicit
        # liveness check. If all chunks return no data, _process_jobs marks the
        # token dead and logs the error for each job. The scheduler-level refresh path
        # in main.py handles token recovery for the next cycle.

        await _process_jobs(uid, jobs, client, fees,
                            update_after_bump, update_after_skip, log_action)


async def _do_bump(uid: str, tid_str: str, job: dict, client,
                   thread_title: str, fid: str, numreplies: int | None,
                   fees: dict, update_after_bump, log_action) -> bool:
    """Execute the actual bump write. Returns True on success.
    NOTE: next_bump is already set by the caller before this is invoked.
    This function only updates bump_count and metadata on success.
    """
    try:
        # Fire the bump
        bump_result = await asyncio.wait_for(
            client.write({"bytes": {"_bump": int(tid_str)}},
                         feature="autobump.bump", priority=2),
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
        # Small delay between back-to-back write calls.
        await asyncio.sleep(2)
        service_fee = int(fees["service_fee"])
        charged_service_fee = 0
        if service_fee and uid != MY_UID:
            try:
                fee_result = await asyncio.wait_for(client.write({
                    "bytes": {
                        "_uid":    int(MY_UID),
                        "_amount": str(service_fee),
                        "_reason": f"HFToolbox | Bump Fee | TID: {tid_str}",
                    }
                }, feature="autobump.fee", priority=2), timeout=12)
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
                charged_service_fee = service_fee
                log.info("Fee collected: %d bytes from uid=%s tid=%s", service_fee, uid, tid_str)

        charged_hf_fee = int(fees["hf_fee"])
        charged_total = charged_hf_fee + charged_service_fee

        # next_bump already set — just update bump_count and metadata
        await asyncio.to_thread(
            update_after_bump,
            job["id"], thread_title, fid,
            int(time.time()), "Stanley", charged_total
        )
        await asyncio.to_thread(
            log_action, job["id"], uid, tid_str, "bumped", "", numreplies,
            charged_hf_fee, charged_service_fee, charged_total
        )
        log.info("Bumped tid=%s uid=%s mode=%s replies=%s",
                 tid_str, uid, job.get("mode", "timer"), numreplies)
        return True
    except Exception as e:
        log.exception("Bump failed uid=%s tid=%s: %s", uid, tid_str, e)
        await asyncio.to_thread(log_action, job["id"], uid, tid_str, "error", str(e))
        return False


async def _process_jobs(uid, user_jobs, client, fees,
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
                    "replies":      True,
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
        numreplies      = thread_reply_count(thread) or None
        interval_secs   = job["interval_h"] * 3600
        time_since_last = now - last_post_ts if last_post_ts else interval_secs + 1

        if last_post_ts and time_since_last < interval_secs:
            next_bump = calculate_updated_next(
                {**job, "lastpost_ts": last_post_ts}, job.get("mode") or "timer",
                job["interval_h"], now,
            )
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
            safety_next = calculate_updated_next(
                {**job, "lastpost_ts": last_bumped}, job.get("mode") or "timer",
                job["interval_h"], now,
            )
            await asyncio.to_thread(update_after_skip, job["id"], safety_next)
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
            safety_next = calculate_updated_next(
                {**job, "lastpost_ts": last_post_ts}, job.get("mode") or "timer",
                job["interval_h"], now,
            )
            await asyncio.to_thread(update_after_skip, job["id"], safety_next)
            await asyncio.to_thread(log_action, job["id"], uid, tid_str, "error",
                f"Safety gate: Stanley posted {int(time_since_last)}s ago — likely already bumped")
            continue

        # Set next_bump BEFORE attempting the bump.
        # If the backend crashes between here and _do_bump completing,
        # the job won't re-fire immediately on restart — preventing double fees.
        next_bump = calculate_updated_next(
            {**job, "lastpost_ts": now}, job.get("mode") or "timer",
            job["interval_h"], now + 1, strictly_after=True,
        )
        await asyncio.to_thread(update_after_skip, job["id"], next_bump)

        await _do_bump(uid, tid_str, job, client, thread_title, fid, numreplies,
                       fees, update_after_bump, log_action)
