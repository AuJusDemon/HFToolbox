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

        # Use cached status data to check for active orders — avoids a redundant HF API call.
        # Fall back to a live API call only if cache is cold (shouldn't happen in normal use).
        import db as _db
        cached = await asyncio.to_thread(_db.get_dash_cache, uid, "sigmarket_status", 600)
        if cached is not None:
            active_count = cached.get("active_order_count", 0)
        else:
            # Cache cold — fetch live
            hf_fallback = HFClient(token)
            uid_int = int(uid)
            data = await hf_fallback.read({
                "sigmarket": {
                    "_type":   "order",
                    "_seller": [uid_int],
                    "_page":   1,
                    "_perpage": 5,
                    "smid":    True,
                    "active":  True,
                    "enddate": True,
                }
            })
            orders = data.get("sigmarket", []) if data else []
            if isinstance(orders, dict):
                orders = [orders]
            active_count = sum(1 for o in orders if int(o.get("active", "0")))

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
