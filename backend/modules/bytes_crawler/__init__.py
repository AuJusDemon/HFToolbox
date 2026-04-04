"""
modules/bytes_crawler/__init__.py

Background crawler that gradually fetches the full bytes history for each user.
- Runs every 30 minutes
- Each cycle: fetches 1 recv page + 1 sent page (2 API calls)
- Once full history fetched, only polls page 1 for new transactions
- Stores everything in bytes_history table — dashboard reads from DB, not HF API
"""

import asyncio
import time
import logging

from module_registry import ModuleMeta, register
from .router import router
from scheduler import on_poll
import db

log = logging.getLogger("bytes_crawler")

register(ModuleMeta(
    id          = "bytes_crawler",
    name        = "Bytes History",
    description = "Background crawl of your full bytes history for analytics.",
    icon        = "📊",
    category    = "tools",
    api_cost    = "low",
    default_on  = True,
    polls       = True,
    poll_interval_seconds = 1800,
), router)


@on_poll("bytes_crawler")
async def poll_bytes_crawler(polling_uid: str, polling_token: str) -> None:
    """Crawl bytes history for all users, 1 page each direction per cycle."""
    from HFClient import HFClient

    uids = await asyncio.to_thread(db.get_all_uids)
    for uid in uids:
        token = await asyncio.to_thread(db.get_token, uid)
        if not token:
            continue
        try:
            await crawl_user(uid, token)
        except Exception as e:
            log.exception("Crawl error uid=%s: %s", uid, e)


async def crawl_user(uid: str, token: str) -> None:
    from HFClient import HFClient
    client  = HFClient(token)
    uid_int = int(uid)
    state   = await asyncio.to_thread(db.get_crawl_state, uid)
    now     = int(time.time())

    recv_done = bool(state["recv_done"])
    sent_done = bool(state["sent_done"])
    recv_page = int(state["recv_page"])
    sent_page = int(state["sent_page"])

    # Fetch recv page
    recv_page_to_fetch = 1 if recv_done else recv_page
    data_recv = await client.read({
        "bytes": {"_to": [uid_int], "_page": recv_page_to_fetch, "_perpage": 30,
                  "id": True, "amount": True, "dateline": True, "reason": True,
                  "type": True, "post": {"tid": True}},
    })
    recv_rows = (data_recv or {}).get("bytes", [])
    if isinstance(recv_rows, dict): recv_rows = [recv_rows]
    recv_txns = []
    for t in (recv_rows or []):
        if not t.get("id"): continue
        post = t.get("post") or {}
        if isinstance(post, list): post = post[0] if post else {}
        recv_txns.append({"id": t.get("id"), "amount": t.get("amount"),
                          "dateline": t.get("dateline"), "reason": t.get("reason"),
                          "type": str(t.get("type") or ""),
                          "post_tid": str(post.get("tid") or ""),
                          "sent": False})
    inserted_recv = await asyncio.to_thread(db.upsert_bytes_txns, uid, recv_txns)

    # Fetch sent page
    sent_page_to_fetch = 1 if sent_done else sent_page
    data_sent = await client.read({
        "bytes": {"_from": [uid_int], "_page": sent_page_to_fetch, "_perpage": 30,
                  "id": True, "amount": True, "dateline": True, "reason": True,
                  "type": True, "post": {"tid": True}},
    })
    sent_rows = (data_sent or {}).get("bytes", [])
    if isinstance(sent_rows, dict): sent_rows = [sent_rows]
    sent_txns = []
    for t in (sent_rows or []):
        if not t.get("id"): continue
        post = t.get("post") or {}
        if isinstance(post, list): post = post[0] if post else {}
        sent_txns.append({"id": t.get("id"), "amount": t.get("amount"),
                          "dateline": t.get("dateline"), "reason": t.get("reason"),
                          "type": str(t.get("type") or ""),
                          "post_tid": str(post.get("tid") or ""),
                          "sent": True})
    inserted_sent = await asyncio.to_thread(db.upsert_bytes_txns, uid, sent_txns)

    # Advance pages
    new_recv_page = recv_page
    new_sent_page = sent_page
    new_recv_done = recv_done
    new_sent_done = sent_done

    if not recv_done:
        if len(recv_rows) < 30:
            new_recv_done = True
            log.info("Recv history complete for uid=%s (%d pages)", uid, recv_page)
        else:
            new_recv_page = recv_page + 1

    if not sent_done:
        if len(sent_rows) < 30:
            new_sent_done = True
            log.info("Sent history complete for uid=%s (%d pages)", uid, sent_page)
        else:
            new_sent_page = sent_page + 1

    count = await asyncio.to_thread(db.get_bytes_history_count, uid)
    log.info("Crawl uid=%s recv_p=%d sent_p=%d new_txns=%d total=%d",
             uid, recv_page_to_fetch, sent_page_to_fetch,
             inserted_recv + inserted_sent, count)

    await asyncio.to_thread(db.update_crawl_state, uid,
        recv_page=new_recv_page, sent_page=new_sent_page,
        recv_done=int(new_recv_done), sent_done=int(new_sent_done),
        last_crawl=now)
