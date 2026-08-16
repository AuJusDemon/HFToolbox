"""Local-first APIs for Market Pulse and paid Market Intelligence."""

from __future__ import annotations

import asyncio
import os
from typing import Literal

import db
import integration_db
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from hf_gateway_client import AuthExpired, HFClient
from modules.market import market_db

router = APIRouter(prefix="/api/market", tags=["market"])

OWNER_UID = str(os.environ.get("MARKET_TOKEN_UID", "")).strip()
PASS_PRICE = int(os.environ.get("MARKET_PASS_PRICE", "500"))
PASS_DAYS = int(os.environ.get("MARKET_PASS_DAYS", "30"))
PASS_PERMANENT = os.environ.get("MARKET_PASS_PERMANENT", "1") != "0"
WATCH_LIMIT = int(os.environ.get("MARKET_WATCH_LIMIT", "25"))
FREE_WATCH_LIMIT = int(os.environ.get("MARKET_FREE_WATCH_LIMIT", "3"))
# DEV ONLY: never enable this in production. It lets the collector owner preview
# real free-tier authorization behavior without changing or purchasing a pass.
ACCESS_PREVIEW_ENABLED = os.environ.get("MARKET_ACCESS_PREVIEW_ENABLED") == "1"


def _payment_reference(payment_id: str) -> str:
    compact = "".join(char for char in payment_id.upper() if char in "0123456789ABCDEF")
    return f"MP-{compact[:12]}"


def _market_fee_label(reference: str) -> str:
    return f"HFToolbox | Market Pass | Ref: {reference}"


def _uid(request: Request) -> str:
    uid = request.session.get("uid")
    if not uid:
        raise HTTPException(401, "Authentication required")
    return str(uid)


def _previewing_free(uid: str, request: Request | None = None) -> bool:
    return bool(
        ACCESS_PREVIEW_ENABLED and uid == OWNER_UID and request
        and request.session.get("market_access_preview") == "free"
    )


async def _paid(uid: str, request: Request | None = None) -> bool:
    if _previewing_free(uid, request):
        return False
    if uid == OWNER_UID:
        return True
    status = await asyncio.to_thread(market_db.access_status, uid)
    return bool(status["paid"])


async def _require_paid(uid: str, request: Request | None = None) -> None:
    if not await _paid(uid, request):
        raise HTTPException(402, "Market Intelligence pass required")


@router.get("/pulse")
async def market_pulse(request: Request):
    uid = _uid(request)
    paid = await _paid(uid, request)
    result = await asyncio.to_thread(market_db.pulse)
    if not (ACCESS_PREVIEW_ENABLED and uid == OWNER_UID):
        for key in ("threads", "sellers", "contracts", "forum_coverage", "contract_coverage", "latest_run"):
            result.pop(key, None)
    if not paid:
        for thread in result.get("recent_threads", []) + result.get("recent_buyer_threads", []):
            for key in (
                "observed_contracts", "active_contracts", "complete_contracts",
                "awaiting_contracts", "cancelled_contracts", "middleman_contracts",
                "disputed_contracts", "expired_contracts",
            ):
                thread.pop(key, None)
        result["categories"] = [
            {"category": row.get("category"), "wtb_threads": row.get("wtb_threads", 0)}
            for row in result.get("categories", [])
        ]
    else:
        from modules.merchant.merchant_db import seller_product_opportunities
        topics, mover_data, disputes, matches, opportunities = await asyncio.gather(
            asyncio.to_thread(market_db.list_topics, 30, 6),
            asyncio.to_thread(market_db.movers, 30),
            asyncio.to_thread(market_db.list_disputes, 1, 5),
            asyncio.to_thread(market_db.list_watch_matches, uid, 5),
            asyncio.to_thread(seller_product_opportunities, uid, 30, 5),
        )
        result["overview_topics"] = topics
        result["overview_movers"] = mover_data.get("threads", [])[:5]
        result["overview_disputes"] = disputes.get("disputes", [])
        result["overview_matches"] = matches
        result["overview_opportunities"] = opportunities
    return result


@router.get("/status")
async def market_status(request: Request):
    uid = _uid(request)
    if uid != OWNER_UID:
        await _require_paid(uid, request)
    return await asyncio.to_thread(market_db.collector_health)


