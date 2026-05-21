from fastapi import APIRouter

from module_registry import ModuleMeta, register
from modules.bytes_crawler.router import router as bytes_router


def _metadata_only(
    *,
    id: str,
    name: str,
    description: str,
    icon: str,
    category: str,
    api_cost: str = "low",
    default_on: bool = True,
    badge: str | None = None,
) -> None:
    register(
        ModuleMeta(
            id=id,
            name=name,
            description=description,
            icon=icon,
            category=category,
            api_cost=api_cost,
            default_on=default_on,
            badge=badge,
        ),
        APIRouter(),
    )


register(
    ModuleMeta(
        id="bytes",
        name="Bytes",
        description="Balance, transaction history, analytics, send, and vault tools.",
        icon="BYT",
        category="dashboard",
        api_cost="medium",
    ),
    bytes_router,
)

_metadata_only(
    id="contracts",
    name="Contracts",
    description="Contract history, detail views, stats, analytics, and exports.",
    icon="CTR",
    category="dashboard",
    api_cost="medium",
)

_metadata_only(
    id="autobump",
    name="Auto Bumper",
    description="Schedule marketplace thread bumps with safety checks and spend tracking.",
    icon="BMP",
    category="tools",
    api_cost="medium",
)

_metadata_only(
    id="posting",
    name="Posting",
    description="Create, schedule, collaborate on, and reply to forum posts.",
    icon="PST",
    category="tools",
    api_cost="medium",
)

_metadata_only(
    id="sigmarket",
    name="Sig Market",
    description="Manage signature marketplace listings, orders, browsing, and rotation.",
    icon="SIG",
    category="market",
    api_cost="high",
)

_metadata_only(
    id="wire",
    name="The Wire",
    description="Curated thread/news workflow with replies, submissions, and curators.",
    icon="WIR",
    category="community",
    api_cost="low",
)
