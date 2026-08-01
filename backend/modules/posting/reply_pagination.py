"""Targeted posts._tid pagination for owned-thread reply tracking."""

import math


async def _read_page(client, tid: str, page: int, cached_pages: dict[int, list]) -> list:
    if page in cached_pages:
        return cached_pages[page]
    data = await client.read({"posts": {
        "_tid": [int(tid)], "_page": page, "_perpage": 30,
        "pid": True, "uid": True, "dateline": True,
        "message": True, "subject": True,
    }})
    if data is None:
        raise RuntimeError("HF returned no data")
    raw = data.get("posts", [])
    if isinstance(raw, dict):
        raw = [raw]
    cached_pages[page] = list(raw or [])
    return cached_pages[page]


async def find_last_posts_page(client, tid: str, cached_pages: dict[int, list]) -> int:
    """Find the final posts._tid page when thread metadata omits numreplies."""
    first = await _read_page(client, tid, 1, cached_pages)
    if len(first) < 30:
        return 1

    low, high = 1, 2
    while True:
        probe = await _read_page(client, tid, high, cached_pages)
        if len(probe) < 30:
            if probe:
                return high
            break
        low, high = high, high * 2

    while high - low > 1:
        middle = (low + high) // 2
        if await _read_page(client, tid, middle, cached_pages):
            low = middle
        else:
            high = middle
    return low


async def fetch_changed_thread_posts(client, tid: str, numreplies_hint: int | None) -> tuple[list, int]:
    """Fetch the final two pages of a changed thread and return posts plus count."""
    cached_pages: dict[int, list] = {}
    if numreplies_hint is None:
        last_page = await find_last_posts_page(client, tid, cached_pages)
    else:
        last_page = max(1, math.ceil((numreplies_hint + 1) / 30))

    pages = list(dict.fromkeys([max(1, last_page - 1), last_page]))
    collected: list = []
    for page in pages:
        collected.extend(await _read_page(client, tid, page, cached_pages))

    final_rows = len(cached_pages.get(last_page, []))
    reply_count = max(0, ((last_page - 1) * 30 + final_rows) - 1)
    return collected, reply_count
