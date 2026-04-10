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
    get_job_stats, get_weekly_bump_count, _db,
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
    s = await asyncio.to_thread(get_settings, uid)
    weekly_budget = int(s.get("weekly_budget") or 0)
    bump_count = await asyncio.to_thread(get_weekly_bump_count, uid)
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
    await asyncio.to_thread(set_settings, uid, body.weekly_budget)
    return {"ok": True}


# ── Jobs ──────────────────────────────────────────────────────────────────────

@router.get("/jobs")
async def list_jobs(request: Request):
    uid = _uid(request)
    await asyncio.to_thread(expire_jobs)
    jobs = await asyncio.to_thread(get_jobs_for_user, uid)
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
            "interval_h":         j["interval_h"],
            "mode":               j.get("mode") or "timer",
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
    token = await asyncio.to_thread(db.get_token, uid)

    title           = None
    fid             = None
    lastpost        = None
    lastposter_name = None

    if token:
        try:
            from HFClient import HFClient
            client = HFClient(token)
            data = await client.read({
                "threads": {
                    "_tid":       [body.tid],
                    "tid":        True,
                    "fid":        True,
                    "subject":    True,
                    "lastpost":   True,
                    "lastposter": True,
                }
            })
            t = data.get("threads") if data else None
            if t:
                if isinstance(t, dict): t = [t]
                title           = str(t[0].get("subject")    or "")
                fid             = str(t[0].get("fid")        or "")
                lastpost        = int(t[0].get("lastpost")   or 0)
                lastposter_name = str(t[0].get("lastposter") or "")
        except Exception:
            pass

    now           = int(time.time())
    interval_secs = body.interval_h * 3600

    if lastpost and (now - lastpost) >= interval_secs:
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
                """UPDATE bump_jobs SET thread_title=?, fid=?, lastpost_ts=?, lastposter=?
                   WHERE uid=? AND tid=?""",
                (title, fid, lastpost or None, lastposter_name or None, uid, str(body.tid))
            )
        return job

    job = await asyncio.to_thread(_create)
    return {"ok": True, "job": job}


@router.delete("/jobs/{tid}")
async def delete_job(request: Request, tid: str):
    uid = _uid(request)
    await asyncio.to_thread(remove_job, uid, tid)
    return {"ok": True}


@router.patch("/jobs/{tid}")
async def toggle_job(request: Request, tid: str, body: ToggleRequest):
    uid = _uid(request)
    await asyncio.to_thread(set_job_enabled, uid, tid, body.enabled)
    return {"ok": True}


@router.get("/jobs/{tid}/stats")
async def job_stats(request: Request, tid: str):
    uid  = _uid(request)
    now  = int(time.time())

    stats = await asyncio.to_thread(get_job_stats, uid, tid)

    # Slot contracts from contracts_history into bump periods if available
    contracts = []
    try:
        contracts = await asyncio.to_thread(_get_contracts_for_thread, uid, tid)
    except Exception:
        contracts = []

    bumps       = stats["bump_history"]
    reply_gains = stats["reply_gains"]

    bump_periods = []
    for i, bump in enumerate(bumps):
        next_ts = bumps[i + 1]["ts"] if i + 1 < len(bumps) else None
        end_ts  = next_ts if next_ts else now

        period_contracts = [
            c for c in contracts
            if c["dateline"] >= bump["ts"] and c["dateline"] < end_ts
        ]
        reply_gain = reply_gains[i] if i < len(reply_gains) else None

        bump_periods.append({
            "bump_num":   i + 1,
            "ts":         bump["ts"],
            "next_ts":    next_ts,
            "duration_s": end_ts - bump["ts"],
            "is_current": next_ts is None,
            "reply_gain": reply_gain,
            "contracts":  period_contracts,
        })

    bump_periods = list(reversed(bump_periods))

    return {
        "total_bumps":     stats["total_bumps"],
        "total_skips":     stats["total_skips"],
        "bytes_spent":     stats["total_bumps"] * STANLEY_FEE,
        "total_contracts": len(contracts),
        "avg_reply_gain":  stats["avg_reply_gain"],
        "has_reply_data":  any(b["numreplies"] is not None for b in bumps),
        "job_info":        stats["job_info"],
        "bump_periods":    bump_periods,
    }


def _get_contracts_for_thread(uid: str, tid: str) -> list[dict]:
    """Pull contracts linked to this thread from local DB. Zero API calls."""
    import sqlite3
    from pathlib import Path
    db_path = Path("data/hf_dash.db")
    conn = sqlite3.connect(str(db_path), check_same_thread=False, timeout=5)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(
            """SELECT cid, status_n, type_n, iproduct, oproduct,
                      iprice, icurrency, oprice, ocurrency, dateline
               FROM contracts_history
               WHERE uid=? AND tid=?
               ORDER BY dateline ASC""",
            (uid, str(tid))
        ).fetchall()
        return [dict(r) for r in rows]
    except Exception:
        return []
    finally:
        conn.close()


# ── Log ───────────────────────────────────────────────────────────────────────

@router.get("/log")
async def bump_log(request: Request):
    uid = _uid(request)
    log = await asyncio.to_thread(get_log, uid, 30)
    return {"log": log}
