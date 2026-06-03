"""
hf_service.py — Central HF API traffic controller.

This is the ONLY layer that should call HFClient.read / HFClient.write.
All modules call hf_service instead of touching HFClient directly.

Provides:
  get_or_fetch()          stale-while-revalidate + in-flight dedup (core)
  pick_best_token()       choose highest-budget token for global/public jobs
  invalidate_after_write() dirty exact cache keys after a write succeeds
  start_service()         start background refresh worker (call once from lifespan)

Usage from any module:

    import hf_service, hf_cache as hfc

    # Single-endpoint resource (most common)
    data, is_stale = await hf_service.get_or_fetch(
        cache_key     = f"user:{target_uid}:profile",
        resource_type = "user_profile",
        fetch_fn      = lambda: _do_profile_fetch(target_uid, token),
        uid           = uid,
    )

    # Multi-call resource (e.g. sigmarket status = 3 parallel reads)
    data, is_stale = await hf_service.get_or_fetch(
        cache_key     = f"sigmarket:status:{uid}",
        resource_type = "sigmarket_status",
        fetch_fn      = lambda: _fetch_sigmarket_status_live(uid, token),
        uid           = uid,
    )

    # After a write, dirty related caches
    hf_service.invalidate_after_write("bump", uid=uid, tid=tid, fid=fid)
"""

import asyncio
import logging
import time
from typing import Callable, Awaitable

import db
import hf_cache as cache

try:
    from HFClient import AuthExpired as _AuthExpired
except ImportError:
    class _AuthExpired(Exception):  # type: ignore[no-redef]
        pass

log = logging.getLogger("hf_service")


# ── In-flight dedup registry ───────────────────────────────────────────────────
#
# Prevents the "cache stampede" problem:
#   cache expires → 4 concurrent requests all miss → 4× HF calls fire
#
# Instead:
#   First caller acquires lock → does the HF call → signals Event
#   Other callers wait on the Event → read from cache when signalled

_inflight_lock  = asyncio.Lock()
_inflight: dict[str, asyncio.Event] = {}   # cache_key → asyncio.Event


# ── Background refresh queue ───────────────────────────────────────────────────
#
# Powers stale-while-revalidate: caller gets stale data instantly,
# refresh is queued here and runs without blocking the response.

_refresh_q: asyncio.Queue | None = None
_REFRESH_QUEUE_SIZE = 64


async def _refresh_worker() -> None:
    """Drain the background refresh queue. Runs as a long-lived asyncio task."""
    while True:
        if _refresh_q is None:
            await asyncio.sleep(5)
            continue
        try:
            item = await asyncio.wait_for(_refresh_q.get(), timeout=30)
        except asyncio.TimeoutError:
            continue
        except Exception:
            continue

        cache_key, resource_type, fetch_fn, uid = item
        try:
            # Skip if already fresh (something else refreshed while we were queued)
            if await asyncio.to_thread(cache.get_fresh, cache_key) is not None:
                continue
            # Skip if another live fetch is in-flight for this key
            if cache_key in _inflight:
                continue

            t0   = time.time()
            data = await asyncio.wait_for(fetch_fn(), timeout=20)
            ms   = int((time.time() - t0) * 1000)

            if data:
                await asyncio.to_thread(cache.set_cache, cache_key, resource_type, data, uid)
                await asyncio.to_thread(cache.log_call, uid, "read",
                                        f"bg:{resource_type}", "",
                                        ms, True, -1, cache_key, "stale_refresh")
                log.debug("bg refresh ok key=%s ms=%d", cache_key, ms)
        except Exception as e:
            log.warning("bg refresh failed key=%s: %s", cache_key, e)
        finally:
            try:
                _refresh_q.task_done()
            except Exception:
                pass


async def start_service() -> None:
    """
    Start the background refresh worker.
    Call exactly once from the FastAPI lifespan startup block.
    """
    global _refresh_q
    _refresh_q = asyncio.Queue(maxsize=_REFRESH_QUEUE_SIZE)
    asyncio.create_task(_refresh_worker())
    log.info("hf_service started (refresh queue size=%d)", _REFRESH_QUEUE_SIZE)


