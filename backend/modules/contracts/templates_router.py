"""
modules/contracts/templates_router.py — contract template CRUD + fire.

GET    /api/contracts/templates          — list (own + public)
POST   /api/contracts/templates          — create
PUT    /api/contracts/templates/{id}     — update (own only)
DELETE /api/contracts/templates/{id}     — delete (own only)
POST   /api/contracts/templates/{id}/fire — create a live HF contract from template
"""

import asyncio
import logging
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import db
try:
    from HFClient import AuthExpired as _AuthExpired
except ImportError:
    class _AuthExpired(Exception):
        pass
from .templates_db import (
    init_templates_db,
    list_templates,
    get_template,
    create_template,
    update_template,
    delete_template,
)

router = APIRouter(prefix="/api/contracts/templates", tags=["contract_templates"])
log = logging.getLogger("contracts.templates")

init_templates_db()


def _auth(request: Request):
    uid = request.session.get("uid")
    if not uid:
        return None, None, JSONResponse({"error": "unauthenticated"}, status_code=401)
    token = db.get_token(uid)
    if not token:
        return None, None, JSONResponse({"error": "no token"}, status_code=401)
    return uid, token, None


@router.get("")
async def get_templates(request: Request):
    uid, _, err = _auth(request)
    if err:
        return err
    templates = await asyncio.to_thread(list_templates, uid)
    return {"templates": templates}


@router.post("")
async def new_template(request: Request):
    uid, _, err = _auth(request)
    if err:
        return err
    data = await request.json()
    tid  = await asyncio.to_thread(create_template, uid, data)
    tmpl = await asyncio.to_thread(get_template, tid, uid)
    return {"template": tmpl}


@router.patch("/{tid}")
async def edit_template(request: Request, tid: int):
    uid, _, err = _auth(request)
    if err:
        return err
    data = await request.json()
    ok   = await asyncio.to_thread(update_template, tid, uid, data)
    if not ok:
        return JSONResponse({"error": "not found or not yours"}, status_code=404)
    tmpl = await asyncio.to_thread(get_template, tid, uid)
    return {"template": tmpl}


@router.delete("/{tid}")
async def remove_template(request: Request, tid: int):
    uid, _, err = _auth(request)
    if err:
        return err
    ok = await asyncio.to_thread(delete_template, tid, uid)
    if not ok:
        return JSONResponse({"error": "not found or not yours"}, status_code=404)
    return {"ok": True}


@router.post("/{tid}/fire")
async def fire_template(request: Request, tid: int):
    """
    Instantiate a contract from a template.
    Body: { counterparty_uid: N, thread_id?: N }
    """
    uid, token, err = _auth(request)
    if err:
        return err

    body           = await request.json()
    counterparty   = body.get("counterparty_uid")
    thread_id      = body.get("thread_id")

    if not counterparty:
        return JSONResponse({"error": "counterparty_uid required"}, status_code=400)

    tmpl = await asyncio.to_thread(get_template, tid, uid)
    if not tmpl:
        return JSONResponse({"error": "template not found"}, status_code=404)

    ask: dict = {
        "_uid":       str(counterparty),
        "_terms":     tmpl["terms"],
        "_position":  tmpl["position"],
        "_timeout":   str(tmpl["timeout_days"]),
        "_public":    "yes",
    }

    if tmpl["yourproduct"]:    ask["_yourproduct"]   = tmpl["yourproduct"]
    if tmpl["yourcurrency"]:   ask["_yourcurrency"]  = tmpl["yourcurrency"]
    if tmpl["youramount"] and tmpl["youramount"] != "0":
        ask["_youramount"] = tmpl["youramount"]

    if tmpl["theirproduct"]:   ask["_theirproduct"]  = tmpl["theirproduct"]
    if tmpl["theircurrency"]:  ask["_theircurrency"] = tmpl["theircurrency"]
    if tmpl["theiramount"] and tmpl["theiramount"] != "0":
        ask["_theiramount"] = tmpl["theiramount"]

    if thread_id:
        ask["_tid"] = str(thread_id)

    if tmpl.get("address"):
        ask["_address"] = tmpl["address"]
    if tmpl.get("middleman_uid"):
        ask["_muid"] = str(tmpl["middleman_uid"])

    from HFClient import HFClient
    hf = HFClient(token)
    try:
        result = await hf.write({"contracts": {"_action": "new", **ask}})
    except _AuthExpired:
        request.session.clear()
        await asyncio.to_thread(db.clear_token, uid)
        return JSONResponse({"error": "hf_token_revoked"}, status_code=401)

    if result is None:
        return JSONResponse({"error": "HF API returned no response"}, status_code=502)

    contracts = result.get("contracts", {})
    if isinstance(contracts, list):
        contracts = contracts[0] if contracts else {}

    cid = contracts.get("cid")
    return {
        "ok":  True,
        "cid": cid,
        "url": f"https://hackforums.net/contracts.php?action=view&cid={cid}" if cid else None,
    }
