"""
main.py — HF Dash entry point.

Start (Windows):
    run_backend.bat
    -- or --
    python -m uvicorn main:app --reload --port 8000

Put your credentials in backend/.env (copy from .env.example).
"""

import os
import sys
import logging
import asyncio
import secrets
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

# Load .env from the same directory as this file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv optional — set env vars manually if not installed

import db
import auth
from module_registry import all_modules, all_routers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
log = logging.getLogger("main")

FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173")
ENV = os.environ.get("ENV", "development").lower()

_WEAK_SESSION_SECRETS = {
    "",
    "changeme",
    "change-me",
    "default",
    "replace_with_64_char_random_hex_string",
}


def _get_session_secret() -> str:
    secret = (os.environ.get("SESSION_SECRET") or "").strip()
    weak = secret in _WEAK_SESSION_SECRETS or len(secret) < 32
    if weak:
        if ENV == "production":
            raise RuntimeError(
                "SESSION_SECRET is missing or weak. Set a long random value before starting production."
            )
        secret = secrets.token_urlsafe(48)
        log.warning(
            "SESSION_SECRET missing or weak. Generated an ephemeral development secret; sessions will reset on restart."
        )
    return secret


SESSION_SECRET = _get_session_secret()

try:
    from HFClient import AuthExpired as _AuthExpired
except ImportError:
    class _AuthExpired(Exception):
        pass


def _handle_auth_expired(request: Request, uid: str) -> JSONResponse:
    """Call when HF returns 401 (token revoked/expired). Wipes session + stored token.
    DB clear is fire-and-forget via create_task so we don't block the event loop."""
    request.session.clear()
    try:
        asyncio.get_event_loop().call_soon(
            lambda: asyncio.ensure_future(asyncio.to_thread(db.clear_token, uid))
        )
    except Exception:
        pass
    return JSONResponse({"error": "hf_token_revoked"}, status_code=401)


# ── Dynamic throttle ───────────────────────────────────────────────────────────
# Levels based on lowest remaining calls across all active user tokens.
#   normal   > 150  — everything runs at full speed
#   caution  100-150 — skip non-critical background work (username cache, tid backfill, browse warm)
#   low       50-100 — skip bytes crawl, double reply poll interval
#   critical  < 50   — skip everything except autobump and scheduled posts

# ── Throttle level — fully in-memory, never blocks the event loop ─────────────
# HFClient._rate_limits is a module-level dict {token: remaining} updated from
# every API response header. We read it directly — zero DB calls, zero blocking.

def _throttle_level() -> str:
    """Return throttle level from HFClient in-memory rate limit data. Never blocks."""
    try:
        import HFClient as _hfc
        values = [v for v in _hfc._rate_limits.values() if v < 9999]
        if not values:
            return "normal"
        lowest = min(values)
        if lowest < 50:   return "critical"
        if lowest < 100:  return "low"
        if lowest < 150:  return "caution"
        return "normal"
    except Exception:
        return "normal"


