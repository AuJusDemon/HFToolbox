"""
hf_cache.py — Unified HF resource cache.

Replaces the scattered get_dash_cache / set_dash_cache calls with a
structured table that supports per-type TTLs, stale-while-revalidate,
and API call telemetry.

Cache key convention (consistent across all modules):
    me:{uid}
    bytes:{uid}:to:p{n}
    bytes:{uid}:from:p{n}
    contracts:{uid}:p{n}
    contract:{cid}:detail
    thread:{tid}:meta
    threads:uid:{uid}:p{n}
    user:{uid}:profile
    user:{uid}:activity
    user:{uid}:trust:p{n}
    sigmarket:status:{uid}
    sigmarket:browse
    sigmarket:analytics:{uid}
    forum:{fid}:p{n}
    posts:tid:{tid}:p{n}
"""

import json
import time
import logging
from db_connection import _db

log = logging.getLogger("hf_cache")

# ── Freshness tiers ────────────────────────────────────────────────────────────
#
#  ttl   — seconds data is "fresh" → return instantly, no refresh
#  stale — additional seconds data is "stale but usable"
#            → return immediately AND queue a background refresh
#          After ttl + stale the entry is considered expired → live call required
#
# Tier 1: Hot  — drives the real-time UI feel
# Tier 2: Warm — useful, not emergency
# Tier 3: Cold — public/analytics, almost never needs to be live

TIERS: dict[str, dict] = {
    # Tier 1: Hot
    "me":                  {"ttl":  300, "stale":  600},   #  5 min fresh,  10 min usable
    "bytes_recv":          {"ttl":  300, "stale":  600},
    "bytes_sent":          {"ttl":  300, "stale":  600},
    "contracts":           {"ttl":  300, "stale":  900},
    "threads_uid":         {"ttl":  300, "stale":  600},
    # Tier 2: Warm
    "sigmarket_status":    {"ttl":  900, "stale": 3600},   # 15 min fresh,  1 hr usable
    "contract_detail":     {"ttl":  300, "stale": 7200},  # 5 min fresh, 2 hr usable
    "thread_meta":         {"ttl":  300, "stale": 1800},
    "user_profile":        {"ttl":  900, "stale": 7200},
    # Tier 3: Cold / public
    "sigmarket_browse":    {"ttl": 1500, "stale": 7200},   # 25 min fresh,  2 hr usable
    "sigmarket_analytics": {"ttl": 3600, "stale": 86400},  #  1 hr fresh,  24 hr usable
    "user_activity":       {"ttl":  900, "stale": 7200},
    "user_trust":          {"ttl":  900, "stale": 7200},
    "forum_page1":         {"ttl":  600, "stale": 3600},
    "wire_replies":        {"ttl":  300, "stale": 1800},
}

_DEFAULT_TIER: dict = {"ttl": 600, "stale": 3600}


def _tier(resource_type: str) -> dict:
    return TIERS.get(resource_type, _DEFAULT_TIER)


# ── Table init ─────────────────────────────────────────────────────────────────

