import asyncio
import logging
import os
import time as _time

import db
import integration_db

log = logging.getLogger("dashboard_refresh")

_FRONTEND_URL = os.environ.get("FRONTEND_URL", "https://hftoolbox.com")

_GAMBLING_KW = {
    "slots winner", "blackjack winner", "sports wager winner",
    "crypto game coin sell", "flips winner",
}

_STATUS_LABEL = {
    "0": "Awaiting Approval", "1": "Awaiting Approval", "2": "Cancelled",
    "5": "Active Deal", "6": "Complete", "7": "Disputed", "8": "Expired",
}
_TYPE_LABEL = {
    "1": "Selling", "2": "Purchasing", "3": "Exchanging",
    "4": "Trading", "5": "Vouch Copy",
}


def contract_value(c: dict) -> str:
    iprice   = str(c.get("iprice")    or "0").strip()
    oprice   = str(c.get("oprice")    or "0").strip()
    icur     = str(c.get("icurrency") or "").strip()
    ocur     = str(c.get("ocurrency") or "").strip()
    iproduct = str(c.get("iproduct")  or "").strip()
    oproduct = str(c.get("oproduct")  or "").strip()
    if iprice and iprice != "0" and icur and icur.lower() != "other":
        return f"{iprice} {icur}"
    if oprice and oprice != "0" and ocur and ocur.lower() != "other":
        return f"{oprice} {ocur}"
    _skip = ("", "other", "n/a", "none")
    if iproduct and iproduct.lower() not in _skip:
        return iproduct
    if oproduct and oproduct.lower() not in _skip:
        return oproduct
    return ""


def parse_brating_rows(rows_raw, uid: str) -> list:
    if isinstance(rows_raw, dict): rows_raw = [rows_raw]
    result = []
    for r in (rows_raw or []):
        crid = str(r.get("crid") or "")
        if not crid:
            continue
        try:
            amt = int(float(r.get("amount") or 0))
        except (TypeError, ValueError):
            amt = 0
        result.append({
            "crid":          crid,
            "contractid":    str(r.get("contractid") or ""),
            "from_uid":      str(r.get("fromid")     or ""),
            "toid":          str(r.get("toid")        or ""),
            "amount":        amt,
            "message":       str(r.get("message")     or ""),
            "dateline":      int(r.get("dateline")    or 0),
            "from_username": "",
        })
    return result


async def store_bratings(uid: str, parsed: list) -> None:
    if not parsed:
        return
    from modules.merchant.merchant_db import upsert_bratings as _ub, mark_sent_ratings_fetched as _ms
    await asyncio.to_thread(_ub, uid, parsed)
    if any(r["from_uid"] == uid for r in parsed):
        await asyncio.to_thread(_ms, uid)


