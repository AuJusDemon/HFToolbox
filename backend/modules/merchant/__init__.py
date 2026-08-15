"""My Business module registration.

Seller operations layer: sales threads, replies, contracts, bumps, and buyers.
Reads only from local DB tables already populated by existing crawlers and schedulers.
Zero HF API calls from this module.
"""

from fastapi import APIRouter

from module_registry import ModuleMeta, register
from modules.merchant.router import router as merchant_router

register(
    ModuleMeta(
        id="merchant",
        name="My Business",
        description="Sales threads, replies, contracts, bumps, and repeat buyers in one seller view.",
        icon="MCH",
        category="market",
        api_cost="low",
        default_on=True,
    ),
    merchant_router,
)
