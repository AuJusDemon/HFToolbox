"""
modules/merchant/__init__.py — Merchant HQ module registration.

Seller operations layer: offers, leads, deals, customers, promotion, reports.
Reads only from local DB tables already populated by existing crawlers/schedulers.
Zero HF API calls from this module.
"""

from module_registry import ModuleMeta, register
from fastapi import APIRouter
from modules.merchant.router import router as merchant_router

register(
    ModuleMeta(
        id="merchant",
        name="Merchant HQ",
        description="Seller operations: offer performance, lead pipeline, deals, and customer history.",
        icon="MCH",
        category="market",
        api_cost="low",
        default_on=True,
    ),
    merchant_router,
)
