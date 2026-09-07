"""Authoritative fee rules for the Auto-Bump service."""

import json
from collections.abc import Iterable


HF_FEE_DEFAULT = 100
HF_FEE_UBER = 75
HF_FEE_VENDOR = 50
SERVICE_FEE = 10

HF_GROUP_L33T = "9"
HF_GROUP_UBER = "28"
HF_GROUP_VENDOR = "67"


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
    if HF_GROUP_VENDOR in group_ids:
        return HF_FEE_VENDOR
    if HF_GROUP_UBER in group_ids:
        return HF_FEE_UBER
    return HF_FEE_DEFAULT


def hf_fee_tier_for_groups(groups) -> str:
    group_ids = normalize_groups(groups)
    if HF_GROUP_VENDOR in group_ids:
        return "Vendor"
    if HF_GROUP_UBER in group_ids:
        return "Ub3r"
    if HF_GROUP_L33T in group_ids:
        return "L33t"
    return "standard"


def fee_breakdown(uid: str, groups, owner_uid: str | None = None) -> dict[str, int | str]:
    hf_fee = hf_fee_for_groups(groups)
    return {
        "hf_fee": hf_fee,
        "hf_fee_tier": hf_fee_tier_for_groups(groups),
        "service_fee": SERVICE_FEE,
        "total_cost": hf_fee + SERVICE_FEE,
    }