async def _crawl_user_bytes(uid: str, token: str) -> None:
    """Crawl one page of recv + one page of sent per hour until history complete.
    Bundles me + contracts(page N) into call 1 (3/4 slots).
    Bundles contracts(page N+1) into call 2's free slots (bytes_from uses only 1/4).
    """
    from HFClient import HFClient
    import time as _t
    client  = HFClient(token)
    uid_int = int(uid)
    state   = await asyncio.to_thread(db.get_crawl_state, uid)
    cstate  = await asyncio.to_thread(db.get_contracts_crawl_state, uid)

    recv_done = bool(state["recv_done"])
    sent_done = bool(state["sent_done"])
    c_done    = bool(cstate["done"])

    recv_page = 1 if recv_done else int(state["recv_page"])
    sent_page = 1 if sent_done else int(state["sent_page"])
    c_page    = 1 if c_done    else int(cstate["page"])
    # When crawl is complete, always re-check page 1 for status changes on recent contracts
    c_page_check = 1 if c_done else c_page

    # ── Call 1: bytes received + me profile + contracts + threads  [4/4 slots] ──
    # threads._uid page 1 = 30 most recently active threads, free in this slot
    data1 = await asyncio.wait_for(client.read({
        "bytes": {"_to": [uid_int], "_page": recv_page, "_perpage": 30,
                  "id": True, "amount": True, "dateline": True, "reason": True},
        "me": {
            "uid": True, "bytes": True, "vault": True,
            "postnum": True, "threadnum": True, "reputation": True,
            "usertitle": True, "timeonline": True,
            "usergroup": True, "displaygroup": True, "additionalgroups": True,
            "unreadpms": True,
        },
        "contracts": {
            "_uid": [uid_int], "_page": c_page_check, "_perpage": 30,
            "cid": True, "status": True, "type": True,
            "inituid": True, "otheruid": True,
            "iprice": True, "icurrency": True,
            "oprice": True, "ocurrency": True,
            "iproduct": True, "oproduct": True,
            "dateline": True, "tid": True,
        },
        "threads": {
            "_uid": [uid_int], "_page": 1, "_perpage": 30,
            "tid": True, "subject": True, "fid": True,
            "lastpost": True, "lastposteruid": True, "numreplies": True,
            "closed": True,
        },
    }), timeout=15)

    # ── Call 2: bytes sent + contracts(page N+1 if still crawling)  [1-2/4] ──
    c_page2 = c_page_check + 1
    call2_ask: dict = {
        "bytes": {"_from": [uid_int], "_page": sent_page, "_perpage": 30,
                  "id": True, "amount": True, "dateline": True, "reason": True},
    }
    if not c_done and c_page2 > 1:
        call2_ask["contracts"] = {
            "_uid": [uid_int], "_page": c_page2, "_perpage": 30,
            "cid": True, "status": True, "type": True,
            "inituid": True, "otheruid": True,
            "iprice": True, "icurrency": True,
            "oprice": True, "ocurrency": True,
            "iproduct": True, "oproduct": True,
            "dateline": True, "tid": True,
        }
    data2 = await asyncio.wait_for(client.read(call2_ask), timeout=15)

    # ── Parse + store bytes ───────────────────────────────────────────────────
    def parse_bytes(data, sent):
        raw = (data or {}).get("bytes", [])
        if isinstance(raw, dict): raw = [raw]
        return [{"id": t.get("id"), "amount": t.get("amount"),
                 "dateline": t.get("dateline"), "reason": t.get("reason"), "sent": sent}
                for t in (raw or []) if t.get("id")]

    recv_txns = parse_bytes(data1, False)
    sent_txns = parse_bytes(data2, True)
    await asyncio.to_thread(db.upsert_bytes_txns, uid, recv_txns + sent_txns)

    new_recv_done = recv_done or len(recv_txns) < 30
    new_sent_done = sent_done or len(sent_txns) < 30
    new_recv_page = recv_page if recv_done else (recv_page + 1 if len(recv_txns) >= 30 else recv_page)
    new_sent_page = sent_page if sent_done else (sent_page + 1 if len(sent_txns) >= 30 else sent_page)

    await asyncio.to_thread(db.update_crawl_state, uid,
        recv_page=new_recv_page, sent_page=new_sent_page,
        recv_done=int(new_recv_done), sent_done=int(new_sent_done),
        last_crawl=int(_t.time()))

    count = await asyncio.to_thread(db.get_bytes_history_count, uid)
    log.info("Bytes crawl uid=%s recv_p=%d sent_p=%d total=%d recv_done=%s sent_done=%s",
             uid, recv_page, sent_page, count, new_recv_done, new_sent_done)

    # ── Parse + store contracts from both calls ───────────────────────────────
    def parse_contracts(data):
        raw = (data or {}).get("contracts", [])
        if isinstance(raw, dict): raw = [raw]
        return [c for c in (raw or []) if c.get("cid")]

    c_batch1 = parse_contracts(data1)
    c_batch2 = parse_contracts(data2) if not c_done and c_page2 > 1 else []
    all_contracts = c_batch1 + c_batch2

    if all_contracts:
        # Check which CIDs are genuinely new BEFORE upsert overwrites them
        try:
            all_cids = [str(c.get("cid","")) for c in all_contracts if c.get("cid")]
            existing_cids = await asyncio.to_thread(db.get_existing_contract_cids, uid, all_cids)
        except Exception:
            existing_cids = set()

        await asyncio.to_thread(db.upsert_contracts, uid, all_contracts)

        # Only notify about new contracts if the initial crawl is already done
        # (c_done was True before this run, meaning we've seen all history)
        if c_done:
            try:
                STATUS_LABELS = {"1":"Awaiting Approval","2":"Cancelled","5":"Active Deal",
                                 "6":"Complete","7":"Disputed","8":"Expired"}
                import time as _tnow
                cutoff = _tnow.time() - 3600  # only notify contracts created in last hour
                for c in all_contracts:
                    cid = str(c.get("cid", ""))
                    if not cid or cid in existing_cids:
                        continue
                    # Extra guard: only notify if contract was actually created recently
                    dateline = int(c.get("dateline") or 0)
                    if dateline and dateline < cutoff:
                        continue
                    status_n = str(c.get("status_n", c.get("status", "")))
                    status_label = STATUS_LABELS.get(status_n, f"Status {status_n}")
                    await asyncio.to_thread(
                        db.add_notification, uid, "contract_new",
                        f"New contract #{cid}",
                        f"Status: {status_label}",
                        f"/dashboard/contracts/{cid}",
                        f"new_{cid}"
                    )
            except Exception as e:
                log.warning("Crawl: contract notification failed uid=%s: %s", uid, e)

    # ── Re-check any contracts still showing as open (Awaiting/Active) ──────────
    # The main crawl only pages through history once. Open contracts need their
    # status refreshed every cycle so stale Awaiting/Active records get updated.
    try:
        open_cids = await asyncio.to_thread(db.get_open_contract_cids, uid)
        # Remove CIDs we already fetched this cycle (page 1 + page 2 of crawl)
        fetched_cids = {str(c.get("cid","")) for c in all_contracts}
        stale_cids = [int(cid) for cid in open_cids if cid not in fetched_cids]
        # Batch into groups of 30 (API max per call), 1 call at a time
        for i in range(0, len(stale_cids), 30):
            batch = stale_cids[i:i+30]
            r = await client.read({"contracts": {
                "_cid": batch,
                "cid": True, "status": True, "type": True,
                "inituid": True, "otheruid": True,
                "iprice": True, "icurrency": True,
                "oprice": True, "ocurrency": True,
                "iproduct": True, "oproduct": True,
                "dateline": True, "tid": True,
            }})
            if r:
                updated = r.get("contracts", [])
                if isinstance(updated, dict): updated = [updated]
                if updated:
                    await asyncio.to_thread(db.upsert_contracts, uid, updated)
                    log.info("Contracts re-check uid=%s updated %d open contracts", uid, len(updated))
    except Exception as e:
        log.warning("Contracts re-check failed uid=%s: %s", uid, e)

    # Advance contracts crawl state
    pages_fetched_this_run = len([b for b in [c_batch1, c_batch2] if b])
    last_batch = c_batch2 if c_batch2 else c_batch1
    new_c_done = c_done or len(last_batch) < 30
    new_c_page = c_page_check if c_done else (c_page_check + pages_fetched_this_run
                                               if not new_c_done else c_page_check)
    await asyncio.to_thread(db.update_contracts_crawl_state, uid,
        page=new_c_page, done=int(new_c_done), last_crawl=int(_t.time()))

    c_total = await asyncio.to_thread(db.get_contracts_history_count, uid)
    log.info("Contracts crawl uid=%s page=%d+%d total=%d done=%s",
             uid, c_page_check, c_page2 if not c_done else 0, c_total, new_c_done)

    # ── Free bonus: thread reply detection (zero extra API calls) ───────────
    # Compares lastpost against stored cursor per thread.
    # Threads with new lastpost from someone other than us/Stanley → flagged for post fetch.
    # The reply poller drains _reply_check_queue — never polls stale/old threads.
    try:
        from modules.posting.posting_db import add_my_thread, update_thread_last_checked, get_all_tracked_threads
        from modules.posting import _reply_check_queue, _reply_check_titles, _reply_check_numreplies, STANLEY_UID
        raw_threads = (data1 or {}).get("threads", [])
        if isinstance(raw_threads, dict): raw_threads = [raw_threads]

        # Load stored cursors for this user
        _tracked_rows = await asyncio.to_thread(get_all_tracked_threads)
        _cursor_map   = {str(t["tid"]): t for t in _tracked_rows if str(t["uid"]) == uid}

        needs_check:    set[str]        = set()
        titles_map:     dict[str, str]  = {}
        numreplies_map: dict[str, int]  = {}

        for th in (raw_threads or []):
            t_tid        = str(th.get("tid") or "")
            t_subject    = str(th.get("subject") or "")
            t_fid        = str(th.get("fid") or "")
            t_lastpost   = int(th.get("lastpost") or 0)
            t_lastposter = str(th.get("lastposteruid") or "")
            t_numreplies = int(th.get("numreplies") or 0)
            t_closed     = int(th.get("closed") or 0)
            if not t_tid or not t_lastpost:
                continue

            # Register thread (idempotent)
            try:
                await asyncio.to_thread(add_my_thread, uid, t_tid, t_fid, t_subject,
                                                   t_lastpost, t_lastposter, t_numreplies, t_closed)
            except Exception:
                pass

            stored_lastpost = int((_cursor_map.get(t_tid) or {}).get("last_checked") or 0)

            if t_lastpost <= stored_lastpost:
                continue  # no change since last crawl

            # If we or Stanley posted last — advance cursor, no reply to queue
            if t_lastposter in (uid, STANLEY_UID):
                try:
                    last_pid = (_cursor_map.get(t_tid) or {}).get("last_pid") or "0"
                    await asyncio.to_thread(update_thread_last_checked, uid, t_tid, last_pid, t_lastpost)
                except Exception:
                    pass
                continue

            # New activity from someone else — flag for post fetch.
            # Do NOT advance last_checked here — let the reply poll do it after
            # successful processing so re-flags work if the poll fails.
            needs_check.add(t_tid)
            titles_map[t_tid]     = t_subject
            numreplies_map[t_tid] = t_numreplies

        if needs_check:
            # Merge into existing queue — do NOT overwrite, prior unflushed flags must survive
            _reply_check_queue.setdefault(uid, set()).update(needs_check)
            _reply_check_titles.setdefault(uid, {}).update(titles_map)
            _reply_check_numreplies.setdefault(uid, {}).update(numreplies_map)
            log.debug("Crawl: flagged %d thread(s) for reply check uid=%s", len(needs_check), uid)

            # Fire the reply poll immediately — don't wait for the separate 5-min timer.
            # Without this, there can be up to 10 min latency (crawl timer + poll timer).
            # Firing inline here reduces it to one crawl cycle (~5 min) worst case.
            try:
                from modules.posting import poll_reply_queues
                await poll_reply_queues(active_uids={uid})
            except Exception as _rpe:
                log.warning("Crawl: inline reply poll failed uid=%s: %s", uid, _rpe)

    except Exception as _te:
        log.warning("Crawl: thread reply detection failed uid=%s: %s", uid, _te)

    # ── Free bonus: update profile cache ─────────────────────────────────────
    me = (data1 or {}).get("me", {})
    if me:
        try:
            await asyncio.to_thread(db.update_profile_cache, uid, {
                "myps":       me.get("bytes"),
                "vault":      me.get("vault"),
                "postnum":    me.get("postnum"),
                "threadnum":  me.get("threadnum"),
                "reputation": me.get("reputation"),
                "usertitle":  me.get("usertitle"),
                "timeonline": me.get("timeonline"),
            })
        except Exception as e:
            log.warning("Crawl: profile cache update failed uid=%s: %s", uid, e)
        # Update groups if they changed
        try:
            import json as _json
            groups: list[str] = []
            for field in ("usergroup", "displaygroup"):
                v = (me.get(field) or "").strip()
                if v: groups.append(v)
            for g in (me.get("additionalgroups") or "").split(","):
                g = g.strip()
                if g: groups.append(g)
            groups = list(dict.fromkeys(groups))  # dedupe, preserve order
            if groups:
                current_user = await asyncio.to_thread(db.get_user, uid)
                current_groups = (current_user.get("groups") or []) if current_user else []
                if sorted(groups) != sorted(current_groups):
                    await asyncio.to_thread(db.update_user_groups, uid, groups)
                    log.info("Crawl: groups updated uid=%s %s", uid, groups)
        except Exception as e:
            log.warning("Crawl: group update failed uid=%s: %s", uid, e)

        # ── Detect new PMs ───────────────────────────────────────────────────
        try:
            unread = int(me.get("unreadpms") or 0)
            if unread > 0:
                last_pm = await asyncio.to_thread(db.get_last_pm_count, uid)
                if last_pm is None or unread > last_pm:
                    await asyncio.to_thread(db.add_notification, uid, "pm",
                        f"You have {unread} unread PM{'s' if unread != 1 else ''}",
                        "", "https://hackforums.net/private.php", f"pm_{unread}")
                await asyncio.to_thread(db.set_last_pm_count, uid, unread)
            else:
                await asyncio.to_thread(db.set_last_pm_count, uid, 0)
        except Exception as e:
            log.warning("Crawl: PM notification failed uid=%s: %s", uid, e)

    # ── Free bonus: refresh contracts dash cache from page-1 batch ───────────
    if c_batch1:
        STATUS  = {"1":"Awaiting Approval","2":"Cancelled","3":"Unknown","4":"Cancelled",
                   "5":"Active Deal","6":"Complete","7":"Disputed","8":"Expired"}
        TYPE_MAP = {"1":"Selling","2":"Purchasing","3":"Exchanging","4":"Trading","5":"Vouch Copy"}
        cached_contracts = []
        for c in c_batch1:
            cached_contracts.append({
                "cid":       str(c.get("cid") or ""),
                "type_n":    str(c.get("type") or ""),
                "status":    STATUS.get(str(c.get("status") or ""), "Unknown"),
                "status_n":  str(c.get("status") or ""),
                "type":      TYPE_MAP.get(str(c.get("type") or ""), str(c.get("type") or "--")),
                "inituid":   str(c.get("inituid") or ""),
                "otheruid":  str(c.get("otheruid") or ""),
                "iprice":    str(c.get("iprice") or "0"),
                "icurrency": str(c.get("icurrency") or ""),
                "oprice":    str(c.get("oprice") or "0"),
                "ocurrency": str(c.get("ocurrency") or ""),
                "iproduct":  str(c.get("iproduct") or ""),
                "oproduct":  str(c.get("oproduct") or ""),
                "dateline":  int(c.get("dateline") or 0),
                "value":     _contract_value(c),
            })
        try:
            await asyncio.to_thread(db.set_dash_cache, uid, "contracts",
                                    {"contracts": cached_contracts, "uid": uid})
        except Exception as e:
            log.warning("Crawl: contracts cache update failed uid=%s: %s", uid, e)


IDLE_THRESHOLD = 900  # 15 minutes — if no activity, skip scheduled crawl cycles


async def _crawl_if_active(uid: str, token: str) -> bool:
    """
    Crawl a user only if they've been active in the last IDLE_THRESHOLD seconds
    AND their API budget is above their configured floor.
    Returns True if crawl ran, False if skipped.
    """
    import time as _t
    from HFClient import get_rate_limit_remaining

    # ── API floor check — hard stop if budget is too low ──────────────────
    settings      = await asyncio.to_thread(db.get_user_settings, uid)
    floor_enabled = settings.get("apiFloorEnabled", False)
    floor_value   = int(settings.get("apiFloor", 30))
    remaining     = get_rate_limit_remaining(token)
    if floor_enabled and remaining < floor_value:
        log.warning("Crawl: uid=%s paused — %d calls remaining, floor=%d", uid, remaining, floor_value)
        return False

    last_active = await asyncio.to_thread(db.get_last_active, uid)
    if last_active is None:
        return False  # user never seen
    idle_secs = _t.time() - last_active
    if idle_secs > IDLE_THRESHOLD:
        # Mark needs_refresh so next endpoint hit triggers an immediate crawl
        await asyncio.to_thread(db.set_needs_refresh, uid, 1)
        log.debug("Crawl: uid=%s idle %.0fs — skipping, flagged needs_refresh", uid, idle_secs)
        return False
    await _crawl_user_bytes(uid, token)
    return True


async def _trigger_listener() -> None:
    """
    Listens on _crawl_trigger queue for UIDs that just returned from idle.
    Fires an immediate crawl so data is fresh when the user hits the dashboard.
    """
    import time as _t
    seen_recently: dict[str, float] = {}  # uid -> last trigger time, debounce 30s
    while True:
        try:
            uid = await asyncio.wait_for(_crawl_trigger.get(), timeout=60)
            last = seen_recently.get(uid, 0)
            if _t.time() - last < 30:
                _crawl_trigger.task_done()
                continue  # debounce — don't spam crawls if many requests fire at once
            seen_recently[uid] = _t.time()
            token = await asyncio.to_thread(db.get_token, uid)
            if token:
                log.info("Crawl: immediate crawl triggered for uid=%s (returning from idle)", uid)
                try:
                    await _crawl_user_bytes(uid, token)
                    await asyncio.to_thread(db.set_needs_refresh, uid, 0)
                except _AuthExpired:
                    log.warning("Crawl: token revoked for uid=%s — clearing token", uid)
                    await asyncio.to_thread(db.clear_token, uid)
                except Exception as e:
                    log.warning("Immediate crawl failed uid=%s: %s", uid, e)
            _crawl_trigger.task_done()
        except asyncio.TimeoutError:
            pass
        except Exception as e:
            log.warning("Trigger listener error: %s", e)


