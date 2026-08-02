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
import logging
import secrets
import time as _time
from urllib.parse import urlencode
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse
from HFClient import exchange_code_for_token, HFClient
import db
import integration_db

router = APIRouter(prefix="/auth", tags=["auth"])
log = logging.getLogger("hftoolbox.auth")

CLIENT_ID     = os.environ["HF_CLIENT_ID"]
CLIENT_SECRET = os.environ["HF_CLIENT_SECRET"]
REDIRECT_URI  = os.environ["HF_REDIRECT_URI"]
FRONTEND_URL  = os.environ.get("FRONTEND_URL", "http://localhost:5173")


def _auth_error_redirect(request: Request, public_code: str, detail: str = ""):
    """Return browsers to login while retaining technical diagnostics in logs."""
    reference = secrets.token_hex(4)
    safe_next = str(request.session.pop("oauth_next", "") or "")
    if safe_next and not safe_next.startswith("/dashboard"):
        safe_next = ""
    request.session.pop("oauth_state", None)
    log.warning("OAuth login failed ref=%s code=%s detail=%s", reference, public_code,
                str(detail or "")[:300])
    params = {"auth_error": public_code, "auth_ref": reference}
    if safe_next:
        params["next"] = safe_next
    return RedirectResponse(f"{FRONTEND_URL}/?{urlencode(params)}")


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
    params = urlencode({
        "response_type": "code",
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "state": full_state,
    })
    return RedirectResponse(f"https://hackforums.net/api/v2/authorize?{params}")


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
        public_code = "cancelled" if error == "access_denied" else "oauth_failed"
        return _auth_error_redirect(
            request,
            public_code,
            f"provider_error={error or 'missing_callback_fields'} description={error_description or ''}",
        )

    # State may be "TOKEN|/dashboard/path" — extract the token part for validation
    state_token = state.split("|")[0]
    if request.session.pop("oauth_state", None) != state_token:
        return _auth_error_redirect(request, "session_expired", "OAuth state mismatch")

    # hf_client.py exchange_code_for_token takes (code, cfg_dict)
    cfg = {
        "hf_client_id":     CLIENT_ID,
        "hf_client_secret": CLIENT_SECRET,
        "redirect_uri":     REDIRECT_URI,
    }
    try:
        access_token, token_expiry, refresh_token = await exchange_code_for_token(code, cfg)
    except Exception as exc:
        return _auth_error_redirect(
            request, "hf_unavailable", f"token exchange exception={type(exc).__name__}: {exc}"
        )

    if not access_token:
        return _auth_error_redirect(request, "hf_unavailable", "token exchange returned no access token")

    client = HFClient(access_token)
    try:
        raw = await client.read({
            "me": {
                "uid": True, "username": True, "avatar": True,
                "usergroup": True, "displaygroup": True, "additionalgroups": True,
            }
        })
    except Exception as exc:
        return _auth_error_redirect(
            request, "hf_unavailable", f"profile read exception={type(exc).__name__}: {exc}"
        )

    if not raw:
        return _auth_error_redirect(request, "hf_unavailable", "profile read returned no response")

    me = raw.get("me", {})
    uid = str(me.get("uid") or "")
    if not uid:
        return _auth_error_redirect(request, "invalid_response", "profile response missing uid")

    profile_me = dict(me)
    try:
        profile_raw = await client.read({
            "me": {
                "postnum": True, "threadnum": True, "reputation": True,
                "bytes": True, "vault": True, "usertitle": True, "timeonline": True,
            }
        })
        if profile_raw and isinstance(profile_raw.get("me"), dict):
            profile_me.update(profile_raw["me"])
    except Exception:
        pass

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
    await asyncio.to_thread(integration_db.upsert_integration_account, uid)
    # expires_in is relative seconds — convert to absolute timestamp
    expiry_ts = int(_time.time()) + int(token_expiry) if token_expiry else 0
    if refresh_token:
        await asyncio.to_thread(db.store_refresh_token, uid, str(refresh_token), expiry_ts)
    elif expiry_ts:
        await asyncio.to_thread(db.update_token_expiry, uid, expiry_ts)
    await asyncio.to_thread(db.mark_token_dead, uid, False)
    await asyncio.to_thread(db.update_profile_cache, uid, {
        "postnum":      profile_me.get("postnum"),
        "threadnum":    profile_me.get("threadnum"),
        "reputation":   profile_me.get("reputation"),
        "myps":         profile_me.get("bytes"),
        "vault":        profile_me.get("vault"),
        "usertitle":    profile_me.get("usertitle"),
        "timeonline":   profile_me.get("timeonline"),
        "displaygroup": profile_me.get("displaygroup") or profile_me.get("usergroup") or "",
    })

    # Regenerate the session to prevent session fixation.
    # Pull next_path before clearing so it isn't lost.
    next_path = request.session.pop("oauth_next", "") or ""
    request.session.clear()
    request.session["uid"] = uid
    redirect_to = f"{FRONTEND_URL}{next_path}" if next_path else f"{FRONTEND_URL}/dashboard"
    return RedirectResponse(redirect_to)


# Dev override: DEV_GROUPS_OVERRIDE=63,53,57,... in .env injects extra group IDs
# into every user's groups list. Only for local dev — never set in production.
_DEV_GROUPS_OVERRIDE: list[str] = [
    g.strip() for g in os.environ.get("DEV_GROUPS_OVERRIDE", "").split(",") if g.strip()
]
if _DEV_GROUPS_OVERRIDE and os.environ.get("ENV") == "production":
    raise RuntimeError(
        "DEV_GROUPS_OVERRIDE must not be set in production — "
        "remove it from .env before starting the server"
    )


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
