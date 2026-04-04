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
async def login(request: Request):
    state = secrets.token_urlsafe(16)
    request.session["oauth_state"] = state
    url = (
        f"https://hackforums.net/api/v2/authorize"
        f"?response_type=code&client_id={CLIENT_ID}&state={state}"
    )
    return RedirectResponse(url)


@router.get("/callback")
async def callback(request: Request, code: str, state: str):
    if request.session.pop("oauth_state", None) != state:
        raise HTTPException(400, "State mismatch")

    # hf_client.py exchange_code_for_token takes (code, cfg_dict)
    cfg = {
        "hf_client_id":     CLIENT_ID,
        "hf_client_secret": CLIENT_SECRET,
    }
    access_token, _, __ = await exchange_code_for_token(code, cfg)

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
    await asyncio.to_thread(db.update_profile_cache, uid, {
        "postnum":   me.get("postnum"),
        "threadnum": me.get("threadnum"),
        "reputation":me.get("reputation"),
        "myps":      me.get("bytes"),
        "vault":     me.get("vault"),
        "usertitle": me.get("usertitle"),
        "timeonline":me.get("timeonline"),
    })

    request.session["uid"] = uid
    return RedirectResponse(f"{FRONTEND_URL}/dashboard")


@router.get("/me")
async def me(request: Request):
    uid = request.session.get("uid")
    if not uid:
        raise HTTPException(401)
    user = await asyncio.to_thread(db.get_user, uid)
    if not user:
        raise HTTPException(401)
    return {
        "uid":      user["uid"],
        "username": user["username"],
        "avatar":   user["avatar"],
        "groups":   user["groups"],
    }


@router.post("/logout")
async def logout(request: Request):
    request.session.clear()
    return JSONResponse({"ok": True})
