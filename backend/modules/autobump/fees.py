"""Authoritative fee rules for the Auto-Bump service."""

import json
import os
from collections.abc import Iterable


HF_FEE_DEFAULT = 100
HF_FEE_UBER = 75
HF_FEE_VENDOR = 50
SERVICE_FEE = 10


def normalize_groups(groups) -> set[str]:
    """Return stored HF groups as normalized string IDs."""
    if groups is None:
        return set()
    if isinstance(groups, str):
        raw = groups.strip()
        if not raw:
            return set()
        try:
            groups = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            groups = raw.split(",")
    if not isinstance(groups, Iterable) or isinstance(groups, (bytes, bytearray)):
        groups = [groups]
    return {str(group).strip() for group in groups if str(group).strip()}


def hf_fee_for_groups(groups) -> int:
    group_ids = normalize_groups(groups)
    if "67" in group_ids:
        return HF_FEE_VENDOR
    if "28" in group_ids:
        return HF_FEE_UBER
    return HF_FEE_DEFAULT


def fee_breakdown(uid: str, groups, owner_uid: str | None = None) -> dict[str, int]:
    owner_uid = os.getenv("PLATFORM_OWNER_UID", "") if owner_uid is None else str(owner_uid)
    hf_fee = hf_fee_for_groups(groups)
    service_fee = 0 if owner_uid and str(uid) == owner_uid else SERVICE_FEE
    return {
        "hf_fee": hf_fee,
        "service_fee": service_fee,
        "total_cost": hf_fee + service_fee,
    }