async def refresh_user_dashboard(uid: str, token: str,
                                 active: bool = True,
                                 reason: str = "scheduler") -> None:
    from HFClient import HFClient

    client  = HFClient(
        token,
        owner_uid=uid,
        feature="dashboard_refresh",
        priority=7,
        background=True,
        route_class="background",
        egress_lane="background",
    )
    uid_int = int(uid)

    state  = await asyncio.to_thread(db.get_crawl_state, uid)
    cstate = await asyncio.to_thread(db.get_contracts_crawl_state, uid)

    recv_done = bool(state["recv_done"])
    sent_done = bool(state["sent_done"])
    c_done    = bool(cstate["done"])

    recv_page    = 1 if recv_done else int(state["recv_page"])
    sent_page    = 1 if sent_done else int(state["sent_page"])
    c_page       = 1 if c_done    else int(cstate["page"])
    c_page_check = 1 if c_done    else c_page

    data1 = await asyncio.wait_for(client.read({
        "bytes": {
            "_to": [uid_int], "_page": recv_page, "_perpage": 30,
            "id": True, "amount": True, "dateline": True, "reason": True,
        },
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
            "istatus": True, "ostatus": True,
            "inituid": True, "otheruid": True,
            "iprice": True, "icurrency": True,
            "oprice": True, "ocurrency": True,
            "iproduct": True, "oproduct": True,
            "iaddress": True, "oaddress": True,
            "timeout_days": True, "timeout": True, "public": True,
            "dateline": True, "tid": True, "brating": True,
        },
        "threads": {
            "_uid": [uid_int], "_page": 1, "_perpage": 30,
            "tid": True, "uid": True, "subject": True, "fid": True,
            "lastpost": True, "lastposteruid": True, "numreplies": True,
            "firstpost": True, "closed": True,
        },
    }, feature="dashboard_refresh.primary", background=True, priority=7,
       cache_ttl=5, stale_ttl=300), timeout=35)

    c_page2    = c_page_check + 1
    call2_ask: dict = {
        "bytes": {
            "_from": [uid_int], "_page": sent_page, "_perpage": 30,
            "id": True, "amount": True, "dateline": True, "reason": True,
        },
    }
    if not c_done and c_page2 > 1:
        call2_ask["contracts"] = {
            "_uid": [uid_int], "_page": c_page2, "_perpage": 30,
            "cid": True, "status": True, "type": True,
            "istatus": True, "ostatus": True,
            "inituid": True, "otheruid": True,
            "iprice": True, "icurrency": True,
            "oprice": True, "ocurrency": True,
            "iproduct": True, "oproduct": True,
            "iaddress": True, "oaddress": True,
            "timeout_days": True, "timeout": True, "public": True,
            "dateline": True, "tid": True, "brating": True,
        }
    data2 = await asyncio.wait_for(
        client.read(call2_ask, feature="dashboard_refresh.secondary",
                    background=True, priority=8, cache_ttl=5, stale_ttl=300),
        timeout=35,
    )

    try:
        await _section_bytes(uid, state, recv_done, sent_done, recv_page, sent_page, data1, data2)
    except Exception as e:
        log.warning("refresh uid=%s [bytes] failed: %s", uid, e)

    try:
        await _section_contracts(uid, cstate, c_done, c_page_check, c_page2, data1, data2, client)
    except Exception as e:
        log.warning("refresh uid=%s [contracts] failed: %s", uid, e)

    try:
        await _section_threads(uid, data1, active)
    except Exception as e:
        log.warning("refresh uid=%s [threads] failed: %s", uid, e)

    try:
        await _section_profile(uid, data1)
    except Exception as e:
        log.warning("refresh uid=%s [profile] failed: %s", uid, e)

    count = await asyncio.to_thread(db.get_bytes_history_count, uid)
    log.info("refresh uid=%s reason=%s bytes_total=%d", uid, reason, count)


