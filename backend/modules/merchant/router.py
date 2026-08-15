"""
modules/merchant/router.py — Merchant HQ API endpoints.

All routes read from local DB only. Zero HF API calls.
"""

import asyncio
from fastapi import APIRouter, Request, HTTPException
from pydantic import BaseModel
from typing import Optional
from hf_thread_stats import thread_reply_count

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


@router.get("/freshness")
async def merchant_freshness(request: Request):
    """Return last-update timestamps for My Business data areas. Lightweight poll target."""
    uid = _uid(request)
    from modules.merchant.service import _get_crawl_freshness
    from modules.merchant.merchant_db import get_received_ratings_freshness
    data = await asyncio.to_thread(_get_crawl_freshness, uid)
    data["ratings_fresh_at"] = await asyncio.to_thread(get_received_ratings_freshness, uid)
    return data


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


@router.get("/thread-updates")
async def merchant_thread_updates(request: Request):
    uid = _uid(request)
    from modules.merchant.service import get_thread_updates
    return await asyncio.to_thread(get_thread_updates, uid)


class ThreadUpdatePost(BaseModel):
    message: str


def _result_post_id(result: dict | None) -> str:
    if not isinstance(result, dict):
        return ""
    posts = result.get("posts")
    if isinstance(posts, dict):
        for key in ("pid", "postid", "id"):
            if posts.get(key):
                return str(posts[key])
    return ""


@router.post("/thread-updates/{tid}/post")
async def merchant_post_thread_update(tid: str, body: ThreadUpdatePost, request: Request):
    uid = _uid(request)
    message = (body.message or "").strip()
    if len(message) < 5:
        raise HTTPException(400, "Write the thread update first")
    if len(message) > 20000:
        raise HTTPException(400, "Thread update is too long")

    from modules.merchant.service import get_offer_detail
    from modules.merchant.merchant_db import (
        create_thread_snapshot,
        create_thread_update,
        mark_thread_update_result,
    )
    offer = await asyncio.to_thread(get_offer_detail, uid, str(tid))
    if not offer:
        raise HTTPException(404, "Sales thread not found")
    if offer.get("closed"):
        raise HTTPException(400, "This sales thread is closed")

    def _as_int(*values):
        for value in values:
            try:
                if value is not None and value != "":
                    return int(value)
            except (TypeError, ValueError):
                continue
        return 0

    replies = _as_int(offer.get("numreplies"), offer.get("replies"))
    posts = _as_int(offer.get("post_count"), offer.get("posts"), replies + 1)
    baseline = {
        "views": offer.get("views", 0),
        "replies": replies,
        "posts": posts,
        "contracts_total": offer.get("contracts_total", 0),
        "contracts_active": offer.get("contracts_active", 0),
        "contracts_complete": offer.get("contracts_complete", 0),
    }
    await asyncio.to_thread(create_thread_snapshot, uid, str(tid), **baseline, source="pre_update")
    update = await asyncio.to_thread(create_thread_update, uid, str(tid), message, baseline)

    import db
    token = await asyncio.to_thread(db.get_token, uid)
    if not token:
        await asyncio.to_thread(
            mark_thread_update_result, uid, update["id"],
            status="failed", result_message="HF token missing", observed=baseline,
        )
        raise HTTPException(401, "HF login required")

    from hf_gateway_client import HFClient, AuthExpired
    hf = HFClient(token, owner_uid=uid, feature="merchant.thread_update", priority=2)
    try:
        result = await hf.write(
            {"posts": {"_tid": int(tid), "_message": message}},
            idempotency_key=update["id"],
        )
    except AuthExpired:
        await asyncio.to_thread(
            mark_thread_update_result, uid, update["id"],
            status="failed", result_message="HF token expired", observed=baseline,
        )
        raise HTTPException(401, "HF login expired")

    if not result:
        saved = await asyncio.to_thread(
            mark_thread_update_result, uid, update["id"],
            status="failed", result_message=hf.last_error or "HF write failed",
            observed=baseline,
        )
        raise HTTPException(502, saved.get("result_message") if saved else "HF write failed")

    saved = await asyncio.to_thread(
        mark_thread_update_result, uid, update["id"],
        status="posted", result_message="Posted through HF API",
        hf_pid=_result_post_id(result), observed=baseline,
    )
    return {"ok": True, "update": saved}


