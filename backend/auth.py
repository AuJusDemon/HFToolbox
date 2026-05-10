import asyncio
"""
auth.py — HackForums OAuth2 flow.

Routes:
  GET  /auth/login      → redirect to HF authorize URL
  GET  /auth/callback   → exchange code, store user, set session
  GET  /auth/me         → return session user (used by frontend on load)
  POST /auth/logout     → clear session
"""

import os
import secrets
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from HFClient import exchange_code_for_token, HFClient
import db

router = APIRouter(prefix="/auth", tags=["auth"])

CLIENT_ID     = os.environ["HF_CLIENT_ID"]
CLIENT_SECRET = os.environ["HF_CLIENT_SECRET"]
REDIRECT_URI  = os.environ["HF_REDIRECT_URI"]
FRONTEND_URL  = os.environ.get("FRONTEND_URL", "http://localhost:5173")


@router.get("/login")
async def login(request: Request, next: str = ""):
    state = secrets.token_urlsafe(16)
    # Encode the return path into the state so it survives the OAuth round-trip
    # Format: "STATE|NEXT_PATH" — pipe is not in urlsafe base64 so safe to split on
    safe_next = next.strip()
    # Only allow internal paths (must start with /dashboard)
    if safe_next and not safe_next.startswith("/dashboard"):
        safe_next = ""
    full_state = f"{state}|{safe_next}" if safe_next else state
    request.session["oauth_state"] = state
    request.session["oauth_next"]  = safe_next
    url = (
        f"https://hackforums.net/api/v2/authorize"
        f"?response_type=code&client_id={CLIENT_ID}&state={full_state}"
    )
    return RedirectResponse(url)


@router.get("/callback")
async def callback(
    request: Request,
    code: str = None,
    state: str = None,
    error: str = None,
    error_description: str = None,
):
    # HF returned an error (user denied, expired state, etc.) — redirect back to login
    if error or not code or not state:
        request.session.pop("oauth_state", None)
        request.session.pop("oauth_next", None)
        return RedirectResponse(f"{FRONTEND_URL}/?auth_error={error or 'unknown'}")

    # State may be "TOKEN|/dashboard/path" — extract the token part for validation
    state_token = state.split("|")[0]
    if request.session.pop("oauth_state", None) != state_token:
        raise HTTPException(400, "State mismatch")

    # hf_client.py exchange_code_for_token takes (code, cfg_dict)
    cfg = {
        "hf_client_id":     CLIENT_ID,
        "hf_client_secret": CLIENT_SECRET,
    }
    access_token, token_expiry, refresh_token = await exchange_code_for_token(code, cfg)

    if not access_token:
        raise HTTPException(500, "Token exchange failed")

    client = HFClient(access_token)
    raw = await client.read({
        "me": {
            "uid": True, "username": True, "avatar": True,
            "usergroup": True, "displaygroup": True, "additionalgroups": True,
            "postnum": True, "threadnum": True, "reputation": True,
            "bytes": True, "vault": True, "usertitle": True, "timeonline": True,
        }
    })

    if not raw:
        raise HTTPException(500, "Failed to reach HF API")

    me = raw.get("me", {})
    uid = str(me.get("uid") or "")
    if not uid:
        raise HTTPException(500, "Failed to get UID from HF")

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

    raw_av = str(me.get("avatar") or "")
    clean_av = ("https://hackforums.net/" + raw_av.lstrip("./")) if raw_av else ""
    await asyncio.to_thread(db.upsert_user,
        uid, str(me.get("username") or ""), access_token,
        clean_av, groups,
    )
    if refresh_token:
        expiry_ts = int(token_expiry) if token_expiry else 0
        await asyncio.to_thread(db.store_refresh_token, uid, str(refresh_token), expiry_ts)
    await asyncio.to_thread(db.mark_token_dead, uid, False)
    await asyncio.to_thread(db.update_profile_cache, uid, {
        "postnum":      me.get("postnum"),
        "threadnum":    me.get("threadnum"),
        "reputation":   me.get("reputation"),
        "myps":         me.get("bytes"),
        "vault":        me.get("vault"),
        "usertitle":    me.get("usertitle"),
        "timeonline":   me.get("timeonline"),
        "displaygroup": me.get("displaygroup") or me.get("usergroup") or "",
    })

    request.session["uid"] = uid
    next_path = request.session.pop("oauth_next", "") or ""
    redirect_to = f"{FRONTEND_URL}{next_path}" if next_path else f"{FRONTEND_URL}/dashboard"
    return RedirectResponse(redirect_to)


# Dev override: DEV_GROUPS_OVERRIDE=63,53,57,... in .env injects extra group IDs
# into every user's groups list. Only for local dev — never set in production.
_DEV_GROUPS_OVERRIDE: list[str] = [
    g.strip() for g in os.environ.get("DEV_GROUPS_OVERRIDE", "").split(",") if g.strip()
]


@router.get("/me")
async def me(request: Request):
    uid = request.session.get("uid")
    if not uid:
        raise HTTPException(401)
    user = await asyncio.to_thread(db.get_user, uid)
    if not user or user.get("token_dead"):
        raise HTTPException(401)
    groups = user["groups"]
    if _DEV_GROUPS_OVERRIDE:
        groups = list(dict.fromkeys(groups + _DEV_GROUPS_OVERRIDE))
    from fastapi.responses import JSONResponse as _JR
    return _JR(
        content={
            "uid":      user["uid"],
            "username": user["username"],
            "avatar":   user["avatar"],
            "groups":   groups,
        },
        headers={"Cache-Control": "no-store, no-cache, must-revalidate"},
    )


@router.post("/logout")
async def logout(request: Request):
    uid = request.session.get("uid")
    if uid:
        await asyncio.to_thread(db.mark_token_dead, uid, True)
    request.session.clear()
    response = JSONResponse({"ok": True})
    https_only = os.environ.get("ENV") == "production"
    response.delete_cookie("session", path="/", httponly=True, samesite="lax", secure=https_only)
    return response