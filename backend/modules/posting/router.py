"""
modules/posting/router.py — API routes for thread posting module.

Endpoints:
  POST   /api/posting/thread          — queue a thread (immediate or scheduled)
  GET    /api/posting/queue           — pending/failed scheduled threads
  DELETE /api/posting/queue/{id}      — cancel a scheduled thread
  GET    /api/posting/sent            — recently sent threads
  GET    /api/posting/threads         — my tracked threads (reply queue source)
  GET    /api/posting/replies         — unread reply queue
  POST   /api/posting/replies/{id}/dismiss — manually dismiss a reply
  POST   /api/posting/reply           — post a reply to a thread
  GET    /api/posting/recents         — recently used forums
  GET    /api/posting/replies/count   — unread count (for nav badge)
"""

import asyncio
import time
import logging
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import db
from .posting_db import (
    init_posting_db,
    create_scheduled_thread,
    get_scheduled_threads,
    get_sent_threads,
    cancel_scheduled_thread,
    get_my_threads,
    get_reply_queue,
    get_unread_count,
    dismiss_reply,
    touch_recent,
    get_recents,
    add_my_thread,
    save_draft, update_draft, get_drafts, delete_draft,
    cancel_to_draft, update_fire_at,
)

router = APIRouter(prefix="/api/posting", tags=["posting"])
log = logging.getLogger("posting.router")

init_posting_db()


def _auth(request: Request):
    uid = request.session.get("uid")
    if not uid:
        return None, JSONResponse({"error": "unauthenticated"}, status_code=401)
    return uid, None


# ── Queue a thread ─────────────────────────────────────────────────────────────

@router.post("/thread")
async def queue_thread(request: Request):
    """
    Queue a thread for posting.

    Body:
      fid         str  — forum ID
      forum_name  str  — forum display name (for recents + UI)
      category_name str — category display name (for recents)
      subject     str  — thread title
      message     str  — BBCode body
      fire_at     int  — unix timestamp. Use 0 or omit for immediate.

    Nothing posts until fire_at <= now AND the scheduler fires.
    Immediate posts (fire_at=0) will fire on the next scheduler tick (≤5 min).
    """
    uid, err = _auth(request)
    if err:
        return err

    body = await request.json()
    fid          = str(body.get("fid") or "").strip()
    forum_name   = str(body.get("forum_name") or "").strip()
    category_name = str(body.get("category_name") or "").strip()
    subject      = str(body.get("subject") or "").strip()
    message      = str(body.get("message") or "").strip()
    fire_at_raw  = body.get("fire_at", 0)

    if not fid:
        return JSONResponse({"error": "fid required"}, status_code=400)
    if not subject:
        return JSONResponse({"error": "subject required"}, status_code=400)
    if not message:
        return JSONResponse({"error": "message required"}, status_code=400)

    # Category FIDs that cannot be posted to
    CATEGORY_FIDS = {
        "1","7","45","88","105","120","141","151","156","241",
        "259","444","445","446","447","448","449","450","451","452","453","460"
    }
    if fid in CATEGORY_FIDS:
        return JSONResponse({"error": "Cannot post to a category — select a forum"}, status_code=400)

    try:
        fire_at = int(fire_at_raw) if fire_at_raw else 0
    except (TypeError, ValueError):
        fire_at = 0

    if fire_at <= 0:
        fire_at = int(time.time())

    auto_bump       = bool(body.get("auto_bump", False))
    bump_interval_h = int(body.get("bump_interval_h", 12))
    if bump_interval_h < 6:  bump_interval_h = 6
    if bump_interval_h > 24: bump_interval_h = 24

    row_id = await asyncio.to_thread(
        create_scheduled_thread,
        uid, fid, forum_name, subject, message, fire_at, auto_bump, bump_interval_h
    )

    # Update recents
    await asyncio.to_thread(touch_recent, uid, fid, forum_name, category_name)

    is_scheduled = fire_at > int(time.time()) + 60
    return {
        "ok":        True,
        "id":        row_id,
        "scheduled": is_scheduled,
        "fire_at":   fire_at,
        "message":   "Thread scheduled" if is_scheduled else "Thread queued — will post within 5 minutes",
    }


# ── Scheduled queue ────────────────────────────────────────────────────────────