async def _bytes_crawl_loop() -> None:
    """
    Runs every 5 minutes. Only crawls users who have been active recently.
    Idle users (no endpoint hit in 15min) are skipped and flagged needs_refresh=1.
    When they return and hit any endpoint, _trigger_listener fires an immediate crawl.
    """
    import time as _t
    # Smart startup delay — don't blindly sleep, check actual last_crawl
    try:
        uids = await asyncio.to_thread(db.get_all_uids)
        if uids:
            state = await asyncio.to_thread(db.get_crawl_state, uids[0])
            last = state.get("last_crawl") or 0
            elapsed = _t.time() - last
            if elapsed < 270:
                wait = 300 - elapsed
                log.info("Bytes crawl: last ran %.0fs ago, waiting %.0fs", elapsed, wait)
                await asyncio.sleep(wait)
            else:
                log.info("Bytes crawl: last ran %.0fs ago (stale), will run after 15s startup delay", elapsed)
    except Exception as e:
        log.warning("Bytes crawl startup check failed: %s", e)

    # Always wait for server to fully start before first crawl
    await asyncio.sleep(15)

    while True:
        try:
            uids = await asyncio.to_thread(db.get_all_uids)
            ran = 0
            # Skip bytes crawl entirely when API budget is low
            _tl = _throttle_level()
            if _tl in ("low", "critical"):
                log.info("Bytes crawl: skipping — throttle=%s", _tl)
            else:
                for uid in uids:
                    token = await asyncio.to_thread(db.get_token, uid)
                    if token:
                        try:
                            did_crawl = await asyncio.wait_for(_crawl_if_active(uid, token), timeout=90)
                        except asyncio.TimeoutError:
                            log.warning("Bytes crawl: timed out after 90s uid=%s — skipping", uid)
                            did_crawl = False
                        except _AuthExpired:
                            log.warning("Bytes crawl: token revoked for uid=%s — clearing token", uid)
                            await asyncio.to_thread(db.clear_token, uid)
                            did_crawl = False
                        if did_crawl:
                            ran += 1
            if ran == 0:
                log.debug("Bytes crawl: all users idle, no API calls made")
        except Exception as e:
            log.exception("Bytes crawl loop error: %s", e)
        _touch_heartbeat()  # watchdog: we completed a crawl cycle
        await asyncio.sleep(300)  # 5 minutes — timer unchanged, activity gate does the work


# ── Activity tracking middleware ───────────────────────────────────────────────
# Touches last_seen on every authenticated request.
# Also triggers an immediate crawl if user was idle (needs_refresh=1).

_crawl_trigger: asyncio.Queue = asyncio.Queue(maxsize=10)  # uid queue for immediate crawls

# ── Event loop watchdog ────────────────────────────────────────────────────────
# Two-layer watchdog:
# 1. Loop ping — detects a fully frozen event loop (rare)
# 2. Activity heartbeat — detects stuck coroutines (common case: relay hangs
#    at OS level below aiohttp timeout, loop is alive but requests never return)
import threading
import os as _os
import time as _time

# Shared heartbeat timestamp — updated by crawl/scheduler loops every cycle
_last_heartbeat: float = 0.0

def _touch_heartbeat() -> None:
    global _last_heartbeat
    _last_heartbeat = _time.time()


def _start_watchdog(loop: asyncio.AbstractEventLoop) -> None:
    PING_INTERVAL      = 10    # seconds between loop pings
    LOOP_HANG_TIMEOUT  = 120   # kill if loop doesn't respond (must exceed crawl timeout of 90s)
    HEARTBEAT_TIMEOUT  = 300   # kill if no crawl activity for 5 min (stuck coroutine)

    async def _ping():
        pass

    def _watchdog_thread():
        global _last_heartbeat
        _last_heartbeat = _time.time()  # init so we don't false-trigger on startup
        while True:
            _time.sleep(PING_INTERVAL)

            # Layer 1: is the event loop itself responding?
            fut = asyncio.run_coroutine_threadsafe(_ping(), loop)
            try:
                fut.result(timeout=LOOP_HANG_TIMEOUT)
            except Exception:
                log.error("WATCHDOG: event loop frozen — killing for restart")
                _dump_tasks(loop)
                _os._exit(1)

            # Layer 2: is any work actually happening? (stuck coroutine detection)
            idle = _time.time() - _last_heartbeat
            if idle > HEARTBEAT_TIMEOUT:
                log.error("WATCHDOG: no crawl activity for %.0fs — stuck coroutine, killing for restart", idle)
                _dump_tasks(loop)
                _os._exit(1)

    def _dump_tasks(loop):
        try:
            for t in asyncio.all_tasks(loop):
                log.error("  task: %s", t.get_name())
                for f in t.get_stack():
                    log.error("    %s:%d in %s", f.f_code.co_filename, f.f_lineno, f.f_code.co_name)
        except Exception as e:
            log.error("  (dump failed: %s)", e)

    t = threading.Thread(target=_watchdog_thread, name="loop_watchdog", daemon=True)
    t.start()
    log.info("Watchdog started (loop_timeout=%ds heartbeat_timeout=%ds)", LOOP_HANG_TIMEOUT, HEARTBEAT_TIMEOUT)


async def _username_resolve_loop() -> None:
    """Resolve unknown counterparty UIDs to usernames in the background.
    Completely separate from the crawl — runs every 10 minutes, resolves
    30 UIDs per user per cycle. Becomes a no-op once all are cached."""
    await asyncio.sleep(120)  # wait 2 min after startup before first run
    while True:
        try:
            # Skip at caution or worse — this is non-critical background work
            _tl = _throttle_level()
            if _tl in ("caution", "low", "critical"):
                log.debug("Username resolver: skipping — throttle=%s", _tl)
                await asyncio.sleep(600)
                continue
            uids = await asyncio.to_thread(db.get_all_uids)
            for uid in uids:
                try:
                    token = await asyncio.to_thread(db.get_token, uid)
                    if not token:
                        continue
                    unknown = await asyncio.to_thread(db.get_unknown_uids_from_contracts, uid, 30)
                    if not unknown:
                        continue
                    chunk = [int(u) for u in unknown if str(u).isdigit()]
                    if not chunk:
                        continue
                    from HFClient import HFClient
                    client = HFClient(token)
                    udata = await asyncio.wait_for(
                        client.read({"users": {"_uid": chunk, "uid": True, "username": True}}),
                        timeout=15
                    )
                    rows = udata.get("users", []) if udata else []
                    if isinstance(rows, dict): rows = [rows]
                    uid_map = {str(r["uid"]): r["username"] for r in rows if r.get("uid") and r.get("username")}
                    if uid_map:
                        await asyncio.to_thread(db.upsert_uid_usernames, uid_map)
                        log.info("Username cache: resolved %d UIDs for user %s", len(uid_map), uid)
                    await asyncio.sleep(2)  # brief pause between users

                    # ── Thread title resolution — same cycle, same token ──
                    unknown_tids = await asyncio.to_thread(db.get_unknown_tids_from_contracts, uid, 30)
                    if unknown_tids:
                        tid_ints = [int(t) for t in unknown_tids if str(t).isdigit()]
                        if tid_ints:
                            tdata = await asyncio.wait_for(
                                client.read({"threads": {"_tid": tid_ints[:30], "tid": True, "subject": True}}),
                                timeout=15
                            )
                            trows = tdata.get("threads", []) if tdata else []
                            if isinstance(trows, dict): trows = [trows]
                            tid_map = {str(r["tid"]): r["subject"] for r in trows if r.get("tid") and r.get("subject")}
                            if tid_map:
                                await asyncio.to_thread(db.upsert_tid_titles, tid_map)
                                log.info("Thread cache: resolved %d titles for uid=%s", len(tid_map), uid)

                except _AuthExpired:
                    log.warning("Username cache: token revoked for uid=%s — clearing token", uid)
                    await asyncio.to_thread(db.clear_token, uid)
                except Exception as e:
                    log.debug("Username cache: skip uid=%s: %s", uid, e)
        except Exception as e:
            log.warning("Username resolve loop error: %s", e)
        await asyncio.sleep(600)  # run every 10 minutes