# ── Core: get_or_fetch ─────────────────────────────────────────────────────────

async def get_or_fetch(
    cache_key:     str,
    resource_type: str,
    fetch_fn:      Callable[[], Awaitable[dict | None]],
    uid:           str = "",
    force:         bool = False,
    fetch_timeout: int = 20,
) -> tuple[dict | None, bool]:
    """
    Stale-while-revalidate with in-flight deduplication.

    Returns (data, is_stale).

    Flow:
      Fresh cache (not forced)  → return immediately, is_stale=False
      Stale-but-usable          → return immediately + queue background refresh,
                                   is_stale=True
      No usable data, or force  → acquire in-flight lock:
          Another fetch running → wait for it, read from cache, return
          First caller          → call fetch_fn(), cache result, signal waiters

    fetch_fn is any async callable returning dict|None.
    It can do a single HFClient.read or 3 parallel reads — this layer doesn't care.
    """
    if not force:
        data, is_stale = await asyncio.to_thread(cache.get_usable, cache_key)
        if data is not None:
            if is_stale:
                _enqueue_refresh(cache_key, resource_type, fetch_fn, uid)
            return data, is_stale

    return await _acquire_and_fetch(cache_key, resource_type, fetch_fn, uid, fetch_timeout)


async def _acquire_and_fetch(
    cache_key:     str,
    resource_type: str,
    fetch_fn:      Callable[[], Awaitable[dict | None]],
    uid:           str,
    fetch_timeout: int = 20,
) -> tuple[dict | None, bool]:
    """In-flight dedup + live fetch. Called when cache is unusable or forced."""
    async with _inflight_lock:
        if cache_key in _inflight:
            event      = _inflight[cache_key]
            is_creator = False
        else:
            event      = asyncio.Event()
            _inflight[cache_key] = event
            is_creator = True

    if not is_creator:
        try:
            await asyncio.wait_for(event.wait(), timeout=25)
        except asyncio.TimeoutError:
            log.warning("in-flight wait timed out key=%s", cache_key)
        # Try usable cache first (fresh or stale-window), then any expired entry
        data, is_stale = await asyncio.to_thread(cache.get_usable, cache_key)
        if data is None:
            data = await asyncio.to_thread(cache.get_any, cache_key)
            if data is not None:
                return data, True
            return None, False
        return data, is_stale

    # We are the creator — do the actual fetch
    t0 = time.time()
    try:
        data = await asyncio.wait_for(fetch_fn(), timeout=fetch_timeout)
        ms   = int((time.time() - t0) * 1000)

        if data:
            # sync DB writes — must use to_thread
            await asyncio.to_thread(cache.set_cache, cache_key, resource_type, data, uid)
            await asyncio.to_thread(cache.log_call, uid, "read", resource_type,
                                    "", ms, True, -1, cache_key, "miss_live")
            return data, False

        await asyncio.to_thread(cache.log_call, uid, "read", resource_type,
                                "", ms, False, -1, cache_key, "miss_live_empty")
        # Fall back to any cached version (even fully expired) rather than returning None.
        # Stale data is always better than a 503 for the user.
        emergency = await asyncio.to_thread(cache.get_any, cache_key)
        if emergency:
            log.warning("live fetch returned nothing key=%s — serving expired cache", cache_key)
            return emergency, True
        return None, False

    except _AuthExpired:
        # Propagate so the route can clear the session and return 401.
        # Do not swallow auth errors as generic 503s.
        raise
    except Exception as e:
        ms = int((time.time() - t0) * 1000)
        await asyncio.to_thread(cache.log_call, uid, "read", resource_type,
                                "", ms, False, -1, cache_key, "miss_error")
        log.warning("live fetch failed key=%s ms=%d: %s", cache_key, ms, e)
        emergency = await asyncio.to_thread(cache.get_any, cache_key)
        if emergency:
            log.warning("fetch error key=%s — serving expired cache", cache_key)
            return emergency, True
        return None, False
    finally:
        event.set()
        async with _inflight_lock:
            _inflight.pop(cache_key, None)


