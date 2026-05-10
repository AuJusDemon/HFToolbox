"""
scheduler.py — Background polling engine.

All DB calls run in asyncio.to_thread() to avoid blocking the event loop on Windows.
"""

import asyncio
import logging
import time
from typing import Callable, Awaitable

import db
from module_registry import all_modules

log = logging.getLogger("scheduler")

_handlers: dict[str, Callable[[str, str], Awaitable[None]]] = {}


def on_poll(module_id: str):
    def decorator(fn):
        _handlers[module_id] = fn
        return fn
    return decorator


async def _run_cycle(module_id: str) -> None:
    handler = _handlers.get(module_id)
    if not handler:
        return

    uids = await asyncio.to_thread(db.get_all_uids)
    if not uids:
        return

    uid   = uids[0]
    token = await asyncio.to_thread(db.get_token, uid)
    if not token:
        return

    try:
        await handler(uid, token)
    except Exception as e:
        log.exception("Poll cycle error module=%s: %s", module_id, e)


async def _module_loop(module_id: str, interval: int) -> None:
    log.info("Poll loop started: %s every %ds", module_id, interval)
    while True:
        start = time.monotonic()
        await _run_cycle(module_id)
        elapsed = time.monotonic() - start
        await asyncio.sleep(max(0, interval - elapsed))


async def start_scheduler() -> None:
    import modules  # noqa

    for meta in all_modules():
        if meta.polls and meta.id in _handlers:
            asyncio.create_task(
                _module_loop(meta.id, meta.poll_interval_seconds),
                name=f"poll:{meta.id}"
            )
            log.info("Scheduler started: %s (every %ds)", meta.id, meta.poll_interval_seconds)