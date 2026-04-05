"""
modules/posting/router.py — API routes for thread posting module.

Endpoints (existing):
  POST   /api/posting/thread                      — queue / schedule a thread
  GET    /api/posting/queue                        — pending scheduled threads
  DELETE /api/posting/queue/{id}                   — cancel
  PATCH  /api/posting/queue/{id}/reschedule        — change fire_at
  DELETE /api/posting/queue/{id}/to-draft          — cancel → save as draft
  GET    /api/posting/sent                         — recently sent threads
  GET    /api/posting/hf-threads                  — live threads from HF API
  GET    /api/posting/replies/count               — unread badge count
  GET    /api/posting/replies                     — unread reply queue
  POST   /api/posting/replies/{id}/dismiss        — dismiss a reply
  POST   /api/posting/reply                       — post a reply to a thread
  GET    /api/posting/recents                     — recently used forums
  POST   /api/posting/imagehost/upload            — proxy to uploadimages.org

Endpoints (collaborative drafts — specific routes before parameterised ones):
  GET    /api/posting/drafts/shared               — drafts shared with me
  GET    /api/posting/drafts                      — my drafts (owner)
  POST   /api/posting/drafts                      — create draft
  GET    /api/posting/drafts/{id}                 — single draft (owner or collaborator)
  PUT    /api/posting/drafts/{id}                 — versioned save (conflict → 409)
  DELETE /api/posting/drafts/{id}                 — delete (owner only)
  GET    /api/posting/drafts/{id}/version         — lightweight version poll
  GET    /api/posting/drafts/{id}/log             — edit history
  POST   /api/posting/drafts/{id}/rollback/{lid}  — rollback to log entry (owner only)
  GET    /api/posting/drafts/{id}/collaborators   — list collaborators
  POST   /api/posting/drafts/{id}/collaborators   — add collaborator (owner only)
  DELETE /api/posting/drafts/{id}/collaborators/{cuid} — remove (owner only)
  POST   /api/posting/drafts/{id}/presence        — heartbeat (owner or collaborator)
  DELETE /api/posting/drafts/{id}/presence        — clear on leave
"""

import asyncio
import time
import logging
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import db
from .posting_db import (
    init_posting_db,
    # scheduled threads
    create_scheduled_thread, get_scheduled_threads, get_sent_threads,
    cancel_scheduled_thread, update_fire_at, cancel_to_draft,
    mark_thread_sending, mark_thread_sent, mark_thread_failed,
    # tracked threads / replies
    get_my_threads, get_reply_queue, get_unread_count, dismiss_reply,
    add_my_thread,
    # recents
    touch_recent, get_recents,
    # drafts — simple
    save_draft, delete_draft,
    # drafts — collaborative
    get_draft, get_drafts_with_collab_info, get_shared_drafts,
    save_draft_collab, get_draft_version_info,
    # collaborators
    add_collaborator, remove_collaborator, get_collaborators,
    # edit log
    get_edit_log, rollback_to_log_entry,
    # presence
    touch_presence, clear_presence,
)

router = APIRouter(prefix="/api/posting", tags=["posting"])
log    = logging.getLogger("posting.router")

init_posting_db()


# ── Auth helpers ───────────────────────────────────────────────────────────────

def _auth(request: Request):
    uid = request.session.get("uid")
    if not uid:
        return None, JSONResponse({"error": "unauthenticated"}, status_code=401)
    return uid, None


async def _get_username(uid: str) -> str:
    """Return username from local DB, falling back to uid string."""
    user = await asyncio.to_thread(db.get_user, uid)
    return user["username"] if user else uid


