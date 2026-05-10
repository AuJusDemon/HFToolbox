"""
modules/bytes_crawler/__init__.py

Background crawler that gradually fetches the full bytes history for each user.
Crawling is handled entirely by _bytes_crawl_loop in main.py (runs every 5 min,
activity-gated). This module only registers the metadata and exports the router.
The @on_poll handler is intentionally removed — running both caused double crawling.
"""

import asyncio
import time
import logging

from module_registry import ModuleMeta, register
from .router import router
import db

log = logging.getLogger("bytes_crawler")

register(ModuleMeta(
    id          = "bytes_crawler",
    name        = "Bytes History",
    description = "Background crawl of your full bytes history for analytics.",
    icon        = "📊",
    category    = "tools",
    api_cost    = "low",
    default_on  = True,
    polls       = False,  # crawl is handled by _bytes_crawl_loop in main.py
    poll_interval_seconds = 1800,
), router)
