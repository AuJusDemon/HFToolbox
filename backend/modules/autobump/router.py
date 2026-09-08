"""modules/autobump/router.py"""

import time
import asyncio
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Optional
import db
from .autobump_db import (
    add_job, remove_job, get_jobs_for_user, set_job_enabled,
    get_log, init, expire_jobs, get_settings, set_settings,
    get_job_stats, get_job, update_job_schedule, get_weekly_spend, _db
)
from .fees import fee_breakdown
from .performance import build_performance
from .schedule import (
    VALID_MODES, calculate_updated_next, validate_allowed_windows,
    validate_calendar_slots, validate_end_condition, validate_interval,
    validate_timezone, next_calendar_slot, end_of_local_date,
)
try:
    from HFClient import AuthExpired as _AuthExpired
except ImportError:
    class _AuthExpired(Exception):
        pass

router = APIRouter(prefix="/api/autobump", tags=["autobump"])
init()

def _fees_for_user(uid: str) -> dict[str, int | str]:
    user = db.get_user(uid) or {}
    return fee_breakdown(uid, user.get("groups"))


def _uid(request: Request) -> str:
    uid = request.session.get("uid")
    if not uid:
        raise HTTPException(401)
    return uid


class AddJobRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tid:        str
    interval_h: int
    mode:       str = "timer"
    timezone: str = "UTC"
    allowed_windows: list[dict] = Field(default_factory=list)
    calendar_slots: list[dict] = Field(default_factory=list)
    end_mode: str = "unlimited"
    end_date: Optional[str] = None
    end_at: Optional[int] = None
    end_days: Optional[int] = None
    end_limit: Optional[int] = None
    bump_until: Optional[int] = None

    @model_validator(mode="after")
    def check_fields(self):
        if self.bump_until and self.end_mode == "unlimited":
            self.end_mode, self.end_at = "date", self.bump_until
        if self.bump_until and self.end_at and self.bump_until != self.end_at:
            raise ValueError("Conflicting end dates")
        if self.mode not in VALID_MODES:
            raise ValueError(f"mode must be one of: {', '.join(VALID_MODES)}")
        validate_interval(self.interval_h)
        self.timezone = validate_timezone(self.timezone)
        self.allowed_windows = validate_allowed_windows(self.allowed_windows)
        self.calendar_slots = validate_calendar_slots(self.calendar_slots)
        if self.mode == "calendar" and not self.calendar_slots:
            raise ValueError("Calendar Scheduling requires at least one weekly slot")
        if self.mode == "calendar" and self.allowed_windows:
            next_calendar_slot(int(time.time()), self.timezone, self.calendar_slots, self.allowed_windows)
        if self.end_date:
            if self.end_at or self.bump_until:
                raise ValueError("Conflicting end dates")
            self.end_at = end_of_local_date(self.end_date, self.timezone)
        self.end_mode, self.end_at, self.end_limit = validate_end_condition(
            self.end_mode, end_at=self.end_at, end_days=self.end_days,
            end_limit=self.end_limit,
        )
        self.bump_until = self.end_at
        return self


class ToggleRequest(BaseModel):
    enabled: bool


class UpdateScheduleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: str
    interval_h: int
    timezone: str = "UTC"
    allowed_windows: list[dict] = Field(default_factory=list)
    calendar_slots: list[dict] = Field(default_factory=list)
    end_mode: str = "unlimited"
    end_date: Optional[str] = None
    end_at: Optional[int] = None
    end_days: Optional[int] = None
    end_limit: Optional[int] = None
    bump_until: Optional[int] = None
    enabled: bool

    @model_validator(mode="after")
    def check_fields(self):
        if self.bump_until and self.end_mode == "unlimited":
            self.end_mode, self.end_at = "date", self.bump_until
        if self.bump_until and self.end_at and self.bump_until != self.end_at:
            raise ValueError("Conflicting end dates")
        if self.mode not in VALID_MODES:
            raise ValueError(f"mode must be one of: {', '.join(VALID_MODES)}")
        validate_interval(self.interval_h)
        self.timezone = validate_timezone(self.timezone)
        self.allowed_windows = validate_allowed_windows(self.allowed_windows)
        self.calendar_slots = validate_calendar_slots(self.calendar_slots)
        if self.mode == "calendar" and not self.calendar_slots:
            raise ValueError("Calendar Scheduling requires at least one weekly slot")
        if self.mode == "calendar" and self.allowed_windows:
            next_calendar_slot(int(time.time()), self.timezone, self.calendar_slots, self.allowed_windows)
        if self.end_date:
            if self.end_at or self.bump_until:
                raise ValueError("Conflicting end dates")
            self.end_at = end_of_local_date(self.end_date, self.timezone)
        self.end_mode, self.end_at, self.end_limit = validate_end_condition(
            self.end_mode, end_at=self.end_at, end_days=self.end_days,
            end_limit=self.end_limit,
        )
        self.bump_until = self.end_at
        return self


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
    fees = await asyncio.get_event_loop().run_in_executor(None, _fees_for_user, uid)
    bytes_this_week = await asyncio.to_thread(get_weekly_spend, uid, fees["total_cost"])
    return {
        "weekly_budget":   weekly_budget,
        "bytes_this_week": bytes_this_week,
        "bumps_this_week": bump_count,
        "remaining_budget": max(0, weekly_budget - bytes_this_week) if weekly_budget else None,
        **fees,
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
    fees = await asyncio.to_thread(_fees_for_user, uid)
    now  = int(time.time())
    result = []
    for j in jobs:
        next_bump  = j.get("next_bump")
        bump_until = j.get("bump_until")
        end_mode = j.get("end_mode") or "unlimited"
        end_limit = int(j.get("end_limit") or 0)
        end_reached = (
            end_mode in ("date", "duration") and bool(bump_until and bump_until <= now)
            or end_mode == "successes" and end_limit > 0 and int(j.get("bump_count") or 0) >= end_limit
            or end_mode == "bytes" and end_limit > 0
            and int(j.get("spent_bytes") or 0) + int(fees["total_cost"]) > end_limit
        )
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
            "timezone":           j.get("timezone") or "UTC",
            "allowed_windows":    j.get("allowed_windows") or [],
            "calendar_slots":     j.get("calendar_slots") or [],
            "end_mode":           end_mode,
            "end_limit":          j.get("end_limit"),
            "spent_bytes":        int(j.get("spent_bytes") or 0),
            "retired_reason":     j.get("retired_reason"),
            "requires_schedule_update": (j.get("mode") == "page1"),
            "bump_until":         bump_until,
            "expired":            end_reached,
            "latest_action":      j.get("latest_action"),
            "latest_reason":      j.get("latest_reason"),
            "latest_result_at":   j.get("latest_result_at"),
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
    smart_next = calculate_updated_next(
        {"lastpost_ts": lastpost}, body.mode, body.interval_h, now,
        body.timezone, body.allowed_windows, body.calendar_slots,
    )

    def _create():
        job = add_job(uid, body.tid, body.interval_h,
                      mode=body.mode,
                      next_bump_override=smart_next,
                      bump_until=body.end_at,
                      timezone=body.timezone,
                      allowed_windows=body.allowed_windows,
                      calendar_slots=body.calendar_slots,
                      end_mode=body.end_mode,
                      end_limit=body.end_limit)
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
    removed = await asyncio.get_event_loop().run_in_executor(None, remove_job, uid, tid)
    if not removed:
        raise HTTPException(404, "Bump job not found")
    return {"ok": True}


@router.patch("/jobs/{tid}")
async def toggle_job(request: Request, tid: str, body: ToggleRequest):
    uid = _uid(request)
    current = await asyncio.to_thread(get_job, uid, tid)
    if not current:
        raise HTTPException(404, "Bump job not found")
    if body.enabled and current.get("mode") == "page1":
        raise HTTPException(409, "Page 1 Watch was retired. Choose a new schedule before resuming.")
    updated = await asyncio.get_event_loop().run_in_executor(None, set_job_enabled, uid, tid, body.enabled)
    if not updated:
        raise HTTPException(404, "Bump job not found")
    return {"ok": True}


@router.put("/jobs/{tid}/schedule")
async def put_job_schedule(request: Request, tid: str, body: UpdateScheduleRequest):
    uid = _uid(request)
    current = await asyncio.to_thread(get_job, uid, tid)
    if not current:
        raise HTTPException(404, "Bump job not found")
    next_bump = calculate_updated_next(
        current, body.mode, body.interval_h, timezone_name=body.timezone,
        allowed_windows=body.allowed_windows, calendar_slots=body.calendar_slots,
    )
    changes = []
    labels = {"timer": "Activity Interval", "page1": "Retired Page 1 Watch", "calendar": "Calendar Scheduling"}
    if current.get("mode") != body.mode:
        changes.append(f"mode {labels.get(current.get('mode'), current.get('mode'))} -> {labels[body.mode]}")
    if int(current.get("interval_h") or 0) != body.interval_h:
        changes.append(f"interval {current.get('interval_h')}h -> {body.interval_h}h")
    if current.get("end_mode") != body.end_mode or current.get("bump_until") != body.end_at or current.get("end_limit") != body.end_limit:
        changes.append("end condition changed")
    if current.get("timezone") != body.timezone or current.get("allowed_windows") != body.allowed_windows:
        changes.append("allowed hours changed")
    if current.get("calendar_slots") != body.calendar_slots:
        changes.append("calendar slots changed")
    if bool(current.get("enabled")) != body.enabled:
        changes.append("resumed" if body.enabled else "paused")
    updated = await asyncio.to_thread(
        update_job_schedule, uid, tid, mode=body.mode, interval_h=body.interval_h,
        bump_until=body.end_at, enabled=body.enabled, timezone=body.timezone,
        allowed_windows=body.allowed_windows, calendar_slots=body.calendar_slots,
        end_mode=body.end_mode, end_limit=body.end_limit, next_bump=next_bump,
        audit_reason="; ".join(changes) or "schedule saved without changes",
    )
    return {"ok": True, "job": updated, "next_bump": next_bump, "changes": changes}


@router.get("/jobs/{tid}/performance")
async def job_performance(request: Request, tid: str, range: str = "30d", page: int = 1,
                          page_size: int = 5):
    uid = _uid(request)
    fees = await asyncio.to_thread(_fees_for_user, uid)
    try:
        result = await asyncio.to_thread(
            build_performance, uid, tid, range, page, page_size, fees
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    if not result:
        raise HTTPException(404, "Thread performance not found")
    return result


# ── Stats ─────────────────────────────────────────────────────────────────────

@router.get("/jobs/{tid}/stats")
async def job_stats(request: Request, tid: str):
    uid  = _uid(request)
    now  = int(time.time())

    stats = await asyncio.get_event_loop().run_in_executor(None, get_job_stats, uid, tid)
    fees = await asyncio.get_event_loop().run_in_executor(None, _fees_for_user, uid)

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
        "bytes_spent":     stats["total_bumps"] * fees["total_cost"],
        "total_contracts": len(contracts),
        "avg_reply_gain":  stats["avg_reply_gain"],
        "has_reply_data":  any(b["numreplies"] is not None for b in bumps),
        "job_info":        stats["job_info"],
        "bump_periods":    bump_periods,   # newest first, max 20
        **fees,
    }


# ── Log ───────────────────────────────────────────────────────────────────────

@router.get("/log")
async def bump_log(request: Request):
    uid = _uid(request)
    log = await asyncio.get_event_loop().run_in_executor(None, get_log, uid, 30)
    return {"log": log}