async def _tid_backfill_loop() -> None:
    """One-time backfill: fetch all contract tids from HF API for any user
    that has contracts with missing tid. Runs at startup, becomes no-op once done.
    Cost: ~3 HF API calls per user, only ever runs if needed."""
    await asyncio.sleep(30)  # let server fully start first
    from HFClient import HFClient
    import time as _t

    all_uids = await asyncio.to_thread(db.get_all_uids)
    for uid in all_uids:
        try:
            # Quick check — skip if all tids already populated
            needs_backfill = await asyncio.to_thread(db.get_contracts_with_empty_tid, uid)
            if not needs_backfill:
                continue

            token = await asyncio.to_thread(db.get_token, uid)
            if not token:
                continue

            log.info("TID backfill: starting for uid=%s", uid)
            client   = HFClient(token)
            uid_int  = int(uid)
            page     = 1
            total    = 0

            while True:
                try:
                    resp = await asyncio.wait_for(
                        client.read({"contracts": {
                            "_uid": [uid_int], "_page": page, "_perpage": 30,
                            "cid": True, "tid": True,
                        }}),
                        timeout=20
                    )
                except Exception as e:
                    log.warning("TID backfill: API error uid=%s page=%d: %s", uid, page, e)
                    break

                rows = (resp or {}).get("contracts", [])
                if isinstance(rows, dict):
                    rows = [rows]
                if not rows:
                    break

                cid_tid_map = {
                    str(r["cid"]): str(r.get("tid") or "")
                    for r in rows if r.get("cid")
                }
                updated = await asyncio.to_thread(db.backfill_contract_tids, uid, cid_tid_map)
                total += updated

                await asyncio.sleep(1)  # be gentle on rate limit
                if len(rows) < 30:
                    break
                page += 1

            log.info("TID backfill: done uid=%s updated=%d pages=%d", uid, total, page)
        except Exception as e:
            log.warning("TID backfill: failed uid=%s: %s", uid, e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Expand thread pool — default is too small for concurrent DB + crawl on Windows
    import concurrent.futures
    loop = asyncio.get_event_loop()
    loop.set_default_executor(concurrent.futures.ThreadPoolExecutor(max_workers=64))
    log.info("Thread pool: set to 64 workers")

    _start_watchdog(loop)

    db.init_db()
    db.init_user_settings()
    db.init_notifications_table()
    from modules.posting.posting_db import init_posting_db
    init_posting_db()
    from modules.sigmarket.sigmarket_db import init_sigmarket_db
    init_sigmarket_db()
    from modules.contracts.templates_db import init_templates_db
    init_templates_db()

    # Reset any NULL last_pid rows so the cursor comparison works cleanly
    try:
        import sqlite3 as _sq3
        from pathlib import Path as _PL
        _pc = _sq3.connect(str(_PL("data/hf_dash.db")), check_same_thread=False)
        _pc.execute("UPDATE my_threads SET last_pid='0' WHERE last_pid IS NULL")
        _pc.commit()
        _pc.close()
    except Exception:
        pass
    import modules  # noqa — triggers all register() calls
    log.info("Modules loaded: %s", [m.id for m in all_modules()])

    # Mount module routers
    for meta, router in all_routers():
        app.include_router(router)
        log.info("Mounted: %s", meta.id)

    # Start background polling
    from scheduler import start_scheduler
    await start_scheduler()

    # Mount autobump router (core, not a module)
    from modules.autobump.router import router as autobump_router
    app.include_router(autobump_router)
    from modules.posting.router import router as posting_router
    app.include_router(posting_router)
    from modules.sigmarket.router import router as sigmarket_router
    app.include_router(sigmarket_router)
    from modules.contracts.templates_router import router as templates_router
    app.include_router(templates_router)

    # ── Unified 5-minute scheduler ──────────────────────────────────────────
    # Replaces the old autobump-only 30-min loop.
    # Handles: scheduled thread posting (every tick), autobump (every 30 min),
    # and reply queue polling (every 15 min). All in one loop, batched per user.
    from modules.autobump import poll_autobump
    from modules.posting import fire_due_threads, poll_reply_queues
    from modules.sigmarket import poll_sigmarket_rotations
    from modules.sigmarket.router import _do_browse_fetch, _browse_cache, warm_sigmarket_status

    async def _unified_loop():
        import time as _t
        _last_autobump      = 0.0
        _last_reply_poll    = 0.0
        _last_browse_warm   = 0.0
        _last_sigmarket_warm = 0.0
        AUTOBUMP_INTERVAL      = 1800  # 30 min — always runs (user-facing feature)
        REPLY_POLL_INTERVAL    =  300  # 5 min normal; doubled at low/critical
        BROWSE_WARM_INTERVAL   = 1500  # 25 min; skipped at caution+
        SIGMARKET_WARM_INTERVAL =  900  # 15 min per-user sigmarket status; skip at caution+
        TICK                   =   60  # 1 min normal; stretched at low/critical

        # Smart startup for autobump — check when it last ran
        try:
            from modules.autobump.autobump_db import get_last_log_ts
            last_ab = get_last_log_ts() or 0
            elapsed = _t.time() - last_ab
            if elapsed < AUTOBUMP_INTERVAL - 60:
                _last_autobump = _t.time() - elapsed  # will wait the remainder
                log.info("Unified scheduler: autobump last ran %.0fs ago, will fire in %.0fs",
                         elapsed, AUTOBUMP_INTERVAL - elapsed)
            else:
                log.info("Unified scheduler: autobump stale (%.0fs ago), will run on first tick", elapsed)
        except Exception:
            pass

        await asyncio.sleep(10)  # brief stagger on startup
        while True:
            now = _t.time()
            try:
                # ── 0. Compute throttle level once per tick ─────────────
                _tl = _throttle_level()
                if _tl != "normal":
                    log.debug("Unified scheduler: throttle=%s", _tl)

                # ── 1. Fire any due scheduled threads (always — user-facing) ──
                try:
                    await asyncio.wait_for(fire_due_threads(), timeout=60)
                except asyncio.TimeoutError:
                    log.warning("Unified scheduler: fire_due_threads timed out")

                # ── 2. Autobump (every 30 min — always runs) ────────────────
                if now - _last_autobump >= AUTOBUMP_INTERVAL:
                    try:
                        uids = await asyncio.to_thread(db.get_all_uids)
                        for uid in uids:
                            token = await asyncio.to_thread(db.get_token, uid)
                            if not token:
                                continue
                            try:
                                await poll_autobump(uid, token)
                                await poll_sigmarket_rotations(uid, token)
                            except _AuthExpired:
                                log.warning("Scheduler: token revoked for uid=%s — clearing token", uid)
                                await asyncio.to_thread(db.clear_token, uid)
                        _last_autobump = _t.time()
                    except Exception as e:
                        log.exception("Unified scheduler: autobump error: %s", e)

                # ── 3. Reply queue poll (5 min normal, 10 min at low/critical) ──
                _reply_interval = REPLY_POLL_INTERVAL * (2 if _tl in ("low", "critical") else 1)
                if now - _last_reply_poll >= _reply_interval:
                    if _tl == "critical":
                        log.info("Unified scheduler: reply poll skipped — throttle=critical")
                        _last_reply_poll = now
                    else:
                        try:
                            # Build active UID set — same idle gate used by bytes crawler.
                            # Idle users' tracked threads are skipped; they get caught
                            # on the next poll cycle after they return.
                            all_uids = await asyncio.to_thread(db.get_all_uids)
                            active_uids: set[str] = set()
                            for _uid in all_uids:
                                _last = await asyncio.to_thread(db.get_last_active, _uid)
                                if _last and (_t.time() - _last) <= IDLE_THRESHOLD:
                                    active_uids.add(_uid)
                            if active_uids:
                                await asyncio.wait_for(poll_reply_queues(active_uids), timeout=60)
                            else:
                                log.debug("Reply poll: all users idle, skipping")
                            _last_reply_poll = _t.time()
                        except asyncio.TimeoutError:
                            log.warning("Unified scheduler: poll_reply_queues timed out")
                        except Exception as e:
                            log.exception("Unified scheduler: reply poll error: %s", e)

                # ── 4. Sigmarket browse pre-warm (every 25 min, skip at caution+) ──
                if now - _last_browse_warm >= BROWSE_WARM_INTERVAL and _tl == "normal":
                    try:
                        uids = await asyncio.to_thread(db.get_all_uids)
                        _warm_token = None
                        for _uid in uids:
                            _warm_token = await asyncio.to_thread(db.get_token, _uid)
                            if _warm_token:
                                break
                        if _warm_token:
                            result = await asyncio.wait_for(_do_browse_fetch(_warm_token), timeout=25)
                            if result is not None and result.get("listings"):
                                _browse_cache["data"] = result
                                _browse_cache["ts"]   = _t.time()
                                await asyncio.to_thread(db.set_dash_cache, "__system__", "sigmarket_browse", result)
                                log.info("Sigmarket browse pre-warmed (%d listings)", len(result.get("listings", [])))
                        _last_browse_warm = _t.time()
                    except asyncio.TimeoutError:
                        log.warning("Sigmarket browse pre-warm timed out")
                    except Exception as e:
                        log.warning("Sigmarket browse pre-warm error: %s", e)

                # ── 5. Sigmarket status per-user warm (every 15 min, skip at caution+) ──
                if now - _last_sigmarket_warm >= SIGMARKET_WARM_INTERVAL and _tl == "normal":
                    try:
                        uids = await asyncio.to_thread(db.get_all_uids)
                        for _uid in uids:
                            _tok = await asyncio.to_thread(db.get_token, _uid)
                            if _tok:
                                await asyncio.wait_for(warm_sigmarket_status(_uid, _tok), timeout=15)
                                await asyncio.sleep(1)  # brief pause between users
                        _last_sigmarket_warm = _t.time()
                    except asyncio.TimeoutError:
                        log.warning("Sigmarket status warm timed out")
                    except Exception as e:
                        log.warning("Sigmarket status warm error: %s", e)

            except Exception as e:
                log.exception("Unified scheduler: unexpected error: %s", e)

            _touch_heartbeat()  # watchdog: unified scheduler is still ticking
            # Stretch the tick when budget is low — less overhead, fewer wasted cycles
            _tick = TICK * (2 if _tl in ("low", "critical") else 1)
            await asyncio.sleep(_tick)

    asyncio.create_task(_unified_loop(), name="unified_scheduler")

    # Pre-warm sigmarket browse cache on startup
    # Loads from DB first (free, instant) — only hits HF API if DB cache is stale/empty
    async def _startup_browse_warm():
        await asyncio.sleep(3)
        try:
            from modules.sigmarket.router import _load_browse_cache_from_db, _do_browse_fetch, _browse_cache

            # Try DB cache first — zero API calls if it's fresh
            if _load_browse_cache_from_db():
                log.info("Startup: sigmarket browse loaded from DB cache (0 API calls)")
                return

            # DB cache stale/empty — fetch from HF
            uids = await asyncio.to_thread(db.get_all_uids)
            token = None
            for _uid in uids:
                token = await asyncio.to_thread(db.get_token, _uid)
                if token:
                    break
            if token:
                result = await asyncio.wait_for(_do_browse_fetch(token), timeout=30)
                if result is not None and result.get("listings"):
                    _browse_cache["data"] = result
                    _browse_cache["ts"]   = __import__('time').time()
                    await asyncio.to_thread(db.set_dash_cache, "__system__", "sigmarket_browse", result)
                    log.info("Startup: sigmarket browse fetched + persisted (%d listings)", len(result.get("listings", [])))
        except Exception as e:
            log.warning("Startup browse warm failed: %s", e)
    asyncio.create_task(_startup_browse_warm(), name="startup_browse_warm")

    # Start bytes history crawler (core, not a module)
    asyncio.create_task(_bytes_crawl_loop(), name="bytes_crawler")
    asyncio.create_task(_username_resolve_loop(), name="username_resolver")
    asyncio.create_task(_tid_backfill_loop(),       name="tid_backfill")
    asyncio.create_task(_trigger_listener(),   name="crawl_trigger_listener")

    # On startup: refresh profile cache for all users with a single cheap me call.
    # The bytes crawl sleeps first (to avoid cold-start burn), so without this
    # the sidebar would show a stale "cached X hours ago" until the first crawl fires.
    # Startup profile refresh removed — crawl handles this on first active cycle

    yield


app = FastAPI(title="HF Dash", lifespan=lifespan)

# In-memory cache for user activity (posts + threads). Keyed by lookup_uid.
_activity_cache: dict = {}  # uid -> {"ts": float, "data": dict}
ACTIVITY_CACHE_TTL = 300    # 5 minutes

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    https_only=ENV == "production",
    same_site="lax",
)

