"""Deterministic local topic discovery for marketplace demand and supply."""

from __future__ import annotations

import json
import math
import re
import time
from collections import Counter
from datetime import datetime, timezone

from _db_compat import _db

STOP = frozenset({
    "wtb", "wts", "buy", "buying", "sell", "selling", "need", "needed",
    "looking", "want", "service", "services", "account", "accounts", "offer",
    "offering", "cheap", "urgent", "best", "new", "available", "request",
    "for", "the", "and", "with", "from", "that", "this", "your", "you",
    "a", "an", "to", "of", "in", "on", "is", "are", "my", "any",
    "people", "who", "high", "quality", "finding", "skilled", "market",
    "guide", "business", "idea", "strategy", "full", "one", "get",
    "start", "contract", "long", "term", "acquisition", "random",
})
MODIFIERS = frozenset({
    "max", "api", "aged", "residential", "bulk", "premium", "lifetime",
    "monthly", "yearly", "verified", "unverified", "mobile", "dedicated",
})


def normalize(text: str) -> list[str]:
    value = re.sub(r"\[/?(?:wtb|wts|buying|selling)[^\]]*\]", " ", text.lower())
    value = re.sub(r"https?://\S+|[^a-z0-9+.#-]+", " ", value)
    tokens = []
    for token in value.split():
        token = token.strip("-+.#")
        if len(token) < 2 or token in STOP or token.isdigit():
            continue
        if token.endswith("s") and len(token) > 4 and token not in ("vps", "rds"):
            token = token[:-1]
        tokens.append(token)
    return tokens[:40]


def vector(tokens: list[str]) -> Counter:
    result = Counter(tokens)
    for size in (2, 3):
        for index in range(len(tokens) - size + 1):
            phrase = " ".join(tokens[index:index + size])
            result[phrase] += size
    return result


def similarity(left: Counter, right: Counter) -> float:
    shared = set(left) & set(right)
    dot = sum(left[key] * right[key] for key in shared)
    lnorm = math.sqrt(sum(value * value for value in left.values()))
    rnorm = math.sqrt(sum(value * value for value in right.values()))
    return dot / (lnorm * rnorm) if lnorm and rnorm else 0.0


def _slug(tokens: list[str]) -> str:
    selected = tokens[:4] or ["unclassified"]
    return "-".join(selected)[:110]


def assign_unclassified(limit: int = 1000) -> dict:
    now = int(time.time())
    with _db() as conn:
        raw_topics = conn.execute(
            "SELECT * FROM market_topics WHERE status='active'"
        ).fetchall()
        topics = []
        for row in raw_topics:
            item = dict(row)
            item["vector"] = vector(normalize(item["canonical_terms"]))
            item["exclusions"] = set(json.loads(item.get("exclusions_json") or "[]"))
            topics.append(item)
        rows = conn.execute(
            "SELECT t.tid,t.subject,t.opening_post,t.market_type FROM market_threads t "
            "LEFT JOIN market_thread_topics mt ON mt.tid=t.tid "
            "WHERE mt.tid IS NULL AND t.closed=0 AND t.market_type IN ('wtb','wts') "
            "AND LOWER(TRIM(t.subject)) NOT LIKE 'delete%%' AND LOWER(TRIM(t.subject)) NOT LIKE 'closed%%' "
            "AND LOWER(TRIM(t.subject)) NOT IN ('sold','-----') "
            "AND LOWER(TRIM(COALESCE(t.opening_post,''))) NOT IN ('[deleted]','deleted','closed') "
            "ORDER BY t.created_at DESC LIMIT ?", (limit,)
        ).fetchall()
        assigned = created = probable = 0
        for raw in rows:
            row = dict(raw)
            title_tokens = normalize(row["subject"])
            body_tokens = normalize(str(row.get("opening_post") or "")[:1200])
            tokens = title_tokens + body_tokens
            if not tokens:
                continue
            modifiers = set(tokens) & MODIFIERS
            item_vector = vector(tokens)
            candidates = []
            for topic in topics:
                topic_tokens = set(normalize(topic["canonical_terms"]))
                topic_modifiers = topic_tokens & MODIFIERS
                if topic_modifiers and modifiers and topic_modifiers != modifiers:
                    continue
                if topic["exclusions"] & set(tokens):
                    continue
                candidates.append((similarity(item_vector, topic["vector"]), topic))
            score, topic = max(candidates, default=(0.0, None), key=lambda value: value[0])
            if topic is None or score < 0.32:
                source_tokens = title_tokens or body_tokens
                key_tokens = [token for token in source_tokens if token not in MODIFIERS][:2]
                key_tokens += [token for token in source_tokens if token in MODIFIERS][:1]
                slug = _slug(key_tokens)
                existing = conn.execute(
                    "SELECT * FROM market_topics WHERE slug=?", (slug,)
                ).fetchone()
                if existing:
                    topic = dict(existing)
                    score = 0.72
                else:
                    name = " ".join(key_tokens).title()[:180]
                    cur = conn.execute(
                        "INSERT INTO market_topics "
                        "(slug,name,canonical_terms,aliases_json,exclusions_json,created_at,updated_at) "
                        "VALUES (?,?,?,?,?,?,?)",
                        (slug, name, " ".join(key_tokens), "[]", "[]", now, now),
                    )
                    topic = {"id": int(cur.lastrowid), "canonical_terms": " ".join(key_tokens),
                             "vector": vector(key_tokens), "exclusions": set()}
                    topics.append(topic)
                    created += 1
                    score = 1.0
            band = "exact" if score >= 0.92 else "strong" if score >= 0.62 else "probable"
            probable += int(band == "probable")
            conn.execute(
                "INSERT OR REPLACE INTO market_thread_topics "
                "(tid,topic_id,confidence,confidence_band,method,assigned_at) "
                "VALUES (?,?,?,?,?,?)",
                (row["tid"], topic["id"], round(score, 4), band, "local_similarity", now),
            )
            assigned += 1
        if assigned:
            conn.execute("DELETE FROM market_cached_views WHERE cache_key LIKE 'topics:%%'")
    return {"assigned": assigned, "topics_created": created, "probable": probable}