@router.get("/threads")
async def market_threads(
    request: Request, page: int = 1, perpage: int = 25, fid: int | None = None,
    category: str = "", market_type: str = "", q: str = "",
    contract_only: bool = False, sort: str = "posted",
    sort_dir: str = "desc", days: int = 0, contract_status: str = "",
    topic_id: int | None = None,
):
    uid = _uid(request)
    paid = await _paid(uid, request)
    advanced_sorts = {
        "recent_contracts", "total_contracts", "complete_contracts",
        "active_contracts", "cancelled_contracts",
        "disputed_contracts", "expired_contracts",
    }
    if contract_status or sort in advanced_sorts:
        await _require_paid(uid, request)
    page = max(1, page)
    perpage = max(1, min(perpage, 50))
    effective_days = days
    if not paid:
        effective_days = 30 if not days else min(max(1, days), 30)
    return await asyncio.to_thread(
        market_db.list_threads, page, perpage, fid, category,
        market_type, q[:120], contract_only, sort, sort_dir, effective_days,
        contract_status, topic_id,
    )


@router.get("/threads/{tid}")
async def market_thread_detail(tid: int, request: Request):
    uid = _uid(request)
    paid = await _paid(uid, request)
    detail = await asyncio.to_thread(market_db.thread_detail, tid)
    if not detail:
        raise HTTPException(404, "Market thread not found")
    if not paid:
        if int(detail.get("created_at") or 0) < int(__import__("time").time()) - 30 * 86400:
            raise HTTPException(402, "Retained history requires Market Intelligence")
        detail.pop("contracts", None)
    return detail


@router.get("/categories")
async def market_categories(request: Request):
    _uid(request)
    pulse = await asyncio.to_thread(market_db.pulse)
    return {"categories": pulse["categories"], "generated_at": pulse["generated_at"]}


@router.get("/forums")
async def market_forums(request: Request):
    _uid(request)
    return {"forums": await asyncio.to_thread(market_db.list_forums)}


@router.get("/movers")
async def market_movers(request: Request, days: int = 30):
    uid = _uid(request)
    await _require_paid(uid, request)
    return await asyncio.to_thread(market_db.movers, days)


@router.get("/disputes")
async def market_disputes(request: Request, page: int = 1, perpage: int = 25):
    _uid(request)
    return await asyncio.to_thread(
        market_db.list_disputes, max(1, page), max(1, min(perpage, 50))
    )


@router.get("/access")
async def market_access(request: Request):
    uid = _uid(request)
    status = await asyncio.to_thread(market_db.access_status, uid)
    preview_free = _previewing_free(uid, request)
    if uid == OWNER_UID and not preview_free:
        status = {"paid": True, "expires_at": 4102444800}
    paid = bool(status["paid"])
    return {
        **status,
        "preview_available": ACCESS_PREVIEW_ENABLED and uid == OWNER_UID,
        "preview_mode": "free" if preview_free else "paid",
        "price": PASS_PRICE,
        "duration_days": PASS_DAYS,
        "permanent": PASS_PERMANENT,
        "receiver_uid": OWNER_UID,
        "watch_limit": WATCH_LIMIT if paid else FREE_WATCH_LIMIT,
        "free_watch_limit": FREE_WATCH_LIMIT,
        "paid_watch_limit": WATCH_LIMIT,
        "telegram_watch_alerts": paid,
        "entitlements": {
            "market_preview": True,
            "own_business": True,
            "individual_contract_actions": True,
            "explore_recent": True,
            "explore_history": paid,
            "history": paid,
            "advanced_filters": paid,
            "demand_detail": paid,
            "movers": paid,
            "disputes": True,
            "market_overlays": paid,
            "demand_matching": paid,
            "competitor_monitoring": paid,
            "advanced_reports": paid,
            "retained_history": paid,
            "telegram_alerts": paid,
        },
    }


class AccessPreviewRequest(BaseModel):
    mode: Literal["free", "paid"]


@router.post("/access/preview")
async def preview_market_access(body: AccessPreviewRequest, request: Request):
    uid = _uid(request)
    if not ACCESS_PREVIEW_ENABLED or uid != OWNER_UID:
        raise HTTPException(404, "Access preview is not available")
    if body.mode == "free":
        request.session["market_access_preview"] = "free"
    else:
        request.session.pop("market_access_preview", None)
    return {"ok": True, "mode": body.mode}


@router.get("/topics")
async def market_topics(request: Request, days: int = 30, limit: int = 20):
    uid = _uid(request)
    paid = await _paid(uid, request)
    rows = await asyncio.to_thread(market_db.list_topics, days if paid else 7, limit if paid else 8)
    if not paid:
        for row in rows:
            row.pop("observed_contracts", None)
            row.pop("completed_contracts", None)
    return {"topics": rows, "limited": not paid}


@router.get("/topics/{topic_id}")
async def market_topic_detail(topic_id: int, request: Request, days: int = 30):
    uid = _uid(request)
    await _require_paid(uid, request)
    result = await asyncio.to_thread(market_db.topic_detail, topic_id, days, True)
    if not result:
        raise HTTPException(404, "Demand topic not found")
    return result


@router.get("/my-business/overview")
async def my_business_overview(request: Request):
    uid = _uid(request)
    from modules.merchant.service import get_overview
    return await asyncio.to_thread(get_overview, uid)


