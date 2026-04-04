"""
modules/sigmarket/router.py — API routes for sigmarket manager.

GET  /api/sigmarket/status          — your listing + seller orders + buyer orders
POST /api/sigmarket/listing         — setsale / removesale / changesig
POST /api/sigmarket/buy             — buy a sig slot
GET  /api/sigmarket/rotation        — get auto-rotate config
POST /api/sigmarket/rotation        — save auto-rotate config
POST /api/sigmarket/rotation/toggle — enable/disable without clobbering config
"""

import asyncio
import logging
import time as _time
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import db
from .sigmarket_db import (
    init_sigmarket_db,
    get_rotation,
    upsert_rotation,
    set_rotation_enabled,
)

router = APIRouter(prefix="/api/sigmarket", tags=["sigmarket"])
log = logging.getLogger("sigmarket.router")

init_sigmarket_db()

SIGMARKET_CACHE_TTL = 300  # 5 minutes


def _auth(request: Request):
    uid = request.session.get("uid")
    if not uid:
        return None, None, JSONResponse({"error": "unauthenticated"}, status_code=401)
    token = db.get_token(uid)
    if not token:
        return None, None, JSONResponse({"error": "no token"}, status_code=401)
    return uid, token, None


@router.get("/status")
async def get_status(request: Request):
    uid, token, err = _auth(request)
    if err:
        return err

    force = request.query_params.get("force") == "true"

    # Serve from cache unless forced
    if not force:
        cached = await asyncio.to_thread(db.get_dash_cache, uid, "sigmarket_status", SIGMARKET_CACHE_TTL)
        if cached:
            return cached

    from HFClient import HFClient
    hf = HFClient(token)
    uid_int = int(uid)

    # Both reads fire in parallel — halves latency vs sequential
    data1, data2 = await asyncio.gather(
        hf.read({
            "sigmarket": {
                "_type":    "market",
                "_uid":     [uid_int],
                "_page":    1,
                "_perpage": 1,
                "uid":      True,
                "price":    True,
                "duration": True,
                "active":   True,
                "sig":      True,
                "ppd":      True,
                "dateadded": True,
            }
        }),
        hf.read({
            "sigmarket": {
                "_type":    "order",
                "_seller":  [uid_int],
                "_page":    1,
                "_perpage": 30,
                "smid":     True,
                "active":   True,
                "startdate": True,
                "enddate":  True,
                "price":    True,
                "duration": True,
                "buyer":    {"uid": True, "username": True},
            }
        }),
    )

    listing_raw = (data1 or {}).get("sigmarket")
    orders_raw  = (data2 or {}).get("sigmarket", [])

    if isinstance(listing_raw, list):
        listing = listing_raw[0] if listing_raw else None
    else:
        listing = listing_raw

    if isinstance(orders_raw, dict):
        orders_raw = [orders_raw]

    now_ts = int(_time.time())
    seller_orders = []
    for o in (orders_raw or []):
        end = int(o.get("enddate") or 0)
        seller_orders.append({
            "smid":       o.get("smid"),
            "active":     int(o.get("active") or 0),
            "startdate":  int(o.get("startdate") or 0),
            "enddate":    end,
            "expires_in": max(0, end - now_ts),
            "price":      o.get("price"),
            "duration":   o.get("duration"),
            "buyer":      o.get("buyer") or {},
        })

    result = {
        "listing":            listing,
        "seller_orders":      seller_orders,
        "active_order_count": sum(1 for o in seller_orders if o["active"]),
    }

    await asyncio.to_thread(db.set_dash_cache, uid, "sigmarket_status", result)
    return result


@router.post("/listing")
async def update_listing(request: Request):
    """
    setsale   — { action: "setsale",   price: N, duration: N }
    removesale — { action: "removesale" }
    changesig  — { action: "changesig", smid: "all"|N, sig: "BBCode" }
    """
    uid, token, err = _auth(request)
    if err:
        return err

    body = await request.json()
    action = body.get("action")
    if action not in ("setsale", "removesale", "changesig"):
        return JSONResponse({"error": "invalid action"}, status_code=400)

    ask: dict = {"_type": action}

    if action == "setsale":
        price    = body.get("price")
        duration = body.get("duration")
        if not price or not duration:
            return JSONResponse({"error": "price and duration required"}, status_code=400)
        ask["_price"]    = int(price)
        ask["_duration"] = int(duration)

    elif action == "changesig":
        smid = body.get("smid", "all")
        sig  = body.get("sig", "")
        ask["_smid"] = smid
        ask["_sig"]  = sig

    from HFClient import HFClient
    hf = HFClient(token)
    result = await hf.write({"sigmarket": ask})
    if result is None:
        return JSONResponse({"error": "HF API returned no response"}, status_code=502)
    await asyncio.to_thread(db.clear_dash_cache, uid, "sigmarket_status")
    return {"ok": True}
