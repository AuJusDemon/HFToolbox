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


@router.post("/contracts/{cid}/complete-side")
async def merchant_complete_side(cid: str, request: Request):
    """Record that the seller has completed their side of a contract locally."""
    uid = _uid(request)
    from modules.merchant.merchant_db import mark_contract_completed_side
    await asyncio.to_thread(mark_contract_completed_side, uid, cid)
    return {"ok": True}


@router.get("/customers")
async def merchant_customers(request: Request, seller_only: bool = True):
    uid = _uid(request)
    from modules.merchant.service import get_customers
    return await asyncio.to_thread(get_customers, uid, seller_only)


@router.get("/customers/{cp_uid}")
async def merchant_customer_detail(cp_uid: str, request: Request):
    uid = _uid(request)
    from modules.merchant.service import get_customer_detail
    detail = await asyncio.to_thread(get_customer_detail, uid, cp_uid)
    if not detail:
        raise HTTPException(404, "Buyer not found")
    return detail


@router.get("/promotion")
async def merchant_promotion(request: Request):
    uid = _uid(request)
    from modules.merchant.service import get_promotion
    return await asyncio.to_thread(get_promotion, uid)


@router.get("/promotion/{tid}")
async def merchant_promotion_detail(tid: str, request: Request):
    uid = _uid(request)
    from modules.merchant.service import get_promotion_detail
    detail = await asyncio.to_thread(get_promotion_detail, uid, tid)
    if not detail:
        raise HTTPException(404, "Thread not found")
    return detail


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
    reply_sla_hours:             Optional[int] = None
    weekly_bump_budget:          Optional[int] = None
    weekly_completed_deal_goal:  Optional[int] = None
    max_stale_offer_days:        Optional[int] = None
    max_bumps_without_lead:      Optional[int] = None
    weekly_new_lead_goal:        Optional[int] = None


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
        body.reply_sla_hours            if body.reply_sla_hours            is not None else current['reply_sla_hours'],
        body.weekly_bump_budget         if body.weekly_bump_budget         is not None else current['weekly_bump_budget'],
        body.weekly_completed_deal_goal if body.weekly_completed_deal_goal is not None else current.get('weekly_completed_deal_goal', 0),
        body.max_stale_offer_days       if body.max_stale_offer_days       is not None else current.get('max_stale_offer_days', 30),
        body.max_bumps_without_lead     if body.max_bumps_without_lead     is not None else current.get('max_bumps_without_lead', 10),
        body.weekly_new_lead_goal       if body.weekly_new_lead_goal       is not None else current.get('weekly_new_lead_goal', 0),
    )
    return {"ok": True}


# ── PM Templates ───────────────────────────────────────────────────────────────

_NAME_MAX    = 120
_SUBJECT_MAX = 250
_BODY_MAX    = 10_000


class PMTemplateCreate(BaseModel):
    name:    str
    subject: Optional[str] = ''
    body:    Optional[str] = ''


class PMTemplatePatch(BaseModel):
    name:    Optional[str] = None
    subject: Optional[str] = None
    body:    Optional[str] = None


@router.get("/pm-templates")
async def list_pm_templates(request: Request):
    uid = _uid(request)
    from modules.merchant.merchant_db import (
        list_pm_templates as _list,
        seed_default_pm_templates as _seed,
    )
    templates = await asyncio.to_thread(_list, uid)
    if not templates:
        await asyncio.to_thread(_seed, uid)
        templates = await asyncio.to_thread(_list, uid)
    return templates


@router.post("/pm-templates", status_code=201)
async def create_pm_template(body: PMTemplateCreate, request: Request):
    uid = _uid(request)
    name    = (body.name    or '').strip()
    subject = (body.subject or '').strip()
    pm_body = (body.body    or '').strip()
    if not name:
        raise HTTPException(400, "name is required")
    if len(name) > _NAME_MAX:
        raise HTTPException(400, f"name exceeds {_NAME_MAX} characters")
    if len(subject) > _SUBJECT_MAX:
        raise HTTPException(400, f"subject exceeds {_SUBJECT_MAX} characters")
    if len(pm_body) > _BODY_MAX:
        raise HTTPException(400, f"body exceeds {_BODY_MAX} characters")
    from modules.merchant.merchant_db import create_pm_template as _create
    return await asyncio.to_thread(_create, uid, name, subject, pm_body)


@router.patch("/pm-templates/{template_id}")
async def update_pm_template(template_id: str, body: PMTemplatePatch, request: Request):
    uid = _uid(request)
    name    = body.name.strip()    if body.name    is not None else None
    subject = body.subject.strip() if body.subject is not None else None
    pm_body = body.body.strip()    if body.body    is not None else None
    if name is not None:
        if not name:
            raise HTTPException(400, "name cannot be empty")
        if len(name) > _NAME_MAX:
            raise HTTPException(400, f"name exceeds {_NAME_MAX} characters")
    if subject is not None and len(subject) > _SUBJECT_MAX:
        raise HTTPException(400, f"subject exceeds {_SUBJECT_MAX} characters")
    if pm_body is not None and len(pm_body) > _BODY_MAX:
        raise HTTPException(400, f"body exceeds {_BODY_MAX} characters")
    from modules.merchant.merchant_db import update_pm_template as _update
    updated = await asyncio.to_thread(_update, uid, template_id, name, subject, pm_body)
    if not updated:
        raise HTTPException(404, "Template not found")
    return {"ok": True}


@router.delete("/pm-templates/{template_id}", status_code=204)
async def delete_pm_template(template_id: str, request: Request):
    uid = _uid(request)
    from modules.merchant.merchant_db import delete_pm_template as _delete
    deleted = await asyncio.to_thread(_delete, uid, template_id)
    if not deleted:
        raise HTTPException(404, "Template not found")
