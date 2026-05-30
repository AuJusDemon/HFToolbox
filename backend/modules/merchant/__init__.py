"""
modules/merchant/__init__.py — Seller HQ module registration.

Seller operations layer: sales threads, replies, contracts, bumps, people.
Reads only from local DB tables already populated by existing crawlers/schedulers.
Zero HF API calls from this module.
"""

from module_registry import ModuleMeta, register
from fastapi import APIRouter
from modules.merchant.router import router as merchant_router

register(
    ModuleMeta(
        id="merchant",
        name="Seller HQ",
        description="Sales threads, replies, contracts, bumps, and repeat buyers in one seller view.",
        icon="MCH",
        category="market",
        api_cost="low",
        default_on=True,
    ),
    merchant_router,
)