def init_hf_cache_tables() -> None:
    """Create hf_resource_cache and hf_api_call_log tables. Safe to call on restart."""
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS hf_resource_cache (
                cache_key      VARCHAR(255) NOT NULL,
                owner_uid      VARCHAR(32)  DEFAULT '',
                resource_type  VARCHAR(64)  NOT NULL,
                data_json      MEDIUMTEXT   NOT NULL,
                fetched_at     BIGINT       NOT NULL,
                expires_at     BIGINT       NOT NULL,
                stale_until    BIGINT       NOT NULL,
                refresh_status VARCHAR(32)  DEFAULT 'idle',
                error_count    INT          DEFAULT 0,
                last_error     TEXT,
                PRIMARY KEY (cache_key)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS hf_api_call_log (
                id          BIGINT AUTO_INCREMENT PRIMARY KEY,
                ts          BIGINT       NOT NULL,
                uid         VARCHAR(32)  DEFAULT '',
                route       VARCHAR(16)  NOT NULL,
                purpose     VARCHAR(128) DEFAULT '',
                ask_keys    VARCHAR(255) DEFAULT '',
                duration_ms INT          DEFAULT 0,
                success     TINYINT      DEFAULT 0,
                remaining   INT          DEFAULT -1,
                cache_key   VARCHAR(255) DEFAULT '',
                cache_status VARCHAR(32) DEFAULT '',
                INDEX idx_ts  (ts),
                INDEX idx_uid (uid)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)


# ── Internal ───────────────────────────────────────────────────────────────────

def _get_row(cache_key: str) -> dict | None:
    """Fetch raw cache row. Returns parsed dict with metadata, or None."""
    with _db() as conn:
        row = conn.execute(
            "SELECT data_json, fetched_at, expires_at, stale_until "
            "FROM hf_resource_cache WHERE cache_key=?",
            (cache_key,)
        ).fetchone()
    if not row:
        return None
    try:
        return {
            "data":        json.loads(row["data_json"]),
            "fetched_at":  int(row["fetched_at"]),
            "expires_at":  int(row["expires_at"]),
            "stale_until": int(row["stale_until"]),
        }
    except Exception:
        return None


# ── Public API ─────────────────────────────────────────────────────────────────

def get_fresh(cache_key: str) -> dict | None:
    """Return data if within TTL (fully fresh). None if stale or missing."""
    row = _get_row(cache_key)
    if not row:
        return None
    if time.time() > row["expires_at"]:
        return None
    return row["data"]


def get_usable(cache_key: str) -> tuple[dict | None, bool]:
    """
    Return (data, is_stale).

    Fresh cache  → (data, False)   — no refresh needed
    Stale window → (data, True)    — queue background refresh
    Expired/miss → (None, False)   — live call required
    """
    row = _get_row(cache_key)
    if not row:
        return None, False
    now = time.time()
    if now <= row["expires_at"]:
        return row["data"], False
    if now <= row["stale_until"]:
        return row["data"], True
    return None, False


def get_age(cache_key: str) -> int:
    """Seconds since last successful fetch. -1 if not in cache."""
    row = _get_row(cache_key)
    if not row:
        return -1
    return max(0, int(time.time() - row["fetched_at"]))


def get_fetched_at(cache_key: str) -> int:
    """Unix timestamp of last fetch, or 0."""
    row = _get_row(cache_key)
    return row["fetched_at"] if row else 0


def set_cache(cache_key: str, resource_type: str, data: dict,
              owner_uid: str = "") -> None:
    """Store data with correct TTL/stale windows for resource_type."""
    tier = _tier(resource_type)
    now  = int(time.time())
    with _db() as conn:
        conn.execute("""
            INSERT INTO hf_resource_cache
                (cache_key, owner_uid, resource_type, data_json,
                 fetched_at, expires_at, stale_until, refresh_status, error_count)
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'idle', 0)
            ON DUPLICATE KEY UPDATE
                owner_uid      = VALUES(owner_uid),
                resource_type  = VALUES(resource_type),
                data_json      = VALUES(data_json),
                fetched_at     = VALUES(fetched_at),
                expires_at     = VALUES(expires_at),
                stale_until    = VALUES(stale_until),
                refresh_status = 'idle',
                error_count    = 0,
                last_error     = NULL
        """, (
            cache_key,
            owner_uid or "",
            resource_type,
            json.dumps(data),
            now,
            now + tier["ttl"],
            now + tier["ttl"] + tier["stale"],
        ))


def get_any(cache_key: str) -> dict | None:
    """Return data regardless of TTL. Last-resort fallback when all fetches fail."""
    row = _get_row(cache_key)
    return row["data"] if row else None


def invalidate(cache_key: str) -> None:
    """Remove a specific cache entry."""
    with _db() as conn:
        conn.execute(
            "DELETE FROM hf_resource_cache WHERE cache_key=?",
            (cache_key,)
        )


def invalidate_prefix(prefix: str) -> None:
    """Delete all cache keys starting with prefix (e.g. 'sigmarket:' to nuke all sig caches)."""
    with _db() as conn:
        conn.execute(
            "DELETE FROM hf_resource_cache WHERE cache_key LIKE ?",
            (prefix.rstrip("%") + "%",)
        )


# ── Telemetry ──────────────────────────────────────────────────────────────────

def log_call(uid: str, route: str, purpose: str, ask_keys: str,
             duration_ms: int, success: bool, remaining: int,
             cache_key: str = "", cache_status: str = "") -> None:
    """Log an HF API call. Never raises — logging must not break the app."""
    try:
        with _db() as conn:
            conn.execute("""
                INSERT INTO hf_api_call_log
                    (ts, uid, route, purpose, ask_keys, duration_ms,
                     success, remaining, cache_key, cache_status)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (
                int(time.time()),
                (uid or "")[:32],
                route[:16],
                purpose[:128],
                ask_keys[:255],
                duration_ms,
                int(success),
                remaining,
                cache_key[:255],
                cache_status[:32],
            ))
    except Exception:
        pass


def get_call_stats(hours: int = 1) -> dict:
    """Return call volume stats for the last N hours. Used by /api/rate-limit debug."""
    try:
        since = int(time.time()) - hours * 3600
        with _db() as conn:
            rows = conn.execute("""
                SELECT uid, COUNT(*) as calls, SUM(1-success) as errors,
                       AVG(duration_ms) as avg_ms,
                       SUM(CASE WHEN cache_status='miss_live' THEN 1 ELSE 0 END) as live_misses,
                       SUM(CASE WHEN cache_status LIKE 'hit%' THEN 1 ELSE 0 END) as cache_hits
                FROM hf_api_call_log
                WHERE ts >= ?
                GROUP BY uid
            """, (since,)).fetchall()
        return {
            "hours":  hours,
            "by_uid": [{
                "uid":        r["uid"],
                "calls":      r["calls"],
                "errors":     r["errors"] or 0,
                "avg_ms":     round(float(r["avg_ms"] or 0)),
                "live_misses": r["live_misses"] or 0,
                "cache_hits": r["cache_hits"] or 0,
            } for r in rows]
        }
    except Exception:
        return {}
