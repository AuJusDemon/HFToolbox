"""modules/autobump/router.py"""

import time
import asyncio
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, model_validator
from typing import Optional
import db
from .autobump_db import (
    add_job, remove_job, get_jobs_for_user, set_job_enabled,
    get_log, init, expire_jobs, get_settings, set_settings,
    get_job_stats, _db
)
try:
    from HFClient import AuthExpired as _AuthExpired
except ImportError:
    class _AuthExpired(Exception):
        pass

router = APIRouter(prefix="/api/autobump", tags=["autobump"])
init()

VALID_MODES  = {"timer", "page1"}
MIN_INTERVAL = 6
MAX_INTERVAL = 168
STANLEY_FEE  = 50

PAGE1_RECHECK_SECS = 1800


def _uid(request: Request) -> str:
    uid = request.session.get("uid")
    if not uid:
        raise HTTPException(401)
    return uid


class AddJobRequest(BaseModel):
    tid:        str
    interval_h: int
    mode:       str = "timer"
    bump_until: Optional[int] = None

    @model_validator(mode="after")
    def check_fields(self):
        if self.mode not in VALID_MODES:
            raise ValueError(f"mode must be one of: {', '.join(VALID_MODES)}")
        if not (MIN_INTERVAL <= self.interval_h <= MAX_INTERVAL):
            raise ValueError(f"Interval must be {MIN_INTERVAL}-{MAX_INTERVAL} hours")
        return self


class ToggleRequest(BaseModel):
    enabled: bool


class SettingsRequest(BaseModel):
    weekly_budget: int


# ── Settings ──────────────────────────────────────────────────────────────────

@router.get("/settings")
async def get_bumper_settings(request: Request):
    uid = _uid(request)
    s = await asyncio.get_event_loop().run_in_executor(None, get_settings, uid)
    weekly_budget = int(s.get("weekly_budget") or 0)
    from .autobump_db import get_weekly_bump_count
    bump_count = await asyncio.get_event_loop().run_in_executor(None, get_weekly_bump_count, uid)
    return {
        "weekly_budget":   weekly_budget,
        "bytes_this_week": bump_count * STANLEY_FEE,
        "bumps_this_week": bump_count,
    }


@router.put("/settings")
async def put_bumper_settings(request: Request, body: SettingsRequest):
    uid = _uid(request)
    if body.weekly_budget < 0:
        raise HTTPException(400, "weekly_budget must be >= 0")
    await asyncio.get_event_loop().run_in_executor(None, set_settings, uid, body.weekly_budget)
    return {"ok": True}


# ── Jobs ──────────────────────────────────────────────────────────────────────

@router.get("/jobs")
async def list_jobs(request: Request):
    uid = _uid(request)
    await asyncio.get_event_loop().run_in_executor(None, expire_jobs)
    jobs = await asyncio.get_event_loop().run_in_executor(None, get_jobs_for_user, uid)
    now  = int(time.time())
    result = []
    for j in jobs:
        next_bump  = j.get("next_bump")
        bump_until = j.get("bump_until")
        result.append({
            "id":                 j["id"],
            "tid":                j["tid"],
            "fid":                j.get("fid"),
            "thread_title":       j.get("thread_title") or f"Thread {j['tid']}",
            "mode":               j.get("mode") or "timer",
            "interval_h":         j["interval_h"],
            "enabled":            bool(j["enabled"]),
            "bump_count":         j["bump_count"],
            "last_bumped":        j.get("last_bumped"),
            "next_bump":          next_bump,
            "seconds_until_bump": max(0, next_bump - now) if next_bump else None,
            "last_skip":          j.get("last_skip"),
            "lastpost_ts":        j.get("lastpost_ts"),
            "lastposter":         j.get("lastposter"),
            "bump_until":         bump_until,
            "expired":            bool(bump_until and bump_until <= now),
        })
    return {"jobs": result}


