"""
modules/sigmarket/router.py — API routes for sigmarket manager.

GET  /api/sigmarket/status          — your listing + seller orders + buyer orders
POST /api/sigmarket/listing         — setsale / removesale / changesig
POST /api/sigmarket/buy             — buy a sig slot
GET  /api/sigmarket/browse          — browse all active market listings
GET  /api/sigmarket/analytics/{uid} — post/thread analytics for any user (cached 1hr)
"""

import asyncio
import logging
import time as _time
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
import db
try:
    from HFClient import AuthExpired as _AuthExpired
except ImportError:
    class _AuthExpired(Exception):
        pass
from .sigmarket_db import init_sigmarket_db

router = APIRouter(prefix="/api/sigmarket", tags=["sigmarket"])
log = logging.getLogger("sigmarket.router")

init_sigmarket_db()

# Status cache is now managed by hf_cache (hf_resource_cache table).
# TTL = 900s (15 min) so the 15-min warmer always refills before expiry.
# Stale window = 3600s (1 hr) so stale data is served immediately while refresh runs.
# The old 10-min TTL vs 15-min warmer created a 5-min cold gap — now gone.
_SIG_STATUS_CACHE_KEY = "sigmarket:status:{uid}"


def _auth(request: Request):
    uid = request.session.get("uid")
    if not uid:
        return None, None, JSONResponse({"error": "unauthenticated"}, status_code=401)
    token = db.get_token(uid)
    if not token:
        return None, None, JSONResponse({"error": "no token"}, status_code=401)
    return uid, token, None


# ── Single source of truth for sigmarket status ────────────────────────────────
# Previously duplicated between get_status() and warm_sigmarket_status().
# Now one function, called by both the route and the scheduler warmer.

async def _do_status_fetch(uid: str, token: str) -> dict | None:
    """
    Fetch sigmarket status: 3 parallel reads (market listing + seller orders + buyer orders).
    Returns parsed result dict, or None on API failure.
    Called via hf_service.get_or_fetch — never call directly from routes.
    """
    from HFClient import HFClient, AuthExpired
    hf      = HFClient(token)
    uid_int = int(uid)
    try:
        data1, data2, data3 = await asyncio.gather(
            hf.read({"sigmarket": {
                "_type": "market", "_uid": [uid_int], "_page": 1, "_perpage": 1,
                "uid": True, "price": True, "duration": True, "active": True,
                "sig": True, "ppd": True, "dateadded": True,
            }}),
            hf.read({"sigmarket": {
                "_type": "order", "_seller": [uid_int], "_page": 1, "_perpage": 30,
                "smid": True, "active": True, "startdate": True, "enddate": True,
                "price": True, "duration": True,
                "buyer": {"uid": True, "username": True},
            }}),
            hf.read({"sigmarket": {
                "_type": "order", "_buyer": [uid_int], "_page": 1, "_perpage": 30,
                "smid": True, "active": True, "startdate": True, "enddate": True,
                "price": True, "duration": True,
                "seller": {"uid": True, "username": True},
            }}),
        )
    except AuthExpired:
        raise _AuthExpired()

    listing_raw       = (data1 or {}).get("sigmarket")
    seller_orders_raw = (data2 or {}).get("sigmarket", [])
    buyer_orders_raw  = (data3 or {}).get("sigmarket", [])

    if data1 is None and data2 is None and data3 is None:
        return None  # complete API failure

    if isinstance(listing_raw, list):    listing = listing_raw[0] if listing_raw else None
    else:                                listing = listing_raw
    if isinstance(seller_orders_raw, dict): seller_orders_raw = [seller_orders_raw]
    if isinstance(buyer_orders_raw,  dict): buyer_orders_raw  = [buyer_orders_raw]

    now_ts = int(_time.time())

    def _parse(o, party_key):
        end = int(o.get("enddate") or 0)
        return {
            "smid": o.get("smid"), "active": int(o.get("active") or 0),
            "startdate": int(o.get("startdate") or 0), "enddate": end,
            "expires_in": max(0, end - now_ts),
            "price": o.get("price"), "duration": o.get("duration"),
            party_key: o.get(party_key) or {},
        }

    seller_orders = [_parse(o, "buyer")  for o in (seller_orders_raw or [])]
    buyer_orders  = [_parse(o, "seller") for o in (buyer_orders_raw  or [])]

    uid_name_map = {}
    for o in seller_orders:
        b = o.get("buyer") or {}
        if b.get("uid") and b.get("username"): uid_name_map[str(b["uid"])] = b["username"]
    for o in buyer_orders:
        s = o.get("seller") or {}
        if s.get("uid") and s.get("username"): uid_name_map[str(s["uid"])] = s["username"]
    if uid_name_map:
        try:
            await asyncio.to_thread(db.upsert_uid_usernames, uid_name_map)
        except Exception:
            pass

    return {
        "listing":            listing,
        "seller_orders":      seller_orders,
        "active_order_count": sum(1 for o in seller_orders if o["active"]),
        "buyer_orders":       buyer_orders,
        "active_buys":        sum(1 for o in buyer_orders if o["active"]),
    }