app.include_router(auth.router)


@app.middleware("http")
async def activity_middleware(request, call_next):
    """
    On every authenticated request:
    1. Touch last_seen so idle detection stays accurate
    2. If needs_refresh=1 (user returning from idle), queue an immediate crawl
    """
    import time as _t
    response = await call_next(request)

    # Only track activity on API paths, not static assets
    path = request.url.path
    if not path.startswith("/api/") and not path.startswith("/auth/"):
        return response

    uid = request.session.get("uid") if hasattr(request, "session") else None
    if not uid:
        return response

    # True fire-and-forget — never block the HTTP response waiting for DB threads
    asyncio.create_task(_activity_task(uid))
    return response


async def _activity_task(uid: str) -> None:
    """Background task: update last_seen and trigger crawl if needed. Never blocks middleware."""
    try:
        needs = await asyncio.to_thread(db.get_needs_refresh, uid)
        await asyncio.to_thread(db.touch_last_active, uid)
        if needs:
            try:
                _crawl_trigger.put_nowait(uid)
            except asyncio.QueueFull:
                pass
    except Exception:
        pass


@app.get("/api/modules")
async def get_modules():
    return {
        "modules": [
            {
                "id":          m.id,
                "name":        m.name,
                "description": m.description,
                "icon":        m.icon,
                "category":    m.category,
                "api_cost":    m.api_cost,
                "default_on":  m.default_on,
                "badge":       m.badge,
            }
            for m in all_modules()
        ]
    }


@app.get("/api/prefs")
async def get_prefs(request: Request):
    uid = request.session.get("uid")
    if not uid:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)
    prefs = await asyncio.to_thread(db.get_module_prefs, uid)
    return {"prefs": prefs}


@app.post("/api/prefs/{module_id}")
async def set_pref(request: Request, module_id: str, enabled: bool):
    uid = request.session.get("uid")
    if not uid:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)
    await asyncio.to_thread(db.set_module_enabled, uid, module_id, enabled)
    return {"ok": True}


@app.get("/api/profile")
async def get_profile(request: Request):
    """Return cached profile for the current session user. No API call."""
    uid = request.session.get("uid")
    if not uid:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)
    profile = await asyncio.to_thread(db.get_cached_profile, uid)
    if not profile:
        return JSONResponse({"error": "no profile cached"}, status_code=404)
    return profile


@app.post("/api/profile/refresh")
async def refresh_profile(request: Request):
    """Force re-fetch profile from HF and update cache. Costs 1 API call."""
    uid = request.session.get("uid")
    if not uid:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)
    token = await asyncio.to_thread(db.get_token, uid)
    if not token:
        return JSONResponse({"error": "no token"}, status_code=401)
    from HFClient import HFClient
    client = HFClient(token)
    try:
        data = await client.read({"me": {
            "uid": True, "username": True, "avatar": True,
            "usergroup": True, "displaygroup": True, "additionalgroups": True,
            "postnum": True, "threadnum": True, "reputation": True,
            "bytes": True, "usertitle": True, "timeonline": True,
        }})
    except _AuthExpired:
        return _handle_auth_expired(request, uid)
    if not data:
        return JSONResponse({"error": "HF API unavailable"}, status_code=503)
    me = data.get("me", {})
    await asyncio.to_thread(db.update_profile_cache, uid, {
        "postnum":    me.get("postnum"),
        "threadnum":  me.get("threadnum"),
        "reputation": me.get("reputation"),
        "myps":       me.get("bytes"),
        "usertitle":  me.get("usertitle"),
        "timeonline": me.get("timeonline"),
    })
    return await asyncio.to_thread(db.get_cached_profile, uid)


@app.get("/api/rate-limit")
async def rate_limit(request: Request):
    uid = request.session.get("uid")
    if not uid:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)
    token = await asyncio.to_thread(db.get_token, uid)
    if not token:
        return JSONResponse({"remaining": None})
    from HFClient import get_rate_limit_remaining
    remaining = get_rate_limit_remaining(token)
    throttle  = _throttle_level()
    return {"remaining": remaining, "throttle": throttle}


# ── Dash data endpoints ─────────────────────────────────────────────────────────

@app.get("/api/dash/bytes")
async def dash_bytes(request: Request, force: bool = False):
    """Bytes balance from DB + recent transactions from bytes_history DB.
    Zero API calls — crawler updates both every 5 minutes.
    Falls back to a live API fetch only if DB has no history at all.
    """
    uid = request.session.get("uid")
    if not uid:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)

    # Always read balance from profile cache — crawler keeps it fresh every 5min
    profile = await asyncio.to_thread(db.get_cached_profile, uid)
    balance = str(profile.get("myps")  or "0") if profile else "0"
    vault   = str(profile.get("vault") or "0") if profile else "0"

    # Transactions from local DB (populated by crawler) — zero API calls
    txns_raw, _ = await asyncio.to_thread(db.get_bytes_history, uid, 30, 0)
    if txns_raw:
        txns = [{"id": str(t["id"]), "amount": str(t["amount"]),
                 "dateline": int(t["dateline"]), "reason": str(t["reason"] or ""),
                 "sent": bool(t["sent"])} for t in txns_raw]
        return {"balance": balance, "vault": vault, "transactions": txns}

    # No history in DB yet — do a live fetch so first-time users see something
    token = await asyncio.to_thread(db.get_token, uid)
    if not token:
        return {"balance": balance, "vault": vault, "transactions": []}

    from HFClient import HFClient
    client  = HFClient(token)
    uid_int = int(uid)
    try:
        data1 = await client.read({
            "me":    {"uid": True, "bytes": True, "vault": True},
            "bytes": {"_to": [uid_int], "_page": 1, "_perpage": 30,
                      "id": True, "amount": True, "dateline": True, "reason": True},
        })
        if not data1:
            return {"balance": balance, "vault": vault, "transactions": []}
        data2 = await client.read({
            "bytes": {"_from": [uid_int], "_page": 1, "_perpage": 30,
                      "id": True, "amount": True, "dateline": True, "reason": True},
        })
    except _AuthExpired:
        return _handle_auth_expired(request, uid)
    me = (data1 or {}).get("me", {})
    balance = str(me.get("bytes") or "0")
    vault   = str(me.get("vault")  or "0")

    def parse(data, sent):
        raw = (data or {}).get("bytes", [])
        if isinstance(raw, dict): raw = [raw]
        return [{"id": str(t.get("id")), "amount": str(t.get("amount") or "0"),
                 "dateline": int(t.get("dateline") or 0),
                 "reason": str(t.get("reason") or ""), "sent": sent}
                for t in (raw or []) if t.get("id")]

    recv_list = parse(data1, False)
    sent_list = parse(data2, True)
    seen, txns = set(), []
    for t in sorted(sent_list + recv_list, key=lambda x: x["dateline"], reverse=True):
        if t["id"] not in seen:
            seen.add(t["id"]); txns.append(t)
    txns = txns[:30]
    await asyncio.to_thread(db.upsert_bytes_txns, uid, recv_list + sent_list)
    await asyncio.to_thread(db.update_profile_cache, uid, {"myps": me.get("bytes"), "vault": me.get("vault")})
    return {"balance": balance, "vault": vault, "transactions": txns}


def _contract_value(c: dict) -> str:
    """Best human-readable payment value from a contract dict."""
    iprice    = str(c.get("iprice") or "0").strip()
    oprice    = str(c.get("oprice") or "0").strip()
    icur      = str(c.get("icurrency") or "").strip()
    ocur      = str(c.get("ocurrency") or "").strip()
    iproduct  = str(c.get("iproduct") or "").strip()
    oproduct  = str(c.get("oproduct") or "").strip()

    # Prefer explicit price+currency if non-zero
    if iprice and iprice != "0" and icur and icur.lower() != "other":
        return f"{iprice} {icur}"
    if oprice and oprice != "0" and ocur and ocur.lower() != "other":
        return f"{oprice} {ocur}"
    # Fall back to product description (contains "12.99 Crypto or Credit Card" etc)
    _skip = ("", "other", "n/a", "none")
    if iproduct and iproduct.lower() not in _skip:
        return iproduct
    if oproduct and oproduct.lower() not in _skip:
        return oproduct
    return ""


@app.get("/api/dash/contracts")
async def dash_contracts(request: Request, force: bool = False):
    """All contracts from local DB. Falls back to HF API only if DB is empty."""
    uid = request.session.get("uid")
    if not uid:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)

    STATUS = {
        "1":"Awaiting Approval","2":"Cancelled","3":"Unknown","4":"Cancelled",
        "5":"Active Deal","6":"Complete","7":"Disputed","8":"Expired"
    }

    def _fmt(c):
        return {
            "cid":      str(c.get("cid") or ""),
            "type_n":   str(c.get("type_n") or c.get("type") or ""),
            "status":   STATUS.get(str(c.get("status_n") or c.get("status") or ""), "Unknown"),
            "status_n": str(c.get("status_n") or c.get("status") or ""),
            "type":     {"1":"Selling","2":"Purchasing","3":"Exchanging","4":"Trading","5":"Vouch Copy"}.get(
                            str(c.get("type_n") or c.get("type") or ""), "--"),
            "inituid":  str(c.get("inituid") or ""),
            "otheruid": str(c.get("otheruid") or ""),
            "iprice":   str(c.get("iprice") or "0"),
            "icurrency":str(c.get("icurrency") or ""),
            "oprice":   str(c.get("oprice") or "0"),
            "ocurrency":str(c.get("ocurrency") or ""),
            "iproduct": str(c.get("iproduct") or ""),
            "oproduct": str(c.get("oproduct") or ""),
            "dateline": int(c.get("dateline") or 0),
            "terms":    str(c.get("terms") or ""),
            "value":    _contract_value(c),
        }

    # ── Try DB first (crawler keeps this populated) ───────────────────────────
    total_count = await asyncio.to_thread(db.get_contracts_history_count, uid)
    if total_count > 0 and not force:
        rows = await asyncio.to_thread(db.get_contracts_history, uid, total_count, 0, None, "dateline", "desc")
        contracts = [_fmt(dict(r)) for r in rows]
        # Enrich with cached counterparty usernames — zero HF API calls
        all_cp_uids = list({str(c["inituid"]) for c in contracts if c.get("inituid")} |
                           {str(c["otheruid"]) for c in contracts if c.get("otheruid")})
        username_map = await asyncio.to_thread(db.get_uid_usernames, all_cp_uids) if all_cp_uids else {}
        for c in contracts:
            is_init = str(c.get("inituid", "")) == str(uid)
            cp_uid  = str(c["otheruid"] if is_init else c["inituid"])
            c["counterparty_uid"]      = cp_uid
            c["counterparty_username"] = username_map.get(cp_uid, "")
        return {"contracts": contracts, "uid": uid, "total_count": total_count, "username_map": username_map}

    # ── DB empty or force refresh — fall back to HF API (page 1 only) ─────────
    token = await asyncio.to_thread(db.get_token, uid)
    if not token:
        return JSONResponse({"error": "no token"}, status_code=401)

    from HFClient import HFClient
    client = HFClient(token)
    try:
        data = await client.read({
            "contracts": {
                "_uid": [int(uid)], "_page": 1, "_perpage": 30,
                "cid": True, "status": True, "type": True,
                "inituid": True, "otheruid": True,
                "iprice": True, "icurrency": True,
                "oprice": True, "ocurrency": True,
                "iproduct": True, "oproduct": True,
                "dateline": True, "terms": True,
            }
        })
    except _AuthExpired:
        return _handle_auth_expired(request, uid)
    if not data:
        return JSONResponse({"error": "HF API unavailable"}, status_code=503)

    raw = data.get("contracts", [])
    if isinstance(raw, dict): raw = [raw]
    contracts = [_fmt(c) for c in (raw or [])]
    total_count = await asyncio.to_thread(db.get_contracts_history_count, uid)
    return {"contracts": contracts, "uid": uid, "total_count": total_count}


