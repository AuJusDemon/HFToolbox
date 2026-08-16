"""Persistence for the shared HFToolbox marketplace index."""

from __future__ import annotations

import json
import time
from collections import Counter
from typing import Any
from hf_thread_stats import has_thread_reply_count, thread_reply_count

from _db_compat import _db
from modules.marketplace_defs import MARKET_FORUMS, MARKET_CATEGORIES


MARKET_FIDS = MARKET_FORUMS
CATEGORIES = MARKET_CATEGORIES


def init_market_db() -> None:
    now = int(time.time())
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS market_forums (
                fid INTEGER PRIMARY KEY,
                name VARCHAR(180) NOT NULL,
                cadence_seconds INTEGER NOT NULL DEFAULT 3600,
                enabled TINYINT NOT NULL DEFAULT 1,
                last_scanned_at BIGINT NOT NULL DEFAULT 0,
                last_row_count INTEGER NOT NULL DEFAULT 0,
                saturated TINYINT NOT NULL DEFAULT 0,
                refresh_page INTEGER NOT NULL DEFAULT 1,
                backfill_page INTEGER NOT NULL DEFAULT 0
            )
        """)
        for column, definition in (
            ("refresh_page", "INTEGER NOT NULL DEFAULT 1"),
            ("backfill_page", "INTEGER NOT NULL DEFAULT 0"),
        ):
            try:
                conn.execute(
                    f"ALTER TABLE market_forums ADD COLUMN {column} {definition}"
                )
            except Exception:
                pass
        conn.execute("""
            CREATE TABLE IF NOT EXISTS market_categories (
                slug VARCHAR(40) PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                enabled TINYINT NOT NULL DEFAULT 1
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS market_threads (
                tid BIGINT PRIMARY KEY,
                fid INTEGER NOT NULL,
                seller_uid BIGINT NOT NULL,
                subject TEXT NOT NULL,
                market_type VARCHAR(12) NOT NULL DEFAULT 'wts',
                category VARCHAR(40) NOT NULL DEFAULT 'other',
                firstpost_pid BIGINT,
                opening_post MEDIUMTEXT,
                opening_post_hash VARCHAR(64),
                created_at BIGINT NOT NULL DEFAULT 0,
                lastpost_at BIGINT NOT NULL DEFAULT 0,
                lastposter_uid BIGINT,
                views INTEGER NOT NULL DEFAULT 0,
                replies INTEGER NOT NULL DEFAULT 0,
                closed TINYINT NOT NULL DEFAULT 0,
                sticky TINYINT NOT NULL DEFAULT 0,
                first_seen_at BIGINT NOT NULL,
                last_seen_at BIGINT NOT NULL,
                last_post_fetched_at BIGINT NOT NULL DEFAULT 0,
                last_reply_checked_at BIGINT NOT NULL DEFAULT 0,
                heat_score INTEGER NOT NULL DEFAULT 0,
                priority_tier VARCHAR(12) NOT NULL DEFAULT 'dormant',
                next_refresh_at BIGINT NOT NULL DEFAULT 0,
                last_activity_at BIGINT NOT NULL DEFAULT 0,
                reply_confidence VARCHAR(12) NOT NULL DEFAULT 'unknown',
                reply_page_cursor INTEGER NOT NULL DEFAULT 1
            )
        """)
        for column, definition in (
            ("heat_score", "INTEGER NOT NULL DEFAULT 0"),
            ("priority_tier", "VARCHAR(12) NOT NULL DEFAULT 'dormant'"),
            ("next_refresh_at", "BIGINT NOT NULL DEFAULT 0"),
            ("last_activity_at", "BIGINT NOT NULL DEFAULT 0"),
            ("reply_confidence", "VARCHAR(12) NOT NULL DEFAULT 'unknown'"),
            ("reply_page_cursor", "INTEGER NOT NULL DEFAULT 1"),
        ):
            try:
                conn.execute(
                    f"ALTER TABLE market_threads ADD COLUMN {column} {definition}"
                )
            except Exception:
                pass
        conn.execute("""
            CREATE TABLE IF NOT EXISTS market_thread_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tid BIGINT NOT NULL,
                observed_at BIGINT NOT NULL,
                views INTEGER NOT NULL DEFAULT 0,
                replies INTEGER NOT NULL DEFAULT 0,
                lastpost_at BIGINT NOT NULL DEFAULT 0,
                UNIQUE (tid, observed_at)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS market_sellers (
                uid BIGINT PRIMARY KEY,
                username VARCHAR(180) NOT NULL DEFAULT '',
                first_seen_at BIGINT NOT NULL,
                last_seen_at BIGINT NOT NULL,
                last_contract_check_at BIGINT NOT NULL DEFAULT 0,
                next_contract_check_at BIGINT NOT NULL DEFAULT 0,
                contract_cursor_page INTEGER NOT NULL DEFAULT 1,
                backfill_done TINYINT NOT NULL DEFAULT 0,
                last_contract_count INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS market_contracts (
                cid BIGINT PRIMARY KEY,
                seller_uid BIGINT NOT NULL,
                initiator_uid BIGINT NOT NULL DEFAULT 0,
                counterparty_uid BIGINT NOT NULL DEFAULT 0,
                tid BIGINT NOT NULL DEFAULT 0,
                status VARCHAR(8) NOT NULL DEFAULT '',
                contract_type VARCHAR(8) NOT NULL DEFAULT '',
                public_flag TINYINT NOT NULL DEFAULT 0,
                scope VARCHAR(12) NOT NULL DEFAULT 'unknown',
                contract_at BIGINT NOT NULL DEFAULT 0,
                other_at BIGINT NOT NULL DEFAULT 0,
                first_seen_at BIGINT NOT NULL,
                last_seen_at BIGINT NOT NULL,
                status_checked_at BIGINT NOT NULL DEFAULT 0,
                next_status_check_at BIGINT NOT NULL DEFAULT 0
            )
        """)
        for column, definition in (
            ("initiator_uid", "BIGINT NOT NULL DEFAULT 0"),
            ("counterparty_uid", "BIGINT NOT NULL DEFAULT 0"),
            ("scope", "VARCHAR(12) NOT NULL DEFAULT 'unknown'"),
            ("status_checked_at", "BIGINT NOT NULL DEFAULT 0"),
            ("next_status_check_at", "BIGINT NOT NULL DEFAULT 0"),
        ):
            try:
                conn.execute(
                    f"ALTER TABLE market_contracts ADD COLUMN {column} {definition}"
                )
            except Exception:
                pass
        conn.execute("""
            CREATE TABLE IF NOT EXISTS market_contract_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cid BIGINT NOT NULL,
                status VARCHAR(8) NOT NULL,
                observed_at BIGINT NOT NULL,
                UNIQUE (cid, status)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS market_contract_thread_queue (
                tid BIGINT PRIMARY KEY,
                first_seen_at BIGINT NOT NULL,
                next_attempt_at BIGINT NOT NULL DEFAULT 0,
                attempts INTEGER NOT NULL DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS market_thread_contract_rollups (
                tid BIGINT PRIMARY KEY,
                observed_contracts INTEGER NOT NULL DEFAULT 0,
                awaiting_contracts INTEGER NOT NULL DEFAULT 0,
                denied_contracts INTEGER NOT NULL DEFAULT 0,
                cancelled_contracts INTEGER NOT NULL DEFAULT 0,
                middleman_contracts INTEGER NOT NULL DEFAULT 0,
                active_contracts INTEGER NOT NULL DEFAULT 0,
                complete_contracts INTEGER NOT NULL DEFAULT 0,
                disputed_contracts INTEGER NOT NULL DEFAULT 0,
                expired_contracts INTEGER NOT NULL DEFAULT 0,
                invalid_contracts INTEGER NOT NULL DEFAULT 0,
                other_contracts INTEGER NOT NULL DEFAULT 0,
                last_contract_at BIGINT NOT NULL DEFAULT 0,
                last_contract_seen_at BIGINT NOT NULL DEFAULT 0,
                updated_at BIGINT NOT NULL DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS market_contract_cursors (
                direction VARCHAR(12) PRIMARY KEY,
                anchor_cid BIGINT NOT NULL,
                next_cid BIGINT NOT NULL,
                last_scanned_at BIGINT NOT NULL DEFAULT 0,
                last_returned_count INTEGER NOT NULL DEFAULT 0,
                empty_streak INTEGER NOT NULL DEFAULT 0,
                confirmed_cid BIGINT NOT NULL DEFAULT 0,
                probe_cid BIGINT NOT NULL DEFAULT 0,
                next_probe_at BIGINT NOT NULL DEFAULT 0,
                overlap_size INTEGER NOT NULL DEFAULT 5,
                updated_at BIGINT NOT NULL
            )
        """)
        for column, definition in (
            ("confirmed_cid", "BIGINT NOT NULL DEFAULT 0"),
            ("probe_cid", "BIGINT NOT NULL DEFAULT 0"),
            ("next_probe_at", "BIGINT NOT NULL DEFAULT 0"),
            ("overlap_size", "INTEGER NOT NULL DEFAULT 5"),
        ):
            try:
                conn.execute(
                    f"ALTER TABLE market_contract_cursors ADD COLUMN {column} {definition}"
                )
            except Exception:
                pass
        conn.execute("""
            CREATE TABLE IF NOT EXISTS market_thread_refresh_queue (
                tid BIGINT PRIMARY KEY,
                priority INTEGER NOT NULL DEFAULT 0,
                reason VARCHAR(32) NOT NULL DEFAULT 'scheduled',
                next_attempt_at BIGINT NOT NULL DEFAULT 0,
                attempts INTEGER NOT NULL DEFAULT 0,
                updated_at BIGINT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS market_reply_verify_queue (
                tid BIGINT PRIMARY KEY,
                next_page INTEGER NOT NULL DEFAULT 1,
                next_attempt_at BIGINT NOT NULL DEFAULT 0,
                attempts INTEGER NOT NULL DEFAULT 0,
                updated_at BIGINT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS market_collection_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at BIGINT NOT NULL,
                finished_at BIGINT,
                source VARCHAR(40) NOT NULL,
                fids_json TEXT NOT NULL,
                calls_used INTEGER NOT NULL DEFAULT 0,
                threads_seen INTEGER NOT NULL DEFAULT 0,
                new_threads INTEGER NOT NULL DEFAULT 0,
                posts_fetched INTEGER NOT NULL DEFAULT 0,
                contracts_seen INTEGER NOT NULL DEFAULT 0,
                remaining INTEGER,
                status VARCHAR(20) NOT NULL DEFAULT 'running',
                error TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS market_watches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                uid VARCHAR(64) NOT NULL,
                name VARCHAR(120) NOT NULL,
                required_phrase VARCHAR(240) NOT NULL DEFAULT '',
                optional_terms TEXT NOT NULL,
                excluded_terms TEXT NOT NULL,
                fids_json TEXT NOT NULL,
                market_type VARCHAR(12) NOT NULL DEFAULT 'any',
                seller_uid VARCHAR(64) NOT NULL DEFAULT '',
                watch_kind VARCHAR(24) NOT NULL DEFAULT 'phrase',
                topic_id INTEGER,
                category_filter VARCHAR(40) NOT NULL DEFAULT '',
                thread_tid BIGINT,
                telegram_enabled TINYINT NOT NULL DEFAULT 0,
                enabled TINYINT NOT NULL DEFAULT 1,
                created_at BIGINT NOT NULL,
                updated_at BIGINT NOT NULL
            )
        """)
        try:
            conn.execute(
                "ALTER TABLE market_watches ADD COLUMN "
                "telegram_enabled TINYINT NOT NULL DEFAULT 0"
            )
        except Exception:
            pass
        for column, definition in (
            ("watch_kind", "VARCHAR(24) NOT NULL DEFAULT 'phrase'"),
            ("topic_id", "INTEGER"),
            ("category_filter", "VARCHAR(40) NOT NULL DEFAULT ''"),
            ("thread_tid", "BIGINT"),
        ):
            try:
                conn.execute(f"ALTER TABLE market_watches ADD COLUMN {column} {definition}")
            except Exception:
                pass
        conn.execute("""
            CREATE TABLE IF NOT EXISTS market_watch_matches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                watch_id INTEGER NOT NULL,
                uid VARCHAR(64) NOT NULL,
                tid BIGINT NOT NULL,
                thread_version VARCHAR(96) NOT NULL,
                matched_at BIGINT NOT NULL,
                alerted_at BIGINT,
                UNIQUE (watch_id, tid, thread_version)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS market_passes (
                uid VARCHAR(64) PRIMARY KEY,
                starts_at BIGINT NOT NULL,
                expires_at BIGINT NOT NULL,
                source_payment_id VARCHAR(64) NOT NULL,
                updated_at BIGINT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS market_payments (
                payment_id VARCHAR(64) PRIMARY KEY,
                uid VARCHAR(64) NOT NULL,
                amount INTEGER NOT NULL,
                duration_days INTEGER NOT NULL,
                status VARCHAR(20) NOT NULL,
                created_at BIGINT NOT NULL,
                completed_at BIGINT,
                error TEXT,
                reference VARCHAR(64) NOT NULL DEFAULT '',
                receiver_uid VARCHAR(64) NOT NULL DEFAULT '',
                fee_label VARCHAR(160) NOT NULL DEFAULT '',
                idempotency_key VARCHAR(96) NOT NULL DEFAULT '',
                hf_result_json TEXT,
                last_attempt_at BIGINT
            )
        """)
        for column, definition in (
            ("reference", "VARCHAR(64) NOT NULL DEFAULT ''"),
            ("receiver_uid", "VARCHAR(64) NOT NULL DEFAULT ''"),
            ("fee_label", "VARCHAR(160) NOT NULL DEFAULT ''"),
            ("idempotency_key", "VARCHAR(96) NOT NULL DEFAULT ''"),
            ("hf_result_json", "TEXT"),
            ("last_attempt_at", "BIGINT"),
        ):
            try:
                conn.execute(f"ALTER TABLE market_payments ADD COLUMN {column} {definition}")
            except Exception:
                pass
        conn.execute("""
            CREATE TABLE IF NOT EXISTS market_topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slug VARCHAR(120) NOT NULL UNIQUE,
                name VARCHAR(180) NOT NULL,
                canonical_terms TEXT NOT NULL,
                aliases_json TEXT NOT NULL,
                exclusions_json TEXT NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'active',
                created_at BIGINT NOT NULL,
                updated_at BIGINT NOT NULL
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS market_thread_topics (
                tid BIGINT NOT NULL,
                topic_id INTEGER NOT NULL,
                confidence REAL NOT NULL DEFAULT 0,
                confidence_band VARCHAR(16) NOT NULL DEFAULT 'probable',
                method VARCHAR(24) NOT NULL DEFAULT 'rules',
                assigned_at BIGINT NOT NULL,
                PRIMARY KEY (tid,topic_id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS market_topic_snapshots (
                topic_id INTEGER NOT NULL,
                snapshot_date VARCHAR(10) NOT NULL,
                buyer_threads INTEGER NOT NULL DEFAULT 0,
                unique_buyers INTEGER NOT NULL DEFAULT 0,
                seller_threads INTEGER NOT NULL DEFAULT 0,
                observed_contracts INTEGER NOT NULL DEFAULT 0,
                completed_contracts INTEGER NOT NULL DEFAULT 0,
                created_at BIGINT NOT NULL,
                PRIMARY KEY (topic_id,snapshot_date)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS market_topic_suggestions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                suggestion_type VARCHAR(20) NOT NULL,
                topic_id INTEGER,
                other_topic_id INTEGER,
                details_json TEXT NOT NULL,
                status VARCHAR(20) NOT NULL DEFAULT 'pending',
                created_at BIGINT NOT NULL,
                reviewed_at BIGINT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS market_cached_views (
                cache_key VARCHAR(64) PRIMARY KEY,
                payload MEDIUMTEXT NOT NULL,
                updated_at BIGINT NOT NULL
            )
        """)
        for statement in (
            "CREATE INDEX idx_mtt_topic_band ON market_thread_topics (topic_id,confidence_band,tid)",
            "CREATE INDEX idx_mc_tid_status_date ON market_contracts (tid,status,contract_at)",
            "CREATE INDEX idx_mc_status_date ON market_contracts (status,contract_at)",
            "CREATE INDEX idx_mt_type_created ON market_threads (market_type,created_at)",
            "CREATE INDEX idx_mt_forum_created ON market_threads (fid,created_at)",
            "CREATE INDEX idx_mt_category_created ON market_threads (category,created_at)",
            "CREATE INDEX idx_mt_views ON market_threads (views)",
            "CREATE INDEX idx_mt_replies ON market_threads (replies)",
            "CREATE INDEX idx_mcr_last_contract ON market_thread_contract_rollups (last_contract_at)",
            "CREATE INDEX idx_mcr_complete ON market_thread_contract_rollups (complete_contracts)",
            "CREATE INDEX idx_mcr_active ON market_thread_contract_rollups (active_contracts)",
            "CREATE INDEX idx_mcr_disputed ON market_thread_contract_rollups (disputed_contracts)",
            "CREATE INDEX idx_mcr_expired ON market_thread_contract_rollups (expired_contracts)",
        ):
            try:
                conn.execute(statement)
            except Exception:
                pass
        for fid, name in MARKET_FIDS.items():
            cadence = 1800 if fid in (44, 106, 107, 176, 263, 291) else 3600
            conn.execute(
                "INSERT OR IGNORE INTO market_forums "
                "(fid,name,cadence_seconds,last_scanned_at) VALUES (?,?,?,0)",
                (fid, name, cadence),
            )
        for slug, name in CATEGORIES:
            conn.execute(
                "INSERT OR IGNORE INTO market_categories (slug,name) VALUES (?,?)",
                (slug, name),
            )
        conn.execute(
            "UPDATE market_sellers SET contract_cursor_page=2,backfill_done=0,"
            "next_contract_check_at=0 WHERE last_contract_check_at>0 "
            "AND last_contract_count>=30 AND contract_cursor_page=1"
        )
        conn.execute(
            "UPDATE market_sellers SET backfill_done=1 "
            "WHERE last_contract_check_at>0 AND last_contract_count<30 "
            "AND contract_cursor_page=1"
        )
        conn.execute(
            "INSERT OR IGNORE INTO market_contract_thread_queue "
            "(tid,first_seen_at,next_attempt_at) "
            "SELECT DISTINCT c.tid,?,0 FROM market_contracts c "
            "LEFT JOIN market_threads t ON t.tid=c.tid "
            "WHERE c.tid>0 AND t.tid IS NULL",
            (now,),
        )
        market_fids = tuple(MARKET_FIDS)
        fid_placeholders = ",".join("?" for _ in market_fids)
        conn.execute(
            "UPDATE market_contracts SET scope='market' WHERE tid IN "
            f"(SELECT tid FROM market_threads WHERE fid IN ({fid_placeholders}))",
            market_fids,
        )
        # Deal Disputes are retained as market-risk records, never listings or demand.
        conn.execute("UPDATE market_threads SET market_type='dispute',category='other' WHERE fid=111")
        conn.execute(
            "DELETE FROM market_thread_topics WHERE tid IN "
            "(SELECT tid FROM market_threads WHERE fid=111 OR market_type='dispute')"
        )
        conn.execute("DELETE FROM market_cached_views WHERE cache_key='pulse'")
        external_tids = [
            int(_value(row, "tid", 0) or 0)
            for row in conn.execute(
                "SELECT tid FROM market_threads "
                f"WHERE fid NOT IN ({fid_placeholders})",
                market_fids,
            ).fetchall()
        ]
        for offset in range(0, len(external_tids), 500):
            batch = tuple(external_tids[offset:offset + 500])
            ext_placeholders = ",".join("?" for _ in batch)
            conn.execute(
                "UPDATE market_contracts SET scope='external' "
                f"WHERE tid IN ({ext_placeholders})", batch,
            )
            conn.execute(
                "DELETE FROM market_watch_matches "
                f"WHERE tid IN ({ext_placeholders})", batch,
            )
            conn.execute(
                "DELETE FROM market_thread_snapshots "
                f"WHERE tid IN ({ext_placeholders})", batch,
            )
            conn.execute(
                "DELETE FROM market_contract_thread_queue "
                f"WHERE tid IN ({ext_placeholders})", batch,
            )
            conn.execute(
                f"DELETE FROM market_threads WHERE tid IN ({ext_placeholders})",
                batch,
            )
        highest = conn.execute(
            "SELECT COALESCE(MAX(cid),0) cid FROM market_contracts"
        ).fetchone()
        anchor = max(1, int(_value(highest, "cid", 0) or 0))
        conn.execute(
            "INSERT OR IGNORE INTO market_contract_cursors "
            "(direction,anchor_cid,next_cid,updated_at) VALUES ('forward',?,?,?)",
            (anchor, anchor + 1, now),
        )
        conn.execute(
            "INSERT OR IGNORE INTO market_contract_cursors "
            "(direction,anchor_cid,next_cid,updated_at) VALUES ('backward',?,?,?)",
            (anchor, anchor, now),
        )
        conn.execute(
            "UPDATE market_contract_cursors SET "
            "confirmed_cid=CASE WHEN confirmed_cid=0 THEN "
            "CASE WHEN next_cid>1 THEN next_cid-1 ELSE 0 END "
            "ELSE confirmed_cid END,"
            "probe_cid=CASE WHEN probe_cid=0 THEN next_cid ELSE probe_cid END "
            "WHERE direction='forward'"
        )
        conn.execute(
            "UPDATE market_contracts SET next_status_check_at=? "
            "WHERE next_status_check_at=0 AND status IN ('0','1','5','7')",
            (now,),
        )
        deleted = (
            "LOWER(TRIM(COALESCE(opening_post,''))) IN ('[deleted]','deleted') "
            "OR LOWER(TRIM(subject)) IN ('[deleted]','deleted')"
        )
        conn.execute(
            f"DELETE FROM market_watch_matches WHERE tid IN "
            f"(SELECT tid FROM market_threads WHERE {deleted})"
        )
        conn.execute(
            f"DELETE FROM market_thread_snapshots WHERE tid IN "
            f"(SELECT tid FROM market_threads WHERE {deleted})"
        )
        conn.execute(f"DELETE FROM market_threads WHERE {deleted}")


def _value(row: Any, key: str, default: Any = None) -> Any:
    if not row:
        return default
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return default


def begin_run(source: str, fids: list[int]) -> int:
    with _db() as conn:
        cur = conn.execute(
            "INSERT INTO market_collection_runs "
            "(started_at,source,fids_json,status) VALUES (?,?,?,'running')",
            (int(time.time()), source, json.dumps(fids)),
        )
        return int(cur.lastrowid)


def finish_run(run_id: int, **values: Any) -> None:
    allowed = {
        "calls_used", "threads_seen", "new_threads", "posts_fetched",
        "contracts_seen", "remaining", "status", "error",
    }
    values = {k: v for k, v in values.items() if k in allowed}
    values["finished_at"] = int(time.time())
    fields = ", ".join(f"{key}=?" for key in values)
    with _db() as conn:
        conn.execute(
            f"UPDATE market_collection_runs SET {fields} WHERE id=?",
            (*values.values(), run_id),
        )


def calls_last_hour() -> int:
    with _db() as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(calls_used),0) AS n FROM market_collection_runs "
            "WHERE started_at>=?",
            (int(time.time()) - 3600,),
        ).fetchone()
        return int(_value(row, "n", 0) or 0)


def last_collection_started(source: str) -> int:
    with _db() as conn:
        row = conn.execute(
            "SELECT MAX(started_at) ts FROM market_collection_runs "
            "WHERE source=? AND status='complete'",
            (source,),
        ).fetchone()
        return int(_value(row, "ts", 0) or 0)


def latest_remaining(max_age: int = 600) -> int | None:
    with _db() as conn:
        row = conn.execute(
            "SELECT remaining FROM market_collection_runs "
            "WHERE remaining IS NOT NULL AND calls_used>0 "
            "AND status IN ('complete','paused') AND finished_at>=? "
            "ORDER BY finished_at DESC LIMIT 1",
            (int(time.time()) - max_age,),
        ).fetchone()
        if not row:
            return None
        return int(_value(row, "remaining", 0) or 0)


def backfill_forums_order() -> list[int]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT fid FROM market_forums WHERE enabled=1 "
            "ORDER BY backfill_page ASC,last_scanned_at ASC,fid ASC"
        ).fetchall()
        return [int(_value(row, "fid", 0) or 0) for row in rows]


def due_forums(limit: int = 1) -> list[dict]:
    now = int(time.time())
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM market_forums WHERE enabled=1 "
            "AND last_scanned_at+cadence_seconds<=? "
            "ORDER BY last_scanned_at ASC,"
            "CASE fid WHEN 107 THEN 0 WHEN 44 THEN 1 WHEN 308 THEN 2 ELSE 3 END,"
            "fid ASC LIMIT ?",
            (now, limit),
        ).fetchall()
        return [dict(row) for row in rows]


def mark_forum_scanned(fid: int, row_count: int, advance: bool = False) -> None:
    with _db() as conn:
        if advance:
            conn.execute(
                "UPDATE market_forums SET last_scanned_at=?,last_row_count=?,"
                "saturated=?,refresh_page=CASE WHEN refresh_page>=3 THEN 1 "
                "ELSE refresh_page+1 END WHERE fid=?",
                (int(time.time()), row_count, int(row_count >= 30), fid),
            )
        else:
            conn.execute(
                "UPDATE market_forums SET last_scanned_at=?,last_row_count=?,"
                "saturated=? WHERE fid=?",
                (int(time.time()), row_count, int(row_count >= 30), fid),
            )


def backfill_start_page(fid: int) -> int:
    with _db() as conn:
        row = conn.execute(
            "SELECT backfill_page FROM market_forums WHERE fid=?", (fid,)
        ).fetchone()
        return int(_value(row, "backfill_page", 0) or 0) + 1


def mark_backfill_page(fid: int, page: int) -> None:
    with _db() as conn:
        conn.execute(
            "UPDATE market_forums SET backfill_page=CASE WHEN backfill_page>? "
            "THEN backfill_page ELSE ? END WHERE fid=?",
            (page, page, fid),
        )


def set_backfill_page(fid: int, page: int) -> None:
    with _db() as conn:
        conn.execute(
            "UPDATE market_forums SET backfill_page=? WHERE fid=?",
            (max(0, page), fid),
        )


def missing_opening_posts(limit: int = 900) -> list[tuple[int, int]]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT firstpost_pid,tid FROM market_threads "
            "WHERE opening_post IS NULL AND firstpost_pid>0 "
            "ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [
            (int(row["firstpost_pid"]), int(row["tid"])) for row in rows
        ]


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(value or default))
    except (TypeError, ValueError):
        return default


def get_thread(tid: int) -> dict | None:
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM market_threads WHERE tid=?", (tid,)
        ).fetchone()
        return dict(row) if row else None


def upsert_thread(row: dict, market_type: str, category: str) -> dict:
    now = int(time.time())
    tid = _as_int(row.get("tid"))
    previous = get_thread(tid)
    firstpost = row.get("firstpost")
    pid = firstpost.get("pid") if isinstance(firstpost, dict) else firstpost
    reply_count_present = has_thread_reply_count(row)
    native_replies = thread_reply_count(
        row, _as_int((previous or {}).get("replies"))
    )
    reply_checked_at = now if reply_count_present else _as_int(
        (previous or {}).get("last_reply_checked_at")
    )
    previous_views = _as_int((previous or {}).get("views"))
    previous_replies = _as_int((previous or {}).get("replies"))
    lastpost_changed = previous is not None and _as_int(
        previous.get("lastpost_at")
    ) != _as_int(row.get("lastpost"))
    view_gain = max(0, _as_int(row.get("views")) - previous_views)
    reply_gain = max(0, native_replies - previous_replies)
    raw_heat = view_gain + reply_gain * 12 + (35 if lastpost_changed else 0)
    heat_score = min(100, max(raw_heat, _as_int((previous or {}).get("heat_score")) - 10))
    activity_age = max(0, now - _as_int(row.get("lastpost"), now))
    closed = int(str(row.get("closed") or "0") not in ("", "0"))
    if heat_score >= 50:
        tier, cadence = "hot", 900
    elif heat_score >= 15 or activity_age < 86400:
        tier, cadence = "active", 3600
    elif activity_age < 30 * 86400:
        tier, cadence = "cooling", 21600
    else:
        tier, cadence = "dormant", 86400 if not closed else 604800
    confidence = "native" if reply_count_present else str(
        (previous or {}).get("reply_confidence") or "unknown"
    )
    values = (
        tid, _as_int(row.get("fid")), _as_int(row.get("uid")),
        str(row.get("subject") or ""), market_type, category, _as_int(pid),
        _as_int(row.get("dateline")), _as_int(row.get("lastpost")),
        _as_int(row.get("lastposteruid")), _as_int(row.get("views")),
        native_replies, reply_checked_at,
        closed,
        _as_int(row.get("sticky")), now, now,
    )
    with _db() as conn:
        conn.execute("""
            INSERT INTO market_threads
            (tid,fid,seller_uid,subject,market_type,category,firstpost_pid,
             created_at,lastpost_at,lastposter_uid,views,replies,last_reply_checked_at,
             closed,sticky,
             first_seen_at,last_seen_at,heat_score,priority_tier,next_refresh_at,
             last_activity_at,reply_confidence)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(tid) DO UPDATE SET
             fid=excluded.fid,seller_uid=excluded.seller_uid,subject=excluded.subject,
             market_type=excluded.market_type,category=excluded.category,
             firstpost_pid=excluded.firstpost_pid,lastpost_at=excluded.lastpost_at,
             lastposter_uid=excluded.lastposter_uid,views=excluded.views,
             replies=excluded.replies,last_reply_checked_at=excluded.last_reply_checked_at,
             closed=excluded.closed,sticky=excluded.sticky,last_seen_at=excluded.last_seen_at,
             heat_score=excluded.heat_score,priority_tier=excluded.priority_tier,
             next_refresh_at=excluded.next_refresh_at,
             last_activity_at=excluded.last_activity_at,
             reply_confidence=excluded.reply_confidence
        """, values + (heat_score, tier, now + cadence,
                         now if lastpost_changed or previous is None else _as_int(previous.get("last_activity_at")),
                         confidence))
        conn.execute(
            "DELETE FROM market_contract_thread_queue WHERE tid=?", (tid,)
        )
        conn.execute(
            "INSERT INTO market_thread_refresh_queue "
            "(tid,priority,reason,next_attempt_at,updated_at) VALUES (?,?,?,?,?) "
            "ON CONFLICT(tid) DO UPDATE SET priority=CASE WHEN priority<excluded.priority "
            "THEN excluded.priority ELSE priority END,reason=excluded.reason,"
            "next_attempt_at=CASE WHEN next_attempt_at<excluded.next_attempt_at "
            "THEN next_attempt_at ELSE excluded.next_attempt_at END,"
            "updated_at=excluded.updated_at",
            (tid, heat_score, "activity" if lastpost_changed else "scheduled",
             0 if lastpost_changed else now + cadence, now),
        )
        if not reply_count_present and (previous is None or lastpost_changed):
            start_page = max(1, (_as_int((previous or {}).get("replies")) + 1) // 30)
            conn.execute(
                "INSERT INTO market_reply_verify_queue "
                "(tid,next_page,next_attempt_at,updated_at) VALUES (?,?,0,?) "
                "ON CONFLICT(tid) DO UPDATE SET next_page=CASE WHEN next_page<excluded.next_page "
                "THEN next_page ELSE excluded.next_page END,"
                "next_attempt_at=0,updated_at=excluded.updated_at",
                (tid, start_page, now),
            )
        conn.execute(
            "INSERT OR IGNORE INTO market_thread_snapshots "
            "(tid,observed_at,views,replies,lastpost_at) VALUES (?,?,?,?,?)",
            (
                tid, now, _as_int(row.get("views")),
                native_replies,
                _as_int(row.get("lastpost")),
            ),
        )
        seller_uid = _as_int(row.get("uid"))
        conn.execute("""
            INSERT INTO market_sellers
            (uid,first_seen_at,last_seen_at,next_contract_check_at)
            VALUES (?,?,?,?)
            ON CONFLICT(uid) DO UPDATE SET last_seen_at=excluded.last_seen_at
        """, (seller_uid, now, now, now))
        conn.execute(
            "DELETE FROM market_cached_views WHERE cache_key='pulse' OR cache_key LIKE 'topics:%%'"
        )
    return {
        "new": previous is None,
        "lastpost_changed": lastpost_changed,
        "needs_post": previous is None or not (previous or {}).get("opening_post"),
        "tid": tid,
        "pid": _as_int(pid),
        "seller_uid": seller_uid,
    }


def update_opening_post(tid: int, message: str, digest: str) -> None:
    now = int(time.time())
    with _db() as conn:
        conn.execute(
            "UPDATE market_threads SET opening_post=?,opening_post_hash=?,"
            "last_post_fetched_at=? WHERE tid=?",
            (message, digest, now, tid),
        )
        if tid:
            _refresh_contract_rollup_conn(conn, tid)
        conn.execute("DELETE FROM market_cached_views WHERE cache_key='pulse' OR cache_key LIKE 'topics:%%'")


def remove_thread(tid: int) -> None:
    """Remove an unavailable listing while retaining detached contract evidence."""
    with _db() as conn:
        conn.execute("DELETE FROM market_thread_snapshots WHERE tid=?", (tid,))
        conn.execute("DELETE FROM market_watch_matches WHERE tid=?", (tid,))
        conn.execute("DELETE FROM market_thread_refresh_queue WHERE tid=?", (tid,))
        conn.execute("DELETE FROM market_reply_verify_queue WHERE tid=?", (tid,))
        conn.execute("DELETE FROM market_threads WHERE tid=?", (tid,))
        conn.execute("DELETE FROM market_cached_views WHERE cache_key='pulse' OR cache_key LIKE 'topics:%%'")


def update_reply_count(tid: int, replies: int, confidence: str = "verified") -> None:
    now = int(time.time())
    with _db() as conn:
        conn.execute(
            "UPDATE market_threads SET replies=?,last_reply_checked_at=?,"
            "reply_confidence=?,reply_page_cursor=? WHERE tid=?",
            (replies, now, confidence, max(1, (replies + 1) // 30), tid),
        )
        conn.execute(
            "UPDATE market_thread_snapshots SET replies=? "
            "WHERE tid=? AND observed_at=("
            "SELECT MAX(observed_at) FROM market_thread_snapshots WHERE tid=?)",
            (replies, tid, tid),
        )


def promote_thread(tid: int, reason: str = "contract", priority: int = 100) -> None:
    now = int(time.time())
    with _db() as conn:
        conn.execute(
            "UPDATE market_threads SET heat_score=CASE WHEN heat_score<? THEN ? ELSE heat_score END,"
            "priority_tier='hot',next_refresh_at=? WHERE tid=?",
            (priority, priority, now, tid),
        )
        conn.execute(
            "INSERT INTO market_thread_refresh_queue "
            "(tid,priority,reason,next_attempt_at,updated_at) VALUES (?,?,?,?,?) "
            "ON CONFLICT(tid) DO UPDATE SET priority=CASE WHEN priority<excluded.priority "
            "THEN excluded.priority ELSE priority END,"
            "reason=excluded.reason,next_attempt_at=0,updated_at=excluded.updated_at",
            (tid, priority, reason, 0, now),
        )


def due_thread_refreshes(limit: int = 30) -> list[int]:
    now = int(time.time())
    with _db() as conn:
        rows = conn.execute(
            "SELECT q.tid FROM market_thread_refresh_queue q "
            "JOIN market_threads t ON t.tid=q.tid "
            "WHERE q.next_attempt_at<=? OR t.next_refresh_at<=? "
            "ORDER BY q.priority DESC,t.next_refresh_at ASC LIMIT ?",
            (now, now, max(1, min(limit, 30))),
        ).fetchall()
        return [int(_value(row, "tid", 0) or 0) for row in rows]


def finish_thread_refreshes(tids: list[int]) -> None:
    if not tids:
        return
    with _db() as conn:
        conn.executemany(
            "DELETE FROM market_thread_refresh_queue WHERE tid=?",
            [(tid,) for tid in tids],
        )


def defer_thread_refreshes(tids: list[int], seconds: int = 3600) -> None:
    if not tids:
        return
    now = int(time.time())
    with _db() as conn:
        conn.executemany(
            "UPDATE market_thread_refresh_queue SET attempts=attempts+1,"
            "next_attempt_at=?,updated_at=? WHERE tid=?",
            [(now + max(300, seconds), now, tid) for tid in tids],
        )


def due_reply_verification() -> dict | None:
    with _db() as conn:
        row = conn.execute(
            "SELECT tid,next_page FROM market_reply_verify_queue "
            "WHERE next_attempt_at<=? ORDER BY attempts ASC,updated_at ASC LIMIT 1",
            (int(time.time()),),
        ).fetchone()
        return dict(row) if row else None


def advance_reply_verification(tid: int, next_page: int) -> None:
    with _db() as conn:
        conn.execute(
            "UPDATE market_reply_verify_queue SET next_page=?,attempts=attempts+1,"
            "updated_at=? WHERE tid=?", (next_page, int(time.time()), tid),
        )


def finish_reply_verification(tid: int, replies: int) -> None:
    update_reply_count(tid, replies, "verified")
    with _db() as conn:
        conn.execute("DELETE FROM market_reply_verify_queue WHERE tid=?", (tid,))


def due_sellers(limit: int = 2) -> list[dict]:
    now = int(time.time())
    with _db() as conn:
        rows = conn.execute(
            "SELECT s.uid,s.contract_cursor_page,s.backfill_done,"
            "s.last_contract_count,s.last_contract_check_at,"
            "COALESCE(MAX(t.views),0) max_views "
            "FROM market_sellers s LEFT JOIN market_threads t "
            "ON t.seller_uid=s.uid WHERE s.last_contract_check_at=0 "
            "OR s.next_contract_check_at<=? "
            "GROUP BY s.uid,s.contract_cursor_page,s.backfill_done,"
            "s.last_contract_count,s.last_contract_check_at,"
            "s.next_contract_check_at "
            "ORDER BY (s.last_contract_check_at=0) DESC,s.backfill_done ASC,"
            "(s.last_contract_count>=30) DESC,"
            "max_views DESC,s.next_contract_check_at ASC LIMIT ?",
            (now, limit),
        ).fetchall()
        return [dict(row) for row in rows]


def _contract_seller_uid(discovered_uid: int, row: dict) -> int:
    contract_type = str(row.get("type") or "")
    initiator_uid = _as_int(row.get("inituid"))
    counterparty_uid = _as_int(row.get("otheruid"))
    if contract_type == "1" and initiator_uid:
        return initiator_uid
    if contract_type == "2" and counterparty_uid:
        return counterparty_uid
    return discovered_uid or initiator_uid or counterparty_uid


def _next_contract_status_check(status: str, now: int, existing_status: str | None) -> int:
    if status == "7":
        return now + 1800
    if status in ("0", "1", "5"):
        return now + 3600
    if status in ("2", "6", "8"):
        return 0 if existing_status == status else now + 86400
    return now + 7200


def upsert_contract(seller_uid: int, row: dict, status_refresh: bool = False) -> None:
    now = int(time.time())
    cid = _as_int(row.get("cid"))
    status = str(row.get("status") or "")
    initiator_uid = _as_int(row.get("inituid"))
    counterparty_uid = _as_int(row.get("otheruid"))
    with _db() as conn:
        existing = conn.execute(
            "SELECT status,scope FROM market_contracts WHERE cid=?", (cid,)
        ).fetchone()
        existing_status = (
            str(_value(existing, "status", "") or "") if existing else None
        )
        next_check = _next_contract_status_check(status, now, existing_status)
        resolved_seller_uid = _contract_seller_uid(seller_uid, row)
        tid = _as_int(row.get("tid"))
        known_market_thread = bool(tid and conn.execute(
            "SELECT 1 FROM market_threads WHERE tid=?", (tid,)
        ).fetchone())
        scope = "market" if known_market_thread else str(
            _value(existing, "scope", "unknown") or "unknown"
        )
        conn.execute("""
            INSERT INTO market_contracts
            (cid,seller_uid,initiator_uid,counterparty_uid,tid,status,
             contract_type,public_flag,scope,contract_at,other_at,first_seen_at,
             last_seen_at,status_checked_at,next_status_check_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(cid) DO UPDATE SET
             seller_uid=CASE WHEN excluded.seller_uid>0 THEN excluded.seller_uid
              ELSE market_contracts.seller_uid END,
             initiator_uid=CASE WHEN excluded.initiator_uid>0
              THEN excluded.initiator_uid ELSE market_contracts.initiator_uid END,
             counterparty_uid=CASE WHEN excluded.counterparty_uid>0
              THEN excluded.counterparty_uid ELSE market_contracts.counterparty_uid END,
             tid=excluded.tid,status=excluded.status,
             contract_type=excluded.contract_type,public_flag=excluded.public_flag,
             other_at=excluded.other_at,last_seen_at=excluded.last_seen_at,
             status_checked_at=excluded.status_checked_at,
             next_status_check_at=excluded.next_status_check_at
        """, (
            cid, resolved_seller_uid, initiator_uid, counterparty_uid,
            tid, status, str(row.get("type") or ""),
            _as_int(row.get("public")),
            scope,
            _as_int(row.get("dateline")), _as_int(row.get("otherdateline")),
            now, now, now if status_refresh else 0, next_check,
        ))
        if not existing or existing_status != status:
            conn.execute(
                "INSERT OR IGNORE INTO market_contract_events "
                "(cid,status,observed_at) VALUES (?,?,?)",
                (cid, status, now),
            )
        if tid and scope == "unknown" and not conn.execute(
            "SELECT 1 FROM market_threads WHERE tid=?", (tid,)
        ).fetchone():
            conn.execute(
                "INSERT OR IGNORE INTO market_contract_thread_queue "
                "(tid,first_seen_at,next_attempt_at) VALUES (?,?,0)",
                (tid, now),
            )
        if tid:
            _refresh_contract_rollup_conn(conn, tid)
        if tid and known_market_thread:
            conn.execute(
                "INSERT INTO market_thread_refresh_queue "
                "(tid,priority,reason,next_attempt_at,updated_at) VALUES (?,100,'contract',0,?) "
                "ON CONFLICT(tid) DO UPDATE SET priority=100,reason='contract',"
                "next_attempt_at=0,updated_at=excluded.updated_at",
                (tid, now),
            )
        conn.execute("DELETE FROM market_cached_views WHERE cache_key='pulse' OR cache_key LIKE 'topics:%%'")


def _refresh_contract_rollup_conn(conn, tid: int) -> None:
    tid = _as_int(tid)
    if not tid:
        return
    now = int(time.time())
    row = conn.execute(
        "SELECT COUNT(*) observed_contracts,"
        "SUM(status IN ('0','1')) awaiting_contracts,"
        "SUM(status='2') denied_contracts,SUM(status='4') cancelled_contracts,"
        "SUM(status='3') middleman_contracts,SUM(status='5') active_contracts,"
        "SUM(status='6') complete_contracts,SUM(status='7') disputed_contracts,"
        "SUM(status='8') expired_contracts,SUM(status='-1') invalid_contracts,"
        "SUM(status NOT IN ('-1','0','1','2','3','4','5','6','7','8')) other_contracts,"
        "MAX(contract_at) last_contract_at,MAX(last_seen_at) last_contract_seen_at "
        "FROM market_contracts WHERE tid=?",
        (tid,),
    ).fetchone()
    if not row or int(_value(row, "observed_contracts", 0) or 0) <= 0:
        conn.execute("DELETE FROM market_thread_contract_rollups WHERE tid=?", (tid,))
        return
    conn.execute(
        "INSERT INTO market_thread_contract_rollups "
        "(tid,observed_contracts,awaiting_contracts,denied_contracts,cancelled_contracts,"
        "middleman_contracts,active_contracts,complete_contracts,disputed_contracts,"
        "expired_contracts,invalid_contracts,other_contracts,last_contract_at,last_contract_seen_at,updated_at) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(tid) DO UPDATE SET "
        "observed_contracts=excluded.observed_contracts,awaiting_contracts=excluded.awaiting_contracts,"
        "denied_contracts=excluded.denied_contracts,cancelled_contracts=excluded.cancelled_contracts,"
        "middleman_contracts=excluded.middleman_contracts,active_contracts=excluded.active_contracts,"
        "complete_contracts=excluded.complete_contracts,disputed_contracts=excluded.disputed_contracts,"
        "expired_contracts=excluded.expired_contracts,invalid_contracts=excluded.invalid_contracts,"
        "other_contracts=excluded.other_contracts,last_contract_at=excluded.last_contract_at,"
        "last_contract_seen_at=excluded.last_contract_seen_at,updated_at=excluded.updated_at",
        (
            tid,
            int(_value(row, "observed_contracts", 0) or 0),
            int(_value(row, "awaiting_contracts", 0) or 0),
            int(_value(row, "denied_contracts", 0) or 0),
            int(_value(row, "cancelled_contracts", 0) or 0),
            int(_value(row, "middleman_contracts", 0) or 0),
            int(_value(row, "active_contracts", 0) or 0),
            int(_value(row, "complete_contracts", 0) or 0),
            int(_value(row, "disputed_contracts", 0) or 0),
            int(_value(row, "expired_contracts", 0) or 0),
            int(_value(row, "invalid_contracts", 0) or 0),
            int(_value(row, "other_contracts", 0) or 0),
            int(_value(row, "last_contract_at", 0) or 0),
            int(_value(row, "last_contract_seen_at", 0) or 0),
            now,
        ),
    )


def refresh_contract_rollups(tids: list[int] | None = None) -> int:
    with _db() as conn:
        if tids:
            changed = 0
            for tid in sorted({_as_int(tid) for tid in tids if _as_int(tid)}):
                _refresh_contract_rollup_conn(conn, tid)
                changed += 1
            return changed
        rows = conn.execute("SELECT DISTINCT tid FROM market_contracts WHERE tid>0").fetchall()
        for row in rows:
            _refresh_contract_rollup_conn(conn, int(_value(row, "tid", 0) or 0))
        return len(rows)


def _ensure_contract_rollups(conn) -> None:
    existing = conn.execute("SELECT COUNT(*) n FROM market_thread_contract_rollups").fetchone()
    if int(_value(existing, "n", 0) or 0) > 0:
        return
    tids = conn.execute("SELECT DISTINCT tid FROM market_contracts WHERE tid>0 LIMIT 50000").fetchall()
    for row in tids:
        _refresh_contract_rollup_conn(conn, int(_value(row, "tid", 0) or 0))


def get_contract_cursor(direction: str) -> dict:
    if direction not in ("forward", "backward"):
        raise ValueError("invalid contract cursor direction")
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM market_contract_cursors WHERE direction=?",
            (direction,),
        ).fetchone()
        if not row:
            raise RuntimeError(f"{direction} contract cursor is not initialized")
        return dict(row)


def advance_contract_cursor(
    direction: str, next_cid: int, returned_count: int,
) -> None:
    now = int(time.time())
    with _db() as conn:
        conn.execute(
            "UPDATE market_contract_cursors SET next_cid=?,last_scanned_at=?,"
            "last_returned_count=?,empty_streak=CASE WHEN ?>0 THEN 0 "
            "ELSE empty_streak+1 END,updated_at=? WHERE direction=?",
            (max(1, next_cid), now, returned_count, returned_count, now, direction),
        )


def update_forward_frontier(
    first_requested: int, returned_cids: list[int], overlap_size: int = 5,
) -> None:
    now = int(time.time())
    with _db() as conn:
        row = conn.execute(
            "SELECT anchor_cid,empty_streak,confirmed_cid FROM market_contract_cursors "
            "WHERE direction='forward'"
        ).fetchone()
        old_streak = int(_value(row, "empty_streak", 0) or 0)
        anchor = int(_value(row, "anchor_cid", 1) or 1)
        confirmed = int(_value(row, "confirmed_cid", 0) or 0)
        highest_returned = max(returned_cids) if returned_cids else 0
        found_new = highest_returned > confirmed
        if found_new:
            confirmed = highest_returned
            probe = max(anchor, confirmed + 1 - max(1, overlap_size))
            streak = 0
            delay = 180
        else:
            probe = max(anchor, first_requested)
            streak = old_streak + 1
            delay = min(3600, 180 * (2 ** min(streak - 1, 4)))
        conn.execute(
            "UPDATE market_contract_cursors SET next_cid=?,confirmed_cid=?,"
            "probe_cid=?,next_probe_at=?,overlap_size=?,last_scanned_at=?,"
            "last_returned_count=?,empty_streak=?,updated_at=? "
            "WHERE direction='forward'",
            (probe, confirmed, probe, now + delay, max(1, overlap_size), now,
             len(returned_cids) if found_new else 0, streak, now),
        )


def contract_frontier_due(direction: str = "forward") -> bool:
    with _db() as conn:
        row = conn.execute(
            "SELECT next_probe_at FROM market_contract_cursors WHERE direction=?",
            (direction,),
        ).fetchone()
        return int(_value(row, "next_probe_at", 0) or 0) <= int(time.time())


def mark_contract_thread_scope(tid: int, scope: str) -> None:
    if scope not in ("market", "external"):
        raise ValueError("invalid contract thread scope")
    with _db() as conn:
        conn.execute(
            "UPDATE market_contracts SET scope=? WHERE tid=?", (scope, tid)
        )
        conn.execute(
            "DELETE FROM market_contract_thread_queue WHERE tid=?", (tid,)
        )


def due_contract_status_cids(limit: int = 30) -> list[int]:
    now = int(time.time())
    with _db() as conn:
        rows = conn.execute(
            "SELECT cid FROM market_contracts WHERE next_status_check_at>0 "
            "AND next_status_check_at<=? ORDER BY "
            "CASE status WHEN '7' THEN 0 WHEN '0' THEN 1 WHEN '1' THEN 1 "
            "WHEN '5' THEN 2 ELSE 3 END,next_status_check_at ASC LIMIT ?",
            (now, max(1, min(limit, 30))),
        ).fetchall()
        return [int(_value(row, "cid", 0) or 0) for row in rows]


def defer_contract_status_cids(cids: list[int], seconds: int = 3600) -> None:
    if not cids:
        return
    due_at = int(time.time()) + max(300, seconds)
    with _db() as conn:
        conn.executemany(
            "UPDATE market_contracts SET next_status_check_at=? WHERE cid=?",
            [(due_at, cid) for cid in cids],
        )


def due_contract_threads(limit: int = 30) -> list[int]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT tid FROM market_contract_thread_queue "
            "WHERE next_attempt_at<=? ORDER BY attempts ASC,first_seen_at DESC "
            "LIMIT ?",
            (int(time.time()), max(1, min(limit, 30))),
        ).fetchall()
        return [int(_value(row, "tid", 0) or 0) for row in rows]


def defer_contract_threads(tids: list[int]) -> None:
    if not tids:
        return
    now = int(time.time())
    with _db() as conn:
        conn.executemany(
            "UPDATE market_contract_thread_queue SET attempts=attempts+1,"
            "next_attempt_at=? WHERE tid=?",
            [(now + 86400, tid) for tid in tids],
        )


def mark_seller_checked(uid: int, contract_count: int, page: int = 1) -> None:
    now = int(time.time())
    saturated = contract_count >= 30
    interval = 0 if saturated else (21600 if contract_count else 86400)
    with _db() as conn:
        conn.execute(
            "UPDATE market_sellers SET last_contract_check_at=?,"
            "next_contract_check_at=?,last_contract_count=?,"
            "contract_cursor_page=?,backfill_done=? WHERE uid=?",
            (
                now, now + interval, contract_count,
                page + 1 if saturated else 1,
                0 if saturated else 1, uid,
            ),
        )


def contract_coverage() -> dict:
    with _db() as conn:
        row = conn.execute(
            "SELECT COUNT(*) discovered,"
            "SUM(last_contract_check_at>0) queried,"
            "SUM(backfill_done=1) fully_paginated,"
            "SUM(contract_cursor_page>1) pagination_pending "
            "FROM market_sellers"
        ).fetchone()
        joined = conn.execute(
            "SELECT COUNT(*) contracts,COUNT(DISTINCT c.tid) threads "
            "FROM market_contracts c JOIN market_threads t ON t.tid=c.tid"
        ).fetchone()
        observed = conn.execute(
            "SELECT COUNT(*) total,"
            "SUM(status='0') awaiting,"
            "SUM(status='2') denied,SUM(status='4') cancelled,"
            "SUM(status='3') middleman,SUM(status='5') active,"
            "SUM(status='6') complete,SUM(status='7') disputed,"
            "SUM(status IN ('1','8')) expired,SUM(status='-1') invalid,"
            "SUM(status NOT IN ('-1','0','1','2','3','4','5','6','7','8')) other "
            "FROM market_contracts"
        ).fetchone()
        observed_total = int(_value(observed, "total", 0) or 0)
        joined_total = int(_value(joined, "contracts", 0) or 0)
        queued = conn.execute(
            "SELECT COUNT(*) n FROM market_contract_thread_queue"
        ).fetchone()
        scopes = conn.execute(
            "SELECT "
            "SUM(scope='market') market_scope,"
            "SUM(scope='external') external_scope,"
            "SUM(scope='unknown') unknown_scope "
            "FROM market_contracts"
        ).fetchone()
        cursors = conn.execute(
            "SELECT direction,anchor_cid,next_cid,last_scanned_at,"
            "last_returned_count,empty_streak,confirmed_cid,probe_cid,"
            "next_probe_at,overlap_size "
            "FROM market_contract_cursors ORDER BY direction"
        ).fetchall()
        return {
            "discovered_sellers": int(_value(row, "discovered", 0) or 0),
            "queried_sellers": int(_value(row, "queried", 0) or 0),
            "fully_paginated_sellers": int(_value(row, "fully_paginated", 0) or 0),
            "pagination_pending": int(_value(row, "pagination_pending", 0) or 0),
            "observed_contracts": observed_total,
            "joined_contracts": joined_total,
            "unlinked_contracts": observed_total - joined_total,
            "pending_thread_lookups": int(_value(queued, "n", 0) or 0),
            "threads_with_contracts": int(_value(joined, "threads", 0) or 0),
            "scope_counts": {
                "market": int(_value(scopes, "market_scope", 0) or 0),
                "external": int(_value(scopes, "external_scope", 0) or 0),
                "unknown": int(_value(scopes, "unknown_scope", 0) or 0),
            },
            "cursors": [dict(cursor) for cursor in cursors],
            "status_counts": {
                key: int(_value(observed, key, 0) or 0)
                for key in (
                    "awaiting", "denied", "cancelled", "middleman", "active",
                    "complete", "disputed", "expired", "invalid", "other",
                )
            },
        }


def collector_health() -> dict:
    now = int(time.time())
    with _db() as conn:
        refresh = conn.execute(
            "SELECT COUNT(*) n,SUM(next_attempt_at<=?) due "
            "FROM market_thread_refresh_queue", (now,)
        ).fetchone()
        replies = conn.execute(
            "SELECT COUNT(*) n,SUM(next_attempt_at<=?) due "
            "FROM market_reply_verify_queue", (now,)
        ).fetchone()
        confidence = conn.execute(
            "SELECT reply_confidence,COUNT(*) n FROM market_threads "
            "GROUP BY reply_confidence"
        ).fetchall()
        tiers = conn.execute(
            "SELECT priority_tier,COUNT(*) n FROM market_threads "
            "GROUP BY priority_tier"
        ).fetchall()
        forums = conn.execute(
            "SELECT SUM(backfill_page) pages,COUNT(*) forums FROM market_forums "
            "WHERE enabled=1"
        ).fetchone()
    coverage = contract_coverage()
    backward = next(
        (row for row in coverage["cursors"] if row["direction"] == "backward"), {}
    )
    anchor = int(backward.get("anchor_cid") or 0)
    remaining = max(0, int(backward.get("next_cid") or 0) - 1)
    return {
        "generated_at": now,
        "calls_last_hour": calls_last_hour(),
        "last_known_remaining": latest_remaining(),
        "contract_frontiers": coverage["cursors"],
        "backlogs": {
            "contract_threads": coverage["pending_thread_lookups"],
            "thread_refresh": int(_value(refresh, "n", 0) or 0),
            "thread_refresh_due": int(_value(refresh, "due", 0) or 0),
            "reply_verification": int(_value(replies, "n", 0) or 0),
            "reply_verification_due": int(_value(replies, "due", 0) or 0),
        },
        "reply_confidence": {
            str(row["reply_confidence"]): int(row["n"]) for row in confidence
        },
        "priority_tiers": {
            str(row["priority_tier"]): int(row["n"]) for row in tiers
        },
        "historical_contract_progress": {
            "anchor_cid": anchor,
            "remaining_cids": remaining,
            "percent": round(100 * (anchor - remaining) / anchor, 2) if anchor else None,
        },
        "historical_thread_pages": int(_value(forums, "pages", 0) or 0),
    }


def run_summary() -> dict:
    with _db() as conn:
        totals = {}
        for name, table in (
            ("threads", "market_threads"),
            ("sellers", "market_sellers"),
            ("contracts", "market_contracts"),
            ("watches", "market_watches"),
        ):
            row = conn.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()
            totals[name] = int(_value(row, "n", 0) or 0)
        latest = conn.execute(
            "SELECT * FROM market_collection_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        totals["latest_run"] = dict(latest) if latest else None
        return totals


def forum_coverage() -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT f.fid,f.name,f.backfill_page,f.refresh_page,"
            "f.last_scanned_at,COUNT(t.tid) indexed_threads "
            "FROM market_forums f LEFT JOIN market_threads t ON t.fid=f.fid "
            "WHERE f.enabled=1 GROUP BY f.fid,f.name,f.backfill_page,"
            "f.refresh_page,f.last_scanned_at ORDER BY indexed_threads DESC"
        ).fetchall()
        return [dict(row) for row in rows]


def list_threads(
    page: int, perpage: int, fid: int | None = None, category: str = "",
    market_type: str = "", query: str = "", contract_only: bool = False,
    sort: str = "posted", sort_dir: str = "desc", days: int = 0,
    contract_status: str = "", topic_id: int | None = None,
) -> dict:
    clauses, params = [
        "LOWER(TRIM(COALESCE(t.opening_post,''))) NOT IN ('[deleted]','deleted')",
        "t.market_type IN ('wtb','wts')",
    ], []
    if fid:
        clauses.append("t.fid=?")
        params.append(fid)
    if category:
        clauses.append("t.category=?")
        params.append(category)
    if market_type:
        clauses.append("t.market_type=?")
        params.append(market_type)
    if query:
        clauses.append("(t.subject LIKE ? OR t.opening_post LIKE ?)")
        params.extend((f"%{query}%", f"%{query}%"))
    if topic_id:
        clauses.append(
            "EXISTS (SELECT 1 FROM market_thread_topics mt WHERE mt.tid=t.tid "
            "AND mt.topic_id=? AND mt.confidence_band IN ('exact','strong'))"
        )
        params.append(topic_id)
    if contract_only:
        clauses.append("EXISTS (SELECT 1 FROM market_contracts c WHERE c.tid=t.tid)")
    if contract_status:
        statuses = {
            "awaiting": ("0", "1"), "cancelled": ("2", "4"),
            "middleman": ("3",), "active": ("5",), "complete": ("6",),
            "disputed": ("7",), "expired": ("8",),
        }.get(contract_status, (contract_status,))
        placeholders = ",".join("?" for _ in statuses)
        clauses.append(
            "EXISTS (SELECT 1 FROM market_contracts c WHERE c.tid=t.tid "
            f"AND c.status IN ({placeholders}))"
        )
        params.extend(statuses)
    if days:
        clauses.append("t.created_at>=?")
        params.append(int(time.time()) - max(1, min(days, 365)) * 86400)
    where = " AND ".join(clauses)
    offset = (page - 1) * perpage
    direction = "ASC" if sort_dir.lower() == "asc" else "DESC"
    sort_column = {
        "newest": "t.created_at", "posted": "t.created_at",
        "views": "t.views", "replies": "t.replies",
        "recent_contracts": "COALESCE(c.last_contract_at,0)",
        "total_contracts": "COALESCE(c.observed_contracts,0)",
        "complete_contracts": "COALESCE(c.complete_contracts,0)",
        "active_contracts": "COALESCE(c.active_contracts,0)",
        "cancelled_contracts": "COALESCE(c.cancelled_contracts,0)",
        "disputed_contracts": "COALESCE(c.disputed_contracts,0)",
        "expired_contracts": "COALESCE(c.expired_contracts,0)",
    }.get(sort, "t.created_at")
    order_by = f"{sort_column} {direction},t.created_at DESC"
    with _db() as conn:
        _ensure_contract_rollups(conn)
        rows = conn.execute(
            f"SELECT t.*,f.name forum_name,"
            "COALESCE(c.observed_contracts,0) observed_contracts,"
            "COALESCE(c.active_contracts,0) active_contracts,"
            "COALESCE(c.complete_contracts,0) complete_contracts,"
            "COALESCE(c.awaiting_contracts,0) awaiting_contracts,"
            "COALESCE(c.denied_contracts,0) denied_contracts,"
            "COALESCE(c.cancelled_contracts,0) cancelled_contracts,"
            "COALESCE(c.middleman_contracts,0) middleman_contracts,"
            "COALESCE(c.disputed_contracts,0) disputed_contracts,"
            "COALESCE(c.expired_contracts,0) expired_contracts,"
            "COALESCE(c.invalid_contracts,0) invalid_contracts,"
            "COALESCE(c.other_contracts,0) other_contracts,"
            "COALESCE(c.last_contract_seen_at,0) last_contract_seen_at "
            "FROM market_threads t JOIN market_forums f ON f.fid=t.fid "
            "LEFT JOIN market_thread_contract_rollups c ON c.tid=t.tid "
            f"WHERE {where} ORDER BY {order_by} LIMIT ? OFFSET ?",
            (*params, perpage, offset),
        ).fetchall()
        total_row = conn.execute(
            f"SELECT COUNT(*) AS n FROM market_threads t WHERE {where}", params
        ).fetchone()
        items = [dict(row) for row in rows]
        now = int(time.time())
        for item in items:
            old = conn.execute(
                "SELECT views,replies FROM market_thread_snapshots "
                "WHERE tid=? AND observed_at<=? ORDER BY observed_at DESC LIMIT 1",
                (item["tid"], now - 604800),
            ).fetchone()
            item["views_7d"] = int(item["views"]) - int(_value(old, "views", item["views"]) or item["views"])
            item["replies_7d"] = int(item["replies"]) - int(_value(old, "replies", item["replies"]) or item["replies"])
            item["excerpt"] = str(item.get("opening_post") or "")[:260]
            item.pop("opening_post", None)
        return {
            "threads": items,
            "total": int(_value(total_row, "n", 0) or 0),
            "page": page,
            "perpage": perpage,
        }


def list_contracts(
    page: int, perpage: int, status: str = "", query: str = "",
    sort: str = "date", sort_dir: str = "desc",
) -> dict:
    clauses, params = [], []
    if status:
        statuses = {
            "awaiting": ("0", "1"), "cancelled": ("2", "4"),
            "middleman": ("3",), "active": ("5",), "complete": ("6",),
            "disputed": ("7",), "expired": ("8",),
        }.get(status, (status,))
        placeholders = ",".join("?" for _ in statuses)
        clauses.append(f"c.status IN ({placeholders})")
        params.extend(statuses)
    if query:
        clauses.append(
            "(CAST(c.cid AS CHAR) LIKE ? OR CAST(c.tid AS CHAR) LIKE ? "
            "OR CAST(c.seller_uid AS CHAR) LIKE ? OR t.subject LIKE ?)"
        )
        term = f"%{query}%"
        params.extend((term, term, term, term))
    where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
    direction = "ASC" if sort_dir.lower() == "asc" else "DESC"
    sort_column = {
        "date": "c.contract_at", "seller": "c.seller_uid",
        "tid": "c.tid", "status": "c.status",
    }.get(sort, "c.contract_at")
    offset = (page - 1) * perpage
    with _db() as conn:
        rows = conn.execute(
            "SELECT c.cid,c.tid,c.seller_uid,c.initiator_uid,"
            "c.counterparty_uid,c.status,c.contract_type,c.public_flag,c.scope,"
            "c.contract_at,c.other_at,c.status_checked_at,"
            "c.next_status_check_at,t.subject,f.name forum_name "
            "FROM market_contracts c LEFT JOIN market_threads t ON t.tid=c.tid "
            "LEFT JOIN market_forums f ON f.fid=t.fid "
            f"{where} ORDER BY {sort_column} {direction},c.cid DESC "
            "LIMIT ? OFFSET ?",
            (*params, perpage, offset),
        ).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) n FROM market_contracts c "
            "LEFT JOIN market_threads t ON t.tid=c.tid "
            f"{where}", params,
        ).fetchone()
        return {
            "contracts": [dict(row) for row in rows],
            "total": int(_value(total, "n", 0) or 0),
            "page": page, "perpage": perpage,
        }


def thread_detail(tid: int) -> dict | None:
    with _db() as conn:
        row = conn.execute(
            "SELECT t.*,f.name forum_name FROM market_threads t "
            "JOIN market_forums f ON f.fid=t.fid WHERE t.tid=? "
            "AND LOWER(TRIM(COALESCE(t.opening_post,''))) "
            "NOT IN ('[deleted]','deleted')", (tid,)
        ).fetchone()
        if not row:
            return None
        item = dict(row)
        contracts = conn.execute(
            "SELECT status,COUNT(*) count,MIN(contract_at) first_at,"
            "MAX(contract_at) last_at FROM market_contracts WHERE tid=? "
            "GROUP BY status ORDER BY status", (tid,)
        ).fetchall()
        snapshots = conn.execute(
            "SELECT observed_at,views,replies,lastpost_at "
            "FROM market_thread_snapshots WHERE tid=? "
            "ORDER BY observed_at DESC LIMIT 90", (tid,)
        ).fetchall()
        item["contract_counts"] = [dict(value) for value in contracts]
        item["snapshots"] = [dict(value) for value in reversed(snapshots)]
        return item


def pulse(force: bool = False) -> dict:
    now = int(time.time())
    week = now - 604800
    with _db() as conn:
        if not force:
            cached = conn.execute(
                "SELECT payload,updated_at FROM market_cached_views WHERE cache_key='pulse'"
            ).fetchone()
            if cached and now - int(cached["updated_at"] or 0) <= 7200:
                return json.loads(cached["payload"])
        category_rows = conn.execute(
            "SELECT t.category,COUNT(*) threads,"
            "SUM(t.market_type='wtb') wtb_threads,"
            "COALESCE(SUM(c.observed_contracts),0) contracts,"
            "COALESCE(SUM(c.active_contracts),0) active_contracts,"
            "COALESCE(SUM(c.complete_contracts),0) complete_contracts "
            "FROM market_threads t LEFT JOIN market_thread_contract_rollups c ON c.tid=t.tid "
            "WHERE t.first_seen_at>=? AND t.market_type IN ('wtb','wts') AND "
            "LOWER(TRIM(COALESCE(t.opening_post,''))) NOT IN ('[deleted]','deleted') "
            "GROUP BY t.category "
            "ORDER BY complete_contracts DESC,threads DESC",
            (week,),
        ).fetchall()
        recent = list_threads(1, 8)
        recent_demand = list_threads(1, 6, market_type="wtb", days=7)
        result = {
            "generated_at": now,
            "categories": [dict(row) for row in category_rows],
            "recent_threads": recent["threads"],
            "recent_buyer_threads": recent_demand["threads"],
            "forum_coverage": forum_coverage(),
            "contract_coverage": contract_coverage(),
            **run_summary(),
        }
        payload = json.dumps(result, separators=(",", ":"), default=str)
        conn.execute(
            "INSERT OR REPLACE INTO market_cached_views (cache_key,payload,updated_at) VALUES ('pulse',?,?)",
            (payload, now),
        )
        return result


def movers(days: int = 30) -> dict:
    cutoff = int(time.time()) - max(1, min(days, 365)) * 86400
    with _db() as conn:
        sellers = conn.execute(
            "SELECT t.seller_uid,COUNT(DISTINCT t.tid) threads,"
            "COUNT(DISTINCT c.cid) observed_contracts,"
            "SUM(c.status='5') active_contracts,SUM(c.status='6') complete_contracts "
            "FROM market_threads t LEFT JOIN market_contracts c ON c.tid=t.tid "
            "AND c.contract_at>=? WHERE t.market_type IN ('wtb','wts') GROUP BY t.seller_uid "
            "ORDER BY complete_contracts DESC,observed_contracts DESC LIMIT 50",
            (cutoff,),
        ).fetchall()
        threads = conn.execute(
            "SELECT t.tid,t.subject,t.seller_uid,t.views,t.replies,"
            "COUNT(c.cid) observed_contracts,SUM(c.status='5') active_contracts,"
            "SUM(c.status='6') complete_contracts "
            "FROM market_threads t JOIN market_contracts c ON c.tid=t.tid "
            "WHERE c.contract_at>=? AND t.market_type IN ('wtb','wts') "
            "GROUP BY t.tid,t.subject,t.seller_uid,t.views,t.replies "
            "ORDER BY complete_contracts DESC,observed_contracts DESC LIMIT 50",
            (cutoff,),
        ).fetchall()
        return {
            "days": days,
            "sellers": [dict(row) for row in sellers],
            "threads": [dict(row) for row in threads],
        }


def list_topics(days: int = 30, limit: int = 50) -> list[dict]:
    now = int(time.time())
    days = max(1, min(days, 365)); limit = max(1, min(limit, 1000))
    cutoff = now - days * 86400
    cache_key = f"topics:{days}:{limit}"
    with _db() as conn:
        cached = conn.execute(
            "SELECT payload,updated_at FROM market_cached_views WHERE cache_key=?", (cache_key,)
        ).fetchone()
        if cached and now - int(cached["updated_at"] or 0) <= 300:
            return json.loads(cached["payload"])
        rows = conn.execute(
            "SELECT p.id,p.slug,p.name,p.updated_at,"
            "COALESCE(a.buyer_threads,0) buyer_threads,"
            "COALESCE(a.unique_buyers,0) unique_buyers,"
            "COALESCE(a.seller_threads,0) seller_threads,"
            "COALESCE(c.observed_contracts,0) observed_contracts,"
            "COALESCE(c.completed_contracts,0) completed_contracts "
            "FROM market_topics p LEFT JOIN ("
            " SELECT mt.topic_id,SUM(t.market_type='wtb') buyer_threads,"
            " COUNT(DISTINCT CASE WHEN t.market_type='wtb' THEN t.seller_uid END) unique_buyers,"
            " SUM(t.market_type='wts') seller_threads FROM market_thread_topics mt "
            " JOIN market_threads t ON t.tid=mt.tid WHERE mt.confidence_band IN ('exact','strong') "
            " AND t.market_type IN ('wtb','wts') "
            " AND t.created_at>=? AND t.closed=0 AND LOWER(TRIM(t.subject)) NOT LIKE 'delete%%' "
            " AND LOWER(TRIM(t.subject)) NOT LIKE 'closed%%' AND LOWER(TRIM(t.subject)) NOT IN ('sold','-----') "
            " AND LOWER(TRIM(COALESCE(t.opening_post,''))) NOT IN ('[deleted]','deleted','closed') "
            " GROUP BY mt.topic_id"
            ") a ON a.topic_id=p.id LEFT JOIN ("
            " SELECT mt.topic_id,COUNT(DISTINCT c.cid) observed_contracts,"
            " COUNT(DISTINCT CASE WHEN c.status='6' THEN c.cid END) completed_contracts "
            " FROM market_thread_topics mt JOIN market_threads t ON t.tid=mt.tid "
            " JOIN market_contracts c ON c.tid=mt.tid "
            " WHERE mt.confidence_band IN ('exact','strong') AND t.market_type IN ('wtb','wts') "
            " AND c.contract_at>=? GROUP BY mt.topic_id"
            ") c ON c.topic_id=p.id WHERE p.status='active' "
            "AND (COALESCE(a.buyer_threads,0)>0 OR COALESCE(a.seller_threads,0)>0) "
            "ORDER BY buyer_threads DESC,unique_buyers DESC LIMIT ?",
            (cutoff, cutoff, max(1, min(limit, 100))),
        ).fetchall()
        result = []
        for raw in rows:
            item = dict(raw)
            supply = int(item.get("seller_threads") or 0)
            demand = int(item.get("unique_buyers") or 0)
            item["demand_supply_ratio"] = round(demand / max(1, supply), 2)
            result.append(item)
        conn.execute(
            "INSERT OR REPLACE INTO market_cached_views (cache_key,payload,updated_at) VALUES (?,?,?)",
            (cache_key, json.dumps(result, separators=(",", ":"), default=str), now),
        )
        return result


def topic_detail(topic_id: int, days: int = 30, include_threads: bool = False) -> dict | None:
    cutoff = int(time.time()) - max(1, min(days, 365)) * 86400
    with _db() as conn:
        topic = conn.execute(
            "SELECT * FROM market_topics WHERE id=? AND status='active'", (topic_id,)
        ).fetchone()
        if not topic:
            return None
        history = conn.execute(
            "SELECT * FROM market_topic_snapshots WHERE topic_id=? "
            "ORDER BY snapshot_date DESC LIMIT 90", (topic_id,)
        ).fetchall()
        result = dict(topic)
        result["history"] = [dict(row) for row in reversed(history)]
        result["summary"] = next(
            (row for row in list_topics(days, 1000) if int(row["id"]) == topic_id), {}
        )
        if include_threads:
            rows = conn.execute(
                "SELECT t.tid,t.subject,t.market_type,t.category,t.seller_uid,t.created_at,"
                "t.views,t.replies,mt.confidence,mt.confidence_band,f.name forum_name "
                "FROM market_thread_topics mt JOIN market_threads t ON t.tid=mt.tid "
                "JOIN market_forums f ON f.fid=t.fid WHERE mt.topic_id=? "
                "AND mt.confidence_band IN ('exact','strong') AND t.market_type IN ('wtb','wts') "
                "AND t.created_at>=? AND t.closed=0 "
                "AND LOWER(TRIM(t.subject)) NOT LIKE 'delete%%' AND LOWER(TRIM(t.subject)) NOT LIKE 'closed%%' "
                "AND LOWER(TRIM(t.subject)) NOT IN ('sold','-----') "
                "AND LOWER(TRIM(COALESCE(t.opening_post,''))) NOT IN ('[deleted]','deleted','closed') "
                "ORDER BY t.created_at DESC LIMIT 100", (topic_id, cutoff)
            ).fetchall()
            result["threads"] = [dict(row) for row in rows]
        return result


def list_disputes(page: int = 1, perpage: int = 25) -> dict:
    """Return Deal Disputes as a risk feed, separate from market demand."""
    page = max(1, page)
    perpage = max(1, min(perpage, 50))
    offset = (page - 1) * perpage
    with _db() as conn:
        rows = conn.execute(
            "SELECT t.tid,t.subject,t.seller_uid,t.created_at,t.lastpost_at,t.views,t.replies,"
            "t.closed,t.last_seen_at,f.name forum_name "
            "FROM market_threads t JOIN market_forums f ON f.fid=t.fid "
            "WHERE (t.fid=111 OR t.market_type='dispute') "
            "AND LOWER(TRIM(COALESCE(t.opening_post,''))) NOT IN ('[deleted]','deleted') "
            "ORDER BY t.created_at DESC LIMIT ? OFFSET ?",
            (perpage, offset),
        ).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) n FROM market_threads t WHERE (t.fid=111 OR t.market_type='dispute') "
            "AND LOWER(TRIM(COALESCE(t.opening_post,''))) NOT IN ('[deleted]','deleted')"
        ).fetchone()
        return {
            "disputes": [dict(row) for row in rows],
            "total": int(_value(total, "n", 0) or 0),
            "page": page,
            "perpage": perpage,
        }


def topic_for_thread(tid: int) -> dict | None:
    with _db() as conn:
        row = conn.execute(
            "SELECT p.id,p.slug,p.name,mt.confidence,mt.confidence_band "
            "FROM market_thread_topics mt JOIN market_topics p ON p.id=mt.topic_id "
            "WHERE mt.tid=? ORDER BY mt.confidence DESC LIMIT 1", (tid,)
        ).fetchone()
        return dict(row) if row else None


def owned_thread_intelligence(uid: str, tid: int) -> dict:
    with _db() as conn:
        owned = conn.execute(
            "SELECT 1 FROM my_threads WHERE uid=? AND tid=?", (uid, str(tid))
        ).fetchone()
        if not owned:
            return {}
    topic = topic_for_thread(tid)
    if not topic:
        return {"topic": None}
    detail = topic_detail(int(topic["id"]), 30, False) or {}
    return {"topic": topic, "market": detail.get("summary", {})}


def access_status(uid: str) -> dict:
    now = int(time.time())
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM market_passes WHERE uid=?", (uid,)
        ).fetchone()
        expires = int(_value(row, "expires_at", 0) or 0)
        return {"paid": expires > now, "expires_at": expires}


def expiring_passes(days: int = 7) -> list[dict]:
    now = int(time.time())
    with _db() as conn:
        rows = conn.execute(
            "SELECT uid,expires_at FROM market_passes "
            "WHERE expires_at>? AND expires_at<=?",
            (now, now + max(1, days) * 86400),
        ).fetchall()
        return [dict(row) for row in rows]


def active_pass_uids() -> list[str]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT uid FROM market_passes WHERE expires_at>?", (int(time.time()),)
        ).fetchall()
        return [str(row["uid"]) for row in rows]


def get_payment(payment_id: str, uid: str) -> dict | None:
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM market_payments WHERE payment_id=? AND uid=?",
            (payment_id, uid),
        ).fetchone()
        return dict(row) if row else None


def create_payment(
    payment_id: str,
    uid: str,
    amount: int,
    days: int,
    reference: str = "",
    receiver_uid: str = "",
    fee_label: str = "",
    idempotency_key: str = "",
) -> None:
    reference = reference or payment_id
    fee_label = fee_label or f"HFToolbox | Market Pass | Ref: {reference}"
    idempotency_key = idempotency_key or payment_id
    with _db() as conn:
        conn.execute(
            "INSERT INTO market_payments "
            "(payment_id,uid,amount,duration_days,status,created_at,reference,"
            "receiver_uid,fee_label,idempotency_key,last_attempt_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (
                payment_id,
                uid,
                amount,
                days,
                "pending",
                int(time.time()),
                reference,
                receiver_uid,
                fee_label,
                idempotency_key,
                int(time.time()),
            ),
        )


def complete_payment(
    payment_id: str,
    uid: str,
    days: int,
    permanent: bool = False,
    hf_result: dict | None = None,
) -> int:
    now = int(time.time())
    with _db() as conn:
        current = conn.execute(
            "SELECT expires_at FROM market_passes WHERE uid=?", (uid,)
        ).fetchone()
        if permanent:
            expires = 4102444800
        else:
            base = max(now, int(_value(current, "expires_at", 0) or 0))
            expires = base + max(1, days) * 86400
        conn.execute("""
            INSERT INTO market_passes
            (uid,starts_at,expires_at,source_payment_id,updated_at)
            VALUES (?,?,?,?,?)
            ON CONFLICT(uid) DO UPDATE SET expires_at=excluded.expires_at,
             source_payment_id=excluded.source_payment_id,updated_at=excluded.updated_at
        """, (uid, now, expires, payment_id, now))
        conn.execute(
            "UPDATE market_payments SET status='complete',completed_at=?,"
            "hf_result_json=? WHERE payment_id=?",
            (
                now,
                json.dumps(hf_result or {}, separators=(",", ":"), default=str),
                payment_id,
            ),
        )
        return expires


def fail_payment(payment_id: str, error: str) -> None:
    with _db() as conn:
        conn.execute(
            "UPDATE market_payments SET status='failed',error=?,last_attempt_at=? "
            "WHERE payment_id=?",
            (error[:500], int(time.time()), payment_id),
        )


def hold_payment(payment_id: str, error: str) -> None:
    with _db() as conn:
        conn.execute(
            "UPDATE market_payments SET status='held',error=?,last_attempt_at=? "
            "WHERE payment_id=?",
            (error[:500], int(time.time()), payment_id),
        )


def list_watches(uid: str) -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM market_watches WHERE uid=? ORDER BY created_at DESC",
            (uid,),
        ).fetchall()
        return [dict(row) for row in rows]


def create_watch(uid: str, data: dict) -> int:
    now = int(time.time())
    with _db() as conn:
        cur = conn.execute(
            "INSERT INTO market_watches "
            "(uid,name,required_phrase,optional_terms,excluded_terms,fids_json,"
            "market_type,seller_uid,watch_kind,topic_id,category_filter,thread_tid,"
            "telegram_enabled,enabled,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?)",
            (
                uid, data["name"], data.get("required_phrase", ""),
                json.dumps(data.get("optional_terms", [])),
                json.dumps(data.get("excluded_terms", [])),
                json.dumps(data.get("fids", [])),
                data.get("market_type", "any"),
                data.get("seller_uid", ""), data.get("watch_kind", "phrase"),
                data.get("topic_id"), data.get("category", ""), data.get("thread_tid"),
                int(data.get("telegram_enabled", False)),
                now, now,
            ),
        )
        return int(cur.lastrowid)


def delete_watch(uid: str, watch_id: int) -> bool:
    with _db() as conn:
        cur = conn.execute(
            "DELETE FROM market_watches WHERE id=? AND uid=?", (watch_id, uid)
        )
        return bool(cur.rowcount)


def list_watch_matches(uid: str, limit: int = 100) -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT m.id,m.watch_id,m.tid,m.matched_at,m.alerted_at,"
            "w.name watch_name,t.subject,t.market_type,t.category,t.views,t.replies "
            "FROM market_watch_matches m "
            "JOIN market_watches w ON w.id=m.watch_id "
            "JOIN market_threads t ON t.tid=m.tid "
            "WHERE m.uid=? ORDER BY m.matched_at DESC LIMIT ?",
            (uid, limit),
        ).fetchall()
        return [dict(row) for row in rows]


def list_watch_matches_page(uid: str, page: int = 1, perpage: int = 25) -> dict:
    page = max(1, int(page)); perpage = max(1, min(int(perpage), 50))
    offset = (page - 1) * perpage
    with _db() as conn:
        rows = conn.execute(
            "SELECT m.id,m.watch_id,m.tid,m.matched_at,m.alerted_at,"
            "w.name watch_name,t.subject,t.market_type,t.category,t.views,t.replies "
            "FROM market_watch_matches m JOIN market_watches w ON w.id=m.watch_id "
            "JOIN market_threads t ON t.tid=m.tid WHERE m.uid=? "
            "ORDER BY m.matched_at DESC LIMIT ? OFFSET ?", (uid, perpage, offset),
        ).fetchall()
        total = conn.execute(
            "SELECT COUNT(*) n FROM market_watch_matches WHERE uid=?", (uid,)
        ).fetchone()
        return {"matches": [dict(row) for row in rows], "total": int(total["n"] or 0),
                "page": page, "perpage": perpage}


def match_watches_for_thread(tid: int) -> int:
    thread = get_thread(tid)
    if not thread:
        return 0
    haystack = f"{thread.get('subject','')} {thread.get('opening_post','')}".lower()
    base_version = f"{thread.get('opening_post_hash') or ''}:{thread.get('lastpost_at') or 0}"
    matched = 0
    with _db() as conn:
        watches = conn.execute(
            "SELECT * FROM market_watches WHERE enabled=1"
        ).fetchall()
        for raw in watches:
            watch = dict(raw)
            kind = str(watch.get("watch_kind") or "phrase")
            phrase = str(watch.get("required_phrase") or "").lower().strip()
            optional = json.loads(watch.get("optional_terms") or "[]")
            excluded = json.loads(watch.get("excluded_terms") or "[]")
            fids = json.loads(watch.get("fids_json") or "[]")
            if phrase and phrase not in haystack:
                continue
            if optional and not any(str(term).lower() in haystack for term in optional):
                continue
            if any(str(term).lower() in haystack for term in excluded):
                continue
            if fids and int(thread["fid"]) not in [int(fid) for fid in fids]:
                continue
            if watch.get("market_type") not in ("", "any", thread["market_type"]):
                continue
            if watch.get("seller_uid") and str(watch["seller_uid"]) != str(thread["seller_uid"]):
                continue
            if watch.get("category_filter") and watch["category_filter"] != thread.get("category"):
                continue
            if watch.get("thread_tid") and int(watch["thread_tid"]) != int(tid):
                continue
            if watch.get("topic_id"):
                topic_match = conn.execute(
                    "SELECT 1 FROM market_thread_topics WHERE tid=? AND topic_id=? "
                    "AND confidence_band IN ('exact','strong')", (tid, watch["topic_id"]),
                ).fetchone()
                if not topic_match:
                    continue
            if kind == "buyer_demand" and thread.get("market_type") != "wtb":
                continue
            if kind == "contract_movement":
                contract = conn.execute(
                    "SELECT COUNT(*) total,MAX(last_seen_at) latest FROM market_contracts WHERE tid=?",
                    (tid,),
                ).fetchone()
                if not contract or not int(contract["total"] or 0):
                    continue
            if kind == "owned_thread_activity":
                owned = conn.execute(
                    "SELECT 1 FROM my_threads WHERE uid=? AND tid=?", (watch["uid"], str(tid))
                ).fetchone()
                if not owned:
                    continue
            version = base_version
            if kind == "contract_movement":
                version += f":contracts:{int(contract['total'] or 0)}:{int(contract['latest'] or 0)}"
            cur = conn.execute(
                "INSERT OR IGNORE INTO market_watch_matches "
                "(watch_id,uid,tid,thread_version,matched_at) VALUES (?,?,?,?,?)",
                (watch["id"], watch["uid"], tid, version, int(time.time())),
            )
            matched += int(cur.rowcount or 0)
    return matched


def pending_matches(limit: int = 100) -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT m.*,w.name watch_name,w.telegram_enabled,"
            "t.subject,t.seller_uid "
            "FROM market_watch_matches m JOIN market_watches w ON w.id=m.watch_id "
            "JOIN market_threads t ON t.tid=m.tid WHERE m.alerted_at IS NULL "
            "ORDER BY m.matched_at ASC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(row) for row in rows]


def mark_match_alerted(match_id: int) -> None:
    with _db() as conn:
        conn.execute(
            "UPDATE market_watch_matches SET alerted_at=? WHERE id=?",
            (int(time.time()), match_id),
        )


def mark_thread_matches_historical(tid: int) -> None:
    """Prevent seeded backlog matches from generating new-thread alerts."""
    with _db() as conn:
        conn.execute(
            "UPDATE market_watch_matches SET alerted_at=? "
            "WHERE tid=? AND alerted_at IS NULL",
            (int(time.time()), tid),
        )