@router.get("/queue")
async def get_queue(request: Request):
    uid, err = _auth(request)
    if err:
        return err
    threads = await asyncio.to_thread(get_scheduled_threads, uid)
    return {"queue": threads}


@router.delete("/queue/{row_id}")
async def cancel_queue_item(request: Request, row_id: int):
    uid, err = _auth(request)
    if err:
        return err
    ok = await asyncio.to_thread(cancel_scheduled_thread, row_id, uid)
    if not ok:
        return JSONResponse({"error": "Not found or already sent"}, status_code=404)
    return {"ok": True}


# ── Sent threads ───────────────────────────────────────────────────────────────

@router.get("/sent")
async def get_sent(request: Request):
    uid, err = _auth(request)
    if err:
        return err
    threads = await asyncio.to_thread(get_sent_threads, uid)
    return {"sent": threads}


# ── My tracked threads ─────────────────────────────────────────────────────────

@router.get("/threads")
async def get_threads(request: Request):
    uid, err = _auth(request)
    if err:
        return err
    threads = await asyncio.to_thread(get_my_threads, uid)
    return {"threads": threads}


@router.get("/hf-threads")
async def get_hf_threads(request: Request, page: int = 1):
    """Fetch user's actual threads from HF API, paginated 30/page."""
    uid, err = _auth(request)
    if err:
        return err
    token = await asyncio.to_thread(db.get_token, uid)
    if not token:
        return JSONResponse({"error": "no token"}, status_code=401)
    try:
        from HFClient import HFClient
        client = HFClient(token)
        data = await asyncio.wait_for(client.read({
            "threads": {
                "_uid":    [int(uid)],
                "_page":   page,
                "_perpage": 30,
                "tid":     True,
                "subject": True,
                "fid":     True,
                "dateline": True,
                "lastpost": True,
                "numreplies": True,
            }
        }), timeout=20)
        if not data:
            return JSONResponse({"error": "no response"}, status_code=503)
        rows = data.get("threads", [])
        if isinstance(rows, dict):
            rows = [rows]
        return {"threads": rows or [], "page": page}
    except asyncio.TimeoutError:
        return JSONResponse({"error": "HF API timeout"}, status_code=503)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── Reply queue ────────────────────────────────────────────────────────────────

@router.get("/replies/count")
async def reply_count(request: Request):
    uid, err = _auth(request)
    if err:
        return err
    count = await asyncio.to_thread(get_unread_count, uid)
    return {"count": count}


@router.get("/replies")
async def get_replies(request: Request):
    uid, err = _auth(request)
    if err:
        return err
    replies = await asyncio.to_thread(get_reply_queue, uid, "unread")
    return {"replies": replies}


@router.post("/replies/{reply_id}/dismiss")
async def dismiss(request: Request, reply_id: int):
    uid, err = _auth(request)
    if err:
        return err
    ok = await asyncio.to_thread(dismiss_reply, reply_id, uid)
    if not ok:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return {"ok": True}


# ── Post a reply ───────────────────────────────────────────────────────────────

@router.post("/reply")
async def post_reply(request: Request):
    """
    Post a reply to one of the user's tracked threads.

    Body:
      tid      str — thread ID
      message  str — BBCode message (should include [quote] of the post being replied to)
    """
    uid, err = _auth(request)
    if err:
        return err

    body    = await request.json()
    tid     = str(body.get("tid") or "").strip()
    message = str(body.get("message") or "").strip()

    if not tid:
        return JSONResponse({"error": "tid required"}, status_code=400)
    if not message:
        return JSONResponse({"error": "message required"}, status_code=400)

    token = await asyncio.to_thread(db.get_token, uid)
    if not token:
        return JSONResponse({"error": "No token"}, status_code=401)

    from HFClient import HFClient
    client = HFClient(token)

    try:
        result = await client.write({
            "posts": {
                "_tid":     int(tid),
                "_message": message,
            }
        })
        log.info("Reply write uid=%s tid=%s raw_result=%s", uid, tid, result)

        if not result:
            return JSONResponse({"error": "API returned empty response"}, status_code=502)

        posts_result = result.get("posts") or {}
        if isinstance(posts_result, list):
            posts_result = posts_result[0] if posts_result else {}
        pid = str(posts_result.get("pid") or "")

        if not pid:
            log.error("Reply write uid=%s tid=%s: no pid in result — full result: %s", uid, tid, result)
            return JSONResponse({"error": f"HF returned no post ID. Raw response: {result}"}, status_code=502)

        return {"ok": True, "pid": pid}

    except Exception as e:
        log.exception("Reply failed uid=%s tid=%s: %s", uid, tid, e)
        return JSONResponse({"error": str(e)}, status_code=500)