def _perspective_type_row(c, uid: str) -> str:
    """Contract type from the user's perspective using product/price fields."""
    TYPE_MAP = {"1":"Selling","2":"Purchasing","3":"Exchanging","4":"Trading","5":"Vouch Copy"}
    type_n = str(c.get("type_n") or c.get("type") or "")
    if type_n in ("3","5"):
        return TYPE_MAP.get(type_n, "--")
    trivial = {"","other","n/a","none","null"}
    has_ip  = str(c.get("iproduct") or "").strip().lower() not in trivial
    has_op  = str(c.get("oproduct") or "").strip().lower() not in trivial
    try:    iprice = float(c.get("iprice") or 0)
    except: iprice = 0
    try:    oprice = float(c.get("oprice") or 0)
    except: oprice = 0
    if str(c.get("inituid") or "") == uid:
        if has_ip:     return "Selling"
        if has_op:     return "Purchasing"
        if iprice > 0: return "Purchasing"
        if oprice > 0: return "Selling"
        return "Selling"
    else:
        if has_op:     return "Selling"
        if has_ip:     return "Purchasing"
        if oprice > 0: return "Purchasing"
        if iprice > 0: return "Selling"
        return "Selling"

@app.get("/api/contracts/history")
async def contracts_history_db(request: Request, page: int = 1, perpage: int = 10,
                                status: str | None = None,
                                sort_col: str = "dateline", sort_dir: str = "desc"):
    """Contracts history from local DB — grows as crawler runs. No API calls."""
    uid = request.session.get("uid")
    if not uid:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)

    # Map frontend sort column names to DB column names
    col_map = {"cid": "cid", "status": "status_n", "type": "type_n", "value": "dateline"}
    db_col   = col_map.get(sort_col, "dateline")
    status_n = status  # e.g. "5" for Active, "6" for Complete, etc.
    offset   = (page - 1) * perpage
    rows     = await asyncio.to_thread(db.get_contracts_history, uid, perpage, offset, status_n, db_col, sort_dir)
    total    = await asyncio.to_thread(db.get_contracts_history_count, uid, status_n)
    cstate   = await asyncio.to_thread(db.get_contracts_crawl_state, uid)

    STATUS   = {"1":"Awaiting Approval","2":"Cancelled","3":"Unknown","4":"Cancelled",
                "5":"Active Deal","6":"Complete","7":"Disputed","8":"Expired"}
    TYPE_MAP = {"1":"Selling","2":"Purchasing","3":"Exchanging","4":"Trading","5":"Vouch Copy"}

    contracts = []
    for c in rows:
        contracts.append({
            "cid":       c["cid"],
            "status_n":  c["status_n"] or "",
            "status":    STATUS.get(str(c["status_n"] or ""), "Unknown"),
            "type_n":    c["type_n"] or "",
            "type":      _perspective_type_row(c, uid),
            "inituid":   c["inituid"] or "",
            "otheruid":  c["otheruid"] or "",
            "iprice":    c["iprice"] or "0",
            "icurrency": c["icurrency"] or "",
            "oprice":    c["oprice"] or "0",
            "ocurrency": c["ocurrency"] or "",
            "iproduct":  c["iproduct"] or "",
            "oproduct":  c["oproduct"] or "",
            "dateline":  c["dateline"] or 0,
            "value":     _contract_value(c),
        })

    return {
        "contracts": contracts,
        "total":     total,
        "page":      page,
        "perpage":   perpage,
        "crawl": {
            "done": bool(cstate.get("done")),
            "page": cstate.get("page", 1),
        },
    }



@app.get("/api/contracts/stats")
async def contracts_stats(request: Request):
    """Aggregate contract counts from local DB. No API calls."""
    uid = request.session.get("uid")
    if not uid:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)
    return await asyncio.to_thread(db.get_contracts_stats, uid)


@app.get("/api/contracts/export")
async def contracts_export(
    request: Request,
    format: str = "csv",           # csv | json
    status: str | None = None,     # e.g. "6" for Complete
    date_from: int | None = None,  # unix timestamp
    date_to:   int | None = None,  # unix timestamp
):
    """Download full contract history as CSV or JSON. Requires crawl to be complete."""
    import csv, io, json as _json
    from fastapi.responses import Response as FResponse

    uid = request.session.get("uid")
    if not uid:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)

    cstate = await asyncio.to_thread(db.get_contracts_crawl_state, uid)
    if not cstate.get("done"):
        return JSONResponse(
            {"error": "Contract history is still being crawled. Export is available once crawl is complete."},
            status_code=409,
        )

    rows = await asyncio.to_thread(db.get_contracts_export, uid, status, date_from, date_to)

    STATUS_MAP = {"1":"Awaiting Approval","2":"Cancelled","3":"Unknown","4":"Cancelled",
                  "5":"Active Deal","6":"Complete","7":"Disputed","8":"Expired"}
    TYPE_MAP   = {"1":"Selling","2":"Purchasing","3":"Exchanging","4":"Trading","5":"Vouch Copy"}

    def _val(r):
        ip, ic = r.get("iprice","0") or "0", r.get("icurrency","other") or "other"
        op, oc = r.get("oprice","0") or "0", r.get("ocurrency","other") or "other"
        ipr, opr = r.get("iproduct","") or "", r.get("oproduct","") or ""
        if ip != "0" and ic.lower() != "other":  return f"{ip} {ic}"
        if op != "0" and oc.lower() != "other":  return f"{op} {oc}"
        if ipr not in ("","other","n/a"):         return ipr
        if opr not in ("","other","n/a"):         return opr
        return ""

    records = []
    for r in rows:
        tid = r.get("tid") or ""
        records.append({
            "cid":         r["cid"],
            "status":      STATUS_MAP.get(str(r.get("status_n") or ""), "Unknown"),
            "type":        TYPE_MAP.get(str(r.get("type_n") or ""), "--"),
            "inituid":     r.get("inituid") or "",
            "otheruid":    r.get("otheruid") or "",
            "value":       _val(r),
            "iprice":      r.get("iprice") or "",
            "icurrency":   r.get("icurrency") or "",
            "iproduct":    r.get("iproduct") or "",
            "oprice":      r.get("oprice") or "",
            "ocurrency":   r.get("ocurrency") or "",
            "oproduct":    r.get("oproduct") or "",
            "tid":         tid,
            "thread_url":  f"https://hackforums.net/showthread.php?tid={tid}" if tid else "",
            "dateline":    r.get("dateline") or "",
            "contract_url": f"https://hackforums.net/contracts.php?action=view&cid={r['cid']}",
        })

    fmt = format.lower()
    if fmt == "json":
        content = _json.dumps(records, indent=2)
        return FResponse(
            content=content,
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=hf_contracts_{uid}.json"},
        )
    else:
        buf = io.StringIO()
        fields = ["cid","status","type","inituid","otheruid","value",
                  "iprice","icurrency","iproduct","oprice","ocurrency","oproduct",
                  "tid","thread_url","dateline","contract_url"]
        w = csv.DictWriter(buf, fieldnames=fields)
        w.writeheader()
        w.writerows(records)
        return FResponse(
            content=buf.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=hf_contracts_{uid}.csv"},
        )


@app.get("/api/contracts/analytics")
async def contracts_analytics_preview(
    request: Request,
    status: str | None = None,
    date_from: int | None = None,
    date_to:   int | None = None,
):
    """Rich aggregate analytics for the export preview panel. No API calls."""
    uid = request.session.get("uid")
    if not uid:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)
    return await asyncio.to_thread(db.get_contracts_analytics, uid, status, date_from, date_to)

@app.get("/api/contracts/preview")
async def contracts_preview(
    request: Request,
    status: str | None = None,
    date_from: int | None = None,
    date_to:   int | None = None,
    limit: int = 10,
):
    """Summary stats + first N preview rows for the export panel. No API calls."""
    uid = request.session.get("uid")
    if not uid:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)
    return await asyncio.to_thread(db.get_contracts_preview, uid, status, date_from, date_to, min(limit, 25))


@app.get("/api/users/resolve")
async def users_resolve(request: Request, uids: str = ""):
    """Lookup usernames from local DB cache. Zero HF API calls.
    UIDs are resolved during the crawl and stored in uid_usernames table."""
    uid = request.session.get("uid")
    if not uid:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)
    uid_list = [u.strip() for u in uids.split(",") if u.strip() and u.strip().isdigit()]
    if not uid_list:
        return JSONResponse({})
    return await asyncio.to_thread(db.get_uid_usernames, uid_list)




@app.get("/api/dash/user/{lookup_uid}")
async def dash_user_lookup(request: Request, lookup_uid: str):
    """Real-time user lookup. No cache — explicit user action."""
    uid = request.session.get("uid")
    if not uid:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)
    token = await asyncio.to_thread(db.get_token, uid)
    if not token:
        return JSONResponse({"error": "no token"}, status_code=401)

    from HFClient import HFClient
    client = HFClient(token)
    try:
        data = await client.read({"users": {
            "_uid": [int(lookup_uid)],
            "uid": True, "username": True, "usergroup": True,
            "displaygroup": True, "additionalgroups": True,
            "postnum": True, "threadnum": True, "myps": True,
            "reputation": True, "usertitle": True, "awards": True,
            "timeonline": True, "avatar": True,
        }})
    except _AuthExpired:
        return _handle_auth_expired(request, uid)
    if not data:
        return JSONResponse({"error": "HF API unavailable"}, status_code=503)
    users = data.get("users", {})
    if isinstance(users, list):
        user = users[0] if users else None
    else:
        user = users
    if not user:
        return JSONResponse({"error": "User not found"}, status_code=404)
    # Passively cache the result so contract lists resolve this UID without extra calls
    if user.get("uid") and user.get("username"):
        try:
            await asyncio.to_thread(db.upsert_uid_usernames, {str(user["uid"]): user["username"]})
        except Exception:
            pass
    return user