@router.post("/jobs")
async def create_job(request: Request, body: AddJobRequest):
    uid   = _uid(request)
    token = db.get_token(uid)
    title = fid = lastpost = lastposter_name = None

    if token:
        try:
            from HFClient import HFClient
            client = HFClient(token)
            data = await asyncio.wait_for(client.read({
                "threads": {
                    "_tid": [body.tid], "tid": True, "fid": True,
                    "subject": True, "lastpost": True, "lastposter": True,
                }
            }), timeout=12)
            t = data.get("threads") if data else None
            if t:
                if isinstance(t, dict): t = [t]
                title           = str(t[0].get("subject")    or "")
                fid             = str(t[0].get("fid")        or "")
                lastpost        = int(t[0].get("lastpost")   or 0)
                lastposter_name = str(t[0].get("lastposter") or "")
        except _AuthExpired:
            request.session.clear()
            await asyncio.to_thread(db.clear_token, uid)
            return JSONResponse({"error": "hf_token_revoked"}, status_code=401)
        except Exception:
            pass

    now           = int(time.time())
    interval_secs = body.interval_h * 3600

    if body.mode == "page1":
        smart_next = now
    elif lastpost and (now - lastpost) >= interval_secs:
        smart_next = now
    elif lastpost:
        smart_next = lastpost + interval_secs
    else:
        smart_next = now + interval_secs

    def _create():
        job = add_job(uid, body.tid, body.interval_h,
                      mode=body.mode,
                      next_bump_override=smart_next,
                      bump_until=body.bump_until)
        with _db() as conn:
            conn.execute(
                """UPDATE bump_jobs SET thread_title=%s, fid=%s, lastpost_ts=%s, lastposter=%s
                   WHERE uid=%s AND tid=%s""",
                (title, fid, lastpost or None, lastposter_name or None, uid, str(body.tid))
            )
        return job

    job = await asyncio.get_event_loop().run_in_executor(None, _create)
    return {"ok": True, "job": job}


@router.delete("/jobs/{tid}")
async def delete_job(request: Request, tid: str):
    uid = _uid(request)
    await asyncio.get_event_loop().run_in_executor(None, remove_job, uid, tid)
    return {"ok": True}


@router.patch("/jobs/{tid}")
async def toggle_job(request: Request, tid: str, body: ToggleRequest):
    uid = _uid(request)
    await asyncio.get_event_loop().run_in_executor(None, set_job_enabled, uid, tid, body.enabled)
    return {"ok": True}


# ── Stats ─────────────────────────────────────────────────────────────────────

@router.get("/jobs/{tid}/stats")
async def job_stats(request: Request, tid: str):
    uid  = _uid(request)
    now  = int(time.time())

    stats = await asyncio.get_event_loop().run_in_executor(None, get_job_stats, uid, tid)

    # All contracts for this TID, oldest first — so we can slot them into bump periods
    contracts = []
    try:
        def _get_contracts():
            from db_connection import _db as _cdb
            with _cdb() as conn:
                rows = conn.execute(
                    """SELECT cid, status_n, type_n, iproduct, oproduct,
                              iprice, icurrency, oprice, ocurrency, dateline
                       FROM contracts_history
                       WHERE uid=%s AND tid=%s
                       ORDER BY dateline ASC""",
                    (uid, str(tid))
                ).fetchall()
                return [dict(r) for r in rows]
        contracts = await asyncio.get_event_loop().run_in_executor(None, _get_contracts)
    except Exception:
        contracts = []

    # Build bump periods — each period = from this bump until the next bump
    # bump_history from get_job_stats is ASC (oldest first), last 20
    bumps      = stats["bump_history"]   # oldest → newest
    reply_gains = stats["reply_gains"]   # reply_gains[i] = bumps[i+1].nr - bumps[i].nr

    bump_periods = []
    for i, bump in enumerate(bumps):
        next_ts = bumps[i + 1]["ts"] if i + 1 < len(bumps) else None
        end_ts  = next_ts if next_ts else now  # open period ends "now"

        # Contracts created between this bump and the next
        period_contracts = [
            c for c in contracts
            if c["dateline"] >= bump["ts"] and c["dateline"] < end_ts
        ]

        # Reply gain: replies added between this bump and the next
        # reply_gains[i] exists only when both bumps[i] and bumps[i+1] have numreplies
        reply_gain = reply_gains[i] if i < len(reply_gains) else None

        bump_periods.append({
            "bump_num":    i + 1,           # 1-indexed, oldest = 1
            "ts":          bump["ts"],
            "next_ts":     next_ts,         # None = still active / most recent
            "duration_s":  end_ts - bump["ts"],
            "is_current":  next_ts is None,
            "reply_gain":  reply_gain,
            "contracts":   period_contracts,
        })

    # Reverse so newest is first in the response
    bump_periods = list(reversed(bump_periods))

    return {
        "total_bumps":     stats["total_bumps"],
        "total_skips":     stats["total_skips"],
        "bytes_spent":     stats["total_bumps"] * STANLEY_FEE,
        "total_contracts": len(contracts),
        "avg_reply_gain":  stats["avg_reply_gain"],
        "has_reply_data":  any(b["numreplies"] is not None for b in bumps),
        "job_info":        stats["job_info"],
        "bump_periods":    bump_periods,   # newest first, max 20
    }


# ── Log ───────────────────────────────────────────────────────────────────────

@router.get("/log")
async def bump_log(request: Request):
    uid = _uid(request)
    log = await asyncio.get_event_loop().run_in_executor(None, get_log, uid, 30)
    return {"log": log}