@router.get("/status")
async def get_status(request: Request):
    uid, token, err = _auth(request)
    if err:
        return err

    force     = request.query_params.get("force") == "true"
    cache_key = _SIG_STATUS_CACHE_KEY.format(uid=uid)

    import hf_service
    import hf_cache as hfc

    try:
        data, is_stale = await hf_service.get_or_fetch(
            cache_key     = cache_key,
            resource_type = "sigmarket_status",
            fetch_fn      = lambda: _do_status_fetch(uid, token),
            uid           = uid,
            force         = force,
        )
    except _AuthExpired:
        request.session.clear()
        await asyncio.to_thread(db.clear_token, uid)
        return JSONResponse({"error": "hf_token_revoked"}, status_code=401)

    if data is None:
        return JSONResponse({"error": "HF API unavailable"}, status_code=503)

    # Include freshness metadata so the frontend can show "updated X ago"
    # and indicate when a background refresh is in progress
    return {
        **data,
        "_cache": {
            "stale":      is_stale,
            "age":        hfc.get_age(cache_key),
            "refreshing": is_stale,
        },
    }


@router.post("/listing")
async def update_listing(request: Request):
    """
    setsale    — { action: "setsale",   price: N, duration: N }
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
    try:
        result = await asyncio.wait_for(hf.write({"sigmarket": ask}), timeout=12)
    except _AuthExpired:
        request.session.clear()
        await asyncio.to_thread(db.clear_token, uid)
        return JSONResponse({"error": "hf_token_revoked"}, status_code=401)
    if result is None:
        return JSONResponse({"error": "HF API returned no response"}, status_code=502)
    await asyncio.to_thread(db.clear_dash_cache, uid, "sigmarket_status")
    return {"ok": True}


@router.post("/buy")
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
    try:
        result = await asyncio.wait_for(hf.write({
            "sigmarket": {
                "_type":  "buy",
                "_uid":   int(target),
                "_price": int(max_price),
            }
        }), timeout=12)
    except _AuthExpired:
        request.session.clear()
        await asyncio.to_thread(db.clear_token, uid)
        return JSONResponse({"error": "hf_token_revoked"}, status_code=401)
    if result is None:
        return JSONResponse({"error": "HF API returned no response"}, status_code=502)
    await asyncio.to_thread(db.clear_dash_cache, uid, "sigmarket_status")
    return {"ok": True}


# ── Analytics ──────────────────────────────────────────────────────────────────
#
# Fetches post FID distribution + thread views for any user.
# Uses requesting user's token (all data is public via Posts/Users scope).
# Cached 1hr per target UID under __system__ key — any viewer benefits from the
# same cached result.

ANALYTICS_CACHE_TTL = 3600  # 1 hour


@router.get("/analytics/{target_uid}")
async def user_analytics(target_uid: str, request: Request):
    try:
        return await asyncio.wait_for(_user_analytics(target_uid, request), timeout=30)
    except asyncio.TimeoutError:
        return JSONResponse({"error": "Analytics timed out — HF API was slow. Try again."}, status_code=504)

async def _user_analytics(target_uid: str, request: Request):
    uid, token, err = _auth(request)
    if err:
        return err

    # Validate target_uid is a valid integer
    try:
        target_int = int(target_uid)
    except ValueError:
        return JSONResponse({"error": "invalid uid"}, status_code=400)

    force = request.query_params.get("force") == "true"

    # Check cache first — keyed by target, shared across all requesters
    cache_key = f"siganalytics_{target_uid}"
    if not force:
        cached = await asyncio.to_thread(db.get_dash_cache, "__system__", cache_key, ANALYTICS_CACHE_TTL)
        if cached:
            return cached

    import math
    from HFClient import HFClient, get_rate_limit_remaining
    hf = HFClient(token)

    PERPAGE = 30

    # Bail early if rate limit is too low to safely run the scan
    remaining = get_rate_limit_remaining(token)
    if remaining < 30:
        return JSONResponse(
            {"error": f"Rate limit too low ({remaining} remaining) — try again shortly."},
            status_code=429
        )

    # ── Call 1: user profile + threads ────────────────────────────────────────
    # We need postnum/threadnum first to calculate the correct posts page.
    # posts._uid is OLDEST-FIRST — page 1 = their first ever posts.
    # Last page = ceil(reply_count / perpage).
    try:
        data1 = await asyncio.wait_for(hf.read({
            "users": {
                "_uid":       [target_int],
                "uid":        True,
                "username":   True,
                "postnum":    True,
                "threadnum":  True,
                "timeonline": True,
            },
            "threads": {
                "_uid":          [target_int],
                "_page":         1,
                "_perpage":      PERPAGE,
                "tid":           True,
                "fid":           True,
                "dateline":      True,
                "views":         True,
                "subject":       True,
                "lastpost":      True,
                "lastposteruid": True,
            },
        }), timeout=15)
    except _AuthExpired:
        request.session.clear()
        await asyncio.to_thread(db.clear_token, uid)
        return JSONResponse({"error": "hf_token_revoked"}, status_code=401)

    if not data1:
        return JSONResponse({"error": "HF API unavailable"}, status_code=503)

    # ── Parse user ────────────────────────────────────────────────────────────
    urows = data1.get("users", [])
    if isinstance(urows, dict): urows = [urows]
    user = urows[0] if urows else {}

    postnum   = int(user.get("postnum")   or 0)
    threadnum = int(user.get("threadnum") or 0)
    # reply_count = posts that are NOT thread OPs
    reply_count = max(1, postnum - threadnum)
    last_page   = math.ceil(reply_count / PERPAGE)

    # ── Calls 2-4: conservative forward scan ─────────────────────────────────
    # posts._uid is oldest-first. Max 3 pages forward — rapid sequential calls
    # to the same endpoint pattern trip CF and cascade into proxy rotations.
    # 1s sleep between pages keeps it clean. Most users land within 1-2 pages.
    posts: list = []
    true_last_page = last_page

    for try_page in range(last_page, last_page + 3):
        if try_page > last_page:
            await asyncio.sleep(1)
        try:
            pd = await asyncio.wait_for(hf.read({
                "posts": {
                    "_uid":     [target_int],
                    "_page":    try_page,
                    "_perpage": PERPAGE,
                    "pid":      True,
                    "fid":      True,
                    "dateline": True,
                    "tid":      True,
                },
            }), timeout=10)
        except _AuthExpired:
            request.session.clear()
            await asyncio.to_thread(db.clear_token, uid)
            return JSONResponse({"error": "hf_token_revoked"}, status_code=401)
        except Exception:
            break
        cur_raw = (pd or {}).get("posts", [])
        if isinstance(cur_raw, dict): cur_raw = [cur_raw]
        cur = [p for p in (cur_raw or []) if p.get("fid")]
        if not cur:
            break
        posts = cur
        true_last_page = try_page

    post_dates = sorted(
        [int(p["dateline"]) for p in posts if p.get("dateline")],
        reverse=True
    )

    # FID distribution {fid_str: count}
    fid_counts: dict[str, int] = {}
    for p in posts:
        fid = str(p["fid"])
        fid_counts[fid] = fid_counts.get(fid, 0) + 1

    # Thread diversity — unique threads they replied in
    unique_tids = len({str(p["tid"]) for p in posts if p.get("tid")})

    # ── Parse threads ─────────────────────────────────────────────────────────
    threads = data1.get("threads", [])
    if isinstance(threads, dict): threads = [threads]
    threads = threads or []

    thread_views = [int(t.get("views") or 0) for t in threads if t.get("views") is not None]

    # Thread creation dates
    thread_dates = sorted(
        [int(t["dateline"]) for t in threads if t.get("dateline")],
        reverse=True
    )
    last_thread_ts = thread_dates[0] if thread_dates else 0

    # Threads where the target user was the last poster — this catches replies
    # they made in their own threads, which posts._uid never returns.
    thread_lastpost_dates = [
        int(t["lastpost"])
        for t in threads
        if t.get("lastpost") and str(t.get("lastposteruid") or "") == str(target_uid)
    ]

    # ── Combined activity ─────────────────────────────────────────────────────
    # last_post_ts: max across all sources to catch OPs + own-thread replies
    all_dates = sorted(post_dates + thread_dates + thread_lastpost_dates, reverse=True)
    last_post_ts = all_dates[0] if all_dates else 0

    # posts_per_day: use ONLY post_dates (actual reply timestamps from last page).
    # thread_dates are creation datelines — an old thread Wake replied in last week
    # could have a dateline from 2019, exploding the span to years and tanking the rate.
    posts_per_day = 0.0
    if len(post_dates) >= 2:
        span_days = (post_dates[0] - post_dates[-1]) / 86400
        if span_days > 0:
            posts_per_day = round(len(post_dates) / span_days, 2)

    thread_fid_counts: dict[str, int] = {}
    for t in threads:
        fid = str(t.get("fid") or "")
        if fid:
            thread_fid_counts[fid] = thread_fid_counts.get(fid, 0) + 1

    result = {
        "uid":           target_uid,
        "username":      user.get("username", ""),
        "threadnum":     user.get("threadnum", "0"),
        "timeonline":    user.get("timeonline", "0"),
        # Post analysis
        "posts_sample":  len(posts),
        "last_post_ts":  last_post_ts,
        "posts_per_day": posts_per_day,
        "unique_tids":   unique_tids,
        "post_fid_dist": fid_counts,
        # Thread analysis
        "threads_sample":    len(threads),
        "last_thread_ts":    last_thread_ts,
        "thread_fid_dist":   thread_fid_counts,
        "thread_views": {
            "count": len(thread_views),
            "avg":   round(sum(thread_views) / len(thread_views)) if thread_views else 0,
            "max":   max(thread_views) if thread_views else 0,
            "total": sum(thread_views),
        },
    }

    await asyncio.to_thread(db.set_dash_cache, "__system__", cache_key, result)
    return result


# ── Browse market listings ─────────────────────────────────────────────────────────────
#
# Cache is pre-warmed by a background task every 25 min (called from main.py).
# Users NEVER trigger the scan — they always hit the in-memory cache.
# Cost: ~10 calls every 25 min, regardless of traffic. Zero per user request.

BROWSE_CACHE_TTL = 1800  # 30 min

_browse_cache: dict = {"ts": 0, "data": None}


def _load_browse_cache_from_db() -> bool:
    """Load persisted browse cache into memory on startup. Returns True if loaded."""
    try:
        cached = db.get_dash_cache("__system__", "sigmarket_browse", BROWSE_CACHE_TTL)
        if cached and cached.get("listings"):
            _browse_cache["data"] = cached
            _browse_cache["ts"]   = _time.time()
            return True
    except Exception:
        pass
    return False


async def _do_browse_fetch(token: str) -> dict | None:
    """Fetch all active sigmarket listings. Called by background pre-warmer."""
    from HFClient import HFClient, AuthExpired
    hf = HFClient(token)

    def _ask(page):
        return {"sigmarket": {
            "_type":    "market",
            "_page":    page,
            "_perpage": 30,
            "uid":      True,
            "price":    True,
            "duration": True,
            "active":   True,
            "sig":      True,
            "ppd":      True,
            "dateadded": True,
        }}

    active_rows = []
    had_errors  = False
    try:
        batch_size = 3
        page = 1
        while page <= 30:
            batch_pages = list(range(page, page + batch_size))
            results = await asyncio.wait_for(
                asyncio.gather(*[hf.read(_ask(p)) for p in batch_pages], return_exceptions=True),
                timeout=12,
            )
            got_short = False
            for res in results:
                if res is None or isinstance(res, Exception):
                    had_errors = True
                    got_short  = True
                    break
                rows = (res or {}).get("sigmarket") or []
                if isinstance(rows, dict):
                    rows = [rows]
                for r in (rows or []):
                    if int(r.get("active") or 0) == 1 and int(r.get("price") or 0) > 0:
                        active_rows.append(r)
                if len(rows) < 30:
                    got_short = True
                    break
            if got_short:
                break
            page += batch_size
    except asyncio.TimeoutError:
        had_errors = True
        if not active_rows:
            return None
    except AuthExpired:
        raise

    if had_errors and not active_rows:
        return None

    user_map = {}
    if active_rows:
        uids = list({int(r["uid"]) for r in active_rows if r.get("uid")})
        try:
            udata = await hf.read({
                "users": {
                    "_uid":       uids,
                    "uid":        True,
                    "username":   True,
                    "reputation": True,
                    "postnum":    True,
                }
            })
        except AuthExpired:
            raise
        urows = (udata or {}).get("users", [])
        if isinstance(urows, dict): urows = [urows]
        for u in (urows or []):
            user_map[str(u.get("uid"))] = u
        uid_name_map = {
            str(u.get("uid")): u.get("username", "")
            for u in (urows or []) if u.get("uid") and u.get("username")
        }
        if uid_name_map:
            try:
                await asyncio.to_thread(db.upsert_uid_usernames, uid_name_map)
            except Exception:
                pass

    listings = []
    for r in sorted(active_rows, key=lambda x: float(x.get("ppd") or 0), reverse=True):
        u = user_map.get(str(r.get("uid")), {})
        listings.append({
            "uid":        r.get("uid"),
            "username":   u.get("username") or f'UID {r.get("uid")}',
            "reputation": u.get("reputation", "0"),
            "postnum":    u.get("postnum", "0"),
            "price":      r.get("price"),
            "duration":   r.get("duration"),
            "ppd":        r.get("ppd"),
            "sig":        r.get("sig") or "",
            "dateadded":  r.get("dateadded"),
        })
    return {"listings": listings}


@router.get("/browse")
async def browse_listings(request: Request):
    uid, token, err = _auth(request)
    if err:
        return err

    force = request.query_params.get("force") == "true"

    if not force:
        if _browse_cache["data"] is not None and (_time.time() - _browse_cache["ts"]) < BROWSE_CACHE_TTL:
            return _browse_cache["data"]

    try:
        result = await _do_browse_fetch(token)
    except _AuthExpired:
        request.session.clear()
        await asyncio.to_thread(db.clear_token, uid)
        return JSONResponse({"error": "hf_token_revoked"}, status_code=401)

    if result is None:
        if _browse_cache["data"] is not None:
            return _browse_cache["data"]
        return JSONResponse({"error": "HF API timed out"}, status_code=504)

    if result.get("listings"):
        _browse_cache["data"] = result
        _browse_cache["ts"]   = _time.time()
        try:
            await asyncio.to_thread(db.set_dash_cache, "__system__", "sigmarket_browse", result)
        except Exception:
            pass
    return result


# ── Exported helpers for main.py scheduler ─────────────────────────────────────

async def warm_sigmarket_status(uid: str, token: str) -> None:
    """
    Pre-warm sigmarket_status cache for a user. Called by the unified scheduler every 15 min.

    Uses hf_service.get_or_fetch with the same _do_status_fetch as the route.
    No duplicate parse logic. In-flight dedup prevents double-fetch if route
    and warmer both fire at the same time.

    Only fetches if cache is not already fresh — if the route already refreshed
    within the TTL window, this is a no-op (zero HF calls).
    """
    import hf_cache as hfc
    cache_key = _SIG_STATUS_CACHE_KEY.format(uid=uid)

    # Skip if still fresh — saves 3 calls when warmer and route overlap
    if hfc.get_fresh(cache_key) is not None:
        log.debug("Sigmarket status warm skipped uid=%s (still fresh)", uid)
        return

    import hf_service
    try:
        data, _ = await hf_service.get_or_fetch(
            cache_key     = cache_key,
            resource_type = "sigmarket_status",
            fetch_fn      = lambda: _do_status_fetch(uid, token),
            uid           = uid,
            force         = True,
        )
        if data:
            so = data.get("seller_orders", [])
            bo = data.get("buyer_orders",  [])
            log.debug("Sigmarket status warmed uid=%s (%d sold, %d bought)",
                      uid, len(so), len(bo))
    except Exception as e:
        log.debug("Sigmarket status warm failed uid=%s: %s", uid, e)


def load_browse_cache_from_db() -> bool:
    """Public wrapper — called from main.py lifespan startup."""
    return _load_browse_cache_from_db()