@router.get("/my-business/contracts")
async def my_business_contracts(request: Request, workflow: str = "", scope: str = "sales"):
    uid = _uid(request)
    from modules.merchant.service import get_deals
    rows = await asyncio.to_thread(get_deals, uid, workflow or None)
    if isinstance(rows, dict):
        items = rows.get("deals", rows.get("contracts", []))
    else:
        items = rows
    if scope != "all":
        from modules.posting.posting_db import get_my_threads
        owned = {str(row.get("tid") or "") for row in await asyncio.to_thread(get_my_threads, uid)}
        items = [row for row in items if str(row.get("tid") or "") in owned]
    return {"contracts": items, "scope": scope}


@router.get("/my-business/opportunities")
async def my_business_opportunities(request: Request, days: int = 30, limit: int = 100):
    uid = _uid(request)
    await _require_paid(uid, request)
    from modules.merchant.merchant_db import seller_product_opportunities
    rows = await asyncio.to_thread(
        seller_product_opportunities, uid, max(1, min(days, 90)), max(1, min(limit, 100))
    )
    return {"opportunities": rows, "days": max(1, min(days, 90))}


class FollowupCreate(BaseModel):
    tid: str = ""
    counterparty_uid: str = ""
    template_id: str | None = None
    subject: str = Field(default="", max_length=250)
    body: str = Field(default="", max_length=10000)
    note: str = Field(default="", max_length=1000)


class FollowupCorrection(BaseModel):
    note: str = Field(default="", max_length=1000)


@router.get("/my-business/contracts/{cid}/followups")
async def followup_list(cid: str, request: Request):
    uid = _uid(request)
    from modules.merchant.merchant_db import list_followups
    return {"followups": await asyncio.to_thread(list_followups, uid, cid)}


@router.post("/my-business/contracts/{cid}/followups", status_code=201)
async def followup_create(cid: str, body: FollowupCreate, request: Request):
    uid = _uid(request)
    from modules.merchant.merchant_db import create_followup
    return await asyncio.to_thread(create_followup, uid, cid, body.tid,
                                   body.counterparty_uid, body.template_id,
                                   body.subject, body.body, body.note)


@router.post("/my-business/contracts/{cid}/followups/{event_id}/correct")
async def followup_correct(cid: str, event_id: str, body: FollowupCorrection, request: Request):
    uid = _uid(request)
    from modules.merchant.merchant_db import correct_followup
    if not await asyncio.to_thread(correct_followup, uid, event_id, body.note):
        raise HTTPException(404, "Follow-up record not found")
    return {"ok": True}


class PurchaseRequest(BaseModel):
    idempotency_key: str = Field(min_length=16, max_length=64)


@router.post("/access/purchase")
async def purchase_market_access(body: PurchaseRequest, request: Request):
    uid = _uid(request)
    if not OWNER_UID:
        raise HTTPException(503, "Market pass receiver is not configured")
    payment_id = body.idempotency_key.strip().lower()
    if not all(char in "0123456789abcdef-" for char in payment_id):
        raise HTTPException(400, "Invalid idempotency key")
    reference = _payment_reference(payment_id)
    fee_label = _market_fee_label(reference)
    controller_key = f"market-pass:{payment_id}"
    existing = await asyncio.to_thread(market_db.get_payment, payment_id, uid)
    if existing:
        if existing["status"] == "complete":
            status = await asyncio.to_thread(market_db.access_status, uid)
            return {
                "ok": True,
                "payment_id": payment_id,
                "reference": existing.get("reference") or reference,
                **status,
            }
        raise HTTPException(409, f"Payment is already {existing['status']}")
    token = await asyncio.to_thread(db.get_token, uid)
    if not token:
        raise HTTPException(401, "HF token unavailable")
    await asyncio.to_thread(
        market_db.create_payment,
        payment_id,
        uid,
        PASS_PRICE,
        0 if PASS_PERMANENT else PASS_DAYS,
        reference,
        OWNER_UID,
        fee_label,
        controller_key,
    )
    client = HFClient(
        token,
        owner_uid=uid,
        feature="market.pass.purchase",
        priority=1,
        background=False,
    )
    try:
        result = await client.write({
            "bytes": {
                "_uid": OWNER_UID,
                "_amount": str(PASS_PRICE),
                "_reason": fee_label,
            }
        }, idempotency_key=controller_key, safe_to_replay=False)
    except AuthExpired:
        await asyncio.to_thread(
            market_db.fail_payment, payment_id, "HF token expired"
        )
        raise HTTPException(401, "HF token expired")
    if result is None:
        if client.last_state == "held_by_controller":
            await asyncio.to_thread(
                market_db.hold_payment,
                payment_id,
                client.last_error or "held by controller",
            )
            raise HTTPException(
                503,
                "HF is busy right now; no bytes were confirmed and access was not activated",
            )
        await asyncio.to_thread(
            market_db.fail_payment,
            payment_id,
            client.last_error or "HF byte transfer failed",
        )
        raise HTTPException(502, "Byte transfer failed; access was not activated")
    expires = await asyncio.to_thread(
        market_db.complete_payment, payment_id, uid, PASS_DAYS, PASS_PERMANENT, result
    )
    return {
        "ok": True,
        "payment_id": payment_id,
        "reference": reference,
        "expires_at": expires,
    }


class WatchCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    required_phrase: str = Field(default="", max_length=240)
    optional_terms: list[str] = Field(default_factory=list, max_length=20)
    excluded_terms: list[str] = Field(default_factory=list, max_length=20)
    fids: list[int] = Field(default_factory=list, max_length=24)
    market_type: Literal["any", "wts", "wtb"] = "any"
    seller_uid: str = Field(default="", max_length=20)
    watch_kind: Literal["phrase", "topic", "category", "buyer_demand", "seller", "competitor_thread", "contract_movement", "owned_thread_activity"] = "phrase"
    topic_id: int | None = None
    category: str = Field(default="", max_length=40)
    thread_tid: int | None = None
    telegram_enabled: bool = False


@router.get("/watches")
async def market_watches(request: Request, page: int = 1, perpage: int = 25):
    uid = _uid(request)
    paid = await _paid(uid, request)
    watches, match_page, telegram = await asyncio.gather(
        asyncio.to_thread(market_db.list_watches, uid),
        asyncio.to_thread(market_db.list_watch_matches_page, uid, page, perpage),
        asyncio.to_thread(integration_db.get_telegram_link, uid),
    )
    return {
        "watches": watches, **match_page,
        "telegram_connected": bool(telegram),
        "telegram_delivery_available": bool(telegram)
        and paid and os.environ.get("DEV_DISABLE_TELEGRAM") != "1",
        "paid": paid,
        "watch_limit": WATCH_LIMIT if paid else FREE_WATCH_LIMIT,
    }


@router.post("/watches", status_code=201)
async def create_market_watch(body: WatchCreate, request: Request):
    uid = _uid(request)
    paid = await _paid(uid, request)
    current = await asyncio.to_thread(market_db.list_watches, uid)
    limit = WATCH_LIMIT if paid else FREE_WATCH_LIMIT
    if len(current) >= limit:
        raise HTTPException(409, f"Watch limit reached ({limit})")
    data = body.model_dump()
    paid_only_kinds = {"topic", "buyer_demand", "seller", "competitor_thread", "contract_movement", "owned_thread_activity"}
    if data["watch_kind"] in paid_only_kinds and not paid:
        raise HTTPException(402, "Market Intelligence is required for this alert type")
    if data["telegram_enabled"]:
        if not paid:
            raise HTTPException(
                402, "Market Intelligence is required for Telegram watch alerts"
            )
        if os.environ.get("DEV_DISABLE_TELEGRAM") == "1":
            raise HTTPException(409, "Telegram delivery is disabled in this environment")
        if not await asyncio.to_thread(integration_db.get_telegram_link, uid):
            raise HTTPException(409, "Connect Telegram before enabling Telegram alerts")
    data["optional_terms"] = [
        term.strip()[:80] for term in data["optional_terms"] if term.strip()
    ]
    data["excluded_terms"] = [
        term.strip()[:80] for term in data["excluded_terms"] if term.strip()
    ]
    data["fids"] = [fid for fid in data["fids"] if fid in market_db.MARKET_FIDS]
    has_target = bool(
        data["required_phrase"].strip() or data["optional_terms"] or data["seller_uid"]
        or data["topic_id"] or data["category"] or data["thread_tid"]
        or data["watch_kind"] in {"contract_movement", "owned_thread_activity"}
    )
    if not has_target:
        raise HTTPException(400, "Add a phrase, topic, category, seller UID, or thread TID")
    watch_id = await asyncio.to_thread(market_db.create_watch, uid, data)
    return {"ok": True, "id": watch_id}


@router.delete("/watches/{watch_id}")
async def delete_market_watch(watch_id: int, request: Request):
    uid = _uid(request)
    deleted = await asyncio.to_thread(market_db.delete_watch, uid, watch_id)
    if not deleted:
        raise HTTPException(404, "Watch not found")
    return {"ok": True}


class CollectRequest(BaseModel):
    fids: list[int] = Field(min_length=1, max_length=6)
    max_calls: int = Field(default=10, ge=1, le=15)


@router.post("/admin/collect")
async def manual_market_collection(body: CollectRequest, request: Request):
    _uid(request)
    raise HTTPException(
        410,
        "Manual marketplace collection has moved to the private collector service",
    )
