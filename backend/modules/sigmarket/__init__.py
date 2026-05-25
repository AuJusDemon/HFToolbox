"""
modules/sigmarket/__init__.py — smart sig rotation background task.

Called from the unified scheduler in main.py every 30 minutes.

Rotation fires only when ALL of the following are true:
  1. enabled = 1
  2. At least 2 sigs in the array
  3. interval_h hours have elapsed since last_rotated
  4. User has at least one ACTIVE sig order (no point rotating if nobody sees it)
"""

import asyncio
import logging
import time

log = logging.getLogger("sigmarket")


async def poll_sigmarket_rotations(uid: str, token: str) -> None:
    """
    Check if this user's sig rotation is due and fire changesig if so.
    Called per-user from the unified scheduler.
    """
    from .sigmarket_db import get_rotation, advance_rotation
    from HFClient import HFClient

    try:
        rot = await asyncio.to_thread(get_rotation, uid)
        if not rot:
            return
        if not rot["enabled"]:
            return
        sigs = rot["sigs"]
        if len(sigs) < 2:
            return

        now = int(time.time())
        elapsed = now - (rot["last_rotated"] or 0)
        if elapsed < rot["interval_h"] * 3600:
            return

        # Use hf_cache to check for active orders — avoids a redundant HF API call.
        # The sigmarket status warmer keeps this fresh every 15 min.
        # Stale data is fine here — we just need to know if there are active orders.
        import hf_cache as _hfc
        cache_key = f"sigmarket:status:{uid}"
        cached_data = _hfc.get_fresh(cache_key)
        if cached_data is None:
            cached_data, _ = _hfc.get_usable(cache_key)  # accept stale
        if cached_data is not None:
            active_count = cached_data.get("active_order_count", 0)
        else:
            # Cache cold — fetch via hf_service (handles in-flight dedup)
            from .router import _do_status_fetch
            import hf_service
            data, _ = await hf_service.get_or_fetch(
                cache_key     = cache_key,
                resource_type = "sigmarket_status",
                fetch_fn      = lambda: _do_status_fetch(uid, token),
                uid           = uid,
            )
            active_count = (data or {}).get("active_order_count", 0)

        # Detect new sig order (sale) — fire once when active_order_count increases
        try:
            import db as _db_mod, integration_db as _idb
            _prev_data = _db_mod.get_dash_cache(uid, "sigmarket_order_count", max_age=86400 * 7)
            _prev_count = (_prev_data or {}).get("count", -1)
            if _prev_count >= 0 and active_count > _prev_count:
                import time as _t
                _new_sales = active_count - _prev_count
                _day = str(int(_t.time()) // 86400)
                await asyncio.to_thread(
                    _idb.create_alert_event,
                    uid, "sigmarket_sale", f"sigmarket_sale:{active_count}:{_day}",
                    f"Sig space sold — {active_count} active order{'s' if active_count != 1 else ''}",
                    f"{_new_sales} new buyer{'s' if _new_sales != 1 else ''} since last check.",
                    "https://hackforums.net/misc.php?action=sigmarket",
                    "toolbox", None, True,
                )
            if _prev_count != active_count:
                _db_mod.set_dash_cache(uid, "sigmarket_order_count", {"count": active_count})
        except Exception as _e:
            log.warning("Sigmarket sale alert failed uid=%s: %s", uid, _e)

        if active_count == 0:
            log.info("Sigmarket rotate uid=%s: no active orders, skipping", uid)
            return

        # Pick next sig
        next_idx = (rot["current_idx"] + 1) % len(sigs)
        next_sig = sigs[next_idx]

        hf = HFClient(token)
        result = await hf.write({
            "sigmarket": {
                "_type": "changesig",
                "_smid": "all",
                "_sig":  next_sig,
            }
        })

        if result is not None:
            await asyncio.to_thread(advance_rotation, uid, next_idx, now)
            log.info(
                "Sigmarket rotate uid=%s: rotated to idx=%d/%d after %dh",
                uid, next_idx, len(sigs) - 1, elapsed // 3600
            )
        else:
            log.warning("Sigmarket rotate uid=%s: changesig returned None", uid)

    except Exception as e:
        log.exception("Sigmarket rotate uid=%s error: %s", uid, e)
