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

    return await _acquire_and_fetch(cache_key, resource_type, fetch_fn, uid)


async def _acquire_and_fetch(
    cache_key:     str,
    resource_type: str,
    fetch_fn:      Callable[[], Awaitable[dict | None]],
    uid:           str,
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
        # sync DB call — must use to_thread
        data = await asyncio.to_thread(cache.get_fresh, cache_key)
        return data, False

    # We are the creator — do the actual fetch
    t0 = time.time()
    try:
        data = await asyncio.wait_for(fetch_fn(), timeout=20)
        ms   = int((time.time() - t0) * 1000)

        if data:
            # sync DB writes — must use to_thread
            await asyncio.to_thread(cache.set_cache, cache_key, resource_type, data, uid)
            await asyncio.to_thread(cache.log_call, uid, "read", resource_type,
                                    "", ms, True, -1, cache_key, "miss_live")
            return data, False

        await asyncio.to_thread(cache.log_call, uid, "read", resource_type,
                                "", ms, False, -1, cache_key, "miss_live_empty")
        return None, False

    except Exception as e:
        ms = int((time.time() - t0) * 1000)
        await asyncio.to_thread(cache.log_call, uid, "read", resource_type,
                                "", ms, False, -1, cache_key, "miss_error")
        log.warning("live fetch failed key=%s ms=%d: %s", cache_key, ms, e)
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
