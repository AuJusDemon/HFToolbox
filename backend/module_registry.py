"""
module_registry.py

The entire plugin contract lives here.

To register a module:
    from module_registry import ModuleMeta, register
    from fastapi import APIRouter

    router = APIRouter(prefix="/modules/example")

    register(ModuleMeta(
        id          = "example",
        name        = "Example",
        description = "Does something.",
        icon        = "🔧",
        category    = "tools",
        api_cost    = "low",
    ), router)

That's it. The sidebar, settings toggle, and routing all happen automatically.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from fastapi import APIRouter


@dataclass
class ModuleMeta:
    id:          str                              # unique snake_case
    name:        str                              # display name in sidebar
    description: str                              # shown in settings
    icon:        str                              # emoji
    category:    str                              # groups sidebar sections
    api_cost:            str = "low"          # "low" | "medium" | "high" — shown as badge
    default_on:          bool = True          # enabled by default for new users
    badge:               str | None = None    # optional extra badge text
    polls:               bool = False         # True if module has a background poll handler
    poll_interval_seconds: int = 900          # how often to poll (default 15 min)


# Internal registry — don't touch directly
_registry: dict[str, tuple[ModuleMeta, APIRouter]] = {}


def register(meta: ModuleMeta, router: APIRouter) -> None:
    if meta.id in _registry:
        raise ValueError(f"Module '{meta.id}' is already registered.")
    _registry[meta.id] = (meta, router)


def all_modules() -> list[ModuleMeta]:
    return [m for m, _ in _registry.values()]


def all_routers() -> list[tuple[ModuleMeta, APIRouter]]:
    return list(_registry.values())