@app.post("/api/dash/bytes/send")
async def dash_send_bytes(request: Request):
    uid = request.session.get("uid")
    if not uid:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)
    body = await request.json()
    token = await asyncio.to_thread(db.get_token, uid)
    if not token:
        return JSONResponse({"error": "no token"}, status_code=401)
    from HFClient import HFClient
    client = HFClient(token)
    try:
        result = await client.write({"bytes": {
            "_uid":    str(body.get("to_uid", "")),
            "_amount": str(body.get("amount", "")),
            "_reason": str(body.get("reason", "")),
        }})
    except _AuthExpired:
        return _handle_auth_expired(request, uid)
    if result is None:
        return JSONResponse({"error": "Send failed"}, status_code=500)
    await asyncio.to_thread(db.clear_dash_cache, uid, "bytes")
    return {"ok": True}


@app.post("/api/dash/bytes/vault")
async def dash_vault(request: Request):
    uid = request.session.get("uid")
    if not uid:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)
    body = await request.json()
    action = body.get("action")  # "deposit" or "withdraw"
    amount = int(body.get("amount", 0))
    if amount < 100:
        return JSONResponse({"error": "Minimum vault amount is 100 bytes"}, status_code=400)
    token = await asyncio.to_thread(db.get_token, uid)
    if not token:
        return JSONResponse({"error": "no token"}, status_code=401)
    from HFClient import HFClient
    client = HFClient(token)
    try:
        if action == "deposit":
            result = await client.write({"bytes": {"_deposit": amount}})
        else:
            result = await client.write({"bytes": {"_withdraw": amount}})
    except _AuthExpired:
        return _handle_auth_expired(request, uid)
    if result is None:
        return JSONResponse({"error": f"{action} failed — check you have enough bytes"}, status_code=500)

    # Immediately fetch fresh balance + vault from HF and update profile cache
    # so the frontend sees the new values right away without waiting for the crawler
    try:
        me_data = await client.read({"me": {"bytes": True, "vault": True}})
        if me_data:
            me = me_data.get("me", {})
            await asyncio.to_thread(db.update_profile_cache, uid, {
                "myps":  me.get("bytes"),
                "vault": me.get("vault"),
            })
            return {
                "ok":      True,
                "balance": str(me.get("bytes") or "0"),
                "vault":   str(me.get("vault")  or "0"),
            }
    except Exception:
        pass

    await asyncio.to_thread(db.clear_dash_cache, uid, "bytes")
    return {"ok": True, "balance": None, "vault": None}


@app.get("/api/bytes/history")
async def bytes_history_db(request: Request, page: int = 1, perpage: int = 30,
                            direction: str = "all", type_filter: str = "", q: str = ""):
    """Bytes history from local DB with optional filters. No API calls."""
    uid = request.session.get("uid")
    if not uid:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)
    offset  = (page - 1) * perpage
    txns, filtered_total = await asyncio.to_thread(
        db.get_bytes_history, uid, perpage, offset, direction, type_filter, q)
    return {"transactions": txns, "total": filtered_total, "page": page, "perpage": perpage}


@app.get("/api/bytes/stats")
async def bytes_stats(request: Request):
    """Bytes analytics from local history DB. Zero API calls."""
    uid = request.session.get("uid")
    if not uid:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)

    txns = await asyncio.to_thread(db.get_bytes_history_all, uid)
    count = len(txns)
    if not count:
        state = await asyncio.to_thread(db.get_crawl_state, uid)
        return {"count": 0, "crawl": {"complete": False,
            "recv_page": state.get("recv_page",1), "sent_page": state.get("sent_page",1)}}

    from collections import defaultdict

    def categorize(reason):
        r = (reason or "").lower()
        if "sportsbook wager" in r: return "Sportsbook Bets"
        if "wager winner" in r or "sports wager winner" in r: return "Sportsbook Wins"
        if "sportsbook cancel" in r or "sportsbook refund" in r: return "Sportsbook Refunds"
        if "slot" in r: return "Slots"
        if "blackjack" in r: return "Blackjack"
        if "flip" in r: return "Coin Flips"
        if "bump" in r: return "Thread Bumps"
        if "quick love" in r: return "Quick Love"
        if "rain" in r: return "Rain"
        if "contract" in r: return "Contracts"
        if "scratch" in r: return "Scratch Cards"
        if "lotto" in r or "lottery" in r: return "Lottery"
        if "crypto" in r: return "Crypto Game"
        if "casino" in r: return "Casino"
        return "Other"

    def _safe_float(val) -> float:
        try:
            return abs(float(val))
        except (TypeError, ValueError):
            return 0.0

    total_in  = sum(_safe_float(t["amount"]) for t in txns if not t["sent"])
    total_out = sum(_safe_float(t["amount"]) for t in txns if t["sent"])
    cat_in  = defaultdict(float)
    cat_out = defaultdict(float)
    for t in txns:
        cat = categorize(t.get("reason") or "")
        amt = _safe_float(t["amount"])
        if t["sent"]: cat_out[cat] += amt
        else:         cat_in[cat]  += amt

    cats = sorted([{
        "name": c, "in": round(cat_in[c],2), "out": round(cat_out[c],2),
        "net": round(cat_in[c]-cat_out[c],2)
    } for c in set(cat_in)|set(cat_out)], key=lambda x: abs(x["net"]), reverse=True)

    state = await asyncio.to_thread(db.get_crawl_state, uid)
    return {
        "count":      count,
        "total_in":   round(total_in, 2),
        "total_out":  round(total_out, 2),
        "net":        round(total_in - total_out, 2),
        "categories": cats,
        "crawl": {
            "complete":  bool(state.get("recv_done")) and bool(state.get("sent_done")),
            "recv_page": state.get("recv_page", 1),
            "sent_page": state.get("sent_page", 1),
        }
    }


@app.get("/api/settings")
async def get_settings(request: Request):
    """Return persisted user settings (polling intervals, API floor, etc.)."""
    uid = request.session.get("uid")
    if not uid:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)
    settings = await asyncio.to_thread(db.get_user_settings, uid)
    return {"settings": settings}


@app.post("/api/settings")
async def save_settings(request: Request):
    """Persist user settings. Merges into existing settings."""
    uid = request.session.get("uid")
    if not uid:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)
    body = await request.json()
    # Load existing and merge so partial updates don't nuke other keys
    existing = await asyncio.to_thread(db.get_user_settings, uid)
    existing.update(body)
    await asyncio.to_thread(db.save_user_settings, uid, existing)
    return {"ok": True, "settings": existing}


@app.get("/api/crawl/status")
async def crawl_status(request: Request):
    """Return crawler state for bytes + contracts. No API calls."""
    uid = request.session.get("uid")
    if not uid:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)
    import time as _t
    bytes_state     = await asyncio.to_thread(db.get_crawl_state, uid)
    contracts_state = await asyncio.to_thread(db.get_contracts_crawl_state, uid)
    bytes_count     = await asyncio.to_thread(db.get_bytes_history_count, uid)
    contracts_count = await asyncio.to_thread(db.get_contracts_history_count, uid)

    def fmt_ts(ts):
        if not ts: return None
        return int(ts)

    return {
        "bytes": {
            "recv_page":  bytes_state.get("recv_page", 1),
            "sent_page":  bytes_state.get("sent_page", 1),
            "recv_done":  bool(bytes_state.get("recv_done")),
            "sent_done":  bool(bytes_state.get("sent_done")),
            "last_crawl": fmt_ts(bytes_state.get("last_crawl")),
            "total_stored": bytes_count,
        },
        "contracts": {
            "page":         contracts_state.get("page", 1),
            "done":         bool(contracts_state.get("done")),
            "last_crawl":   fmt_ts(contracts_state.get("last_crawl")),
            "total_stored": contracts_count,
        },
    }


