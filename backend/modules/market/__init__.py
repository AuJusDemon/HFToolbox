"""Market Pulse module registration."""

from module_registry import ModuleMeta, register
from modules.market.market_db import init_market_db
from modules.market.router import router

init_market_db()

register(
    ModuleMeta(
        id="market",
        name="Marketplace",
        description="Market activity, observed contracts, movers, and saved watches.",
        icon="MKT",
        category="market",
        api_cost="low",
        default_on=True,
    ),
    router,
)