async def buy_sig(request: Request):
    """{ uid: N, max_price: N }"""
    uid, token, err = _auth(request)
    if err:
        return err

    body      = await request.json()
    target    = body.get("uid")
    max_price = body.get("max_price")
    if not target or not max_price:
        return JSONResponse({"error": "uid and max_price required"}, status_code=400)

    from HFClient import HFClient
    hf = HFClient(token)
    result = await hf.write({
        "sigmarket": {
            "_type":  "buy",
            "_uid":   int(target),
            "_price": int(max_price),
        }
    })
    if result is None:
        return JSONResponse({"error": "HF API returned no response"}, status_code=502)
    await asyncio.to_thread(db.clear_dash_cache, uid, "sigmarket_status")
    return {"ok": True}


# ── Auto-rotate config ─────────────────────────────────────────────────────────

@router.get("/rotation")
async def get_rotation_config(request: Request):
    uid, token, err = _auth(request)
    if err:
        return err
    rot = await asyncio.to_thread(get_rotation, uid)
    if not rot:
        return {"uid": uid, "sigs": [], "interval_h": 6, "enabled": False, "last_rotated": 0, "current_idx": 0}
    rot["enabled"] = bool(rot["enabled"])
    return rot


@router.post("/rotation")
async def save_rotation_config(request: Request):
    """Save full rotation config: { sigs: [...], interval_h: N, enabled: bool }"""
    uid, token, err = _auth(request)
    if err:
        return err
    body = await request.json()
    sigs       = body.get("sigs", [])
    interval_h = int(body.get("interval_h", 6))
    enabled    = bool(body.get("enabled", False))

    if not isinstance(sigs, list):
        return JSONResponse({"error": "sigs must be an array"}, status_code=400)
    if interval_h < 1:
        interval_h = 1

    await asyncio.to_thread(upsert_rotation, uid, sigs, interval_h, enabled)
    return {"ok": True}


@router.post("/rotation/toggle")
async def toggle_rotation(request: Request):
    """{ enabled: bool }"""
    uid, token, err = _auth(request)
    if err:
        return err
    body    = await request.json()
    enabled = bool(body.get("enabled", False))
    await asyncio.to_thread(set_rotation_enabled, uid, enabled)
    return {"ok": True}


# ── Browse market listings ─────────────────────────────────────────────────────

@router.get("/browse")
async def browse_listings(request: Request):
    uid, token, err = _auth(request)
    if err:
        return err

    target_uid = request.query_params.get("uid", "")
    page       = max(1, int(request.query_params.get("page", "1")))

    from HFClient import HFClient
    hf = HFClient(token)

    # "POST /read/sigmarket/market" means asks key is "sigmarket/market"
    # not a URL sub-route — still goes through standard /read endpoint
    ask: dict = {
        "_page":     page,
        "_perpage":  20,
        "uid":       True,
        "price":     True,
        "duration":  True,
        "active":    True,
        "sig":       True,
        "ppd":       True,
        "dateadded": True,
    }
    if target_uid:
        try:
            ask["_uid"] = [int(target_uid)]
        except ValueError:
            return JSONResponse({"error": "uid must be a number"}, status_code=400)

    data = await hf.read({"sigmarket/market": ask})
    # Response key matches the asks key
    rows = (data or {}).get("sigmarket/market") or (data or {}).get("sigmarket") or []
    if isinstance(rows, dict):
        rows = [rows]
    if not rows:
        return {"listings": [], "page": page, "has_more": False}

    # Batch-resolve usernames
    uids = list({int(r["uid"]) for r in rows if r.get("uid")})
    user_map = {}
    if uids:
        udata = await hf.read({
            "users": {
                "_uid":       uids,
                "uid":        True,
                "username":   True,
                "reputation": True,
                "postnum":    True,
            }
        })
        urows = (udata or {}).get("users", [])
        if isinstance(urows, dict):
            urows = [urows]
        for u in (urows or []):
            user_map[str(u.get("uid"))] = u

    listings = []
    for r in rows:
        u = user_map.get(str(r.get("uid")), {})
        listings.append({
            "uid":        r.get("uid"),
            "username":   u.get("username") or f'UID {r.get("uid")}',
            "reputation": u.get("reputation", "0"),
            "postnum":    u.get("postnum", "0"),
            "price":      r.get("price"),
            "duration":   r.get("duration"),
            "ppd":        r.get("ppd"),
            "active":     int(r.get("active") or 0),
            "sig":        r.get("sig", ""),
            "dateadded":  r.get("dateadded"),
        })

    return {"listings": listings, "page": page, "has_more": len(rows) == 20}
