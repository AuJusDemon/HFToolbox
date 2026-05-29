"""
modules/merchant/router.py — Merchant HQ API endpoints.

All routes read from local DB only. Zero HF API calls.
"""

import asyncio
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Optional

router = APIRouter(prefix="/api/merchant", tags=["merchant"])


def _uid(r: Request) -> str:
    uid = r.session.get("uid")
    if not uid:
        raise HTTPException(401)
    return uid


# ── Read endpoints ─────────────────────────────────────────────────────────────

@router.get("/overview")
async def merchant_overview(request: Request):
    uid = _uid(request)
    from modules.merchant.service import get_overview
    return await asyncio.to_thread(get_overview, uid)


@router.get("/offers")
async def merchant_offers(request: Request,
                           status: Optional[str] = None,
                           sort: str = "health"):
    uid = _uid(request)
    from modules.merchant.service import get_offers
    return await asyncio.to_thread(get_offers, uid, status, sort)


@router.get("/offers/{tid}")
async def merchant_offer_detail(tid: str, request: Request):
    uid = _uid(request)
    from modules.merchant.service import get_offer_detail
    detail = await asyncio.to_thread(get_offer_detail, uid, tid)
    if not detail:
        raise HTTPException(404, "Offer not found")
    return detail


@router.get("/pipeline")
async def merchant_pipeline(request: Request):
    uid = _uid(request)
    from modules.merchant.service import get_pipeline
    return await asyncio.to_thread(get_pipeline, uid)


@router.get("/deals")
async def merchant_deals(request: Request, bucket: Optional[str] = None):
    uid = _uid(request)
    from modules.merchant.service import get_deals
    return await asyncio.to_thread(get_deals, uid, bucket)


@router.get("/customers")
async def merchant_customers(request: Request):
    uid = _uid(request)
    from modules.merchant.service import get_customers
    return await asyncio.to_thread(get_customers, uid)


@router.get("/customers/{cp_uid}")
async def merchant_customer_detail(cp_uid: str, request: Request):
    uid = _uid(request)
    from modules.merchant.service import get_customer_detail
    detail = await asyncio.to_thread(get_customer_detail, uid, cp_uid)
    if not detail:
        raise HTTPException(404, "Customer not found")
    return detail


@router.get("/promotion")
async def merchant_promotion(request: Request):
    uid = _uid(request)
    from modules.merchant.service import get_promotion
    return await asyncio.to_thread(get_promotion, uid)


@router.get("/reports/weekly")
async def merchant_weekly_report(request: Request, week: int = 0):
    uid = _uid(request)
    from modules.merchant.service import get_reports_weekly
    return await asyncio.to_thread(get_reports_weekly, uid, week)


@router.get("/freshness")
async def merchant_freshness(request: Request):
    uid = _uid(request)
    from modules.merchant.service import get_freshness
    return await asyncio.to_thread(get_freshness, uid)


# ── Workflow state mutations ────────────────────────────────────────────────────

class LeadGroupPatch(BaseModel):
    stage:       Optional[str] = None
    priority:    Optional[str] = None
    note:        Optional[str] = None
    followup_at: Optional[int] = None


@router.patch("/leads/{from_uid}/{tid}")
async def patch_lead_group(from_uid: str, tid: str, body: LeadGroupPatch, request: Request):
    uid = _uid(request)
    from modules.merchant.merchant_db import patch_lead_group as _patch
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "No fields to update")
    await asyncio.to_thread(_patch, uid, from_uid, tid, **updates)
    return {"ok": True}


class CustomerPatch(BaseModel):
    label:      Optional[str] = None
    note:       Optional[str] = None
    tags_json:  Optional[str] = None
    followup_at: Optional[int] = None


@router.patch("/customers/{cp_uid}")
async def patch_customer(cp_uid: str, body: CustomerPatch, request: Request):
    uid = _uid(request)
    from modules.merchant.merchant_db import patch_customer as _patch
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "No fields to update")
    await asyncio.to_thread(_patch, uid, cp_uid, **updates)
    return {"ok": True}


class OfferPatch(BaseModel):
    label:    Optional[str] = None
    category: Optional[str] = None
    status:   Optional[str] = None
    hidden:   Optional[bool] = None


@router.patch("/offers/{tid}")
async def patch_offer(tid: str, body: OfferPatch, request: Request):
    uid = _uid(request)
    from modules.merchant.merchant_db import patch_offer as _patch
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "No fields to update")
    await asyncio.to_thread(_patch, uid, tid, **updates)
    return {"ok": True}


class GoalsPatch(BaseModel):
    reply_sla_hours:    Optional[int] = None
    weekly_bump_budget: Optional[int] = None
    min_contract_value: Optional[int] = None


@router.get("/goals")
async def get_goals_endpoint(request: Request):
    uid = _uid(request)
    from modules.merchant.merchant_db import get_goals
    return await asyncio.to_thread(get_goals, uid)


@router.patch("/goals")
async def patch_goals(body: GoalsPatch, request: Request):
    uid = _uid(request)
    from modules.merchant.merchant_db import get_goals, upsert_goals
    current = await asyncio.to_thread(get_goals, uid)
    await asyncio.to_thread(
        upsert_goals, uid,
        body.reply_sla_hours    if body.reply_sla_hours    is not None else current['reply_sla_hours'],
        body.weekly_bump_budget if body.weekly_bump_budget is not None else current['weekly_bump_budget'],
        body.min_contract_value if body.min_contract_value is not None else current['min_contract_value'],
    )
    return {"ok": True}
