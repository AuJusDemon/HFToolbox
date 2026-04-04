"""modules/autobump/router.py"""

import time
import asyncio
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel, field_validator
import db
from .autobump_db import (
    add_job, remove_job, get_jobs_for_user, set_job_enabled, get_log, init, _db
)

router = APIRouter(prefix="/api/autobump", tags=["autobump"])
init()

MIN_INTERVAL = 6
MAX_INTERVAL = 24


def _uid(request: Request) -> str:
    uid = request.session.get("uid")
    if not uid:
        raise HTTPException(401)
    return uid


def _run_sync(fn, *args):
    loop = asyncio.get_event_loop()
    return loop.run_in_executor(None, fn, *args)


class AddJobRequest(BaseModel):
    tid:        str
    interval_h: int

    @field_validator("interval_h")
    @classmethod
    def check_interval(cls, v):
        if v < MIN_INTERVAL or v > MAX_INTERVAL:
            raise ValueError(f"Interval must be {MIN_INTERVAL}-{MAX_INTERVAL} hours")
        return v


class ToggleRequest(BaseModel):
    enabled: bool


@router.get("/jobs")
async def list_jobs(request: Request):
    uid  = _uid(request)
    jobs = await asyncio.get_event_loop().run_in_executor(None, get_jobs_for_user, uid)
    now  = int(time.time())

    result = []
    for j in jobs:
        next_bump   = j.get("next_bump")
        last_bumped = j.get("last_bumped")
        result.append({
            "id":                 j["id"],
            "tid":                j["tid"],
            "fid":                j.get("fid"),
            "thread_title":       j.get("thread_title") or f"Thread {j['tid']}",
            "interval_h":         j["interval_h"],
            "enabled":            bool(j["enabled"]),
            "bump_count":         j["bump_count"],
            "last_bumped":        last_bumped,
            "next_bump":          next_bump,
            "seconds_until_bump": max(0, next_bump - now) if next_bump else None,
            "last_skip":          j.get("last_skip"),
            "lastpost_ts":        j.get("lastpost_ts"),
            "lastposter":         j.get("lastposter"),
        })
    return {"jobs": result}


@router.post("/jobs")
async def create_job(request: Request, body: AddJobRequest):
    uid   = _uid(request)
    token = db.get_token(uid)

    title           = None
    fid             = None
    lastpost        = None
    lastposter_name = None

    if token:
        try:
            from HFClient import HFClient
            client = HFClient(token)
            # Single read call — get everything we need
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
        smart_next = now                       # already stale — bump ASAP
    elif lastpost:
        smart_next = lastpost + interval_secs  # fresh — schedule from lastpost
    else:
        smart_next = now + interval_secs       # no data — full interval

    def _create():
        job = add_job(uid, body.tid, body.interval_h, next_bump_override=smart_next)
        with _db() as conn:
            conn.execute(
                """UPDATE bump_jobs SET thread_title=?, fid=?, lastpost_ts=?, lastposter=?
                   WHERE uid=? AND tid=?""",
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
    await asyncio.get_event_loop().run_in_executor(
        None, set_job_enabled, uid, tid, body.enabled
    )
    return {"ok": True}


@router.get("/log")
async def bump_log(request: Request):
    uid = _uid(request)
    log = await asyncio.get_event_loop().run_in_executor(None, get_log, uid, 30)
    return {"log": log}
