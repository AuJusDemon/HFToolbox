from __future__ import annotations

from typing import Any, Mapping

REPLY_COUNT_FIELDS = ("replies", "numreplies", "replycount", "reply_count")
POST_COUNT_FIELDS = ("posts", "numposts", "post_count")


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value if value is not None else default))
    except (TypeError, ValueError):
        return default


def has_thread_reply_count(thread: Mapping[str, Any] | None) -> bool:
    if not thread:
        return False
    return any(thread.get(field) is not None for field in REPLY_COUNT_FIELDS)


def thread_reply_count(
    thread: Mapping[str, Any] | None,
    default: int | None = 0,
) -> int:
    if not thread:
        return _as_int(default)
    for field in REPLY_COUNT_FIELDS:
        if thread.get(field) is not None:
            return max(0, _as_int(thread.get(field)))
    for field in POST_COUNT_FIELDS:
        if thread.get(field) is not None:
            return max(0, _as_int(thread.get(field)) - 1)
    return _as_int(default)


def has_thread_post_count(thread: Mapping[str, Any] | None) -> bool:
    if not thread:
        return False
    return any(thread.get(field) is not None for field in POST_COUNT_FIELDS)


def thread_post_count(
    thread: Mapping[str, Any] | None,
    default: int | None = 1,
) -> int:
    if not thread:
        return max(1, _as_int(default, 1))
    for field in POST_COUNT_FIELDS:
        if thread.get(field) is not None:
            return max(1, _as_int(thread.get(field), 1))
    if has_thread_reply_count(thread):
        return thread_reply_count(thread) + 1
    return max(1, _as_int(default, 1))