@router.post("/thread-updates/{tid}/op-draft")
async def merchant_create_op_draft(tid: str, request: Request):
    uid = _uid(request)
    from modules.merchant.service import get_offer_detail
    offer = await asyncio.to_thread(get_offer_detail, uid, str(tid))
    if not offer:
        raise HTTPException(404, "Sales thread not found")

    import db
    token = await asyncio.to_thread(db.get_token, uid)
    if not token:
        raise HTTPException(401, "HF login required")

    from _db_compat import _db
    with _db() as conn:
        row = conn.execute(
            "SELECT firstpost,fid,title FROM my_threads WHERE uid=? AND tid=?",
            (uid, str(tid)),
        ).fetchone()
    thread = dict(row) if row else {}
    firstpost = str(thread.get("firstpost") or "0")

    from hf_gateway_client import HFClient, AuthExpired
    hf = HFClient(token, owner_uid=uid, feature="merchant.op_draft_import", priority=3)
    try:
        if firstpost in ("", "0"):
            thread_result = await hf.read({
                "threads": {
                    "_tid": [int(tid)],
                    "tid": True, "fid": True, "subject": True, "firstpost": True,
                    "views": True, "numreplies": True, "replies": True,
                    "lastpost": True,
                }
            }, cache_ttl=0)
            thread_row = (thread_result or {}).get("threads")
            if isinstance(thread_row, list):
                thread_row = thread_row[0] if thread_row else {}
            if isinstance(thread_row, dict):
                firstpost = str(thread_row.get("firstpost") or firstpost)
                thread["fid"] = str(thread_row.get("fid") or thread.get("fid") or "")
                thread["title"] = str(thread_row.get("subject") or thread.get("title") or "")
                thread["numreplies"] = thread_reply_count(thread_row, thread.get("numreplies", 0))

        if firstpost in ("", "0"):
            raise HTTPException(404, "Opening post was not found")

        post_result = await hf.read({
            "posts": {"_pid": [int(firstpost)], "pid": True, "tid": True, "message": True, "subject": True}
        }, cache_ttl=0)
    except AuthExpired:
        raise HTTPException(401, "HF login expired")

    post_row = (post_result or {}).get("posts")
    if isinstance(post_row, list):
        post_row = post_row[0] if post_row else {}
    if not isinstance(post_row, dict) or not str(post_row.get("message") or "").strip():
        raise HTTPException(502, "Opening post content could not be imported")

    from modules.posting.posting_db import create_draft
    subject = f"OP rewrite - {offer.get('raw_title') or offer.get('title') or f'TID {tid}'}"
    draft_id = await asyncio.to_thread(
        create_draft,
        uid,
        str(thread.get("fid") or offer.get("fid") or ""),
        f"FID {thread.get('fid') or offer.get('fid') or ''}",
        subject[:250],
        str(post_row.get("message") or ""),
    )
    return {"ok": True, "draft_id": draft_id}


@router.get("/reports/weekly")
async def merchant_weekly_report(request: Request, week: int = 0):
    uid = _uid(request)
    from modules.merchant.service import get_reports_weekly
    return await asyncio.to_thread(get_reports_weekly, uid, week)


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


class ProductPatch(BaseModel):
    name: str


class ProductThreadPatch(BaseModel):
    tid: str
    excluded: bool = False


@router.post("/products", status_code=201)
async def create_product(body: ProductPatch, request: Request):
    uid = _uid(request)
    from modules.merchant.merchant_db import create_seller_product
    product = await asyncio.to_thread(create_seller_product, uid, body.name)
    if not product:
        raise HTTPException(400, "Product name is required")
    return product


@router.get("/products")
async def merchant_products(request: Request):
    uid = _uid(request)
    from modules.merchant.merchant_db import list_seller_products
    return {"products": await asyncio.to_thread(list_seller_products, uid)}


@router.patch("/products/{product_id}")
async def patch_product(product_id: str, body: ProductPatch, request: Request):
    uid = _uid(request)
    from modules.merchant.merchant_db import rename_seller_product
    if not await asyncio.to_thread(rename_seller_product, uid, product_id, body.name):
        raise HTTPException(404, "Product not found")
    return {"ok": True}


@router.delete("/products/{product_id}", status_code=204)
async def delete_product(product_id: str, request: Request):
    uid = _uid(request)
    from modules.merchant.merchant_db import delete_seller_product
    if not await asyncio.to_thread(delete_seller_product, uid, product_id):
        raise HTTPException(404, "Product not found")
    return None


@router.put("/products/{product_id}/thread")
async def put_product_thread(product_id: str, body: ProductThreadPatch, request: Request):
    uid = _uid(request)
    from modules.merchant.merchant_db import assign_product_thread
    if not await asyncio.to_thread(
        assign_product_thread, uid, product_id, body.tid, body.excluded
    ):
        raise HTTPException(404, "Product or owned sales thread not found")
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


class NotificationPreferences(BaseModel):
    telegram_replies: bool = False
    telegram_followups: bool = False
    telegram_ratings: bool = False


@router.get("/notification-preferences")
async def notification_preferences(request: Request):
    uid = _uid(request)
    from modules.merchant.merchant_db import get_notification_preferences
    return await asyncio.to_thread(get_notification_preferences, uid)


@router.put("/notification-preferences")
async def update_notification_preferences(body: NotificationPreferences, request: Request):
    uid = _uid(request)
    from modules.merchant.merchant_db import set_notification_preferences
    return await asyncio.to_thread(
        set_notification_preferences, uid, body.telegram_followups,
        body.telegram_ratings, body.telegram_replies,
    )


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