# ── Recents ────────────────────────────────────────────────────────────────────

@router.patch("/queue/{row_id}/reschedule")
async def reschedule_queue_item(request: Request, row_id: int):
    """Update fire_at for a pending scheduled thread."""
    uid, err = _auth(request)
    if err:
        return err
    body    = await request.json()
    fire_at = int(body.get("fire_at") or 0)
    if fire_at <= 0:
        return JSONResponse({"error": "invalid fire_at"}, status_code=400)
    ok = await asyncio.to_thread(update_fire_at, row_id, uid, fire_at)
    if not ok:
        return JSONResponse({"error": "not found or already sent"}, status_code=404)
    return {"ok": True}


@router.delete("/queue/{row_id}/to-draft")
async def cancel_to_draft_route(request: Request, row_id: int):
    """Cancel a scheduled thread and save it as a draft."""
    uid, err = _auth(request)
    if err:
        return err
    row = await asyncio.to_thread(cancel_to_draft, row_id, uid)
    if not row:
        return JSONResponse({"error": "not found or already sent"}, status_code=404)
    draft_id = await asyncio.to_thread(
        save_draft, uid, row["fid"], row["forum_name"], row["subject"], row["message"]
    )
    return {"ok": True, "draft_id": draft_id}


@router.get("/drafts")
async def list_drafts(request: Request):
    uid, err = _auth(request)
    if err:
        return err
    drafts = await asyncio.to_thread(get_drafts, uid)
    return {"drafts": drafts}


@router.post("/drafts")
async def create_draft(request: Request):
    uid, err = _auth(request)
    if err:
        return err
    body = await request.json()
    draft_id = await asyncio.to_thread(
        save_draft, uid,
        str(body.get("fid") or ""),
        str(body.get("forum_name") or ""),
        str(body.get("subject") or ""),
        str(body.get("message") or ""),
    )
    return {"ok": True, "draft_id": draft_id}


@router.put("/drafts/{draft_id}")
async def edit_draft(request: Request, draft_id: int):
    uid, err = _auth(request)
    if err:
        return err
    body = await request.json()
    ok = await asyncio.to_thread(
        update_draft, draft_id, uid,
        str(body.get("fid") or ""),
        str(body.get("forum_name") or ""),
        str(body.get("subject") or ""),
        str(body.get("message") or ""),
    )
    return {"ok": ok}


@router.delete("/drafts/{draft_id}")
async def remove_draft(request: Request, draft_id: int):
    uid, err = _auth(request)
    if err:
        return err
    ok = await asyncio.to_thread(delete_draft, draft_id, uid)
    return {"ok": ok}


@router.get("/recents")
async def get_recents_route(request: Request):
    uid, err = _auth(request)
    if err:
        return err
    recents = await asyncio.to_thread(get_recents, uid)
    return {"recents": recents}


# ── Image host proxy ───────────────────────────────────────────────────────────
@router.post("/imagehost/upload")
async def imagehost_upload(request: Request):
    """
    Proxy the encrypted blob to uploadimages.org.
    The decryption key lives only in the URL fragment — never transmitted here.
    We just forward the ciphertext + metadata and pass back their JSON.
    """
    _auth(request)
    import httpx as _httpx

    form = await request.form()
    file_field = form.get("file")
    if not file_field:
        return JSONResponse({"error": "no file"}, status_code=400)

    file_bytes = await file_field.read()
    # Forward all non-file fields as form data
    fwd_data = {k: v for k, v in form.items() if k != "file"}

    try:
        async with _httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://uploadimages.org/api/upload",
                files={"file": (file_field.filename or "upload.bin", file_bytes, "application/octet-stream")},
                data=fwd_data,
            )
        return JSONResponse(resp.json(), status_code=resp.status_code)
    except Exception as exc:
        return JSONResponse({"error": str(exc)}, status_code=502)