def repair_assignments(limit: int = 5000) -> dict:
    """Repair low-confidence seed assignments and retire empty generic topics."""
    now = int(time.time())
    retired = promoted = 0
    with _db() as conn:
        dead = conn.execute(
            "SELECT COUNT(*) n FROM market_thread_topics mt JOIN market_threads t ON t.tid=mt.tid "
            "WHERE t.market_type NOT IN ('wtb','wts') OR t.closed=1 OR LOWER(TRIM(t.subject)) LIKE 'delete%%' "
            "OR LOWER(TRIM(t.subject)) LIKE 'closed%%' OR LOWER(TRIM(t.subject)) IN ('sold','-----') OR "
            "LOWER(TRIM(COALESCE(t.opening_post,''))) IN ('[deleted]','deleted','closed')"
        ).fetchone()
        conn.execute(
            "DELETE FROM market_thread_topics WHERE tid IN (SELECT tid FROM market_threads WHERE "
            "market_type NOT IN ('wtb','wts') OR closed=1 OR LOWER(TRIM(subject)) LIKE 'delete%%' OR LOWER(TRIM(subject)) LIKE 'closed%%' "
            "OR LOWER(TRIM(subject)) IN ('sold','-----') "
            "OR LOWER(TRIM(COALESCE(opening_post,''))) IN ('[deleted]','deleted','closed'))"
        )
        topic_rows = conn.execute(
            "SELECT id,canonical_terms FROM market_topics WHERE status='active'"
        ).fetchall()
        for raw in topic_rows:
            if normalize(raw["canonical_terms"]):
                continue
            conn.execute("DELETE FROM market_thread_topics WHERE topic_id=?", (raw["id"],))
            conn.execute("UPDATE market_topics SET status='excluded',updated_at=? WHERE id=?",
                         (now, raw["id"]))
            retired += 1
        rows = conn.execute(
            "SELECT mt.tid,mt.topic_id,t.subject,t.opening_post,p.canonical_terms "
            "FROM market_thread_topics mt JOIN market_threads t ON t.tid=mt.tid "
            "JOIN market_topics p ON p.id=mt.topic_id "
            "WHERE mt.confidence_band='probable' AND p.status='active' LIMIT ?", (limit,)
        ).fetchall()
        for raw in rows:
            canonical = set(normalize(raw["canonical_terms"]))
            content = set(normalize(f"{raw['subject']} {str(raw['opening_post'] or '')[:1200]}"))
            if canonical and canonical.issubset(content):
                conn.execute(
                    "UPDATE market_thread_topics SET confidence=?,confidence_band='strong',"
                    "method='local_repair',assigned_at=? WHERE tid=? AND topic_id=?",
                    (0.75, now, raw["tid"], raw["topic_id"]),
                )
                promoted += 1
        if retired or promoted or int(dead["n"] or 0):
            conn.execute("DELETE FROM market_cached_views WHERE cache_key LIKE 'topics:%%'")
    return {"retired_topics": retired, "promoted": promoted,
            "dead_assignments_removed": int(dead["n"] or 0)}


def snapshot_topics() -> int:
    now = int(time.time())
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with _db() as conn:
        topic_ids = conn.execute("SELECT id FROM market_topics WHERE status='active'").fetchall()
        for raw in topic_ids:
            topic_id = int(raw["id"])
            row = conn.execute(
                "SELECT SUM(t.market_type='wtb') buyer_threads,"
                "COUNT(DISTINCT CASE WHEN t.market_type='wtb' THEN t.seller_uid END) unique_buyers,"
                "SUM(t.market_type='wts') seller_threads,COUNT(DISTINCT c.cid) observed_contracts,"
                "SUM(c.status='6') completed_contracts FROM market_thread_topics mt "
                "JOIN market_threads t ON t.tid=mt.tid LEFT JOIN market_contracts c ON c.tid=t.tid "
                "WHERE mt.topic_id=? AND mt.confidence_band IN ('exact','strong') "
                "AND t.market_type IN ('wtb','wts')", (topic_id,),
            ).fetchone()
            conn.execute(
                "INSERT OR REPLACE INTO market_topic_snapshots "
                "(topic_id,snapshot_date,buyer_threads,unique_buyers,seller_threads,"
                "observed_contracts,completed_contracts,created_at) VALUES (?,?,?,?,?,?,?,?)",
                (topic_id, day, int(row["buyer_threads"] or 0), int(row["unique_buyers"] or 0),
                 int(row["seller_threads"] or 0), int(row["observed_contracts"] or 0),
                 int(row["completed_contracts"] or 0), now),
            )
        conn.execute("DELETE FROM market_cached_views WHERE cache_key LIKE 'topics:%%'")
    return len(topic_ids)
