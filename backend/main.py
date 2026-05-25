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
import hmac
import logging
import asyncio
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
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
import integration_db
from module_registry import all_modules, all_routers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
log = logging.getLogger("main")


# Global semaphore — limits concurrent live HF API calls to prevent proxy saturation
_hf_sem = asyncio.Semaphore(4)
FRONTEND_URL = os.environ.get("FRONTEND_URL", "http://localhost:5173")

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
        # get_running_loop() is the correct call inside an async context (FastAPI handler).
        # The old get_event_loop() pattern is deprecated in Python 3.10+ and raises in 3.12+.
        loop = asyncio.get_running_loop()
        loop.create_task(asyncio.to_thread(db.clear_token, uid))
    except RuntimeError:
        pass  # no running loop — shouldn't happen from a FastAPI handler
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


async def _crawl_user_bytes(uid: str, token: str, active: bool = True) -> None:
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
            "dateline": True, "tid": True, "brating": True,
        },
        "threads": {
            "_uid": [uid_int], "_page": 1, "_perpage": 30,
            "tid": True, "subject": True, "fid": True,
            "lastpost": True, "lastposteruid": True, "numreplies": True,
            "firstpost": True, "closed": True,
        },
    }), timeout=35)

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
            "dateline": True, "tid": True, "brating": True,
        }
    data2 = await asyncio.wait_for(client.read(call2_ask), timeout=35)

    # ── Parse + store bytes ───────────────────────────────────────────────────
    def parse_bytes(data, sent):
        raw = (data or {}).get("bytes", [])
        if isinstance(raw, dict): raw = [raw]
        return [{"id": t.get("id"), "amount": t.get("amount"),
                 "dateline": t.get("dateline"), "reason": t.get("reason"), "sent": sent}
                for t in (raw or []) if t.get("id")]

    recv_txns = parse_bytes(data1, False)
    sent_txns = parse_bytes(data2, True)

    # Detect new received transactions before they get upserted (dedup by ID)
    if recv_done and recv_txns:
        try:
            recv_ids = [str(t["id"]) for t in recv_txns if t.get("id")]
            existing_recv_ids = await asyncio.to_thread(db.get_existing_bytes_ids, uid, recv_ids)
            for t in recv_txns:
                txn_id = str(t.get("id") or "")
                if not txn_id or txn_id in existing_recv_ids:
                    continue
                amount = str(t.get("amount") or "")
                reason = str(t.get("reason") or "")
                title = f"+{amount} bytes"
                body  = reason[:120] if reason else ""
                _bytes_link = (os.environ.get("FRONTEND_URL", "").rstrip("/") or "https://hftoolbox.com") + "/dashboard/bytes"
                await asyncio.to_thread(
                    integration_db.create_alert_event,
                    uid, "bytes_received", f"txn:{txn_id}",
                    title, body,
                    _bytes_link,
                    "toolbox", None, True,
                )
        except Exception as e:
            log.warning("Crawl: bytes_received alert failed uid=%s: %s", uid, e)

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
                        integration_db.create_alert_event,
                        uid, "contract_new", f"cid:{cid}",
                        f"New contract #{cid}",
                        f"Status: {status_label}",
                        f"/dashboard/contracts/{cid}",
                        "toolbox", None, True,
                    )
            except Exception as e:
                log.warning("Crawl: contract notification failed uid=%s: %s", uid, e)

    # ── Re-check any contracts still showing as open (Awaiting/Active) ──────────
    # Runs at most once every 15 minutes, capped at 1 batch (30 contracts).
    # Old code fired up to 3 batches every crawl cycle = up to 36 calls/hr waste.
    try:
        _now_ts  = int(_t.time())
        _last_rc = int(cstate.get("last_recheck_ts") or 0)
        if _now_ts - _last_rc >= 900:  # 15-minute cooldown
            open_cids    = await asyncio.to_thread(db.get_open_contract_cids, uid)
            fetched_cids = {str(c.get("cid","")) for c in all_contracts}
            stale_cids   = [int(cid) for cid in open_cids if cid not in fetched_cids]
            if stale_cids:
                batch = stale_cids[:30]
                try:
                    r = await asyncio.wait_for(client.read({"contracts": {
                        "_cid": batch,
                        "cid": True, "status": True, "type": True,
                        "inituid": True, "otheruid": True,
                        "iprice": True, "icurrency": True,
                        "oprice": True, "ocurrency": True,
                        "iproduct": True, "oproduct": True,
                        "dateline": True, "tid": True, "brating": True,
                    }}), timeout=12)
                except asyncio.TimeoutError:
                    log.warning("Contracts re-check: API timeout uid=%s", uid)
                    r = None
                if r:
                    updated = r.get("contracts", [])
                    if isinstance(updated, dict): updated = [updated]
                    if updated:
                        # Snapshot current status/brating before overwriting so we can detect changes
                        try:
                            _recheck_cids = [str(c.get("cid","")) for c in updated if c.get("cid")]
                            _before = await asyncio.to_thread(db.get_contracts_statuses, uid, _recheck_cids)
                        except Exception:
                            _before = {}
                        await asyncio.to_thread(db.upsert_contracts, uid, updated)
                        log.info("Contracts re-check uid=%s updated %d open contracts", uid, len(updated))
                        # Fire contract change alerts
                        try:
                            STATUS_LABELS = {"1":"Awaiting Approval","2":"Cancelled","5":"Active Deal",
                                             "6":"Complete","7":"Disputed","8":"Expired"}
                            for c in updated:
                                cid       = str(c.get("cid",""))
                                new_sn    = str(c.get("status",""))
                                new_br    = str(c.get("brating") or "")
                                old_entry = _before.get(cid, {})
                                old_sn    = old_entry.get("status_n","")
                                old_br    = old_entry.get("brating","")
                                if not cid or not old_entry:
                                    continue
                                if new_sn and new_sn != old_sn:
                                    label = STATUS_LABELS.get(new_sn, f"Status {new_sn}")
                                    atype = "contract_dispute" if new_sn == "7" else "contract_status_change"
                                    await asyncio.to_thread(
                                        integration_db.create_alert_event,
                                        uid, atype, f"cid:{cid}:status:{new_sn}",
                                        f"Contract #{cid} — {label}",
                                        "", f"/dashboard/contracts/{cid}",
                                        "toolbox", None, True,
                                    )
                                if new_br and new_br != old_br:
                                    await asyncio.to_thread(
                                        integration_db.create_alert_event,
                                        uid, "contract_b_rating", f"cid:{cid}:brating",
                                        f"Contract #{cid} — B-rating received",
                                        "", f"/dashboard/contracts/{cid}",
                                        "toolbox", None, True,
                                    )
                        except Exception as e:
                            log.warning("Contracts re-check: alert failed uid=%s: %s", uid, e)
            await asyncio.to_thread(db.update_contracts_crawl_state, uid, last_recheck_ts=_now_ts)
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
            t_firstpost  = str(th.get("firstpost") or "0")
            t_closed     = int(th.get("closed") or 0)
            if not t_tid or not t_lastpost:
                continue

            # Register thread (idempotent)
            try:
                await asyncio.to_thread(add_my_thread, uid, t_tid, t_fid, t_subject,
                                                   t_lastpost, t_lastposter, t_numreplies, t_closed,
                                                   firstpost=t_firstpost)
            except Exception:
                pass

            stored_lastpost = int((_cursor_map.get(t_tid) or {}).get("last_checked") or 0)

            if t_lastpost <= stored_lastpost:
                continue  # no change since last crawl

            if stored_lastpost == 0:
                try:
                    await asyncio.to_thread(update_thread_last_checked, uid, t_tid, "0", t_lastpost)
                except Exception:
                    pass

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
            if active:
                try:
                    from modules.posting import poll_reply_queues
                    await asyncio.wait_for(poll_reply_queues(active_uids={uid}), timeout=30)
                except asyncio.TimeoutError:
                    log.warning("Crawl: inline reply poll timed out uid=%s", uid)
                except Exception as _rpe:
                    log.warning("Crawl: inline reply poll failed uid=%s: %s", uid, _rpe)

    except Exception as _te:
        log.warning("Crawl: thread reply detection failed uid=%s: %s", uid, _te)

    # ── Free bonus: update profile cache ─────────────────────────────────────
    me = (data1 or {}).get("me", {})
    if me:
        try:
            await asyncio.to_thread(db.update_profile_cache, uid, {
                "myps":         me.get("bytes"),
                "vault":        me.get("vault"),
                "postnum":      me.get("postnum"),
                "threadnum":    me.get("threadnum"),
                "reputation":   me.get("reputation"),
                "usertitle":    me.get("usertitle"),
                "timeonline":   me.get("timeonline"),
                "displaygroup": me.get("displaygroup") or me.get("usergroup") or "",
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
                    await asyncio.to_thread(
                        integration_db.create_alert_event,
                        uid, "pm_unread_increase", f"unread:{unread}",
                        f"You have {unread} unread PM{'s' if unread != 1 else ''}",
                        "", "https://hackforums.net/private.php",
                        "toolbox", None, True,
                    )
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


IDLE_THRESHOLD = 900
IDLE_CRAWL_INTERVAL = 1800


async def _crawl_if_active(uid: str, token: str) -> bool:
    """
    Active users get the full crawl. Idle users get a slower maintenance crawl.
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
        await asyncio.to_thread(db.set_needs_refresh, uid, 1)
        state = await asyncio.to_thread(db.get_crawl_state, uid)
        last_crawl = int(state.get("last_crawl") or 0)
        if _t.time() - last_crawl >= IDLE_CRAWL_INTERVAL:
            log.info("Crawl: uid=%s idle %.0fs - running maintenance crawl", uid, idle_secs)
            await _crawl_user_bytes(uid, token, active=False)
            return True
        log.debug("Crawl: uid=%s idle %.0fs - skipping until maintenance interval", uid, idle_secs)
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
                    log.warning("Crawl: AuthExpired uid=%s — attempting refresh before clearing", uid)
                    from token_manager import try_refresh_token
                    new_tok = await try_refresh_token(uid)
                    if not new_tok:
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
    Runs every 5 minutes. Active users get full crawls; idle users get slower
    maintenance crawls and are flagged for a full refresh on return.
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
            # Critical throttle is the only global stop; user API floors still apply per token.
            _tl = _throttle_level()
            if _tl == "critical":
                log.info("Bytes crawl: skipping - throttle=%s", _tl)
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
                    chunk    = [int(u) for u in (unknown or []) if str(u).isdigit()]

                    # ── Bundle UID and TID lookups into one read call ────────────────
                    unknown_tids = await asyncio.to_thread(db.get_unknown_tids_from_contracts, uid, 30)
                    tid_ints     = [int(t) for t in (unknown_tids or []) if str(t).isdigit()]

                    if not chunk and not tid_ints:
                        continue

                    from HFClient import HFClient
                    client = HFClient(token)
                    ask: dict = {}
                    if chunk:
                        ask["users"]   = {"_uid": chunk[:30], "uid": True, "username": True}
                    if tid_ints:
                        ask["threads"] = {"_tid": tid_ints[:30], "tid": True, "subject": True}

                    combined = await asyncio.wait_for(client.read(ask), timeout=15)
                    if combined:
                        if "users" in combined:
                            rows = combined["users"]
                            if isinstance(rows, dict): rows = [rows]
                            uid_map = {str(r["uid"]): r["username"] for r in rows if r.get("uid") and r.get("username")}
                            if uid_map:
                                await asyncio.to_thread(db.upsert_uid_usernames, uid_map)
                                log.info("Username cache: resolved %d UIDs for user %s", len(uid_map), uid)
                        if "threads" in combined:
                            trows = combined["threads"]
                            if isinstance(trows, dict): trows = [trows]
                            tid_map = {str(r["tid"]): r["subject"] for r in trows if r.get("tid") and r.get("subject")}
                            if tid_map:
                                await asyncio.to_thread(db.upsert_tid_titles, tid_map)
                                log.info("Thread cache: resolved %d titles for uid=%s", len(tid_map), uid)
                    await asyncio.sleep(2)  # brief pause between users

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
    that has contracts with missing tid. Delayed so startup stays cheap.
    Cost: ~3 HF API calls per user, only ever runs if needed.
    Capped at MAX_BACKFILL_PAGES per user to bound API spend on cold starts."""
    await asyncio.sleep(1800)
    from HFClient import HFClient
    import time as _t

    MAX_BACKFILL_PAGES = 20  # hard cap: 600 contracts max — prevents runaway API spend

    if _throttle_level() != "normal":
        log.info("TID backfill: skipped because API throttle is not normal")
        return

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

            while page <= MAX_BACKFILL_PAGES:
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

            if page > MAX_BACKFILL_PAGES:
                log.warning("TID backfill: hit page cap (%d) for uid=%s — will resume next restart",
                            MAX_BACKFILL_PAGES, uid)
            log.info("TID backfill: done uid=%s updated=%d pages=%d", uid, total, page)
        except Exception as e:
            log.warning("TID backfill: failed uid=%s: %s", uid, e)


async def _telegram_delivery_loop():
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        log.info("Telegram delivery: TELEGRAM_BOT_TOKEN not set, skipping")
        return
    from telegram_sender import send_message
    from telegram_alerts import format_alert
    while True:
        try:
            events = await asyncio.wait_for(
                asyncio.to_thread(integration_db.get_all_undelivered_events),
                timeout=10,
            )
            for event in events:
                chat_id = event.get("chat_id")
                if not chat_id:
                    continue
                text = format_alert(event)
                ok = await send_message(token, int(chat_id), text)
                if ok:
                    await asyncio.wait_for(
                        asyncio.to_thread(integration_db.mark_alert_event_delivered, event["id"]),
                        timeout=10,
                    )
                await asyncio.sleep(0.05)
        except asyncio.TimeoutError:
            log.warning("Telegram delivery loop: DB call timed out, skipping cycle")
        except Exception as e:
            log.warning("Telegram delivery loop error: %s", e)
        await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Expand thread pool — default is too small for concurrent DB + crawl on Windows
    import concurrent.futures
    loop = asyncio.get_event_loop()
    # 32 workers: enough for concurrent HF API calls + DB ops, but well below
    # the DB connection pool cap (MAX_POOL_CONNS=8 in db_connection.py).
    # Old value of 64 caused max_user_connections MySQL errors.
    loop.set_default_executor(concurrent.futures.ThreadPoolExecutor(max_workers=32))
    log.info("Thread pool: set to 32 workers")

    db.init_db()
    db.init_user_settings()
    db.init_notifications_table()
    integration_db.init_integration_tables()
    from modules.posting.posting_db import init_posting_db
    init_posting_db()
    from modules.sigmarket.sigmarket_db import init_sigmarket_db
    init_sigmarket_db()

    # ── Startup DB cleanup ──────────────────────────────────────────────────
    # 1. Reset NULL last_pid rows so cursor comparisons work cleanly.
    # 2. Reset any 'sending' threads to 'failed'.
    #    If the server crashed between mark_thread_sending() and mark_thread_sent(),
    #    those rows stay 'sending' forever — get_due_threads() only fetches 'pending',
    #    so the scheduled thread silently disappears. We reset to 'failed' rather than
    #    'pending' because we can't know if the API write went through — auto-retrying
    #    could create a duplicate post on HF. User sees it in their failed list and can
    #    verify on HF before deciding to resend.
    try:
        from db_connection import _db as _pdb
        with _pdb() as _pc:
            _pc.execute("UPDATE my_threads SET last_pid='0' WHERE last_pid IS NULL")
            stuck = _pc.execute(
                "SELECT COUNT(*) AS cnt FROM scheduled_threads WHERE status='sending'"
            ).fetchone()
            stuck_count = int((stuck or {}).get("cnt") or 0)
            if stuck_count:
                _pc.execute(
                    "UPDATE scheduled_threads SET status='failed', "
                    "error='Server restarted during send — check HF to verify if posted before resending' "
                    "WHERE status='sending'"
                )
                log.warning(
                    "Startup: reset %d stuck 'sending' thread(s) to 'failed' — "
                    "users should verify on HF before resending",
                    stuck_count,
                )
    except Exception as e:
        log.warning("Startup DB cleanup failed: %s", e)
    import modules  # noqa — triggers all register() calls
    log.info("Modules loaded: %s", [m.id for m in all_modules()])

    # Mount module routers
    for meta, router in all_routers():
        app.include_router(router)
        log.info("Mounted: %s", meta.id)

    _disable_crawl = os.environ.get("DEV_DISABLE_CRAWL") == "1"
    if _disable_crawl:
        log.warning("DEV_DISABLE_CRAWL=1 — all background crawl/scheduler tasks disabled")
    else:
        _start_watchdog(loop)

    # Start background polling
    from scheduler import start_scheduler
    if not _disable_crawl:
        await start_scheduler()

    # Start hf_service background refresh worker
    import hf_service as _hfs
    await _hfs.start_service()

    # Mount autobump router (core, not a module)
    from modules.autobump.router import router as autobump_router
    app.include_router(autobump_router)
    from modules.posting.router import router as posting_router
    app.include_router(posting_router)
    from modules.sigmarket.router import router as sigmarket_router
    app.include_router(sigmarket_router)
    from modules.wire.router import router as wire_router
    app.include_router(wire_router)

    # ── Unified 5-minute scheduler ──────────────────────────────────────────
    # Handles: scheduled thread posting (every tick), autobump (every 30 min),
    # and reply queue polling (every 15 min). All in one loop, batched per user.
    from modules.autobump import poll_autobump
    from modules.posting import fire_due_threads, poll_reply_queues
    from modules.sigmarket import poll_sigmarket_rotations
    from modules.sigmarket.router import _do_browse_fetch, _browse_cache, warm_sigmarket_status

    async def _unified_loop():
        import time as _t
        import hf_service  # noqa — used for pick_best_token in global jobs
        _last_autobump      = 0.0
        _last_reply_poll    = 0.0
        _last_browse_warm   = 0.0
        _last_sigmarket_warm = 0.0
        _last_wire_sync     = 0.0
        AUTOBUMP_INTERVAL      = 1800  # 30 min — always runs (user-facing feature)
        REPLY_POLL_INTERVAL    =  300  # 5 min normal; doubled at low/critical
        BROWSE_WARM_INTERVAL   = 1500  # 25 min; skipped at caution+
        SIGMARKET_WARM_INTERVAL =  900  # 15 min per-user sigmarket status; skip at caution+
        WIRE_SYNC_INTERVAL     = 21600  # 6 hr — refresh numreplies/lastpost/closed on wire threads
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
                        from token_manager import try_refresh_token
                        uids = await asyncio.to_thread(db.get_all_uids)
                        for uid in uids:
                            token = await asyncio.to_thread(db.get_token, uid)
                            # If token is dead, try to refresh it first
                            if not token or await asyncio.to_thread(db.is_token_dead, uid):
                                log.info("Scheduler: uid=%s token dead/missing — attempting refresh", uid)
                                token = await try_refresh_token(uid)
                                if not token:
                                    log.warning("Scheduler: uid=%s refresh failed — skipping autobump", uid)
                                    continue
                            # Warn if token expiring within 72 hours
                            try:
                                import time as _tnow
                                _user_row    = await asyncio.to_thread(db.get_user, uid)
                                _tok_expiry  = int((_user_row or {}).get("token_expiry") or 0)
                                _secs_left   = _tok_expiry - _tnow.time() if _tok_expiry else None
                                if _secs_left is not None and 0 < _secs_left < 72 * 3600:
                                    _hrs = int(_secs_left // 3600)
                                    await asyncio.to_thread(
                                        integration_db.create_alert_event,
                                        uid, "token_expiring", f"token_expiring:{_tok_expiry}",
                                        "Auth token expiring soon",
                                        f"Expires in ~{_hrs} hour{'s' if _hrs != 1 else ''}. Log in to HFToolbox to refresh it before autobump stops.",
                                        "/dashboard/settings", "toolbox", None, True,
                                    )
                            except Exception:
                                pass
                            try:
                                await poll_autobump(uid, token)
                                await poll_sigmarket_rotations(uid, token)
                            except _AuthExpired:
                                log.warning("Scheduler: AuthExpired uid=%s — attempting refresh", uid)
                                new_tok = await try_refresh_token(uid)
                                if new_tok:
                                    log.info("Scheduler: uid=%s token refreshed, retrying autobump", uid)
                                    try:
                                        await poll_autobump(uid, new_tok)
                                    except _AuthExpired:
                                        log.warning("Scheduler: uid=%s refresh succeeded but still AuthExpired — clearing", uid)
                                        await asyncio.to_thread(db.clear_token, uid)
                                else:
                                    log.warning("Scheduler: uid=%s refresh failed — clearing token", uid)
                                    await asyncio.to_thread(db.clear_token, uid)
                        _last_autobump = _t.time()
                        # Daily bump digest — once per day per user if bumps ran
                        try:
                            from modules.autobump.autobump_db import get_bumped_since
                            import time as _tdig
                            _now_dig = int(_tdig.time())
                            _since   = _now_dig - (_now_dig % 86400)  # UTC midnight
                            _today   = str(_since // 86400)
                            for uid in uids:
                                bumps = await asyncio.to_thread(get_bumped_since, uid, _since)
                                if not bumps:
                                    continue
                                thread_titles = list(dict.fromkeys(
                                    b.get("thread_title") or f"TID {b['tid']}" for b in bumps
                                ))
                                n_bumps   = len(bumps)
                                n_threads = len(thread_titles)
                                preview   = ", ".join(thread_titles[:3])
                                if n_threads > 3:
                                    preview += f" +{n_threads - 3} more"
                                await asyncio.to_thread(
                                    integration_db.create_alert_event,
                                    uid, "autobump_daily", f"autobump_daily:{_today}",
                                    f"{n_bumps} bump{'s' if n_bumps != 1 else ''} ran today",
                                    preview,
                                    "/dashboard/autobump", "toolbox", None, True,
                                )
                        except Exception as _e:
                            log.warning("Unified scheduler: daily digest error: %s", _e)
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
                        # pick_best_token: highest remaining budget, skip dead tokens
                        _, _warm_token = await hf_service.pick_best_token()
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

                # ── 6. Wire thread sync (every 6 hr — keeps stats fresh) ──────────
                if now - _last_wire_sync >= WIRE_SYNC_INTERVAL and _tl == "normal":
                    try:
                        from modules.wire.router import sync_wire_threads
                        # Try all users' tokens —
                        # so wire sync still works if that token has expired.
                        # pick_best_token: highest remaining budget, skip dead tokens
                        _, _wire_token = await hf_service.pick_best_token()
                        if _wire_token:
                            # Hard 120s cap — prevents watchdog heartbeat starvation
                            # when there are many Wire threads (each batch costs ~12s worst-case)
                            await asyncio.wait_for(sync_wire_threads(_wire_token), timeout=120)
                        else:
                            log.warning("Wire sync: no valid token available — skipping")
                        _last_wire_sync = _t.time()
                    except asyncio.TimeoutError:
                        log.warning("Wire sync: timed out after 120s — will retry in 6h")
                        _last_wire_sync = _t.time()  # still advance so we don't spam retries
                    except Exception as e:
                        log.warning("Wire sync error: %s", e)

            except Exception as e:
                log.exception("Unified scheduler: unexpected error: %s", e)

            _touch_heartbeat()  # watchdog: unified scheduler is still ticking
            # Stretch the tick when budget is low — less overhead, fewer wasted cycles
            _tick = TICK * (2 if _tl in ("low", "critical") else 1)
            await asyncio.sleep(_tick)

    if not _disable_crawl:
        asyncio.create_task(_unified_loop(), name="unified_scheduler")

    # Pre-warm sigmarket browse cache on startup from local DB only.
    async def _startup_browse_warm():
        await asyncio.sleep(3)
        try:
            from modules.sigmarket.router import _load_browse_cache_from_db

            if _load_browse_cache_from_db():
                log.info("Startup: sigmarket browse loaded from DB cache (0 API calls)")
            else:
                log.info("Startup: sigmarket browse DB cache empty/stale; skipping HF fetch")
        except Exception as e:
            log.warning("Startup browse warm failed: %s", e)
    asyncio.create_task(_startup_browse_warm(), name="startup_browse_warm")

    if not _disable_crawl:
        # Start bytes history crawler (core, not a module)
        asyncio.create_task(_bytes_crawl_loop(), name="bytes_crawler")
        asyncio.create_task(_username_resolve_loop(), name="username_resolver")
        asyncio.create_task(_tid_backfill_loop(),       name="tid_backfill")
        asyncio.create_task(_trigger_listener(),   name="crawl_trigger_listener")

    # Telegram alert delivery - runs regardless of DEV_DISABLE_CRAWL (reads DB only, no HF API)
    asyncio.create_task(_telegram_delivery_loop(), name="telegram_delivery")

    # Register Telegram webhook on startup
    _tg_token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    _tg_secret  = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
    _tg_baseurl = os.environ.get("FRONTEND_URL", "").rstrip("/")
    if _tg_token and _tg_secret and _tg_baseurl:
        from telegram_sender import register_webhook as _reg_webhook
        asyncio.create_task(
            _reg_webhook(_tg_token, f"{_tg_baseurl}/api/telegram/webhook", _tg_secret),
            name="telegram_webhook_registration",
        )
    elif _tg_token:
        log.warning("TELEGRAM_BOT_TOKEN set but TELEGRAM_WEBHOOK_SECRET or FRONTEND_URL missing - webhook not registered")

    yield


app = FastAPI(title="HF Dash", lifespan=lifespan)

# In-memory cache for user activity (posts + threads).
# Keyed by (session_uid, lookup_uid) so one user's lookups never bleed into another's.
_activity_cache: dict = {}  # (session_uid, lookup_uid) -> {"ts": float, "data": dict}
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
    secret_key=os.environ["SESSION_SECRET"],
    https_only=os.environ.get("ENV") == "production",
    same_site="lax",
    max_age=60 * 60 * 24 * 14,  # 14 days
)

app.include_router(auth.router)


@app.middleware("http")
async def activity_middleware(request, call_next):
    """
    On every authenticated request:
    1. Touch last_seen so idle detection stays accurate
    2. If needs_refresh=1 (user returning from idle), queue an immediate crawl
    """
    path = request.url.path
    if not path.startswith("/api/") and not path.startswith("/auth/"):
        return await call_next(request)

    response = await call_next(request)

    session = request.scope.get("session") or {}
    uid = session.get("uid")
    if uid:
        asyncio.create_task(_activity_task(uid))

    return response


async def _activity_task(uid: str) -> None:
    """Background task: update last_seen and trigger crawl if needed. Never blocks middleware."""
    try:
        import time as _t
        needs = await asyncio.to_thread(db.get_needs_refresh, uid)
        last_active = await asyncio.to_thread(db.get_last_active, uid)
        was_idle = bool(last_active and (_t.time() - last_active) > IDLE_THRESHOLD)
        await asyncio.to_thread(db.touch_last_active, uid)
        if needs or was_idle:
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
    dg = me.get("displaygroup") or ""
    if not dg or dg == "0":
        dg = me.get("usergroup") or ""
    await asyncio.to_thread(db.update_profile_cache, uid, {
        "postnum":      me.get("postnum"),
        "threadnum":    me.get("threadnum"),
        "reputation":   me.get("reputation"),
        "myps":         me.get("bytes"),
        "usertitle":    me.get("usertitle"),
        "timeonline":   me.get("timeonline"),
        "displaygroup": dg,
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


@app.get("/api/shell-data")
async def shell_data(request: Request):
    """Single endpoint that replaces 3 separate Shell polls (profile, notifications,
    reply count). All DB reads — zero HF API calls. Reduces HTTP chatter by 2/min."""
    uid = request.session.get("uid")
    if not uid:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)
    from modules.posting.posting_db import get_unread_count as _get_unread_count
    profile      = await asyncio.to_thread(db.get_cached_profile, uid)
    notifs       = await asyncio.to_thread(db.get_notifications, uid, 30)
    unseen       = await asyncio.to_thread(db.get_unseen_count, uid)
    reply_count  = await asyncio.to_thread(_get_unread_count, uid)
    user_row     = await asyncio.to_thread(db.get_user, uid)
    token_expiry = int((user_row or {}).get("token_expiry") or 0)
    return {
        "profile":       profile,
        "notifications": notifs,
        "unseen":        unseen,
        "reply_count":   reply_count,
        "token_expiry":  token_expiry,
    }


# ── Dash data endpoints ─────────────────────────────────────────────────────────


@app.get("/api/dashboard/snapshot")
async def dashboard_snapshot(request: Request):
    """
    Single call for the full dashboard initial load and 60s polling.

    Returns all dashboard sections from DB/cache — zero HF API calls under normal
    operation. Replaces the old pattern of 4+ separate polling endpoints.

    Response envelope:
      profile, notifications, unseen, reply_count   — shell data
      bytes, contracts                              — from crawl cache
      job_count, sig_status, sig_stale, sig_age     — from hf_resource_cache
      rate_limit                                    — from HFClient memory
      ts                                            — server unix timestamp

    Frontend shows "updated X ago" using the ts + age fields.
    """
    uid = request.session.get("uid")
    if not uid:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)

    import hf_cache as _hfc
    import time as _t

    from modules.posting.posting_db import get_unread_count as _get_unread

    # ── DB-only reads (zero HF calls) ────────────────────────────────────────
    profile      = await asyncio.to_thread(db.get_cached_profile, uid)
    notifs       = await asyncio.to_thread(db.get_notifications, uid, 30)
    unseen       = await asyncio.to_thread(db.get_unseen_count, uid)
    reply_count  = await asyncio.to_thread(_get_unread, uid)

    # Bytes + contracts from crawl-populated dash_cache (5-min staleness max)
    bytes_data   = await asyncio.to_thread(db.get_dash_cache, uid, "bytes",     7200) or {}
    contracts    = await asyncio.to_thread(db.get_dash_cache, uid, "contracts", 7200) or {}

    # Autobump job count
    try:
        from modules.autobump.autobump_db import get_jobs_for_user as _get_jobs
        jobs     = await asyncio.to_thread(_get_jobs, uid)
        job_count = len(jobs)
    except Exception:
        job_count = -1

    # Sigmarket status from hf_resource_cache (stale-while-revalidate)
    sig_key            = f"sigmarket:status:{uid}"
    sig_data, sig_stale = _hfc.get_usable(sig_key)
    sig_age            = _hfc.get_age(sig_key)

    # Rate limit from HFClient in-memory map (zero DB calls)
    rate_remaining = -1
    try:
        token = await asyncio.to_thread(db.get_token, uid)
        if token:
            from HFClient import get_rate_limit_remaining
            rate_remaining = get_rate_limit_remaining(token)
    except Exception:
        pass

    return {
        # Shell
        "profile":       profile,
        "notifications": notifs,
        "unseen":        unseen,
        "reply_count":   reply_count,
        # Dashboard sections
        "bytes":         bytes_data,
        "contracts":     contracts,
        "job_count":     job_count,
        # Sigmarket (stale-while-revalidate)
        "sig_status":    sig_data,
        "sig_stale":     sig_stale,
        "sig_age":       sig_age,
        # Meta
        "rate_remaining": rate_remaining,
        "ts":            int(_t.time()),
    }


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
        username_map = {uid: info["username"] for uid, info in (await asyncio.to_thread(db.get_uid_usernames, all_cp_uids)).items()} if all_cp_uids else {}
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
        is_init = str(c["inituid"] or "") == str(uid)
        cp_uid = str(c["otheruid"] if is_init else c["inituid"] or "")
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
            "counterparty_uid": cp_uid,
        })

    cp_uids = list({str(c.get("counterparty_uid") or "") for c in contracts if c.get("counterparty_uid")})
    username_map = {u: info["username"] for u, info in (await asyncio.to_thread(db.get_uid_usernames, cp_uids)).items() if info.get("username")} if cp_uids else {}
    for c in contracts:
        c["counterparty_username"] = username_map.get(str(c.get("counterparty_uid") or ""), "")

    return {
        "contracts": contracts,
        "total":     total,
        "page":      page,
        "perpage":   perpage,
        "username_map": username_map,
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
    from datetime import datetime, timezone
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

    party_uids = list({str(r.get("inituid") or "") for r in rows if r.get("inituid")} |
                      {str(r.get("otheruid") or "") for r in rows if r.get("otheruid")})
    username_map = {
        u: info["username"]
        for u, info in (await asyncio.to_thread(db.get_uid_usernames, party_uids)).items()
        if info.get("username")
    } if party_uids else {}

    def _created_at(ts) -> str:
        try:
            return datetime.fromtimestamp(int(ts), timezone.utc).isoformat().replace("+00:00", "Z")
        except Exception:
            return ""

    def _offer(r, side: str) -> str:
        price    = str(r.get(f"{side}price") or "0").strip()
        currency = str(r.get(f"{side}currency") or "").strip()
        product  = str(r.get(f"{side}product") or "").strip()
        parts = []
        if price and price != "0" and currency and currency.lower() != "other":
            parts.append(f"{price} {currency}")
        if product and product.lower() not in ("other", "n/a", "none", "null"):
            parts.append(product)
        return " - ".join(parts)

    records = []
    for r in rows:
        tid       = str(r.get("tid") or "")
        cid       = str(r.get("cid") or "")
        init_uid  = str(r.get("inituid") or "")
        other_uid = str(r.get("otheruid") or "")
        user_is_init = init_uid == str(uid)
        cp_uid    = other_uid if user_is_init else init_uid
        cp_name   = username_map.get(cp_uid, "")
        user_side = "i" if user_is_init else "o"
        cp_side   = "o" if user_is_init else "i"
        records.append({
            "cid": cid,
            "status": STATUS_MAP.get(str(r.get("status_n") or ""), "Unknown"),
            "type": _perspective_type_row(r, uid),
            "role": "Initiator" if user_is_init else "Counterparty",
            "counterparty_username": cp_name,
            "counterparty_uid": cp_uid,
            "value": _contract_value(r),
            "your_offer": _offer(r, user_side),
            "their_offer": _offer(r, cp_side),
            "created_at": _created_at(r.get("dateline")),
            "dateline": r.get("dateline") or "",
            "tid": tid,
            "thread_url":  f"https://hackforums.net/showthread.php?tid={tid}" if tid else "",
            "contract_url": f"https://hackforums.net/contracts.php?action=view&cid={cid}",
            "initiator_uid": init_uid,
            "other_uid": other_uid,
            "raw_type": r.get("type_n") or "",
            "raw_status": r.get("status_n") or "",
            "iprice": r.get("iprice") or "",
            "icurrency": r.get("icurrency") or "",
            "iproduct": r.get("iproduct") or "",
            "oprice": r.get("oprice") or "",
            "ocurrency": r.get("ocurrency") or "",
            "oproduct": r.get("oproduct") or "",
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
        fields = [
            "cid", "status", "type", "role",
            "counterparty_username", "counterparty_uid",
            "value", "your_offer", "their_offer",
            "created_at", "dateline",
            "tid", "thread_url", "contract_url",
            "initiator_uid", "other_uid",
            "raw_type", "raw_status",
            "iprice", "icurrency", "iproduct", "oprice", "ocurrency", "oproduct",
        ]
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
    raw = await asyncio.to_thread(db.get_uid_usernames, uid_list)
    return {uid: info["username"] for uid, info in raw.items()}




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
            av_raw = str(user.get("avatar","") or "")
            if av_raw and not av_raw.startswith("http"):
                av_raw = "https://hackforums.net/" + av_raw.lstrip("./")
            await asyncio.to_thread(db.upsert_uid_usernames, {str(user["uid"]): {
                "username":        user.get("username",""),
                "avatar":          av_raw,
                "usertitle":       user.get("usertitle","") or "",
                "reputation":      int(user.get("reputation") or 0),
                "displaygroup":    str(user.get("displaygroup") or user.get("usergroup") or ""),
                "additionalgroups":str(user.get("additionalgroups") or ""),
            }})
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
    bytes_state     = await asyncio.to_thread(db.get_crawl_state, uid)
    contracts_state = await asyncio.to_thread(db.get_contracts_crawl_state, uid)
    bytes_count     = await asyncio.to_thread(db.get_bytes_history_count, uid)
    contracts_count = await asyncio.to_thread(db.get_contracts_history_count, uid)
    user_row    = await asyncio.to_thread(db.get_user, uid)
    refresh_tok = (user_row or {}).get("refresh_token") or None
    last_active = await asyncio.to_thread(db.get_last_active, uid)
    token_expiry = int((user_row or {}).get("token_expiry") or 0)

    def fmt_ts(ts):
        if not ts: return None
        return int(ts)

    return {
        "crawl_disabled":    os.environ.get("DEV_DISABLE_CRAWL") == "1",
        "has_refresh_token": bool(refresh_tok),
        "token_expiry":      token_expiry,
        "last_active":       fmt_ts(last_active),
        "bytes": {
            "recv_page":    bytes_state.get("recv_page", 1),
            "sent_page":    bytes_state.get("sent_page", 1),
            "recv_done":    bool(bytes_state.get("recv_done")),
            "sent_done":    bool(bytes_state.get("sent_done")),
            "last_crawl":   fmt_ts(bytes_state.get("last_crawl")),
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
    _cache_key = (uid, lookup_uid)
    cached = _activity_cache.get(_cache_key)
    if cached and (time.time() - cached["ts"]) < ACTIVITY_CACHE_TTL:
        return cached["data"]

    token = await asyncio.to_thread(db.get_token, uid)
    if not token:
        return JSONResponse({"error": "no token"}, status_code=401)
    from HFClient import HFClient
    client = HFClient(token)
    target = int(lookup_uid)

    PERPAGE = 20

    # ── Call 1 (2 endpoints): profile + threads page 1 ─────────────────────────
    # Bundling saves a solo-profile call. We need postnum/threadnum from user data
    # to estimate the posts page, so threads p2 + posts come in call 2.
    try:
        data1 = await client.read({
            "users": {
                "_uid": [target],
                "uid": True, "username": True, "usergroup": True,
                "displaygroup": True, "additionalgroups": True,
                "postnum": True, "threadnum": True, "myps": True,
                "reputation": True, "usertitle": True, "timeonline": True,
                "avatar": True, "awards": True, "website": True, "referrals": True,
            },
            "threads": {
                "_uid": [target], "_page": 1, "_perpage": PERPAGE,
                "tid": True, "fid": True, "subject": True, "dateline": True,
                "firstpost": True, "views": True, "lastpost": True,
                "closed": True, "sticky": True,
            },
        })
    except _AuthExpired:
        return _handle_auth_expired(request, uid)
    if not data1:
        return JSONResponse({"error": "HF API unavailable"}, status_code=503)

    users_raw = data1.get("users", {})
    user = (users_raw[0] if isinstance(users_raw, list) else users_raw) or {}
    if not user:
        return JSONResponse({"error": "User not found"}, status_code=404)

    t1_raw = data1.get("threads", [])
    if isinstance(t1_raw, dict): t1_raw = [t1_raw]
    all_threads    = list(t1_raw or [])
    firstpost_pids = {str(t["firstpost"]) for t in all_threads if t.get("firstpost")}

    postnum     = int(user.get("postnum")   or 0)
    threadnum   = int(user.get("threadnum") or 0)
    reply_count = max(0, postnum - threadnum)
    base_page   = max(1, -(-reply_count // PERPAGE))  # mathematical last page estimate

    # ── Call 2 (2 endpoints): threads page 2 + posts estimated last page ────────
    # posts._uid is oldest-first; base_page is the calculated last page.
    try:
        data2 = await client.read({
            "threads": {
                "_uid": [target], "_page": 2, "_perpage": PERPAGE,
                "tid": True, "fid": True, "subject": True, "dateline": True,
                "firstpost": True, "views": True, "lastpost": True,
                "closed": True, "sticky": True,
            },
            "posts": {
                "_uid": [target], "_page": base_page, "_perpage": PERPAGE,
                "pid": True, "tid": True, "fid": True,
                "dateline": True, "subject": True, "message": True,
            },
        })
    except _AuthExpired:
        return _handle_auth_expired(request, uid)

    t2_raw = (data2 or {}).get("threads", [])
    if isinstance(t2_raw, dict): t2_raw = [t2_raw]
    if t2_raw:
        all_threads.extend(t2_raw)
        firstpost_pids.update(str(t["firstpost"]) for t in t2_raw if t.get("firstpost"))

    posts_raw = (data2 or {}).get("posts", [])
    if isinstance(posts_raw, dict): posts_raw = [posts_raw]
    raw_last        = list(posts_raw or [])
    true_last_page  = base_page

    # ── Call 3 (1 endpoint): prev page for more history (or fallback if estimate missed) ──
    # Old code scanned forward up to 8 pages. Now we make at most 1 extra call:
    # if the estimated page was empty → back off by 1; otherwise → grab prev for depth.
    raw_prev = []
    need_extra = (not raw_last and base_page > 1) or (raw_last and base_page > 1)
    if need_extra:
        try_page = (base_page - 1) if not raw_last else (base_page - 1)
        if try_page >= 1:
            try:
                pd3 = await client.read({"posts": {
                    "_uid": [target], "_page": try_page, "_perpage": PERPAGE,
                    "pid": True, "tid": True, "fid": True,
                    "dateline": True, "subject": True, "message": True,
                }})
            except _AuthExpired:
                return _handle_auth_expired(request, uid)
            p3 = (pd3 or {}).get("posts", [])
            if isinstance(p3, dict): p3 = [p3]
            p3 = list(p3 or [])
            if not raw_last:
                # estimate was off by 1 — shift the pages down
                raw_last       = p3
                true_last_page = try_page
            else:
                raw_prev = p3

    # Combine, filter OPs, sort newest-first
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
    _activity_cache[_cache_key] = {"ts": time.time(), "data": result}
    return result



@app.get("/api/user/{lookup_uid}/trust")
async def user_trust(request: Request, lookup_uid: str, ratings_page: int = 1):
    """Credibility ratings received + contract stats for trust lookup. 1 API call."""
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

    # 1 call: credibility ratings received + contracts (2 endpoints, well under limit)
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

    # ── Parse credibility ratings ────────────────────────────────────────────
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

        async with _hf_sem:
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
            }), timeout=30)
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
            cached_names = await asyncio.to_thread(db.get_uid_usernames, [str(cp_uid)])
            cached_user = cached_names.get(str(cp_uid), {})
            username = cached_user.get("username") or None
        if cp_uid and not username:
            try:
                async with _hf_sem:
                    u_data = await asyncio.wait_for(client.read({
                        "users": {"_uid": [cp_uid], "uid": True, "username": True}
                    }), timeout=30)
                u_rows = u_data.get("users", []) if u_data else []
                if isinstance(u_rows, dict): u_rows = [u_rows]
                if u_rows:
                    username = u_rows[0].get("username")
                    if username:
                        await asyncio.to_thread(db.upsert_uid_usernames, {str(cp_uid): username})
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


@app.get("/api/proxy/uimg/{image_id}")
async def proxy_uimg(request: Request, image_id: str, key: str = ""):
    """Proxy raw encrypted bytes from uploadimages.org/api/image/{id}?key={gwKey}.
    The server only ever sees opaque ciphertext — no E2E key, no plaintext."""
    uid = request.session.get("uid")
    if not uid:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)
    import re as _re
    if not _re.fullmatch(r"[a-f0-9]{6,32}", image_id):
        return JSONResponse({"error": "invalid id"}, status_code=400)
    # key is the uploadimages.org gwKey (base64url, ~43 chars) — required
    if not key or not _re.fullmatch(r"[A-Za-z0-9+/=_\-]{10,100}", key):
        return JSONResponse({"error": "invalid key"}, status_code=400)
    import aiohttp as _aiohttp
    from fastapi.responses import Response as _Response
    url = f"https://uploadimages.org/api/image/{image_id}?key={key}"
    try:
        timeout = _aiohttp.ClientTimeout(total=15)
        async with _aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url) as resp:
                if resp.status != 200:
                    return JSONResponse({"error": f"upstream {resp.status}"}, status_code=502)
                data = await resp.read()
        return _Response(
            content=data,
            media_type="application/octet-stream",
            headers={"Cache-Control": "private, max-age=86400"},
        )
    except Exception as e:
        log.warning("uimg proxy failed image_id=%s: %s", image_id, e)
        return JSONResponse({"error": "proxy error"}, status_code=502)



_MANIFEST_EXCLUDE_DIRS = {
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "node_modules",
    "dist",
    "build",
    "data",
    "logs",
}
_MANIFEST_EXCLUDE_FILES = {
    "agent.md",
    "backend/.env",
    "backend/deploy_info.json",
}
_MANIFEST_EXCLUDE_SUFFIXES = (
    ".db",
    ".db-shm",
    ".db-wal",
    ".log",
    ".pyc",
    ".pyo",
    ".pyd",
    ".exe",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _load_deploy_info() -> dict:
    import json as _json

    try:
        return _json.loads((Path(__file__).parent / "deploy_info.json").read_text())
    except Exception:
        return {}


def _git_runtime_info() -> dict:
    import subprocess as _subprocess

    root = _repo_root()
    try:
        commit = _subprocess.run(
            ["git", "-C", str(root), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        branch = _subprocess.run(
            ["git", "-C", str(root), "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        status = _subprocess.run(
            ["git", "-C", str(root), "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        if commit.returncode != 0:
            return {"available": False}
        dirty_lines = [line for line in status.stdout.splitlines() if line.strip()]
        full_commit = commit.stdout.strip()
        return {
            "available": True,
            "commit": full_commit,
            "commit_short": full_commit[:7],
            "branch": branch.stdout.strip() or "unknown",
            "dirty": bool(dirty_lines),
            "dirty_count": len(dirty_lines),
        }
    except Exception:
        return {"available": False}


def _is_manifest_file(path: Path, root: Path) -> bool:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return False

    rel_s = rel.as_posix()
    if rel_s in _MANIFEST_EXCLUDE_FILES:
        return False
    if path.name == ".env" or (path.name.startswith(".env.") and path.name != ".env.example"):
        return False
    if any(part in _MANIFEST_EXCLUDE_DIRS for part in rel.parts):
        return False
    if path.name in {".DS_Store", "Thumbs.db", "desktop.ini"}:
        return False
    if path.suffix.lower() in _MANIFEST_EXCLUDE_SUFFIXES:
        return False
    return path.is_file()


def _file_sha256(path: Path) -> str:
    import hashlib as _hl

    digest = _hl.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _manifest_for(paths: list[Path], root: Path) -> dict:
    import hashlib as _hl

    files = {}
    for path in sorted(paths, key=lambda p: p.relative_to(root).as_posix()):
        rel = path.relative_to(root).as_posix()
        files[rel] = {
            "sha256": _file_sha256(path),
            "size": path.stat().st_size,
        }

    manifest_digest = _hl.sha256()
    for rel, meta in files.items():
        manifest_digest.update(rel.encode("utf-8"))
        manifest_digest.update(b"\0")
        manifest_digest.update(str(meta["size"]).encode("ascii"))
        manifest_digest.update(b"\0")
        manifest_digest.update(meta["sha256"].encode("ascii"))
        manifest_digest.update(b"\n")

    return {
        "algorithm": "sha256",
        "file_count": len(files),
        "manifest_hash": manifest_digest.hexdigest(),
        "files": files,
    }


def _public_repo_manifest() -> dict:
    root = _repo_root()
    paths = [p for p in root.rglob("*") if _is_manifest_file(p, root)]
    return _manifest_for(paths, root)


def _frontend_manifest() -> dict:
    root = _repo_root()
    dist_root = root / "frontend" / "dist"
    if dist_root.exists():
        paths = [p for p in dist_root.rglob("*") if p.is_file()]
        manifest = _manifest_for(paths, root)
        manifest["source"] = "frontend/dist"
        return manifest

    src_root = root / "frontend" / "src"
    paths = [p for p in src_root.rglob("*") if p.is_file()]
    manifest = _manifest_for(paths, root)
    manifest["source"] = "frontend/src"
    return manifest


def _manifest_exclusions() -> dict:
    return {
        "dirs": sorted(_MANIFEST_EXCLUDE_DIRS),
        "files": sorted(_MANIFEST_EXCLUDE_FILES),
        "env_files": [".env", ".env.* except .env.example"],
        "suffixes": list(_MANIFEST_EXCLUDE_SUFFIXES),
    }


@app.get("/api/telegram/status")
async def telegram_status(request: Request):
    uid = request.session.get("uid")
    if not uid:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)
    link = await asyncio.to_thread(integration_db.get_telegram_link, uid)
    bot_username = os.environ.get("TELEGRAM_BOT_USERNAME", "")
    return {
        "linked":       link is not None,
        "chat_id":      link["chat_id"] if link else None,
        "linked_at":    link["linked_at"] if link else None,
        "bot_username": bot_username,
    }


@app.post("/api/telegram/link-code")
async def telegram_link_code(request: Request):
    uid = request.session.get("uid")
    if not uid:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)
    code = await asyncio.to_thread(integration_db.generate_link_code, uid)
    bot_username = os.environ.get("TELEGRAM_BOT_USERNAME", "")
    link = f"https://t.me/{bot_username}?start=tb_{code}" if bot_username else ""
    return {
        "code":    code,
        "link":    link,
        "expires": integration_db.LINK_CODE_TTL,
    }


@app.post("/api/telegram/unlink")
async def telegram_unlink(request: Request):
    uid = request.session.get("uid")
    if not uid:
        return JSONResponse({"error": "unauthenticated"}, status_code=401)
    await asyncio.to_thread(integration_db.unlink_telegram, uid)
    return {"ok": True}


@app.post("/api/telegram/webhook")
async def telegram_webhook(request: Request):
    secret = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "")
    if secret:
        incoming = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
        if not hmac.compare_digest(incoming, secret):
            return Response(status_code=403)

    try:
        update = await request.json()
    except Exception:
        return Response(status_code=400)

    msg     = update.get("message") or {}
    text    = msg.get("text", "")
    chat_id = (msg.get("chat") or {}).get("id")

    if not chat_id or not text.startswith("/start tb_"):
        return Response(status_code=200)

    code = text[len("/start tb_"):].strip()
    if not code:
        return Response(status_code=200)

    hf_uid    = await asyncio.to_thread(integration_db.consume_link_code, code)
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")

    from telegram_sender import send_message as _tg_send
    if not hf_uid:
        if bot_token:
            await _tg_send(bot_token, chat_id,
                "That link has expired or already been used. "
                "Generate a new one from HFToolbox Settings.")
        return Response(status_code=200)

    await asyncio.to_thread(integration_db.link_telegram, hf_uid, int(chat_id))

    if bot_token:
        await _tg_send(bot_token, chat_id,
            "Connected! You'll receive Telegram alerts here as they happen.")

    log.info("Telegram linked via webhook: hf_uid=%s chat_id=%s", hf_uid, chat_id)
    return Response(status_code=200)


@app.get("/health")
async def health():
    deploy_info = _load_deploy_info()
    git_info = await asyncio.to_thread(_git_runtime_info)
    return {"ok": True, **deploy_info, "git": git_info}


@app.get("/health/integrity")
async def health_integrity():
    deploy_info = _load_deploy_info()
    manifest = await asyncio.to_thread(_public_repo_manifest)
    return {
        "commit": deploy_info.get("commit", "unknown"),
        "deployed_at": deploy_info.get("deployed_at", "unknown"),
        "algorithm": manifest["algorithm"],
        "file_count": manifest["file_count"],
        "manifest_hash": manifest["manifest_hash"],
        "checksums": {rel: meta["sha256"] for rel, meta in manifest["files"].items()},
        "excluded": _manifest_exclusions(),
    }


@app.get("/health/manifest")
async def health_manifest():
    deploy_info = _load_deploy_info()
    git_info = await asyncio.to_thread(_git_runtime_info)
    manifest = await asyncio.to_thread(_public_repo_manifest)
    return {
        "commit": deploy_info.get("commit", "unknown"),
        "deployed_at": deploy_info.get("deployed_at", "unknown"),
        "git": git_info,
        **manifest,
        "excluded": _manifest_exclusions(),
    }


@app.get("/health/frontend")
async def health_frontend():
    deploy_info = _load_deploy_info()
    manifest = await asyncio.to_thread(_frontend_manifest)
    return {
        "commit": deploy_info.get("commit", "unknown"),
        "deployed_at": deploy_info.get("deployed_at", "unknown"),
        **manifest,
    }