def _enqueue_refresh(
    cache_key:     str,
    resource_type: str,
    fetch_fn:      Callable[[], Awaitable[dict | None]],
    uid:           str,
) -> None:
    """Queue a background refresh. Silently drops if queue is full or not started."""
    if _refresh_q is None:
        return
    try:
        _refresh_q.put_nowait((cache_key, resource_type, fetch_fn, uid))
    except asyncio.QueueFull:
        pass  # stale data stays until next natural refresh — acceptable


# ── Token selection ────────────────────────────────────────────────────────────

async def pick_best_token(exclude_uid: str = "") -> tuple[str | None, str | None]:
    """
    Pick the best token for a global/public job (browse warm, wire sync, etc).

    Strategy:
      1. Skip dead tokens and exclude_uid
      2. Prefer token with most remaining HF API calls
      3. Fall back to first available if no rate-limit data exists yet

    Returns (uid, token) or (None, None) if nothing is available.
    """
    try:
        from HFClient import _rate_limits as _rl
    except ImportError:
        _rl = {}

    uids = await asyncio.to_thread(db.get_all_uids)

    best_uid:   str | None = None
    best_token: str | None = None
    best_rem:   int        = -1

    for uid in uids:
        if uid == exclude_uid:
            continue
        dead = await asyncio.to_thread(db.is_token_dead, uid)
        if dead:
            continue
        token = await asyncio.to_thread(db.get_token, uid)
        if not token:
            continue
        # 9999 = no data yet (token hasn't been used this session) → treat as full
        remaining = _rl.get(token, 9999)
        if remaining > best_rem:
            best_rem   = remaining
            best_uid   = uid
            best_token = token

    return best_uid, best_token


# ── Write-triggered cache invalidation ────────────────────────────────────────

# Maps write action name → cache key templates to invalidate.
# Templates are filled with str.format(**kwargs) from caller-supplied values.
# Add entries here whenever a new write endpoint is added to the app.

_WRITE_INVALIDATIONS: dict[str, list[str]] = {
    "send_bytes": [
        "me:{uid}",
        "bytes:{uid}:from:p1",
    ],
    "recv_bytes": [
        "me:{uid}",
        "bytes:{uid}:to:p1",
    ],
    "vault": [
        "me:{uid}",
    ],
    "bump": [
        "thread:{tid}:meta",
        "threads:uid:{uid}:p1",
        "forum:{fid}:p1",
        "me:{uid}",
    ],
    "post_reply": [
        "thread:{tid}:meta",
        "threads:uid:{uid}:p1",
    ],
    "create_thread": [
        "threads:uid:{uid}:p1",
        "forum:{fid}:p1",
        "me:{uid}",
    ],
    "contract_action": [
        "contract:{cid}:detail",
        "contracts:{uid}:p1",
    ],
    "sigmarket_listing": [
        "sigmarket:status:{uid}",
        "sigmarket:browse",
    ],
    "sigmarket_buy": [
        "sigmarket:status:{uid}",
        "sigmarket:browse",
    ],
}


def invalidate_after_write(action: str, **kwargs) -> None:
    """
    Invalidate related caches after a successful write operation.

    Call immediately after any confirmed write — the next read will
    get fresh data instead of stale cached data.

    Examples:
        invalidate_after_write("bump",           uid="123456", tid="1000000", fid="106")
        invalidate_after_write("post_reply",     uid="123456", tid="1000000")
        invalidate_after_write("send_bytes",     uid="123456")
        invalidate_after_write("contract_action",uid="123456", cid="100000")
        invalidate_after_write("sigmarket_listing", uid="123456")
    """
    for pattern in _WRITE_INVALIDATIONS.get(action, []):
        try:
            key = pattern.format(**kwargs)
            cache.invalidate(key)
        except KeyError:
            pass  # pattern needs a kwarg not supplied — skip silently
        except Exception as e:
            log.debug("invalidate_after_write error pattern=%s: %s", pattern, e)