async def _lookup_collab_username(collab_uid: str, owner_uid: str) -> str:
    """
    Look up a HF username for collab_uid.
    Priority: uid_usernames cache → users table → HF API call → raw UID string.
    """
    # 1. Local username cache
    name_map = await asyncio.to_thread(db.get_uid_usernames, [collab_uid])
    if collab_uid in name_map:
        return name_map[collab_uid]
    # 2. Users table
    user = await asyncio.to_thread(db.get_user, collab_uid)
    if user:
        return user["username"]
    # 3. HF API (live, costs 1 rate-limit slot)
    try:
        token = await asyncio.to_thread(db.get_token, owner_uid)
        if token:
            from HFClient import HFClient
            client = HFClient(token)
            data = await asyncio.wait_for(
                client.read({"users": {"_uid": [int(collab_uid)], "uid": True, "username": True}}),
                timeout=10,
            )
            rows = data.get("users", [])
            if isinstance(rows, dict):
                rows = [rows]
            if rows:
                name = rows[0].get("username", "")
                if name:
                    await asyncio.to_thread(db.upsert_uid_usernames, {collab_uid: name})
                    return name
    except Exception:
        pass
    return collab_uid   # last resort: show the UID


# ── Queue a thread ─────────────────────────────────────────────────────────────

@router.post("/thread")
async def queue_thread(request: Request):
    uid, err = _auth(request)
    if err:
        return err

    body          = await request.json()
    fid           = str(body.get("fid") or "").strip()
    forum_name    = str(body.get("forum_name") or "").strip()
    category_name = str(body.get("category_name") or "").strip()
    subject       = str(body.get("subject") or "").strip()
    message       = str(body.get("message") or "").strip()
    fire_at_raw   = body.get("fire_at", 0)

    if not fid:     return JSONResponse({"error": "fid required"}, status_code=400)
    if not subject: return JSONResponse({"error": "subject required"}, status_code=400)
    if not message: return JSONResponse({"error": "message required"}, status_code=400)
    if len(subject) > 300:
        return JSONResponse({"error": "subject too long (max 300)"}, status_code=400)
    if len(message) > 200_000:
        return JSONResponse({"error": "message too long"}, status_code=400)

    CATEGORY_FIDS = {
        "1","7","45","88","105","120","141","151","156","241",
        "259","444","445","446","447","448","449","450","451","452","453","460"
    }
    if fid in CATEGORY_FIDS:
        return JSONResponse({"error": "Cannot post to a category — select a forum"}, status_code=400)

    try:
        fid_int = int(fid)
        if fid_int <= 0:
            raise ValueError
    except (ValueError, TypeError):
        return JSONResponse({"error": "fid must be a positive integer"}, status_code=400)

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
    if err: return err
    return {"queue": await asyncio.to_thread(get_scheduled_threads, uid)}


@router.delete("/queue/{row_id}")
async def cancel_queue_item(request: Request, row_id: int):
    uid, err = _auth(request)
    if err: return err
    ok = await asyncio.to_thread(cancel_scheduled_thread, row_id, uid)
    if not ok:
        return JSONResponse({"error": "Not found or already sent"}, status_code=404)
    return {"ok": True}


@router.patch("/queue/{row_id}/reschedule")
async def reschedule_queue_item(request: Request, row_id: int):
    uid, err = _auth(request)
    if err: return err
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
    uid, err = _auth(request)
    if err: return err
    row = await asyncio.to_thread(cancel_to_draft, row_id, uid)
    if not row:
        return JSONResponse({"error": "not found or already sent"}, status_code=404)
    draft_id = await asyncio.to_thread(
        save_draft, uid, row["fid"], row["forum_name"], row["subject"], row["message"]
    )
    return {"ok": True, "draft_id": draft_id}


# ── Sent threads ───────────────────────────────────────────────────────────────

@router.get("/sent")
async def get_sent(request: Request):
    uid, err = _auth(request)
    if err: return err
    return {"sent": await asyncio.to_thread(get_sent_threads, uid)}


# ── My tracked threads ─────────────────────────────────────────────────────────

@router.get("/threads")
async def get_threads(request: Request):
    uid, err = _auth(request)
    if err: return err
    return {"threads": await asyncio.to_thread(get_my_threads, uid)}