async def _section_bytes(uid, state, recv_done, sent_done,
                         recv_page, sent_page, data1, data2) -> None:
    bytes_link = _FRONTEND_URL.rstrip("/") + "/dashboard/bytes"

    def _parse(data, sent: bool) -> list:
        raw = (data or {}).get("bytes", [])
        if isinstance(raw, dict): raw = [raw]
        return [{"id": t.get("id"), "amount": t.get("amount"),
                 "dateline": t.get("dateline"), "reason": t.get("reason"), "sent": sent}
                for t in (raw or []) if t.get("id")]

    recv_txns = _parse(data1, False)
    sent_txns = _parse(data2, True)

    # Alert on new received bytes only after initial crawl is done — during backfill
    # we're seeing old txns for the first time and they aren't genuinely new.
    if recv_done and recv_txns:
        try:
            recv_ids     = [str(t["id"]) for t in recv_txns if t.get("id")]
            existing_ids = await asyncio.to_thread(db.get_existing_bytes_ids, uid, recv_ids)
            gambling_new: list = []
            for t in recv_txns:
                txn_id = str(t.get("id") or "")
                if not txn_id or txn_id in existing_ids:
                    continue
                amount = str(t.get("amount") or "")
                reason = str(t.get("reason") or "")
                if any(k in reason.lower() for k in _GAMBLING_KW):
                    gambling_new.append({"id": txn_id, "amount": amount, "reason": reason})
                else:
                    await asyncio.to_thread(
                        integration_db.create_alert_event,
                        uid, "bytes_received", f"txn:{txn_id}",
                        f"+{amount} bytes", reason[:120] if reason else "",
                        bytes_link, "toolbox", None, True,
                    )
            if gambling_new:
                _FLUSH_SECS  = 1800
                _gpend       = await asyncio.to_thread(db.get_dash_cache, uid, "gambling_pending", 86400 * 30) or {}
                _pending     = _gpend.get("txns", [])
                _last_flush  = int(_gpend.get("flush_ts", 0))
                _pending.extend(gambling_new)
                _now_g = int(_time.time())
                if _now_g - _last_flush >= _FLUSH_SECS:
                    _count = len(_pending)
                    _lines = "\n".join(f"+{x['amount']} - {x['reason']}" for x in _pending[:15])
                    if _count > 15:
                        _lines += f"\n+{_count - 15} more"
                    _wkey = str(int(_now_g // _FLUSH_SECS))
                    await asyncio.to_thread(
                        integration_db.create_alert_event,
                        uid, "bytes_gambling_bundle", f"gambling:{_wkey}",
                        f"{_count} gambling win{'s' if _count != 1 else ''}",
                        _lines, bytes_link, "toolbox", None, True,
                    )
                    await asyncio.to_thread(db.set_dash_cache, uid, "gambling_pending",
                                            {"txns": [], "flush_ts": _now_g})
                else:
                    await asyncio.to_thread(db.set_dash_cache, uid, "gambling_pending",
                                            {"txns": _pending, "flush_ts": _last_flush or _now_g})
        except Exception as e:
            log.warning("refresh uid=%s [bytes alerts] failed: %s", uid, e)

    await asyncio.to_thread(db.upsert_bytes_txns, uid, recv_txns + sent_txns)

    _recv_frontier = _sent_frontier = False
    if not recv_done and len(recv_txns) >= 30:
        try:
            _ids = [str(t["id"]) for t in recv_txns if t.get("id")]
            _ex  = await asyncio.to_thread(db.get_existing_bytes_ids, uid, _ids)
            if _ex and all(str(t["id"]) in _ex for t in recv_txns):
                _recv_frontier = True
                log.info("Bytes crawl: recv frontier page=%d uid=%s", recv_page, uid)
        except Exception:
            pass
    if not sent_done and len(sent_txns) >= 30:
        try:
            _ids = [str(t["id"]) for t in sent_txns if t.get("id")]
            _ex  = await asyncio.to_thread(db.get_existing_bytes_ids, uid, _ids)
            if _ex and all(str(t["id"]) in _ex for t in sent_txns):
                _sent_frontier = True
                log.info("Bytes crawl: sent frontier page=%d uid=%s", sent_page, uid)
        except Exception:
            pass

    new_recv_done = recv_done or len(recv_txns) < 30 or _recv_frontier
    new_sent_done = sent_done or len(sent_txns) < 30 or _sent_frontier
    new_recv_page = recv_page if recv_done else (
        recv_page + 1 if len(recv_txns) >= 30 and not _recv_frontier else recv_page)
    new_sent_page = sent_page if sent_done else (
        sent_page + 1 if len(sent_txns) >= 30 and not _sent_frontier else sent_page)

    await asyncio.to_thread(db.update_crawl_state, uid,
        recv_page=new_recv_page, sent_page=new_sent_page,
        recv_done=int(new_recv_done), sent_done=int(new_sent_done),
        last_crawl=int(_time.time()))

    log.info("Bytes crawl uid=%s recv_p=%d sent_p=%d recv_done=%s sent_done=%s",
             uid, recv_page, sent_page, new_recv_done, new_sent_done)


async def _section_contracts(uid, cstate, c_done, c_page_check, c_page2,
                              data1, data2, client) -> None:
    fe = _FRONTEND_URL.rstrip("/")

    def _parse_contracts(data) -> list:
        raw = (data or {}).get("contracts", [])
        if isinstance(raw, dict): raw = [raw]
        return [c for c in (raw or []) if c.get("cid")]

    c_batch1 = _parse_contracts(data1)
    c_batch2 = _parse_contracts(data2) if not c_done and c_page2 > 1 else []
    all_contracts = c_batch1 + c_batch2
    existing_cids: set = set()

    if all_contracts:
        try:
            all_cids      = [str(c.get("cid", "")) for c in all_contracts if c.get("cid")]
            existing_cids = await asyncio.to_thread(db.get_existing_contract_cids, uid, all_cids)
            _c_before     = await asyncio.to_thread(db.get_contracts_statuses, uid, all_cids) if c_done else {}
        except Exception:
            existing_cids = set()
            _c_before     = {}

        await asyncio.to_thread(db.upsert_contracts, uid, all_contracts)

        if c_done:
            try:
                cutoff   = _time.time() - 3600
                _cp_uids = list({
                    str(c.get("otheruid", "")) if str(c.get("inituid", "")) == uid
                    else str(c.get("inituid", ""))
                    for c in all_contracts if c.get("cid")
                } - {""})
                _cp_map  = await asyncio.to_thread(db.get_uid_usernames, _cp_uids) if _cp_uids else {}

                for c in all_contracts:
                    cid = str(c.get("cid", ""))
                    if not cid:
                        continue
                    _cp_uid  = (str(c.get("otheruid", "")) if str(c.get("inituid", "")) == uid
                                else str(c.get("inituid", "")))
                    _cp_name = (_cp_map.get(_cp_uid) or {}).get("username") or f"UID {_cp_uid}"
                    _link    = f"{fe}/dashboard/contracts/{cid}"

                    if cid not in existing_cids:
                        dateline = int(c.get("dateline") or 0)
                        if dateline and dateline < cutoff:
                            continue
                        _sn      = str(c.get("status_n", c.get("status", "")))
                        _slabel  = _STATUS_LABEL.get(_sn, f"Status {_sn}")
                        _tlabel  = _TYPE_LABEL.get(str(c.get("type", "")), "Contract")
                        _product = str(c.get("iproduct", "") or "").strip()[:60]
                        _price   = str(c.get("iprice", "") or "").strip()
                        _curr    = str(c.get("icurrency", "") or "").strip()
                        body_parts = [f"With: {_cp_name}", f"Status: {_slabel}"]
                        if _product:
                            body_parts.insert(1, f"Product: {_product}")
                        if _price:
                            body_parts.append(f"Price: {_price} {_curr}".strip())
                        await asyncio.to_thread(
                            integration_db.create_alert_event,
                            uid, "contract_new", f"cid:{cid}",
                            f"New contract #{cid} - {_tlabel}",
                            "\n".join(body_parts), _link, "toolbox", None, True,
                        )
                    else:
                        old_entry = _c_before.get(cid, {})
                        if not old_entry:
                            continue
                        new_sn = str(c.get("status", ""))
                        new_br = str(c.get("brating") or "")
                        old_sn = old_entry.get("status_n", "")
                        old_br = old_entry.get("brating", "")
                        if new_sn and new_sn != old_sn:
                            _slabel = _STATUS_LABEL.get(new_sn, f"Status {new_sn}")
                            atype   = "contract_dispute" if new_sn == "7" else "contract_status_change"
                            _prod   = str(c.get("iproduct", "") or "").strip()[:40]
                            body    = f"With: {_cp_name}" + (f" | {_prod}" if _prod else "")
                            await asyncio.to_thread(
                                integration_db.create_alert_event,
                                uid, atype, f"cid:{cid}:status:{new_sn}",
                                f"Contract #{cid} - {_slabel}",
                                body, _link, "toolbox", None, True,
                            )
                            try:
                                from modules.merchant.merchant_db import record_contract_status_event as _rec
                                await asyncio.to_thread(_rec, uid, cid, old_sn, new_sn)
                            except Exception:
                                pass
                        if new_br and new_br != old_br:
                            await asyncio.to_thread(
                                integration_db.create_alert_event,
                                uid, "contract_b_rating", f"cid:{cid}:brating:{new_br}",
                                f"Contract #{cid} - B-rating received",
                                f"With: {_cp_name} | Rating: {new_br}",
                                _link, "toolbox", None, True,
                            )
            except Exception as e:
                log.warning("refresh uid=%s [contract alerts] failed: %s", uid, e)

    try:
        _now_ts  = int(_time.time())
        _last_rc = int(cstate.get("last_recheck_ts") or 0)
        if _now_ts - _last_rc >= 900:
            open_cids    = await asyncio.to_thread(db.get_open_contract_cids, uid)
            fetched_cids = {str(c.get("cid", "")) for c in all_contracts}
            stale_cids   = [int(cid) for cid in open_cids if cid not in fetched_cids]
            if stale_cids:
                batch = stale_cids[:30]
                try:
                    r = await asyncio.wait_for(client.read({"contracts": {
                        "_cid": batch,
                        "cid": True, "status": True, "type": True,
                        "istatus": True, "ostatus": True,
                        "inituid": True, "otheruid": True,
                        "iprice": True, "icurrency": True,
                        "oprice": True, "ocurrency": True,
                        "iproduct": True, "oproduct": True,
                        "iaddress": True, "oaddress": True,
                        "terms": True, "timeout_days": True, "timeout": True,
                        "public": True, "idispute": True, "odispute": True,
                        "dateline": True, "tid": True, "brating": True,
                    }}, feature="dashboard_refresh.contract_recheck",
                       background=True, priority=8, cache_ttl=5, stale_ttl=300), timeout=12)
                except asyncio.TimeoutError:
                    log.warning("Contracts re-check: API timeout uid=%s", uid)
                    r = None
                if r:
                    updated = r.get("contracts", [])
                    if isinstance(updated, dict): updated = [updated]
                    if updated:
                        try:
                            _rc_cids = [str(c.get("cid", "")) for c in updated if c.get("cid")]
                            _before  = await asyncio.to_thread(db.get_contracts_statuses, uid, _rc_cids)
                        except Exception:
                            _before = {}
                        await asyncio.to_thread(db.upsert_contracts, uid, updated)
                        log.info("Contracts re-check uid=%s updated %d open contracts", uid, len(updated))
                        _completed_cids: list = []
                        try:
                            _rc_cp_uids = list({
                                str(c.get("otheruid", "")) if str(c.get("inituid", "")) == uid
                                else str(c.get("inituid", ""))
                                for c in updated if c.get("cid")
                            } - {""})
                            _rc_cp_map = await asyncio.to_thread(db.get_uid_usernames, _rc_cp_uids) if _rc_cp_uids else {}
                            for c in updated:
                                cid       = str(c.get("cid", ""))
                                new_sn    = str(c.get("status", ""))
                                new_br    = str(c.get("brating") or "")
                                old_entry = _before.get(cid, {})
                                old_sn    = old_entry.get("status_n", "")
                                old_br    = old_entry.get("brating", "")
                                if not cid or not old_entry:
                                    continue
                                _rc_cp  = (str(c.get("otheruid", "")) if str(c.get("inituid", "")) == uid
                                           else str(c.get("inituid", "")))
                                _rc_who = (_rc_cp_map.get(_rc_cp) or {}).get("username") or f"UID {_rc_cp}"
                                _rc_lnk = f"{fe}/dashboard/contracts/{cid}"
                                if new_sn and new_sn != old_sn:
                                    label = _STATUS_LABEL.get(new_sn, f"Status {new_sn}")
                                    atype = "contract_dispute" if new_sn == "7" else "contract_status_change"
                                    _prod = str(c.get("iproduct", "") or "").strip()[:40]
                                    body  = f"With: {_rc_who}" + (f" | {_prod}" if _prod else "")
                                    await asyncio.to_thread(
                                        integration_db.create_alert_event,
                                        uid, atype, f"cid:{cid}:status:{new_sn}",
                                        f"Contract #{cid} - {label}",
                                        body, _rc_lnk, "toolbox", None, True,
                                    )
                                    try:
                                        from modules.merchant.merchant_db import record_contract_status_event as _rec
                                        await asyncio.to_thread(_rec, uid, cid, old_sn, new_sn)
                                    except Exception:
                                        pass
                                    if new_sn == "6":
                                        try:
                                            _completed_cids.append(int(cid))
                                        except Exception:
                                            pass
                                if new_br and new_br != old_br:
                                    await asyncio.to_thread(
                                        integration_db.create_alert_event,
                                        uid, "contract_b_rating", f"cid:{cid}:brating:{new_br}",
                                        f"Contract #{cid} - B-rating received",
                                        f"With: {_rc_who} | Rating: {new_br}",
                                        _rc_lnk, "toolbox", None, True,
                                    )
                        except Exception as e:
                            log.warning("Contracts re-check alerts uid=%s: %s", uid, e)
                        if _completed_cids:
                            try:
                                _br_resp = await asyncio.wait_for(client.read({"bratings": {
                                    "_cid": _completed_cids[:8],
                                    "crid": True, "contractid": True, "fromid": True, "toid": True,
                                    "dateline": True, "amount": True, "message": True,
                                }}, feature="dashboard_refresh.brating_check",
                                   background=True, priority=8, cache_ttl=5, stale_ttl=300), timeout=8)
                                if _br_resp and _br_resp.get("success") is not False:
                                    await store_bratings(uid, parse_brating_rows(
                                        (_br_resp or {}).get("bratings", []), uid))
                                    log.info("Contracts re-check: bratings fetched for %d cids uid=%s",
                                             len(_completed_cids), uid)
                            except Exception as _bre:
                                log.warning("Contracts re-check: bratings fetch failed uid=%s: %s", uid, _bre)
            await asyncio.to_thread(db.update_contracts_crawl_state, uid, last_recheck_ts=_now_ts)
    except Exception as e:
        log.warning("refresh uid=%s [contract recheck] failed: %s", uid, e)

    pages_fetched = len([b for b in [c_batch1, c_batch2] if b])
    last_batch    = c_batch2 if c_batch2 else c_batch1
    _frontier = (
        not c_done
        and len(last_batch) >= 30
        and existing_cids
        and all(str(c.get("cid", "")) in existing_cids for c in last_batch)
    )
    if _frontier:
        log.info("Contracts crawl: frontier hit page=%d uid=%s -- all CIDs known", c_page_check, uid)
    new_c_done = c_done or len(last_batch) < 30 or _frontier
    new_c_page = c_page_check if c_done else (
        c_page_check + pages_fetched if not new_c_done else c_page_check)
    await asyncio.to_thread(db.update_contracts_crawl_state, uid,
        page=new_c_page, done=int(new_c_done), last_crawl=int(_time.time()))

    c_total = await asyncio.to_thread(db.get_contracts_history_count, uid)
    log.info("Contracts crawl uid=%s page=%d total=%d done=%s%s",
             uid, c_page_check, c_total, new_c_done, " (frontier)" if _frontier else "")

    if c_batch1:
        _CACHE_STATUS = {
            "0": "Awaiting Approval", "1": "Awaiting Approval", "2": "Cancelled",
            "3": "Unknown", "4": "Cancelled",
            "5": "Active Deal", "6": "Complete", "7": "Disputed", "8": "Expired",
        }
        cached = []
        for c in c_batch1:
            cached.append({
                "cid":       str(c.get("cid") or ""),
                "type_n":    str(c.get("type") or ""),
                "status":    _CACHE_STATUS.get(str(c.get("status") or ""), "Unknown"),
                "status_n":  str(c.get("status") or ""),
                "type":      _TYPE_LABEL.get(str(c.get("type") or ""), str(c.get("type") or "--")),
                "inituid":   str(c.get("inituid") or ""),
                "otheruid":  str(c.get("otheruid") or ""),
                "istatus":   str(c.get("istatus") or ""),
                "ostatus":   str(c.get("ostatus") or ""),
                "iprice":    str(c.get("iprice") or "0"),
                "icurrency": str(c.get("icurrency") or ""),
                "oprice":    str(c.get("oprice") or "0"),
                "ocurrency": str(c.get("ocurrency") or ""),
                "iproduct":  str(c.get("iproduct") or ""),
                "oproduct":  str(c.get("oproduct") or ""),
                "dateline":  int(c.get("dateline") or 0),
                "value":     contract_value(c),
            })
        try:
            await asyncio.to_thread(db.set_dash_cache, uid, "contracts",
                                    {"contracts": cached, "uid": uid})
        except Exception as e:
            log.warning("refresh uid=%s [contracts cache] failed: %s", uid, e)


async def _section_threads(uid: str, data1, active: bool) -> None:
    from modules.posting.posting_db import (
        add_my_thread, update_thread_last_checked, get_all_tracked_threads)
    from modules.posting import (
        _reply_check_queue, _reply_check_titles, _reply_check_numreplies,
        _reply_check_seed_tids, STANLEY_UID)

    raw_threads = (data1 or {}).get("threads", [])
    if isinstance(raw_threads, dict): raw_threads = [raw_threads]

    _tracked_rows = await asyncio.to_thread(get_all_tracked_threads)
    _cursor_map   = {str(t["tid"]): t for t in _tracked_rows if str(t["uid"]) == uid}

    needs_check:    set[str]       = set()
    titles_map:     dict[str, str] = {}
    numreplies_map: dict[str, int] = {}
    seed_tids_uid:  set[str]       = set()

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

        # HF's threads._uid filter isn't reliable enough alone (see HF_API_REFERENCE.md) -
        # threads where this uid was only a contract counterparty, not the real author,
        # have leaked through before. Verify real authorship before treating it as "my thread"
        # for anything, including reply tracking.
        if str(th.get("uid") or "") != uid:
            continue

        try:
            await asyncio.to_thread(add_my_thread, uid, t_tid, t_fid, t_subject,
                                     t_lastpost, t_lastposter, t_numreplies, t_closed,
                                     firstpost=t_firstpost)
        except Exception as _mt_err:
            log.warning("refresh uid=%s add_my_thread tid=%s: %s", uid, t_tid, _mt_err)

        stored_lastpost = int((_cursor_map.get(t_tid) or {}).get("last_checked") or 0)
        if t_lastpost <= stored_lastpost:
            continue

        stored_last_pid = str((_cursor_map.get(t_tid) or {}).get("last_pid") or "0")
        if stored_lastpost == 0 and stored_last_pid == "0":
            try:
                await asyncio.to_thread(update_thread_last_checked, uid, t_tid, "0", t_lastpost)
            except Exception:
                pass
            seed_tids_uid.add(t_tid)

        # Always inspect a changed owned thread. The owner or Stanley may be the
        # latest poster after another member replied, so lastposter alone cannot
        # prove that there are no unseen replies before it.
        needs_check.add(t_tid)
        titles_map[t_tid]     = t_subject
        numreplies_map[t_tid] = t_numreplies
        log.info("refresh uid=%s reply-check flagged tid=%s numreplies=%d", uid, t_tid, t_numreplies)

    if needs_check:
        _reply_check_queue.setdefault(uid, set()).update(needs_check)
        _reply_check_titles.setdefault(uid, {}).update(titles_map)
        _reply_check_numreplies.setdefault(uid, {}).update(numreplies_map)
        if seed_tids_uid:
            _reply_check_seed_tids.setdefault(uid, set()).update(seed_tids_uid)
        log.debug("refresh uid=%s flagged %d thread(s) for reply check", uid, len(needs_check))

        if active:
            try:
                from modules.posting import poll_reply_queues
                await asyncio.wait_for(poll_reply_queues(active_uids={uid}), timeout=30)
            except asyncio.TimeoutError:
                log.warning("refresh uid=%s inline reply poll timed out", uid)
            except Exception as _rpe:
                log.warning("refresh uid=%s inline reply poll failed: %s", uid, _rpe)


async def _section_profile(uid: str, data1) -> None:
    me = (data1 or {}).get("me", {})
    if not me:
        return

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
        log.warning("refresh uid=%s [profile cache] failed: %s", uid, e)

    try:
        groups: list[str] = []
        for field in ("usergroup", "displaygroup"):
            v = (me.get(field) or "").strip()
            if v:
                groups.append(v)
        for g in (me.get("additionalgroups") or "").split(","):
            g = g.strip()
            if g:
                groups.append(g)
        groups = list(dict.fromkeys(groups))
        if groups:
            current_user   = await asyncio.to_thread(db.get_user, uid)
            current_groups = (current_user.get("groups") or []) if current_user else []
            if sorted(groups) != sorted(current_groups):
                await asyncio.to_thread(db.update_user_groups, uid, groups)
                log.info("refresh uid=%s groups updated %s", uid, groups)
    except Exception as e:
        log.warning("refresh uid=%s [groups] failed: %s", uid, e)

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
        await asyncio.to_thread(db.set_last_pm_count, uid, max(0, unread))
    except Exception as e:
        log.warning("refresh uid=%s [PM] failed: %s", uid, e)