# ── Convenience wrappers ───────────────────────────────────────────────────────
# These are thin wrappers around get_or_fetch for the most common resource types.
# They exist to give modules a clean API without knowing about cache keys or types.

async def get_user_profile(target_uid: str, token: str,
                           force: bool = False) -> tuple[dict | None, bool]:
    """
    Fetch /users profile for any HF user. Global cache (not per-viewer).
    Used by: user lookup, sigmarket analytics, wire user resolution, contracts.
    """
    from HFClient import HFClient
    async def _fetch() -> dict | None:
        client = HFClient(token)
        return await client.read({"users": {
            "_uid":       [int(target_uid)],
            "uid":        True, "username": True, "usergroup": True,
            "displaygroup": True, "additionalgroups": True,
            "postnum":    True, "threadnum": True, "myps": True,
            "reputation": True, "usertitle": True, "timeonline": True,
            "avatar":     True, "awards": True, "website": True, "referrals": True,
        }})

    return await get_or_fetch(
        cache_key     = f"user:{target_uid}:profile",
        resource_type = "user_profile",
        fetch_fn      = _fetch,
        uid           = "",      # global, not per-viewer
        force         = force,
    )


async def get_thread_meta(tid: str, token: str,
                          force: bool = False) -> tuple[dict | None, bool]:
    """
    Fetch thread metadata by TID. Global cache.
    Used by: autobump (can skip batch fetch if fresh), contract detail, wire.
    """
    from HFClient import HFClient
    async def _fetch() -> dict | None:
        client = HFClient(token)
        return await client.read({"threads": {
            "_tid":          [int(tid)],
            "tid":           True, "fid":   True, "subject":      True,
            "lastpost":      True, "lastposteruid": True,
            "numreplies":    True, "firstpost": True, "closed":   True,
        }})

    return await get_or_fetch(
        cache_key     = f"thread:{tid}:meta",
        resource_type = "thread_meta",
        fetch_fn      = _fetch,
        uid           = "",
        force         = force,
    )


