"""Server-side operator gate for private owner-only endpoints."""

from __future__ import annotations

import os

from fastapi import HTTPException, Request

DEFAULT_OPERATOR_UIDS = {"761578"}


def operator_uids() -> set[str]:
    raw = os.environ.get("HFT_OPERATOR_UIDS", "").strip()
    if not raw:
        return set(DEFAULT_OPERATOR_UIDS)
    return {part.strip() for part in raw.split(",") if part.strip()}


def is_operator_uid(uid: object) -> bool:
    return str(uid or "") in operator_uids()


def require_operator(request: Request) -> str:
    uid = request.session.get("uid")
    if not uid:
        raise HTTPException(status_code=401, detail="unauthenticated")
    if not is_operator_uid(uid):
        raise HTTPException(status_code=404, detail="not found")
    return str(uid)
