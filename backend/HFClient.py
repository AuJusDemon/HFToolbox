"""Application adapter for the dedicated HF control-plane service.

No application module may contact Hack Forums directly. This adapter preserves
the former HFClient interface while submitting every operation to the internal
dispatcher.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import time
import uuid

import aiohttp
import requests


_rate_limits: dict[str, int] = {}
_rate_limit_seen_at: dict[str, float] = {}
_last_circuit = {"available": True, "retry_after_seconds": 0, "reason": "",
                 "last_status": 0, "failure_count": 0}
_floor_cache: dict[str, tuple[float, int]] = {}

_CIRCUIT_ERRORS = {
    "global_circuit_open",
    "control_plane_unavailable",
    "upstream_unavailable",
    "token_cooldown",
    "rate_limited",
    "http_403",
    "http_429",
    "http_502_503",
    "html_challenge",
    "cloudflare_challenge",
}


def _is_circuit_error(error: str) -> bool:
    error = (error or "").strip().lower()
    return bool(error) and any(marker in error for marker in _CIRCUIT_ERRORS)


def _user_background_floor_sync(owner_uid: str) -> int:
    uid = str(owner_uid or "").strip()
    if not uid:
        return 0
    cached = _floor_cache.get(uid)
    if cached and time.time() - cached[0] < 30:
        return cached[1]
    try:
        import db
        settings = db.get_user_settings(uid)
        floor = int(settings.get("apiFloor", 30)) if settings.get("apiFloorEnabled", False) else 0
    except Exception:
        floor = 0
    floor = max(0, min(240, floor))
    _floor_cache[uid] = (time.time(), floor)
    return floor


async def _user_background_floor(owner_uid: str) -> int:
    import asyncio
    return await asyncio.to_thread(_user_background_floor_sync, owner_uid)


class AuthExpired(Exception):
    pass


def _settings() -> tuple[str, str, str]:
    return (
        os.environ["HF_CONTROL_PLANE_URL"].rstrip("/"),
        os.environ.get("HF_CONTROL_PLANE_CALLER", "dev"),
        os.environ["HF_CONTROL_PLANE_SECRET"],
    )


def _app_name() -> str:
    return os.environ.get("HF_CONTROL_PLANE_APP", "toolbox-prod")


def _headers(body: bytes) -> dict[str, str]:
    _, caller, secret = _settings()
    timestamp = str(int(time.time()))
    nonce = secrets.token_hex(24)
    signed = timestamp.encode() + b"." + nonce.encode() + b"." + body
    signature = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return {
        "content-type": "application/json",
        "x-hft-caller": caller,
        "x-hft-timestamp": timestamp,
        "x-hft-nonce": nonce,
        "x-hft-signature": signature,
    }


async def _get(path: str, timeout: int = 15) -> dict:
    base, _, _ = _settings()
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=timeout)) as session:
            async with session.get(base + path, headers=_headers(b"")) as response:
                if response.status >= 400:
                    return {"state": "failed", "error_code": f"control_plane_http_{response.status}"}
                return await response.json()
    except Exception:
        return {"state": "failed", "error_code": "control_plane_unavailable"}


async def _submit(data: dict, timeout: int = 42, endpoint: str = "/internal/v1/request") -> dict:
    global _last_circuit
    base, _, _ = _settings()
    body = json.dumps(data, separators=(",", ":")).encode()
    client_timeout = aiohttp.ClientTimeout(total=timeout)
    try:
        async with aiohttp.ClientSession(timeout=client_timeout) as session:
            async with session.post(base + endpoint, data=body,
                                    headers=_headers(body)) as response:
                if response.status >= 400:
                    error = f"control_plane_http_{response.status}"
                    _last_circuit = {
                        "available": False,
                        "retry_after_seconds": 60 if response.status == 429 else 30,
                        "reason": error,
                        "last_status": response.status,
                        "failure_count": 1,
                    }
                    return {"state": "failed", "result": None, "error_code": error}
                value = await response.json()
            remaining = value.get("remaining")
            token = str(data.get("token") or "")
            if remaining is not None and token:
                _rate_limits[token] = int(remaining)
                _rate_limit_seen_at[token] = time.time()
            error = str(value.get("error_code") or "")
            if error == "global_circuit_open":
                _last_circuit = {"available": False, "retry_after_seconds": 1,
                                 "reason": error, "last_status": 0,
                                 "failure_count": 1}
            elif _is_circuit_error(error):
                _last_circuit = {"available": False, "retry_after_seconds": 60,
                                 "reason": error, "last_status": 0,
                                 "failure_count": 1}
            elif value.get("state") == "succeeded":
                _last_circuit = {"available": True, "retry_after_seconds": 0,
                                 "reason": "", "last_status": 0,
                                 "failure_count": 0}
            return value
    except Exception:
        return {"state": "failed", "result": None,
                "error_code": "control_plane_unavailable"}


def submit_sync(data: dict, timeout: int = 42) -> dict:
    base, _, _ = _settings()
    body = json.dumps(data, separators=(",", ":")).encode()
    response = requests.post(base + "/internal/v1/request", data=body,
                             headers=_headers(body), timeout=timeout)
    response.raise_for_status()
    return response.json()


def read_sync(token: str, asks: dict, *, owner_uid: str = "",
              feature: str = "maintenance_probe", priority: int = 8) -> dict | None:
    response = submit_sync({
        "token": token, "owner_uid": owner_uid, "app": _app_name(), "feature": feature,
        "route": "read", "payload": asks, "priority": priority,
        "background": True, "background_floor": _user_background_floor_sync(owner_uid),
        "privacy_scope": "private", "cache_ttl": 0,
        "stale_ttl": 0,
    })
    return response.get("result") if response.get("state") == "succeeded" else None


async def submit_background(token: str, asks: dict, *, owner_uid: str,
                            feature: str, priority: int = 8,
                            privacy_scope: str = "private") -> dict:
    floor = await _user_background_floor(owner_uid)
    return await _submit({
        "token": token, "owner_uid": owner_uid, "app": _app_name(), "feature": feature,
        "route": "read", "payload": asks, "priority": priority,
        "background": True, "background_floor": floor, "privacy_scope": privacy_scope,
        "cache_ttl": 0, "stale_ttl": 0,
    }, endpoint="/internal/v1/background")


async def get_result(request_id: str) -> dict:
    return await _get(f"/internal/v1/result/{request_id}")


async def get_status() -> dict:
    return await _get("/internal/v1/status")


def get_rate_limit_remaining(token: str) -> int:
    return int(_rate_limits.get(token, 9999))


def get_rate_limit_state(token: str) -> dict:
    seen = float(_rate_limit_seen_at.get(token, 0) or 0)
    age = max(0, int(time.time() - seen)) if seen else None
    return {"remaining": _rate_limits.get(token), "observed_at": int(seen) if seen else None,
            "age_seconds": age, "stale": age is None or age > 3900}


def get_circuit_status(token: str | None = None, route: str = "read") -> dict:
    return dict(_last_circuit)


class HFClient:
    def __init__(self, token: str, *, owner_uid: str = "", feature: str = "interactive",
                 priority: int = 3, background: bool = False,
                 route_class: str = "", egress_lane: str = ""):
        self.token = token
        self.owner_uid = owner_uid
        self.feature = feature
        self.priority = priority
        self.background = background
        self.route_class = route_class
        self.egress_lane = egress_lane
        self.last_error = ""

    async def read(self, asks: dict, **options) -> dict | None:
        owner_uid = str(options.get("owner_uid", self.owner_uid) or "")
        background = bool(options.get("background", self.background))
        floor = await _user_background_floor(owner_uid) if background else 0
        route_class = str(options.get("route_class", self.route_class) or "")
        egress_lane = str(options.get("egress_lane", self.egress_lane) or "")
        if background:
            route_class = route_class or "background"
            egress_lane = egress_lane or "background"
        response = await _submit({
            "token": self.token, "owner_uid": owner_uid,
            "app": _app_name(),
            "feature": options.get("feature", self.feature), "route": "read",
            "payload": asks, "priority": options.get("priority", self.priority),
            "route_class": route_class or "normal",
            "egress_lane": egress_lane or "critical",
            "background": background, "background_floor": floor,
            "privacy_scope": options.get("privacy_scope", "private"),
            "cache_ttl": options.get("cache_ttl", 5),
            "stale_ttl": options.get("stale_ttl", 300),
        }, timeout=310 if background else 52)
        if response.get("error_code") == "auth_expired":
            raise AuthExpired()
        self.last_error = str(response.get("error_code") or "")
        return response.get("result") if response.get("state") == "succeeded" else None

    async def write(self, asks: dict, **options) -> dict | None:
        if os.environ.get("DEV_DISABLE_HF_WRITES") == "1":
            return None
        payload_json = json.dumps(asks, sort_keys=True, separators=(",", ":"))
        fallback_key = hashlib.sha256(
            f"{self.owner_uid}:{self.feature}:{int(time.time()) // 60}:{payload_json}".encode()
        ).hexdigest()
        owner_uid = str(options.get("owner_uid", self.owner_uid) or "")
        background = bool(options.get("background", self.background))
        floor = await _user_background_floor(owner_uid) if background else 0
        route_class = str(options.get("route_class", self.route_class) or "")
        egress_lane = str(options.get("egress_lane", self.egress_lane) or "")
        if background:
            route_class = route_class or "background"
            egress_lane = egress_lane or "background"
        response = await _submit({
            "token": self.token, "owner_uid": owner_uid,
            "app": _app_name(),
            "feature": options.get("feature", self.feature), "route": "write",
            "payload": asks, "priority": options.get("priority", min(self.priority, 2)),
            "route_class": route_class or "high",
            "egress_lane": egress_lane or "critical",
            "background": background, "background_floor": floor,
            "privacy_scope": "private", "cache_ttl": 0, "stale_ttl": 0,
            "idempotency_key": options.get("idempotency_key") or fallback_key,
        })
        if response.get("error_code") == "auth_expired":
            raise AuthExpired()
        return response.get("result") if response.get("state") == "succeeded" else None

    async def ping(self) -> bool:
        try:
            result = await self.read({"me": {"uid": True}}, priority=1, cache_ttl=0)
            return bool(result and "me" in result)
        except AuthExpired:
            return False


async def exchange_code_for_token(code: str, cfg: dict):
    response = await _submit({
        "token": "oauth-exchange-placeholder", "owner_uid": "", "app": _app_name(), "feature": "oauth",
        "route": "oauth", "payload": {"code": code, "config": cfg}, "priority": 1,
        "background": False, "background_floor": 0, "privacy_scope": "private", "cache_ttl": 0,
        "stale_ttl": 0,
    })
    result = response.get("result") or {}
    return result.get("access_token"), result.get("expires_in"), result.get("refresh_token")


async def refresh_access_token(refresh_token: str, cfg: dict):
    response = await _submit({
        "token": "oauth-refresh-placeholder", "owner_uid": "", "app": _app_name(), "feature": "oauth_refresh",
        "route": "oauth", "payload": {"grant_type": "refresh_token",
        "refresh_token": refresh_token, "config": cfg}, "priority": 1,
        "background": True, "background_floor": 0, "privacy_scope": "private", "cache_ttl": 0,
        "stale_ttl": 0,
    })
    result = response.get("result") or {}
    return result.get("access_token"), result.get("expires_in"), result.get("refresh_token")