@app.get("/api/user/{lookup_uid}/activity")
async def user_activity(request: Request, lookup_uid: str):
    """Return profile + recent posts + threads. Results cached 5 min — no page params needed,
    frontend paginates client-side so there are zero extra API calls on page navigation."""
    import time, math
    uid = request.session.get("uid")
    if not uid:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)

    # Return cached result if still fresh
    cached = _activity_cache.get(lookup_uid)
    if cached and (time.time() - cached["ts"]) < ACTIVITY_CACHE_TTL:
        return cached["data"]

    token = await asyncio.to_thread(db.get_token, uid)
    if not token:
        return JSONResponse({"error": "no token"}, status_code=401)
    from HFClient import HFClient
    client = HFClient(token)
    target = int(lookup_uid)

    # Call 1: profile
    try:
        profile_data = await client.read({
            "users": {
                "_uid": [target],
                "uid": True, "username": True, "usergroup": True,
                "displaygroup": True, "additionalgroups": True,
                "postnum": True, "threadnum": True, "myps": True,
                "reputation": True, "usertitle": True, "timeonline": True,
                "avatar": True, "awards": True, "website": True, "referrals": True,
            },
        })
    except _AuthExpired:
        return _handle_auth_expired(request, uid)
    if not profile_data:
        return JSONResponse({"error": "HF API unavailable"}, status_code=503)
    users_raw = profile_data.get("users", {})
    user = (users_raw[0] if isinstance(users_raw, list) else users_raw) or {}
    if not user:
        return JSONResponse({"error": "User not found"}, status_code=404)

    PERPAGE = 20

    # Call 2: threads pages 1+2 (newest-first, no inversion needed).
    # Collect firstpost PIDs to strip OPs from the posts list.
    all_threads = []
    firstpost_pids = set()
    for t_page in range(1, 3):
        try:
            td = await client.read({"threads": {
                "_uid": [target], "_page": t_page, "_perpage": PERPAGE,
                "tid": True, "fid": True, "subject": True, "dateline": True,
                "firstpost": True, "views": True, "lastpost": True,
                "closed": True, "sticky": True,
            }})
        except _AuthExpired:
            return _handle_auth_expired(request, uid)
        if not td: break
        raw = td.get("threads", [])
        if isinstance(raw, dict): raw = [raw]
        page_rows = list(raw or [])
        if not page_rows: break
        all_threads.extend(page_rows)
        firstpost_pids.update(str(t["firstpost"]) for t in page_rows if t.get("firstpost"))

    # Calls 3-N: forward scan to find true last page of posts._uid (oldest-first),
    # then also fetch the page before it. Gives ~40 posts total.
    postnum     = int(user.get("postnum")   or 0)
    threadnum   = int(user.get("threadnum") or 0)
    reply_count = max(0, postnum - threadnum)
    base_page   = max(1, -(-reply_count // PERPAGE))

    true_last_page = base_page
    raw_last = []
    for try_page in range(base_page, base_page + 8):
        try:
            pd = await client.read({"posts": {
                "_uid": [target], "_page": try_page, "_perpage": PERPAGE,
                "pid": True, "tid": True, "fid": True,
                "dateline": True, "subject": True, "message": True,
            }})
        except _AuthExpired:
            return _handle_auth_expired(request, uid)
        cur = []
        if pd:
            r = pd.get("posts", [])
            if isinstance(r, dict): r = [r]
            cur = list(r or [])
        if not cur: break
        raw_last = cur
        true_last_page = try_page

    # Fetch one extra page back for more history
    raw_prev = []
    if true_last_page > 1:
        try:
            pd2 = await client.read({"posts": {
                "_uid": [target], "_page": true_last_page - 1, "_perpage": PERPAGE,
                "pid": True, "tid": True, "fid": True,
                "dateline": True, "subject": True, "message": True,
            }})
        except _AuthExpired:
            return _handle_auth_expired(request, uid)
        if pd2:
            r2 = pd2.get("posts", [])
            if isinstance(r2, dict): r2 = [r2]
            raw_prev = list(r2 or [])

    # Combine pages, filter OPs, sort newest-first
    seen = set()
    all_posts = []
    for p in list(reversed(raw_last)) + list(reversed(raw_prev)):
        pid = str(p.get("pid", ""))
        if pid and pid not in firstpost_pids and pid not in seen:
            seen.add(pid)
            all_posts.append(p)
    all_posts.sort(key=lambda p: int(p.get("dateline") or 0), reverse=True)

    result = {
        "user":    user,
        "posts":   all_posts,
        "threads": all_threads,
    }
    _activity_cache[lookup_uid] = {"ts": time.time(), "data": result}
    return result



@app.get("/api/user/{lookup_uid}/trust")
async def user_trust(request: Request, lookup_uid: str, ratings_page: int = 1):
    """B-ratings received + contract stats for trust lookup. 1 API call."""
    uid = request.session.get("uid")
    if not uid:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)
    token = await asyncio.to_thread(db.get_token, uid)
    if not token:
        return JSONResponse({"error": "no token"}, status_code=401)
    from HFClient import HFClient
    client = HFClient(token)
    target = int(lookup_uid)
    PERPAGE = 15

    # 1 call: b-ratings received + contracts (2 endpoints, well under limit)
    try:
        data = await client.read({
            "bratings": {
                "_to": [target], "_page": ratings_page, "_perpage": PERPAGE,
                "crid": True, "contractid": True, "fromid": True, "toid": True,
                "dateline": True, "amount": True, "message": True,
                "from": {"uid": True, "username": True},
            },
            "contracts": {
                "_uid": [target], "_page": 1, "_perpage": 30,
                "cid": True, "status": True, "type": True, "dateline": True,
            },
        })
    except _AuthExpired:
        return _handle_auth_expired(request, uid)

    if not data:
        return JSONResponse({"error": "HF API unavailable"}, status_code=503)

    # ── Parse b-ratings ──────────────────────────────────────────────────────
    br_raw = data.get("bratings", [])
    if isinstance(br_raw, dict): br_raw = [br_raw]
    ratings = []
    for r in (br_raw or []):
        from_user = r.get("from") or {}
        if isinstance(from_user, list):
            from_user = from_user[0] if from_user else {}
        if isinstance(from_user, dict):
            from_username = str(from_user.get("username") or r.get("fromid") or "")
            from_uid      = str(from_user.get("uid")      or r.get("fromid") or "")
        else:
            from_username = str(r.get("fromid") or "")
            from_uid      = str(r.get("fromid") or "")
        try:
            amt = int(float(r.get("amount") or 0))
        except (TypeError, ValueError):
            amt = 0
        ratings.append({
            "crid":       str(r.get("crid") or ""),
            "contractid": str(r.get("contractid") or ""),
            "from_uid":   from_uid,
            "from_username": from_username,
            "dateline":   int(r.get("dateline") or 0),
            "amount":     amt,
            "message":    str(r.get("message") or ""),
        })

    # ── Parse contracts for stats ─────────────────────────────────────────────
    c_raw = data.get("contracts", [])
    if isinstance(c_raw, dict): c_raw = [c_raw]
    counts: dict[str, int] = {}
    for c in (c_raw or []):
        s = str(c.get("status") or "")
        counts[s] = counts.get(s, 0) + 1
    total      = sum(counts.values())
    complete   = counts.get("6", 0)
    disputed   = counts.get("7", 0)
    cancelled  = counts.get("2", 0)
    active     = counts.get("5", 0)
    awaiting   = counts.get("1", 0)
    expired    = counts.get("8", 0)
    non_canc   = total - cancelled
    comp_rate  = round(complete / non_canc * 100) if non_canc > 0 else 0
    disp_rate  = round(disputed / non_canc * 100) if non_canc > 0 else 0

    return {
        "ratings":          ratings,
        "ratings_page":     ratings_page,
        "ratings_has_more": len(ratings) >= PERPAGE,
        "contract_stats": {
            "total":           total,
            "active":          active,
            "awaiting":        awaiting,
            "complete":        complete,
            "disputed":        disputed,
            "cancelled":       cancelled,
            "expired":         expired,
            "completion_rate": comp_rate,
            "dispute_rate":    disp_rate,
        },
    }


@app.delete("/api/account")
async def delete_account(request: Request):
    """Delete ALL stored data for the current user and log them out."""
    uid = request.session.get("uid")
    if not uid:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)
    await asyncio.to_thread(db.delete_user_data, uid)
    request.session.clear()
    return {"ok": True}


@app.get("/api/notifications")
async def get_notifications(request: Request):
    uid = request.session.get("uid")
    if not uid:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)
    notifs = await asyncio.to_thread(db.get_notifications, uid, 30)
    unseen = await asyncio.to_thread(db.get_unseen_count, uid)
    return {"notifications": notifs, "unseen": unseen}


@app.post("/api/notifications/seen")
async def mark_seen(request: Request):
    uid = request.session.get("uid")
    if not uid:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)
    await asyncio.to_thread(db.mark_notifications_seen, uid)
    return {"ok": True}


@app.get("/api/contracts/{cid}")
async def get_contract_detail(request: Request, cid: int):
    """Fetch contract detail with 5-min cache. Force-refresh with ?force=true."""
    uid = request.session.get("uid")
    if not uid:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)
    token = await asyncio.to_thread(db.get_token, uid)
    if not token:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)

    force     = request.query_params.get("force") == "true"
    cache_key = f"contract_detail_{cid}"
    CACHE_TTL = 300  # 5 minutes

    # Serve from cache unless forced or stale
    if not force:
        cached = await asyncio.to_thread(db.get_dash_cache, uid, cache_key, CACHE_TTL)
        if cached:
            return cached

    try:
        from HFClient import HFClient
        client  = HFClient(token)
        uid_int = int(uid)

        data = await asyncio.wait_for(client.read({
            "contracts": {
                "_cid": [int(cid)],
                "cid": True, "dateline": True, "status": True, "type": True,
                "istatus": True, "ostatus": True, "muid": True,
                "inituid": True, "otheruid": True,
                "iprice": True, "icurrency": True, "iproduct": True,
                "oprice": True, "ocurrency": True, "oproduct": True,
                "terms": True, "timeout_days": True, "timeout": True,
                "public": True, "tid": True, "idispute": True, "odispute": True,
            },
        }), timeout=8)
        if not data:
            return JSONResponse({"error": "No response from HF"}, status_code=503)
        rows = data.get("contracts", [])
        if isinstance(rows, dict): rows = [rows]
        if not rows:
            return JSONResponse({"error": "Contract not found"}, status_code=404)
        c = rows[0]

        # Counterparty username — local DB first, API only if missing
        init_uid  = int(c.get("inituid") or 0)
        other_uid = int(c.get("otheruid") or 0)
        cp_uid    = other_uid if init_uid == uid_int else init_uid
        username  = None
        if cp_uid:
            cached_user = await asyncio.to_thread(db.get_user, str(cp_uid))
            if cached_user:
                username = cached_user.get("username")
        if cp_uid and not username:
            try:
                u_data = await asyncio.wait_for(client.read({
                    "users": {"_uid": [cp_uid], "uid": True, "username": True}
                }), timeout=8)
                u_rows = u_data.get("users", []) if u_data else []
                if isinstance(u_rows, dict): u_rows = [u_rows]
                if u_rows: username = u_rows[0].get("username")
            except Exception:
                pass

        result = {"contract": c, "counterparty_username": username, "my_uid": uid}
        await asyncio.to_thread(db.set_dash_cache, uid, cache_key, result)
        return result
    except asyncio.TimeoutError:
        return JSONResponse({"error": "HF API timeout"}, status_code=503)
    except Exception as e:
        log.error("contract detail error cid=%s: %s", cid, e)
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/contracts/{cid}/action")
async def contract_action(request: Request, cid: int):
    """Perform a contract action (approve, deny, cancel, complete, undo)."""
    uid   = request.session.get("uid")
    if not uid:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)
    token = await asyncio.to_thread(db.get_token, uid)
    if not token:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)
    body = await request.json()
    action  = body.get("action", "")
    address = body.get("address", "")
    ALLOWED = {"approve", "deny", "cancel", "complete", "undo"}
    if action not in ALLOWED:
        return JSONResponse({"error": f"Unknown action: {action}"}, status_code=400)
    try:
        from HFClient import HFClient
        client  = HFClient(token)
        payload: dict = {"_action": action, "_cid": int(cid)}
        if address:
            payload["_address"] = address
        data = await asyncio.wait_for(client.write({"contracts": payload}), timeout=8)
        if not data:
            return JSONResponse({"error": "No response from HF"}, status_code=503)
        return {"ok": True, "response": data}
    except asyncio.TimeoutError:
        return JSONResponse({"error": "HF API timeout"}, status_code=503)
    except Exception as e:
        log.error("contract action error cid=%s action=%s: %s", cid, action, e)
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/health")
async def health():
    return {"ok": True}