async def get_user_activity(target_uid: str, token: str,
                            force: bool = False) -> tuple[dict | None, bool]:
    """
    Fetch user profile + recent threads + recent posts for any HF user.
    Global cache per target UID - shared across all session viewers.
    Makes 2-3 bundled HF API calls on cold miss; instant from cache on hit.
    """
    from HFClient import HFClient

    async def _fetch() -> dict | None:
        client  = HFClient(token)
        target  = int(target_uid)
        PERPAGE = 20

        # Call 1: profile + threads page 1
        data1 = await client.read({
            "users": {
                "_uid": [target],
                "uid": True, "username": True, "usergroup": True,
                "displaygroup": True, "additionalgroups": True,
                "postnum": True, "threadnum": True, "myps": True,
                "reputation": True, "usertitle": True, "timeonline": True,
                "avatar": True, "awards": True, "website": True, "referrals": True,
            },
            "threads": {
                "_uid": [target], "_page": 1, "_perpage": PERPAGE,
                "tid": True, "fid": True, "subject": True, "dateline": True,
                "firstpost": True, "views": True, "lastpost": True,
                "closed": True, "sticky": True,
            },
        })
        if not data1:
            return None

        users_raw = data1.get("users", {})
        user = (users_raw[0] if isinstance(users_raw, list) else users_raw) or {}
        if not user:
            return None

        t1_raw = data1.get("threads", [])
        if isinstance(t1_raw, dict): t1_raw = [t1_raw]
        all_threads    = list(t1_raw or [])
        firstpost_pids = {str(t["firstpost"]) for t in all_threads if t.get("firstpost")}

        postnum     = int(user.get("postnum")   or 0)
        threadnum   = int(user.get("threadnum") or 0)
        reply_count = max(0, postnum - threadnum)
        # ceiling division without math import
        base_page   = max(1, -(-reply_count // PERPAGE))

        # Call 2: threads page 2 + posts estimated last page
        data2 = await client.read({
            "threads": {
                "_uid": [target], "_page": 2, "_perpage": PERPAGE,
                "tid": True, "fid": True, "subject": True, "dateline": True,
                "firstpost": True, "views": True, "lastpost": True,
                "closed": True, "sticky": True,
            },
            "posts": {
                "_uid": [target], "_page": base_page, "_perpage": PERPAGE,
                "pid": True, "tid": True, "fid": True,
                "dateline": True, "subject": True, "message": True,
            },
        })

        t2_raw = (data2 or {}).get("threads", [])
        if isinstance(t2_raw, dict): t2_raw = [t2_raw]
        if t2_raw:
            all_threads.extend(t2_raw)
            firstpost_pids.update(str(t["firstpost"]) for t in t2_raw if t.get("firstpost"))

        posts_raw = (data2 or {}).get("posts", [])
        if isinstance(posts_raw, dict): posts_raw = [posts_raw]
        raw_last = list(posts_raw or [])

        # Call 3 (conditional): grab the prev page for depth, or back off if estimate missed
        raw_prev   = []
        need_extra = (not raw_last and base_page > 1) or (raw_last and base_page > 1)
        if need_extra:
            try_page = base_page - 1
            if try_page >= 1:
                pd3 = await client.read({"posts": {
                    "_uid": [target], "_page": try_page, "_perpage": PERPAGE,
                    "pid": True, "tid": True, "fid": True,
                    "dateline": True, "subject": True, "message": True,
                }})
                p3 = (pd3 or {}).get("posts", [])
                if isinstance(p3, dict): p3 = [p3]
                p3 = list(p3 or [])
                if not raw_last:
                    raw_last = p3
                else:
                    raw_prev = p3

        # Combine, filter OP posts, sort newest-first
        seen, all_posts = set(), []
        for p in list(reversed(raw_last)) + list(reversed(raw_prev)):
            pid = str(p.get("pid", ""))
            if pid and pid not in firstpost_pids and pid not in seen:
                seen.add(pid)
                all_posts.append(p)
        all_posts.sort(key=lambda p: int(p.get("dateline") or 0), reverse=True)

        return {"user": user, "posts": all_posts, "threads": all_threads}

    return await get_or_fetch(
        cache_key     = f"user:{target_uid}:activity",
        resource_type = "user_activity",
        fetch_fn      = _fetch,
        uid           = "",   # global, not per-viewer
        force         = force,
    )


async def get_contract_detail(cid: int, token: str, force: bool = False) -> tuple[dict | None, bool]:
    # Caches raw contract + both party usernames globally; route resolves counterparty per viewer.
    from HFClient import HFClient
    async def _fetch() -> dict | None:
        client = HFClient(token)
        data = await client.read({
            "contracts": {
                "_cid": [int(cid)],
                "cid": True, "dateline": True, "status": True, "type": True,
                "istatus": True, "ostatus": True, "muid": True,
                "inituid": True, "otheruid": True,
                "iprice": True, "icurrency": True, "iproduct": True,
                "oprice": True, "ocurrency": True, "oproduct": True,
                "iaddress": True, "oaddress": True,
                "terms": True, "timeout_days": True, "timeout": True,
                "public": True, "tid": True, "idispute": True, "odispute": True,
            },
        })
        if not data:
            return None
        rows = data.get("contracts", [])
        if isinstance(rows, dict): rows = [rows]
        if not rows:
            return None
        c = rows[0]

        init_uid  = str(c.get("inituid")  or "")
        other_uid = str(c.get("otheruid") or "")
        party_uids = [u for u in [init_uid, other_uid] if u]

        # Resolve both party usernames: local cache first, then API fallback
        resolved: dict[str, str] = {}
        if party_uids:
            cached_names = await asyncio.to_thread(db.get_uid_usernames, party_uids)
            for u in party_uids:
                name = (cached_names.get(u) or {})
                if isinstance(name, dict):
                    name = name.get("username") or ""
                resolved[u] = str(name or "")

        missing = [u for u in party_uids if not resolved.get(u)]
        if missing:
            try:
                u_data = await client.read({
                    "users": {"_uid": [int(u) for u in missing], "uid": True, "username": True}
                })
                u_rows = u_data.get("users", []) if u_data else []
                if isinstance(u_rows, dict): u_rows = [u_rows]
                seed: dict[str, str] = {}
                for row in u_rows:
                    ru = str(row.get("uid") or "")
                    rn = str(row.get("username") or "")
                    if ru and rn:
                        resolved[ru] = rn
                        seed[ru] = rn
                if seed:
                    await asyncio.to_thread(db.upsert_uid_usernames, seed)
            except Exception:
                pass

        return {
            "contract":       c,
            "init_username":  resolved.get(init_uid,  ""),
            "other_username": resolved.get(other_uid, ""),
        }

    return await get_or_fetch(
        cache_key     = f"contract:{cid}:detail",
        resource_type = "contract_detail",
        fetch_fn      = _fetch,
        uid           = "",   # global, not per-viewer
        force         = force,
        fetch_timeout = 30,   # 2 sequential calls (contract + username); needs more than default 20s
    )


async def get_user_trust(
    target_uid: str,
    token: str,
    ratings_page: int = 1,
    force: bool = False,
) -> tuple[dict | None, bool]:
    from HFClient import HFClient
    async def _fetch() -> dict | None:
        client  = HFClient(token)
        target  = int(target_uid)
        PERPAGE = 15
        data = await client.read({
            "bratings": {
                "_to": [target], "_page": ratings_page, "_perpage": PERPAGE,
                "crid": True, "contractid": True, "fromid": True, "toid": True,
                "dateline": True, "amount": True, "message": True,
                "from": {"uid": True, "username": True},
            },
            "contracts": {
                "_uid": [target], "_page": 1, "_perpage": 30,
                "cid": True, "status": True, "type": True, "dateline": True,
            },
        })
        if not data:
            return None

        br_raw = data.get("bratings", [])
        if isinstance(br_raw, dict): br_raw = [br_raw]
        ratings = []
        for r in (br_raw or []):
            from_user = r.get("from") or {}
            if isinstance(from_user, list):
                from_user = from_user[0] if from_user else {}
            if isinstance(from_user, dict):
                from_username = str(from_user.get("username") or r.get("fromid") or "")
                from_uid      = str(from_user.get("uid")      or r.get("fromid") or "")
            else:
                from_username = str(r.get("fromid") or "")
                from_uid      = str(r.get("fromid") or "")
            try:
                amt = int(float(r.get("amount") or 0))
            except (TypeError, ValueError):
                amt = 0
            ratings.append({
                "crid":          str(r.get("crid") or ""),
                "contractid":    str(r.get("contractid") or ""),
                "from_uid":      from_uid,
                "from_username": from_username,
                "dateline":      int(r.get("dateline") or 0),
                "amount":        amt,
                "message":       str(r.get("message") or ""),
            })

        c_raw = data.get("contracts", [])
        if isinstance(c_raw, dict): c_raw = [c_raw]
        counts: dict[str, int] = {}
        for c in (c_raw or []):
            s = str(c.get("status") or "")
            counts[s] = counts.get(s, 0) + 1
        total     = sum(counts.values())
        complete  = counts.get("6", 0)
        disputed  = counts.get("7", 0)
        cancelled = counts.get("2", 0)
        active    = counts.get("5", 0)
        awaiting  = counts.get("1", 0)
        expired   = counts.get("8", 0)
        non_canc  = total - cancelled
        comp_rate = round(complete / non_canc * 100) if non_canc > 0 else 0
        disp_rate = round(disputed / non_canc * 100) if non_canc > 0 else 0

        return {
            "ratings":          ratings,
            "ratings_page":     ratings_page,
            "ratings_has_more": len(ratings) >= PERPAGE,
            "contract_stats": {
                "total":           total,
                "active":          active,
                "awaiting":        awaiting,
                "complete":        complete,
                "disputed":        disputed,
                "cancelled":       cancelled,
                "expired":         expired,
                "completion_rate": comp_rate,
                "dispute_rate":    disp_rate,
            },
        }

    return await get_or_fetch(
        cache_key     = f"user:{target_uid}:trust:p{ratings_page}",
        resource_type = "user_trust",
        fetch_fn      = _fetch,
        uid           = "",   # global, not per-viewer
        force         = force,
    )


async def get_sigmarket_analytics(
    target_uid: str,
    token: str,
    force: bool = False,
) -> tuple[dict | None, bool]:
    import math
    from HFClient import HFClient
    async def _fetch() -> dict | None:
        hf = HFClient(token)
        target_int = int(target_uid)
        PERPAGE = 30

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
        if not data1:
            return None

        urows = data1.get("users", [])
        if isinstance(urows, dict): urows = [urows]
        user = urows[0] if urows else {}

        postnum     = int(user.get("postnum")   or 0)
        threadnum   = int(user.get("threadnum") or 0)
        reply_count = max(1, postnum - threadnum)
        last_page   = math.ceil(reply_count / PERPAGE)

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
        fid_counts: dict[str, int] = {}
        for p in posts:
            fid = str(p["fid"])
            fid_counts[fid] = fid_counts.get(fid, 0) + 1
        unique_tids = len({str(p["tid"]) for p in posts if p.get("tid")})

        threads = data1.get("threads", [])
        if isinstance(threads, dict): threads = [threads]
        threads = threads or []
        thread_views = [int(t.get("views") or 0) for t in threads if t.get("views") is not None]
        thread_dates = sorted(
            [int(t["dateline"]) for t in threads if t.get("dateline")],
            reverse=True
        )
        last_thread_ts = thread_dates[0] if thread_dates else 0
        thread_lastpost_dates = [
            int(t["lastpost"])
            for t in threads
            if t.get("lastpost") and str(t.get("lastposteruid") or "") == str(target_uid)
        ]
        all_dates    = sorted(post_dates + thread_dates + thread_lastpost_dates, reverse=True)
        last_post_ts = all_dates[0] if all_dates else 0

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

        return {
            "uid":           target_uid,
            "username":      user.get("username", ""),
            "threadnum":     user.get("threadnum", "0"),
            "timeonline":    user.get("timeonline", "0"),
            "posts_sample":  len(posts),
            "last_post_ts":  last_post_ts,
            "posts_per_day": posts_per_day,
            "unique_tids":   unique_tids,
            "post_fid_dist": fid_counts,
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

    return await get_or_fetch(
        cache_key     = f"sigmarket:analytics:{target_uid}",
        resource_type = "sigmarket_analytics",
        fetch_fn      = _fetch,
        uid           = "",        # global, not per-viewer
        force         = force,
        fetch_timeout = 60,        # multi-call fetch with sleeps; outer route caps at 30s
    )


async def get_me(uid: str, token: str, force: bool = False) -> tuple[dict | None, bool]:
    """
    Fetch /me for the authenticated user.
    Note: the main crawl already keeps this fresh via dash_cache.
    Use this for on-demand refreshes or when crawl hasn't run yet.
    """
    from HFClient import HFClient
    async def _fetch() -> dict | None:
        client = HFClient(token)
        return await client.read({"me": {
            "uid":          True, "bytes":        True, "vault":        True,
            "postnum":      True, "threadnum":    True, "reputation":   True,
            "usertitle":    True, "timeonline":   True, "unreadpms":   True,
            "usergroup":    True, "displaygroup": True, "additionalgroups": True,
        }})

    return await get_or_fetch(
        cache_key     = f"me:{uid}",
        resource_type = "me",
        fetch_fn      = _fetch,
        uid           = uid,
        force         = force,
    )