@router.get("/hf-threads")
async def get_hf_threads(request: Request, page: int = 1):
    uid, err = _auth(request)
    if err: return err
    token = await asyncio.to_thread(db.get_token, uid)
    if not token:
        return JSONResponse({"error": "no token"}, status_code=401)
    try:
        from HFClient import HFClient
        client = HFClient(token)
        data   = await asyncio.wait_for(client.read({
            "threads": {
                "_uid": [int(uid)], "_page": page, "_perpage": 30,
                "tid": True, "subject": True, "fid": True,
                "dateline": True, "lastpost": True, "numreplies": True,
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
    if err: return err
    return {"count": await asyncio.to_thread(get_unread_count, uid)}


@router.get("/replies")
async def get_replies(request: Request):
    uid, err = _auth(request)
    if err: return err
    return {"replies": await asyncio.to_thread(get_reply_queue, uid, "unread")}


@router.post("/replies/{reply_id}/dismiss")
async def dismiss(request: Request, reply_id: int):
    uid, err = _auth(request)
    if err: return err
    ok = await asyncio.to_thread(dismiss_reply, reply_id, uid)
    if not ok:
        return JSONResponse({"error": "Not found"}, status_code=404)
    return {"ok": True}


# ── Post a reply ───────────────────────────────────────────────────────────────

@router.post("/reply")
async def post_reply(request: Request):
    uid, err = _auth(request)
    if err: return err

    body    = await request.json()
    tid     = str(body.get("tid") or "").strip()
    message = str(body.get("message") or "").strip()

    if not tid:     return JSONResponse({"error": "tid required"}, status_code=400)
    if not message: return JSONResponse({"error": "message required"}, status_code=400)

    token = await asyncio.to_thread(db.get_token, uid)
    if not token:
        return JSONResponse({"error": "No token"}, status_code=401)

    from HFClient import HFClient
    client = HFClient(token)

    try:
        result = await client.write({"posts": {"_tid": int(tid), "_message": message}})
        log.info("Reply write uid=%s tid=%s raw_result=%s", uid, tid, result)
        if not result:
            return JSONResponse({"error": "API returned empty response"}, status_code=502)
        posts_result = result.get("posts") or {}
        if isinstance(posts_result, list):
            posts_result = posts_result[0] if posts_result else {}
        pid = str(posts_result.get("pid") or "")
        if not pid:
            return JSONResponse({"error": f"HF returned no post ID. Raw: {result}"}, status_code=502)

        # Auto-dismiss: any reply the user explicitly quoted in their message is no
        # longer "unread" — they already responded to it. Parse [quote ... pid='X'] tags.
        try:
            import re as _re
            from .posting_db import auto_dismiss_by_pid, auto_dismiss_by_thread_before
            quoted_pids = _re.findall(r"\[quote[^\]]*pid='(\d+)'", message, _re.IGNORECASE)
            for qpid in quoted_pids:
                await asyncio.to_thread(auto_dismiss_by_pid, uid, qpid)
            # Also dismiss all replies in this thread that predate our new post dateline —
            # if the user replied without quoting, they still saw those replies.
            new_dateline = int(posts_result.get("dateline") or 0)
            if new_dateline:
                await asyncio.to_thread(auto_dismiss_by_thread_before, uid, tid, new_dateline)
        except Exception as _de:
            log.debug("Auto-dismiss failed uid=%s tid=%s: %s", uid, tid, _de)

        return {"ok": True, "pid": pid}
    except Exception as e:
        log.exception("Reply failed uid=%s tid=%s: %s", uid, tid, e)
        return JSONResponse({"error": str(e)}, status_code=500)


# ── Recents ────────────────────────────────────────────────────────────────────

@router.get("/recents")
async def get_recents_route(request: Request):
    uid, err = _auth(request)
    if err: return err
    return {"recents": await asyncio.to_thread(get_recents, uid)}


# ── Image host proxy ───────────────────────────────────────────────────────────

@router.post("/imagehost/upload")
async def imagehost_upload(request: Request):
    _auth(request)
    import httpx as _httpx

    form       = await request.form()
    file_field = form.get("file")
    if not file_field:
        return JSONResponse({"error": "no file"}, status_code=400)

    file_bytes = await file_field.read()
    fwd_data   = {k: v for k, v in form.items() if k != "file"}

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


# ══════════════════════════════════════════════════════════════════════════════
# Collaborative Drafts
# NOTE: Specific literal routes (/drafts/shared) MUST appear before parameterised
#       ones (/drafts/{id}) so FastAPI doesn't swallow "shared" as a draft_id.
# ══════════════════════════════════════════════════════════════════════════════

@router.get("/drafts/shared")
async def list_shared_drafts(request: Request):
    """Drafts where the current user is a collaborator (not owner)."""
    uid, err = _auth(request)
    if err: return err
    drafts = await asyncio.to_thread(get_shared_drafts, uid)
    return {"drafts": drafts}


@router.get("/drafts")
async def list_drafts(request: Request):
    """Owner's own drafts with version + collaborator count."""
    uid, err = _auth(request)
    if err: return err
    drafts = await asyncio.to_thread(get_drafts_with_collab_info, uid)
    return {"drafts": drafts}


@router.post("/drafts")
async def create_draft(request: Request):
    uid, err = _auth(request)
    if err: return err
    body = await request.json()
    draft_id = await asyncio.to_thread(
        save_draft, uid,
        str(body.get("fid") or ""),
        str(body.get("forum_name") or ""),
        str(body.get("subject") or ""),
        str(body.get("message") or ""),
    )
    return {"ok": True, "draft_id": draft_id}


@router.get("/drafts/{draft_id}")
async def get_single_draft(request: Request, draft_id: int):
    """Full draft content — accessible by owner or collaborator."""
    uid, err = _auth(request)
    if err: return err
    draft = await asyncio.to_thread(get_draft, draft_id, uid)
    if not draft:
        return JSONResponse({"error": "Not found or no access"}, status_code=404)
    # Also return collaborator list for the UI
    collabs = await asyncio.to_thread(get_collaborators, draft_id)
    draft["collaborators"] = collabs
    return {"draft": draft}


@router.put("/drafts/{draft_id}")
async def save_draft_versioned(request: Request, draft_id: int):
    """
    Versioned save with optimistic locking.
    Body must include base_version (the version the client loaded from).
    Returns 409 with current draft state on conflict.
    """
    uid, err = _auth(request)
    if err: return err

    body         = await request.json()
    fid          = str(body.get("fid") or "").strip()
    forum_name   = str(body.get("forum_name") or "").strip()
    subject      = str(body.get("subject") or "").strip()
    message      = str(body.get("message") or "").strip()
    base_version = int(body.get("base_version") or 1)

    if not subject: return JSONResponse({"error": "subject required"}, status_code=400)
    if not message: return JSONResponse({"error": "message required"}, status_code=400)
    if len(subject) > 300:
        return JSONResponse({"error": "subject too long"}, status_code=400)
    if len(message) > 200_000:
        return JSONResponse({"error": "message too long"}, status_code=400)

    editor_name = await _get_username(uid)

    status, data = await asyncio.to_thread(
        save_draft_collab,
        draft_id, uid, fid, forum_name, subject, message, base_version, editor_name
    )

    if status == "notfound":
        return JSONResponse({"error": "Not found or no access"}, status_code=404)

    if status == "conflict":
        # 409 — return current DB state so the client can present conflict UI
        return JSONResponse(
            {
                "conflict":       True,
                "current_version": data.get("version") or 1,
                "current_subject": data.get("subject") or "",
                "current_message": data.get("message") or "",
                "last_editor":     data.get("last_editor_name") or "",
            },
            status_code=409,
        )

    return {"ok": True, "draft": data}


@router.delete("/drafts/{draft_id}")
async def remove_draft(request: Request, draft_id: int):
    """Hard delete — owner only."""
    uid, err = _auth(request)
    if err: return err
    ok = await asyncio.to_thread(delete_draft, draft_id, uid)
    if not ok:
        return JSONResponse({"error": "Not found or not owner"}, status_code=404)
    return {"ok": True}


# ── Version poll (lightweight — no content transfer) ──────────────────────────

@router.get("/drafts/{draft_id}/version")
async def draft_version(request: Request, draft_id: int):
    uid, err = _auth(request)
    if err: return err
    info = await asyncio.to_thread(get_draft_version_info, draft_id, uid)
    if not info:
        return JSONResponse({"error": "Not found or no access"}, status_code=404)
    return info


# ── Edit log & rollback ────────────────────────────────────────────────────────

@router.get("/drafts/{draft_id}/log")
async def draft_log(request: Request, draft_id: int):
    uid, err = _auth(request)
    if err: return err
    # Verify access
    draft = await asyncio.to_thread(get_draft, draft_id, uid)
    if not draft:
        return JSONResponse({"error": "Not found or no access"}, status_code=404)
    entries = await asyncio.to_thread(get_edit_log, draft_id)
    return {"log": entries}


@router.post("/drafts/{draft_id}/rollback/{log_id}")
async def draft_rollback(request: Request, draft_id: int, log_id: int):
    """Restore draft to the state saved in log_id. Owner only."""
    uid, err = _auth(request)
    if err: return err
    owner_name = await _get_username(uid)
    status, data = await asyncio.to_thread(
        rollback_to_log_entry, draft_id, log_id, uid, owner_name
    )
    if status == "forbidden":
        return JSONResponse({"error": "Owner only"}, status_code=403)
    if status == "notfound":
        return JSONResponse({"error": "Log entry not found"}, status_code=404)
    return {"ok": True, "new_version": data}


# ── Collaborators ──────────────────────────────────────────────────────────────

@router.get("/drafts/{draft_id}/collaborators")
async def list_collaborators(request: Request, draft_id: int):
    uid, err = _auth(request)
    if err: return err
    draft = await asyncio.to_thread(get_draft, draft_id, uid)
    if not draft:
        return JSONResponse({"error": "Not found or no access"}, status_code=404)
    collabs = await asyncio.to_thread(get_collaborators, draft_id)
    return {"collaborators": collabs}


@router.post("/drafts/{draft_id}/collaborators")
async def add_collab(request: Request, draft_id: int):
    """Add a collaborator by UID. Owner only."""
    uid, err = _auth(request)
    if err: return err

    body       = await request.json()
    collab_uid = str(body.get("uid") or "").strip()
    if not collab_uid:
        return JSONResponse({"error": "uid required"}, status_code=400)

    # Validate it looks like a UID
    try:
        int(collab_uid)
    except ValueError:
        return JSONResponse({"error": "uid must be numeric"}, status_code=400)

    collab_name = await _lookup_collab_username(collab_uid, uid)
    ok = await asyncio.to_thread(add_collaborator, draft_id, uid, collab_uid, collab_name)
    if not ok:
        return JSONResponse({"error": "Not owner, draft not found, or adding yourself"}, status_code=403)

    return {"ok": True, "uid": collab_uid, "username": collab_name}


@router.delete("/drafts/{draft_id}/collaborators/{collab_uid}")
async def remove_collab(request: Request, draft_id: int, collab_uid: str):
    """Remove a collaborator. Owner only."""
    uid, err = _auth(request)
    if err: return err
    ok = await asyncio.to_thread(remove_collaborator, draft_id, uid, collab_uid)
    if not ok:
        return JSONResponse({"error": "Not owner or draft not found"}, status_code=403)
    return {"ok": True}


# ── Presence ───────────────────────────────────────────────────────────────────

@router.post("/drafts/{draft_id}/presence")
async def presence_heartbeat(request: Request, draft_id: int):
    """Heartbeat — sent every ~20 s while draft is open."""
    uid, err = _auth(request)
    if err: return err
    # Quick access check via version info (cheaper than get_draft)
    info = await asyncio.to_thread(get_draft_version_info, draft_id, uid)
    if not info:
        return JSONResponse({"error": "No access"}, status_code=403)
    username = await _get_username(uid)
    await asyncio.to_thread(touch_presence, draft_id, uid, username)
    return {"ok": True}


@router.delete("/drafts/{draft_id}/presence")
async def presence_leave(request: Request, draft_id: int):
    """Clear presence when user navigates away."""
    uid, err = _auth(request)
    if err: return err
    await asyncio.to_thread(clear_presence, draft_id, uid)
    return {"ok": True}
