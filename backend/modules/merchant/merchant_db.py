"""
modules/merchant/merchant_db.py — Merchant HQ local workflow state.

Only stores UX/workflow data that doesn't exist anywhere else:
  - merchant_leads: local lead stage/priority/note/follow-up for reply_queue items
  - merchant_customers: private notes/tags on counterparties
  - merchant_offers: local label/category/status/hidden flag for tracked threads
  - merchant_goals: per-user seller goals and SLA thresholds
  - contract_status_events: crawler-detected contract status transitions (with timestamp)
"""

import secrets
import time
import re
import json
from modules.marketplace_defs import MARKET_FORUMS
from _db_compat import _db


def init_merchant_db() -> None:
    with _db() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS merchant_leads (
                uid          VARCHAR(64)  NOT NULL,
                reply_id     INT          NOT NULL,
                tid          VARCHAR(64)  NOT NULL DEFAULT '',
                pid          VARCHAR(64)  NOT NULL DEFAULT '',
                stage        VARCHAR(32)  NOT NULL DEFAULT 'new',
                priority     VARCHAR(16)  NOT NULL DEFAULT 'normal',
                note         TEXT,
                followup_at  BIGINT,
                closed_at    BIGINT,
                created_at   BIGINT       NOT NULL DEFAULT 0,
                updated_at   BIGINT       NOT NULL DEFAULT 0,
                PRIMARY KEY (uid, reply_id),
                INDEX idx_ml_uid (uid)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS merchant_customers (
                uid                VARCHAR(64)  NOT NULL,
                counterparty_uid   VARCHAR(64)  NOT NULL,
                label              VARCHAR(255),
                note               TEXT,
                tags_json          TEXT,
                followup_at        BIGINT,
                created_at         BIGINT       NOT NULL DEFAULT 0,
                updated_at         BIGINT       NOT NULL DEFAULT 0,
                PRIMARY KEY (uid, counterparty_uid),
                INDEX idx_mc_uid (uid)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS merchant_offers (
                uid        VARCHAR(64)  NOT NULL,
                tid        VARCHAR(64)  NOT NULL,
                label      VARCHAR(255),
                category   VARCHAR(64),
                status     VARCHAR(32)  NOT NULL DEFAULT 'active',
                goal_json  TEXT,
                hidden     TINYINT      NOT NULL DEFAULT 0,
                created_at BIGINT       NOT NULL DEFAULT 0,
                updated_at BIGINT       NOT NULL DEFAULT 0,
                PRIMARY KEY (uid, tid),
                INDEX idx_mo_uid (uid)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS merchant_goals (
                uid                          VARCHAR(64) NOT NULL,
                reply_sla_hours              INT         NOT NULL DEFAULT 24,
                weekly_bump_budget           INT         NOT NULL DEFAULT 0,
                min_contract_value           INT         NOT NULL DEFAULT 0,
                weekly_completed_deal_goal   INT         NOT NULL DEFAULT 0,
                max_stale_offer_days         INT         NOT NULL DEFAULT 30,
                max_bumps_without_lead       INT         NOT NULL DEFAULT 10,
                weekly_new_lead_goal         INT         NOT NULL DEFAULT 0,
                settings_json                TEXT,
                PRIMARY KEY (uid)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        # One lead group per person per thread - replaces per-reply merchant_leads for pipeline
        conn.execute("""
            CREATE TABLE IF NOT EXISTS merchant_lead_groups (
                uid             VARCHAR(64) NOT NULL,
                from_uid        VARCHAR(64) NOT NULL,
                tid             VARCHAR(64) NOT NULL,
                stage           VARCHAR(32) NOT NULL DEFAULT 'new',
                priority        VARCHAR(16) NOT NULL DEFAULT 'normal',
                note            TEXT,
                followup_at     BIGINT,
                closed_at       BIGINT,
                first_reply_id  INT,
                created_at      BIGINT      NOT NULL DEFAULT 0,
                updated_at      BIGINT      NOT NULL DEFAULT 0,
                PRIMARY KEY (uid, from_uid, tid),
                INDEX idx_mlg_uid (uid)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS contract_status_events (
                uid          VARCHAR(64)  NOT NULL,
                cid          VARCHAR(64)  NOT NULL,
                from_status  VARCHAR(8)   NOT NULL DEFAULT '',
                to_status    VARCHAR(8)   NOT NULL,
                detected_at  BIGINT       NOT NULL,
                PRIMARY KEY (uid, cid, to_status),
                INDEX idx_cse_uid_ts (uid, detected_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS merchant_pm_templates (
                uid         VARCHAR(64)  NOT NULL,
                template_id VARCHAR(64)  NOT NULL,
                name        VARCHAR(120) NOT NULL,
                subject     TEXT,
                body        TEXT,
                created_at  BIGINT       NOT NULL DEFAULT 0,
                updated_at  BIGINT       NOT NULL DEFAULT 0,
                PRIMARY KEY (uid, template_id),
                INDEX idx_mpt_uid (uid)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS merchant_contract_workflow (
                uid               VARCHAR(64) NOT NULL,
                cid               VARCHAR(64) NOT NULL,
                completed_side_at BIGINT,
                last_followup_at  BIGINT,
                updated_at        BIGINT      NOT NULL DEFAULT 0,
                PRIMARY KEY (uid, cid),
                INDEX idx_mcw_uid (uid)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS merchant_bratings (
                uid           VARCHAR(64)  NOT NULL,
                crid          VARCHAR(64)  NOT NULL,
                contractid    VARCHAR(64)  NOT NULL,
                fromid        VARCHAR(64)  NOT NULL DEFAULT '',
                toid          VARCHAR(64)  NOT NULL DEFAULT '',
                amount        INT          NOT NULL DEFAULT 0,
                message       TEXT,
                dateline      BIGINT       NOT NULL DEFAULT 0,
                from_username VARCHAR(255),
                created_at    BIGINT       NOT NULL DEFAULT 0,
                PRIMARY KEY (uid, crid),
                INDEX idx_mb_uid (uid),
                INDEX idx_mb_cid (uid, contractid)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS merchant_products (
                id          VARCHAR(64) NOT NULL,
                uid         VARCHAR(64) NOT NULL,
                name        VARCHAR(255) NOT NULL,
                slug        VARCHAR(255) NOT NULL,
                status      VARCHAR(16) NOT NULL DEFAULT 'active',
                source      VARCHAR(24) NOT NULL DEFAULT 'suggested',
                confidence  DECIMAL(5,4) NOT NULL DEFAULT 0,
                created_at  BIGINT NOT NULL DEFAULT 0,
                updated_at  BIGINT NOT NULL DEFAULT 0,
                PRIMARY KEY (id),
                UNIQUE KEY uq_mp_uid_slug (uid,slug),
                INDEX idx_mp_uid_status (uid,status,name)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS merchant_product_threads (
                uid         VARCHAR(64) NOT NULL,
                product_id  VARCHAR(64) NOT NULL,
                tid         VARCHAR(64) NOT NULL,
                confidence  DECIMAL(5,4) NOT NULL DEFAULT 0,
                source      VARCHAR(24) NOT NULL DEFAULT 'suggested',
                excluded    TINYINT NOT NULL DEFAULT 0,
                created_at  BIGINT NOT NULL DEFAULT 0,
                updated_at  BIGINT NOT NULL DEFAULT 0,
                PRIMARY KEY (uid,tid),
                INDEX idx_mpt_product (uid,product_id,excluded)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS merchant_competitors (
                id          INT NOT NULL AUTO_INCREMENT,
                uid         VARCHAR(64) NOT NULL,
                product_id  VARCHAR(64),
                seller_uid  VARCHAR(64) NOT NULL DEFAULT '',
                tid         VARCHAR(64) NOT NULL DEFAULT '',
                created_at  BIGINT NOT NULL DEFAULT 0,
                PRIMARY KEY (id),
                UNIQUE KEY uq_mcomp_target (uid,product_id,seller_uid,tid),
                INDEX idx_mcomp_uid (uid,product_id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS merchant_followups (
                id                VARCHAR(64) NOT NULL,
                uid               VARCHAR(64) NOT NULL,
                cid               VARCHAR(64) NOT NULL,
                tid               VARCHAR(64) NOT NULL DEFAULT '',
                counterparty_uid  VARCHAR(64) NOT NULL DEFAULT '',
                template_id       VARCHAR(64),
                subject_snapshot  TEXT,
                body_snapshot     TEXT,
                note              TEXT,
                marked_sent_at    BIGINT NOT NULL,
                corrected_at      BIGINT,
                correction_note   TEXT,
                created_at        BIGINT NOT NULL,
                PRIMARY KEY (id),
                INDEX idx_mf_uid_cid (uid, cid, marked_sent_at),
                INDEX idx_mf_uid_due (uid, corrected_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS merchant_thread_snapshots (
                id                 INT NOT NULL AUTO_INCREMENT,
                uid                VARCHAR(64) NOT NULL,
                tid                VARCHAR(64) NOT NULL,
                observed_at        BIGINT NOT NULL,
                views              INT NOT NULL DEFAULT 0,
                replies            INT NOT NULL DEFAULT 0,
                posts              INT NOT NULL DEFAULT 1,
                contracts_total    INT NOT NULL DEFAULT 0,
                contracts_active   INT NOT NULL DEFAULT 0,
                contracts_complete INT NOT NULL DEFAULT 0,
                source             VARCHAR(32) NOT NULL DEFAULT 'local',
                PRIMARY KEY (id),
                INDEX idx_mts_uid_tid_at (uid, tid, observed_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS merchant_thread_updates (
                id                         VARCHAR(64) NOT NULL,
                uid                        VARCHAR(64) NOT NULL,
                tid                        VARCHAR(64) NOT NULL,
                message_snapshot           MEDIUMTEXT,
                status                     VARCHAR(24) NOT NULL DEFAULT 'queued',
                result_message             TEXT,
                hf_pid                     VARCHAR(64) NOT NULL DEFAULT '',
                posted_at                  BIGINT NOT NULL DEFAULT 0,
                baseline_views             INT NOT NULL DEFAULT 0,
                baseline_replies           INT NOT NULL DEFAULT 0,
                baseline_posts             INT NOT NULL DEFAULT 1,
                baseline_contracts         INT NOT NULL DEFAULT 0,
                observed_views             INT NOT NULL DEFAULT 0,
                observed_replies           INT NOT NULL DEFAULT 0,
                observed_posts             INT NOT NULL DEFAULT 1,
                observed_contracts         INT NOT NULL DEFAULT 0,
                observed_at                BIGINT NOT NULL DEFAULT 0,
                created_at                 BIGINT NOT NULL,
                updated_at                 BIGINT NOT NULL,
                PRIMARY KEY (id),
                INDEX idx_mtu_uid_tid_at (uid, tid, posted_at, created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
        """)
        for _col in [
            "ALTER TABLE merchant_goals ADD COLUMN weekly_completed_deal_goal INT NOT NULL DEFAULT 0",
            "ALTER TABLE merchant_goals ADD COLUMN max_stale_offer_days INT NOT NULL DEFAULT 30",
            "ALTER TABLE merchant_goals ADD COLUMN max_bumps_without_lead INT NOT NULL DEFAULT 10",
            "ALTER TABLE merchant_goals ADD COLUMN weekly_new_lead_goal INT NOT NULL DEFAULT 0",
            "ALTER TABLE merchant_goals ADD COLUMN templates_seeded TINYINT NOT NULL DEFAULT 0",
            "ALTER TABLE merchant_goals ADD COLUMN sent_ratings_fetched TINYINT NOT NULL DEFAULT 0",
            "ALTER TABLE merchant_goals ADD COLUMN received_ratings_fetched_at BIGINT NOT NULL DEFAULT 0",
        ]:
            try:
                conn.execute(_col)
            except Exception:
                pass
        # One-time migration: carry existing merchant_leads stage data into the new table.
        # INSERT OR IGNORE is idempotent - safe to run on every startup.
        try:
            conn.execute("""
                INSERT OR IGNORE INTO merchant_lead_groups
                    (uid, from_uid, tid, stage, priority, note, followup_at,
                     closed_at, first_reply_id, created_at, updated_at)
                SELECT ml.uid, rq.from_uid, ml.tid,
                       ml.stage, ml.priority, ml.note, ml.followup_at,
                       ml.closed_at, ml.reply_id, ml.created_at, ml.updated_at
                FROM merchant_leads ml
                JOIN reply_queue rq ON rq.id = ml.reply_id
                WHERE rq.from_uid IS NOT NULL AND rq.from_uid != ''
            """)
        except Exception:
            pass


def create_followup(uid: str, cid: str, tid: str = "", counterparty_uid: str = "",
                    template_id: str | None = None, subject: str = "", body: str = "",
                    note: str = "", marked_sent_at: int | None = None) -> dict:
    now = int(time.time())
    event_id = secrets.token_hex(16)
    sent_at = int(marked_sent_at or now)
    with _db() as conn:
        conn.execute(
            """INSERT INTO merchant_followups
               (id,uid,cid,tid,counterparty_uid,template_id,subject_snapshot,
                body_snapshot,note,marked_sent_at,created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (event_id, uid, str(cid), str(tid or ""), str(counterparty_uid or ""),
             template_id, subject, body, note, sent_at, now),
        )
        conn.execute(
            """INSERT OR IGNORE INTO merchant_contract_workflow
               (uid,cid,last_followup_at,updated_at) VALUES (?,?,?,?)""",
            (uid, str(cid), sent_at, now),
        )
        conn.execute(
            """UPDATE merchant_contract_workflow SET last_followup_at=?, updated_at=?
               WHERE uid=? AND cid=?""", (sent_at, now, uid, str(cid)),
        )
    return {"id": event_id, "marked_sent_at": sent_at}


def list_followups(uid: str, cid: str) -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            """SELECT * FROM merchant_followups WHERE uid=? AND cid=?
               ORDER BY marked_sent_at DESC, created_at DESC""", (uid, str(cid))
        ).fetchall()
    return [dict(row) for row in rows]


def correct_followup(uid: str, event_id: str, note: str = "") -> bool:
    now = int(time.time())
    with _db() as conn:
        cur = conn.execute(
            """UPDATE merchant_followups SET corrected_at=?, correction_note=?
               WHERE id=? AND uid=? AND corrected_at IS NULL""",
            (now, note, event_id, uid),
        )
        if not cur.rowcount:
            return False
        row = conn.execute(
            "SELECT cid FROM merchant_followups WHERE id=? AND uid=?", (event_id, uid)
        ).fetchone()
        latest = conn.execute(
            """SELECT MAX(marked_sent_at) AS ts FROM merchant_followups
               WHERE uid=? AND cid=? AND corrected_at IS NULL""", (uid, row["cid"])
        ).fetchone()
        conn.execute(
            """UPDATE merchant_contract_workflow SET last_followup_at=?, updated_at=?
               WHERE uid=? AND cid=?""", (latest["ts"], now, uid, row["cid"])
        )
    return True


# ── Leads ─────────────────────────────────────────────────────────────────────

VALID_STAGES = {'new', 'qualified', 'follow_up', 'contract_opened', 'won', 'lost', 'ignored'}
VALID_PRIORITIES = {'low', 'normal', 'high'}


def get_lead(uid: str, reply_id: int) -> dict | None:
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM merchant_leads WHERE uid=? AND reply_id=?",
            (uid, reply_id)
        ).fetchone()
        return dict(row) if row else None


def upsert_lead(uid: str, reply_id: int, tid: str, pid: str,
                stage: str = 'new', priority: str = 'normal',
                note: str | None = None, followup_at: int | None = None) -> None:
    now = int(time.time())
    stage    = stage    if stage    in VALID_STAGES     else 'new'
    priority = priority if priority in VALID_PRIORITIES else 'normal'
    closed_at = now if stage in ('won', 'lost', 'ignored') else None
    with _db() as conn:
        conn.execute(
            """INSERT INTO merchant_leads
               (uid, reply_id, tid, pid, stage, priority, note, followup_at, closed_at, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(uid, reply_id) DO UPDATE SET
                 stage=excluded.stage, priority=excluded.priority,
                 note=excluded.note, followup_at=excluded.followup_at,
                 closed_at=excluded.closed_at, updated_at=excluded.updated_at""",
            (uid, reply_id, tid, pid, stage, priority, note,
             followup_at, closed_at, now, now)
        )


def patch_lead(uid: str, reply_id: int, **fields) -> bool:
    allowed = {'stage', 'priority', 'note', 'followup_at'}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    now = int(time.time())
    if 'stage' in updates:
        s = updates['stage']
        updates['stage'] = s if s in VALID_STAGES else 'new'
        if updates['stage'] in ('won', 'lost', 'ignored'):
            updates['closed_at'] = now
    updates['updated_at'] = now
    set_clause = ', '.join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [uid, reply_id]
    with _db() as conn:
        cur = conn.execute(
            f"UPDATE merchant_leads SET {set_clause} WHERE uid=? AND reply_id=?",
            values
        )
        return cur.rowcount > 0


# ── Customers ─────────────────────────────────────────────────────────────────

def get_customer_meta(uid: str, counterparty_uid: str) -> dict | None:
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM merchant_customers WHERE uid=? AND counterparty_uid=?",
            (uid, counterparty_uid)
        ).fetchone()
        return dict(row) if row else None


def patch_customer(uid: str, counterparty_uid: str, **fields) -> bool:
    allowed = {'label', 'note', 'tags_json', 'followup_at'}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    now = int(time.time())
    updates['updated_at'] = now
    # Ensure row exists first
    with _db() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO merchant_customers
               (uid, counterparty_uid, created_at, updated_at)
               VALUES (?,?,?,?)""",
            (uid, counterparty_uid, now, now)
        )
        set_clause = ', '.join(f"{k}=?" for k in updates)
        values = list(updates.values()) + [uid, counterparty_uid]
        cur = conn.execute(
            f"UPDATE merchant_customers SET {set_clause} WHERE uid=? AND counterparty_uid=?",
            values
        )
        return cur.rowcount > 0


# ── Offers ─────────────────────────────────────────────────────────────────────

def get_offer_meta(uid: str, tid: str) -> dict | None:
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM merchant_offers WHERE uid=? AND tid=?",
            (uid, tid)
        ).fetchone()
        return dict(row) if row else None


def get_all_offer_meta(uid: str) -> dict[str, dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM merchant_offers WHERE uid=?", (uid,)
        ).fetchall()
        return {str(r['tid']): dict(r) for r in rows}


def patch_offer(uid: str, tid: str, **fields) -> bool:
    allowed = {'label', 'category', 'status', 'goal_json', 'hidden'}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return False
    now = int(time.time())
    updates['updated_at'] = now
    with _db() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO merchant_offers
               (uid, tid, created_at, updated_at)
               VALUES (?,?,?,?)""",
            (uid, tid, now, now)
        )
        set_clause = ', '.join(f"{k}=?" for k in updates)
        values = list(updates.values()) + [uid, tid]
        cur = conn.execute(
            f"UPDATE merchant_offers SET {set_clause} WHERE uid=? AND tid=?",
            values
        )
        return cur.rowcount > 0


# ── Goals ─────────────────────────────────────────────────────────────────────

def create_thread_snapshot(uid: str, tid: str, *, views: int = 0, replies: int = 0,
                           posts: int = 1, contracts_total: int = 0,
                           contracts_active: int = 0, contracts_complete: int = 0,
                           source: str = "local", observed_at: int | None = None) -> dict:
    now = int(observed_at or time.time())
    row = {
        "uid": uid,
        "tid": str(tid),
        "observed_at": now,
        "views": max(0, int(views or 0)),
        "replies": max(0, int(replies or 0)),
        "posts": max(1, int(posts or 1)),
        "contracts_total": max(0, int(contracts_total or 0)),
        "contracts_active": max(0, int(contracts_active or 0)),
        "contracts_complete": max(0, int(contracts_complete or 0)),
        "source": (source or "local")[:32],
    }
    with _db() as conn:
        conn.execute(
            """INSERT INTO merchant_thread_snapshots
               (uid,tid,observed_at,views,replies,posts,contracts_total,
                contracts_active,contracts_complete,source)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (row["uid"], row["tid"], row["observed_at"], row["views"],
             row["replies"], row["posts"], row["contracts_total"],
             row["contracts_active"], row["contracts_complete"], row["source"]),
        )
    return row


def latest_thread_snapshot(uid: str, tid: str) -> dict | None:
    with _db() as conn:
        row = conn.execute(
            """SELECT * FROM merchant_thread_snapshots
               WHERE uid=? AND tid=? ORDER BY observed_at DESC, id DESC LIMIT 1""",
            (uid, str(tid)),
        ).fetchone()
        return dict(row) if row else None


def create_thread_update(uid: str, tid: str, message: str, baseline: dict) -> dict:
    now = int(time.time())
    update_id = secrets.token_hex(16)
    row = {
        "id": update_id,
        "uid": uid,
        "tid": str(tid),
        "message_snapshot": message,
        "status": "queued",
        "result_message": "",
        "hf_pid": "",
        "posted_at": 0,
        "baseline_views": int(baseline.get("views") or 0),
        "baseline_replies": int(baseline.get("replies") or 0),
        "baseline_posts": int(baseline.get("posts") or 1),
        "baseline_contracts": int(baseline.get("contracts_total") or baseline.get("contracts") or 0),
        "observed_views": int(baseline.get("views") or 0),
        "observed_replies": int(baseline.get("replies") or 0),
        "observed_posts": int(baseline.get("posts") or 1),
        "observed_contracts": int(baseline.get("contracts_total") or baseline.get("contracts") or 0),
        "observed_at": now,
        "created_at": now,
        "updated_at": now,
    }
    with _db() as conn:
        conn.execute(
            """INSERT INTO merchant_thread_updates
               (id,uid,tid,message_snapshot,status,result_message,hf_pid,posted_at,
                baseline_views,baseline_replies,baseline_posts,baseline_contracts,
                observed_views,observed_replies,observed_posts,observed_contracts,
                observed_at,created_at,updated_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (row["id"], row["uid"], row["tid"], row["message_snapshot"],
             row["status"], row["result_message"], row["hf_pid"], row["posted_at"],
             row["baseline_views"], row["baseline_replies"], row["baseline_posts"],
             row["baseline_contracts"], row["observed_views"], row["observed_replies"],
             row["observed_posts"], row["observed_contracts"], row["observed_at"],
             row["created_at"], row["updated_at"]),
        )
    return row


def mark_thread_update_result(uid: str, update_id: str, *, status: str,
                              result_message: str = "", hf_pid: str = "",
                              posted_at: int | None = None,
                              observed: dict | None = None) -> dict | None:
    now = int(time.time())
    observed = observed or {}
    with _db() as conn:
        existing = conn.execute(
            "SELECT * FROM merchant_thread_updates WHERE uid=? AND id=?",
            (uid, update_id),
        ).fetchone()
        if not existing:
            return None
        conn.execute(
            """UPDATE merchant_thread_updates
               SET status=?, result_message=?, hf_pid=?, posted_at=?,
                   observed_views=?, observed_replies=?, observed_posts=?,
                   observed_contracts=?, observed_at=?, updated_at=?
               WHERE uid=? AND id=?""",
            (
                status[:24], result_message[:1000], str(hf_pid or ""),
                int(posted_at or existing["posted_at"] or now),
                int(observed.get("views", existing["observed_views"]) or 0),
                int(observed.get("replies", existing["observed_replies"]) or 0),
                int(observed.get("posts", existing["observed_posts"]) or 1),
                int(observed.get("contracts_total", existing["observed_contracts"]) or 0),
                int(observed.get("observed_at") or now),
                now, uid, update_id,
            ),
        )
        row = conn.execute(
            "SELECT * FROM merchant_thread_updates WHERE uid=? AND id=?",
            (uid, update_id),
        ).fetchone()
        return dict(row) if row else None


def list_thread_updates(uid: str, tid: str | None = None, limit: int = 40) -> list[dict]:
    limit = max(1, min(int(limit or 40), 100))
    with _db() as conn:
        if tid:
            rows = conn.execute(
                """SELECT u.*, t.title FROM merchant_thread_updates u
                   LEFT JOIN my_threads t ON t.uid=u.uid AND t.tid=u.tid
                   WHERE u.uid=? AND u.tid=?
                   ORDER BY COALESCE(NULLIF(u.posted_at,0), u.created_at) DESC
                   LIMIT ?""",
                (uid, str(tid), limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT u.*, t.title FROM merchant_thread_updates u
                   LEFT JOIN my_threads t ON t.uid=u.uid AND t.tid=u.tid
                   WHERE u.uid=?
                   ORDER BY COALESCE(NULLIF(u.posted_at,0), u.created_at) DESC
                   LIMIT ?""",
                (uid, limit),
            ).fetchall()
    return [dict(row) for row in rows]


def get_goals(uid: str) -> dict:
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM merchant_goals WHERE uid=?", (uid,)
        ).fetchone()
        if row:
            r = dict(row)
            r.setdefault('weekly_completed_deal_goal', 0)
            r.setdefault('max_stale_offer_days', 30)
            r.setdefault('max_bumps_without_lead', 10)
            r.setdefault('weekly_new_lead_goal', 0)
            return r
        return {
            'uid': uid,
            'reply_sla_hours': 24,
            'weekly_bump_budget': 0,
            'weekly_completed_deal_goal': 0,
            'max_stale_offer_days': 30,
            'max_bumps_without_lead': 10,
            'weekly_new_lead_goal': 0,
            'settings_json': None,
        }


# ── Lead groups (per person per thread) ───────────────────────────────────────

def get_all_lead_group_metas(uid: str) -> dict[tuple, dict]:
    """Returns {(from_uid, tid): row_dict} for all lead groups belonging to uid."""
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM merchant_lead_groups WHERE uid=?", (uid,)
        ).fetchall()
        return {(r['from_uid'], r['tid']): dict(r) for r in rows}


def patch_lead_group(uid: str, from_uid: str, tid: str, **fields) -> None:
    allowed = {'stage', 'priority', 'note', 'followup_at'}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return
    now = int(time.time())
    if 'stage' in updates:
        s = updates['stage']
        updates['stage'] = s if s in VALID_STAGES else 'new'
        if updates['stage'] in ('won', 'lost', 'ignored'):
            updates['closed_at'] = now
    updates['updated_at'] = now
    set_clause = ', '.join(f"{k}=?" for k in updates)
    values = list(updates.values()) + [uid, from_uid, tid]
    with _db() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO merchant_lead_groups
               (uid, from_uid, tid, created_at, updated_at)
               VALUES (?,?,?,?,?)""",
            (uid, from_uid, tid, now, now)
        )
        conn.execute(
            f"UPDATE merchant_lead_groups SET {set_clause} WHERE uid=? AND from_uid=? AND tid=?",
            values
        )


def upsert_goals(uid: str, reply_sla_hours: int = 24, weekly_bump_budget: int = 0,
                 weekly_completed_deal_goal: int = 0, max_stale_offer_days: int = 30,
                 max_bumps_without_lead: int = 10, weekly_new_lead_goal: int = 0,
                 settings_json: str | None = None) -> None:
    with _db() as conn:
        conn.execute(
            """INSERT INTO merchant_goals
               (uid, reply_sla_hours, weekly_bump_budget,
                weekly_completed_deal_goal, max_stale_offer_days,
                max_bumps_without_lead, weekly_new_lead_goal, settings_json)
               VALUES (?,?,?,?,?,?,?,?)
               ON CONFLICT(uid) DO UPDATE SET
                 reply_sla_hours=excluded.reply_sla_hours,
                 weekly_bump_budget=excluded.weekly_bump_budget,
                 weekly_completed_deal_goal=excluded.weekly_completed_deal_goal,
                 max_stale_offer_days=excluded.max_stale_offer_days,
                 max_bumps_without_lead=excluded.max_bumps_without_lead,
                 weekly_new_lead_goal=excluded.weekly_new_lead_goal,
                 settings_json=excluded.settings_json""",
            (uid, reply_sla_hours, weekly_bump_budget,
             weekly_completed_deal_goal, max_stale_offer_days,
             max_bumps_without_lead, weekly_new_lead_goal, settings_json)
        )


# ── Contract status events ─────────────────────────────────────────────────────

def record_contract_status_event(uid: str, cid: str,
                                  from_status: str, to_status: str) -> None:
    now = int(time.time())
    try:
        with _db() as conn:
            conn.execute(
                """INSERT OR IGNORE INTO contract_status_events
                   (uid, cid, from_status, to_status, detected_at)
                   VALUES (?,?,?,?,?)""",
                (uid, str(cid), str(from_status), str(to_status), now)
            )
    except Exception:
        pass  # Never break the crawl


# ── PM Templates ───────────────────────────────────────────────────────────────

def list_pm_templates(uid: str) -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM merchant_pm_templates WHERE uid=? ORDER BY name ASC",
            (uid,)
        ).fetchall()
        return [dict(r) for r in rows]


def create_pm_template(uid: str, name: str, subject: str, body: str) -> dict:
    template_id = secrets.token_hex(8)
    now = int(time.time())
    with _db() as conn:
        conn.execute(
            """INSERT INTO merchant_pm_templates
               (uid, template_id, name, subject, body, created_at, updated_at)
               VALUES (?,?,?,?,?,?,?)""",
            (uid, template_id, name, subject, body, now, now)
        )
    return {
        'uid': uid,
        'template_id': template_id,
        'name': name,
        'subject': subject,
        'body': body,
        'created_at': now,
        'updated_at': now,
    }


def update_pm_template(uid: str, template_id: str,
                       name: str | None = None,
                       subject: str | None = None,
                       body: str | None = None) -> bool:
    allowed = {'name', 'subject', 'body'}
    updates = {}
    if name is not None:
        updates['name'] = name
    if subject is not None:
        updates['subject'] = subject
    if body is not None:
        updates['body'] = body
    if not updates:
        return False
    updates['updated_at'] = int(time.time())
    set_clause = ', '.join(f"{k}=?" for k in updates if k in allowed | {'updated_at'})
    values = list(updates.values()) + [uid, template_id]
    with _db() as conn:
        cur = conn.execute(
            f"UPDATE merchant_pm_templates SET {set_clause} WHERE uid=? AND template_id=?",
            values
        )
        return cur.rowcount > 0


def delete_pm_template(uid: str, template_id: str) -> bool:
    with _db() as conn:
        cur = conn.execute(
            "DELETE FROM merchant_pm_templates WHERE uid=? AND template_id=?",
            (uid, template_id)
        )
        return cur.rowcount > 0


# ── Contract workflow (seller-side state) ─────────────────────────────────────

def mark_contract_completed_side(uid: str, cid: str) -> None:
    now = int(time.time())
    with _db() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO merchant_contract_workflow
               (uid, cid, updated_at) VALUES (?,?,?)""",
            (uid, str(cid), now)
        )
        conn.execute(
            """UPDATE merchant_contract_workflow
               SET completed_side_at=?, updated_at=? WHERE uid=? AND cid=?""",
            (now, now, uid, str(cid))
        )


def get_all_contract_workflows(uid: str) -> dict:
    with _db() as conn:
        rows = conn.execute(
            """SELECT cid, completed_side_at, last_followup_at
               FROM merchant_contract_workflow WHERE uid=?""",
            (uid,)
        ).fetchall()
        return {str(r['cid']): dict(r) for r in rows}


# ── Default PM template seeding ───────────────────────────────────────────────

_DEFAULT_PM_TEMPLATES = [
    {
        'name': 'Approval Reminder',
        'subject': 'Contract #{cid} - Approval Reminder',
        'body': 'Hey {username}, contract #{cid} is waiting for approval. Please approve it if you want to move forward.',
    },
    {
        'name': 'Active Contract Follow-Up',
        'subject': 'Contract #{cid} - Follow Up',
        'body': 'Hey {username}, contract #{cid} is open for {product}. If you still want to continue, please let me know.',
    },
    {
        'name': 'Completed My Side',
        'subject': 'Contract #{cid} - Completed',
        'body': 'Hey {username}, I completed my side for contract #{cid}. Please check it when you can.',
    },
]


def seed_default_pm_templates(uid: str) -> bool:
    """Seed 3 default templates once per user. Returns True if templates were created."""
    now = int(time.time())
    with _db() as conn:
        goals_row = conn.execute(
            "SELECT templates_seeded FROM merchant_goals WHERE uid=?", (uid,)
        ).fetchone()
        if goals_row and int(goals_row.get('templates_seeded') or 0):
            return False
        existing = conn.execute(
            "SELECT COUNT(*) FROM merchant_pm_templates WHERE uid=?", (uid,)
        ).fetchone()[0]
        # Mark seeded regardless - either they already have templates or we create defaults
        conn.execute(
            """INSERT OR IGNORE INTO merchant_goals
               (uid, reply_sla_hours, weekly_bump_budget, weekly_completed_deal_goal,
                max_stale_offer_days, max_bumps_without_lead, weekly_new_lead_goal)
               VALUES (?,24,0,0,30,10,0)""",
            (uid,)
        )
        conn.execute(
            "UPDATE merchant_goals SET templates_seeded=1 WHERE uid=?", (uid,)
        )
        if existing:
            return False
        for t in _DEFAULT_PM_TEMPLATES:
            conn.execute(
                """INSERT INTO merchant_pm_templates
                   (uid, template_id, name, subject, body, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?)""",
                (uid, secrets.token_hex(8), t['name'], t['subject'], t['body'], now, now)
            )
        return True


# ── B-rating tracking ─────────────────────────────────────────────────────────

def upsert_bratings(uid: str, ratings: list) -> None:
    """Store received b-ratings fetched from the HF bratings endpoint."""
    now = int(time.time())
    with _db() as conn:
        for r in ratings:
            crid = str(r.get('crid', '') or '')
            if not crid:
                continue
            conn.execute(
                """INSERT OR IGNORE INTO merchant_bratings
                   (uid, crid, contractid, fromid, toid, amount,
                    message, dateline, from_username, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?,?)""",
                (
                    uid,
                    crid,
                    str(r.get('contractid', '') or ''),
                    str(r.get('from_uid',    '') or ''),
                    str(r.get('toid',        '') or ''),
                    int(r.get('amount', 0)   or 0),
                    str(r.get('message',     '') or ''),
                    int(r.get('dateline', 0) or 0),
                    str(r.get('from_username', '') or ''),
                    now,
                )
            )


def get_bratings_by_cid(uid: str) -> dict:
    """Return {contractid: rating_row} for ratings received by uid (fromid != uid)."""
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM merchant_bratings WHERE uid=? AND fromid!=? ORDER BY dateline DESC",
            (uid, uid)
        ).fetchall()
    result: dict = {}
    for r in rows:
        cid = str(r['contractid'])
        if cid not in result:
            result[cid] = dict(r)
    return result


def get_sent_brating_cids(uid: str) -> set:
    """Return set of contractids where the current user has left a b-rating."""
    with _db() as conn:
        rows = conn.execute(
            "SELECT contractid FROM merchant_bratings WHERE uid=? AND fromid=?",
            (uid, uid)
        ).fetchall()
        return {str(r['contractid']) for r in rows}


def has_sent_ratings_data(uid: str) -> bool:
    """Return True if sent ratings have been fetched at least once for this user."""
    with _db() as conn:
        row = conn.execute(
            "SELECT sent_ratings_fetched FROM merchant_goals WHERE uid=?", (uid,)
        ).fetchone()
        if row and int(row.get('sent_ratings_fetched') or 0):
            return True
        # Also treat as known if sent ratings actually exist in the table
        row2 = conn.execute(
            "SELECT 1 FROM merchant_bratings WHERE uid=? AND fromid=? LIMIT 1",
            (uid, uid)
        ).fetchone()
        return row2 is not None


def mark_sent_ratings_fetched(uid: str) -> None:
    with _db() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO merchant_goals
               (uid, reply_sla_hours, weekly_bump_budget, weekly_completed_deal_goal,
                max_stale_offer_days, max_bumps_without_lead, weekly_new_lead_goal)
               VALUES (?,24,0,0,30,10,0)""",
            (uid,)
        )
        conn.execute(
            "UPDATE merchant_goals SET sent_ratings_fetched=1 WHERE uid=?", (uid,)
        )


def mark_received_ratings_fetched(uid: str) -> None:
    """Record that received (_to) ratings were successfully fetched from HF."""
    now = int(time.time())
    with _db() as conn:
        conn.execute(
            """INSERT OR IGNORE INTO merchant_goals
               (uid, reply_sla_hours, weekly_bump_budget, weekly_completed_deal_goal,
                max_stale_offer_days, max_bumps_without_lead, weekly_new_lead_goal)
               VALUES (?,24,0,0,30,10,0)""",
            (uid,)
        )
        conn.execute(
            "UPDATE merchant_goals SET received_ratings_fetched_at=? WHERE uid=?",
            (now, uid)
        )


def get_received_ratings_freshness(uid: str) -> int:
    """Return Unix timestamp of last successful _to fetch, or 0 if never fetched."""
    with _db() as conn:
        row = conn.execute(
            "SELECT received_ratings_fetched_at FROM merchant_goals WHERE uid=?", (uid,)
        ).fetchone()
        return int(row['received_ratings_fetched_at'] or 0) if row else 0


def has_local_received_ratings(uid: str) -> bool:
    """Return True if any received (counterparty-to-me) ratings exist in local DB."""
    with _db() as conn:
        row = conn.execute(
            "SELECT 1 FROM merchant_bratings WHERE uid=? AND fromid!=? LIMIT 1",
            (uid, uid)
        ).fetchone()
        return row is not None


def clear_received_ratings_freshness(uid: str) -> None:
    """Reset the received-ratings freshness flag so next sync is treated as unknown."""
    with _db() as conn:
        conn.execute(
            "UPDATE merchant_goals SET received_ratings_fetched_at=0 WHERE uid=?", (uid,)
        )


def get_notification_preferences(uid: str) -> dict:
    with _db() as conn:
        row = conn.execute("SELECT settings_json FROM merchant_goals WHERE uid=?", (uid,)).fetchone()
    try:
        stored = json.loads((row["settings_json"] if row else "") or "{}")
    except Exception:
        stored = {}
    return {
        "telegram_replies": bool(stored.get("telegram_replies", False)),
        "telegram_followups": bool(stored.get("telegram_followups", False)),
        "telegram_ratings": bool(stored.get("telegram_ratings", False)),
    }


def set_notification_preferences(uid: str, telegram_followups: bool,
                                 telegram_ratings: bool, telegram_replies: bool = False) -> dict:
    now_data = {"telegram_replies": bool(telegram_replies),
                "telegram_followups": bool(telegram_followups),
                "telegram_ratings": bool(telegram_ratings)}
    with _db() as conn:
        conn.execute("INSERT OR IGNORE INTO merchant_goals (uid) VALUES (?)", (uid,))
        conn.execute("UPDATE merchant_goals SET settings_json=? WHERE uid=?",
                     (json.dumps(now_data), uid))
    return now_data


def due_followup_reminders(uid: str, now: int | None = None) -> list[dict]:
    cutoff = int(now or time.time())
    with _db() as conn:
        rows = conn.execute(
            """SELECT g.from_uid,g.tid,g.followup_at,mt.title
               FROM merchant_lead_groups g LEFT JOIN my_threads mt
                 ON mt.uid=g.uid AND mt.tid=g.tid
               WHERE g.uid=? AND g.followup_at IS NOT NULL AND g.followup_at<=?
                 AND g.stage NOT IN ('won','lost','ignored')
               ORDER BY g.followup_at ASC LIMIT 50""", (uid, cutoff),
        ).fetchall()
        return [dict(row) for row in rows]


_PRODUCT_NOISE = {
    "official", "shop", "store", "service", "services", "selling", "sale", "sales",
    "buy", "best", "cheap", "cheapest", "fast", "new", "premium", "instant",
    "unlimited", "trusted", "verified", "available", "thread", "the", "and", "for",
    "with", "your", "you", "from", "only", "now",
}


def _product_name(value: str) -> tuple[str, str, float]:
    words = re.findall(r"[a-z0-9]+", (value or "").lower())
    kept = [word for word in words if len(word) > 1 and word not in _PRODUCT_NOISE][:6]
    if not kept:
        kept = words[:4] or ["unclassified"]
    slug = "-".join(kept)[:255]
    name = " ".join(word.upper() if word in {"api", "rdp", "vpn", "otp", "seo"} else word.title()
                    for word in kept)
    confidence = 0.92 if len(kept) >= 2 else 0.65
    return name[:255], slug, confidence


def sync_seller_products(uid: str) -> int:
    """Create deterministic product groups for owned marketplace threads not yet classified."""
    now = int(time.time())
    cutoff = now - 30 * 86400
    created = 0
    with _db() as conn:
        fids = [str(fid) for fid in MARKET_FORUMS]
        placeholders = ",".join("?" for _ in fids)
        rows = conn.execute(
            f"""SELECT mt.tid,mt.title,COALESCE(NULLIF(mo.label,''),(
                    SELECT topic.name FROM market_thread_topics tt
                    JOIN market_topics topic ON topic.id=tt.topic_id
                    WHERE tt.tid=mt.tid
                      AND tt.confidence_band IN ('exact','strong') AND topic.status='active'
                    ORDER BY tt.confidence DESC LIMIT 1
                 ),'') label
               FROM my_threads mt
               LEFT JOIN merchant_offers mo ON mo.uid=mt.uid AND mo.tid=mt.tid
               LEFT JOIN merchant_product_threads a ON a.uid=mt.uid AND a.tid=mt.tid
               WHERE mt.uid=? AND a.tid IS NULL AND
                 (mt.fid IN ({placeholders}) OR EXISTS (
                    SELECT 1 FROM contracts_history c WHERE c.uid=mt.uid AND c.tid=mt.tid
                 )) AND (
                    mt.lastpost>=? OR EXISTS (
                      SELECT 1 FROM contracts_history c
                      WHERE c.uid=mt.uid AND c.tid=mt.tid
                        AND (c.status_n IN ('1','2','3','4','5') OR c.dateline>=?)
                    )
                 )""", (uid, *fids, cutoff, cutoff),
        ).fetchall()
        for row in rows:
            name, slug, confidence = _product_name(str(row["label"] or row["title"] or ""))
            existing = conn.execute(
                "SELECT id FROM merchant_products WHERE uid=? AND slug=?", (uid, slug)
            ).fetchone()
            product_id = str(existing["id"]) if existing else secrets.token_hex(12)
            if not existing:
                conn.execute(
                    """INSERT INTO merchant_products
                       (id,uid,name,slug,source,confidence,created_at,updated_at)
                       VALUES (?,?,?,?,'suggested',?,?,?)""",
                    (product_id, uid, name, slug, confidence, now, now),
                )
                created += 1
            conn.execute(
                """INSERT INTO merchant_product_threads
                   (uid,product_id,tid,confidence,source,created_at,updated_at)
                   VALUES (?,?,?,?,'suggested',?,?)""",
                (uid, product_id, str(row["tid"]), confidence, now, now),
            )
    return created


def list_seller_products(uid: str) -> list[dict]:
    cutoff = int(time.time()) - 30 * 86400
    with _db() as conn:
        rows = conn.execute(
            """SELECT p.*,
                      COUNT(DISTINCT CASE WHEN a.excluded=0 THEN a.tid END) thread_count,
                      COUNT(DISTINCT c.cid) contract_count,
                      SUM(CASE WHEN c.status_n='6' THEN 1 ELSE 0 END) completed_contracts
               FROM merchant_products p
               LEFT JOIN merchant_product_threads a ON a.uid=p.uid AND a.product_id=p.id
               LEFT JOIN contracts_history c ON c.uid=p.uid AND c.tid=a.tid
               LEFT JOIN my_threads mt ON mt.uid=p.uid AND mt.tid=a.tid
               WHERE p.uid=? AND p.status='active'
                 AND (
                   p.source='manual'
                   OR mt.lastpost>=?
                   OR EXISTS (
                     SELECT 1 FROM contracts_history cx
                     WHERE cx.uid=p.uid AND cx.tid=a.tid
                       AND (cx.status_n IN ('1','2','3','4','5') OR cx.dateline>=?)
                   )
                 )
               GROUP BY p.id ORDER BY p.name""", (uid, cutoff, cutoff),
        ).fetchall()
        products = [dict(row) for row in rows]
        for product in products:
            threads = conn.execute(
                """SELECT a.tid,a.confidence,a.source,a.excluded,mt.title,mt.fid
                   FROM merchant_product_threads a JOIN my_threads mt
                     ON mt.uid=a.uid AND mt.tid=a.tid
                   WHERE a.uid=? AND a.product_id=? ORDER BY mt.lastpost DESC""",
                (uid, product["id"]),
            ).fetchall()
            product["threads"] = [dict(row) for row in threads]
        return products


def rename_seller_product(uid: str, product_id: str, name: str) -> bool:
    clean = " ".join(str(name or "").split())[:255]
    if not clean:
        return False
    _, slug, _ = _product_name(clean)
    with _db() as conn:
        cur = conn.execute(
            "UPDATE merchant_products SET name=?,slug=?,source='manual',confidence=1,updated_at=? "
            "WHERE uid=? AND id=?", (clean, slug, int(time.time()), uid, product_id),
        )
        return cur.rowcount > 0


def delete_seller_product(uid: str, product_id: str) -> bool:
    now = int(time.time())
    with _db() as conn:
        product = conn.execute(
            "SELECT 1 FROM merchant_products WHERE uid=? AND id=? AND status='active'",
            (uid, product_id),
        ).fetchone()
        if not product:
            return False
        conn.execute(
            "UPDATE merchant_product_threads SET excluded=1,updated_at=? WHERE uid=? AND product_id=?",
            (now, uid, product_id),
        )
        cur = conn.execute(
            "UPDATE merchant_products SET status='deleted',updated_at=? WHERE uid=? AND id=?",
            (now, uid, product_id),
        )
        return cur.rowcount > 0


def create_seller_product(uid: str, name: str) -> dict | None:
    clean = " ".join(str(name or "").split())[:255]
    if not clean:
        return None
    _, slug, _ = _product_name(clean)
    product_id, now = secrets.token_hex(12), int(time.time())
    with _db() as conn:
        existing = conn.execute(
            "SELECT id,name,status FROM merchant_products WHERE uid=? AND slug=?", (uid, slug)
        ).fetchone()
        if existing:
            conn.execute(
                """UPDATE merchant_products
                   SET name=?, status='active', source='manual', confidence=1, updated_at=?
                   WHERE uid=? AND id=?""",
                (clean, now, uid, str(existing["id"])),
            )
            return {"id": str(existing["id"]), "name": clean}
        conn.execute(
            """INSERT INTO merchant_products
               (id,uid,name,slug,status,source,confidence,created_at,updated_at)
               VALUES (?,?,?,?,'active','manual',1,?,?)""",
            (product_id, uid, clean, slug, now, now),
        )
    return {"id": product_id, "name": clean}


def assign_product_thread(uid: str, product_id: str, tid: str, excluded: bool = False) -> bool:
    now = int(time.time())
    with _db() as conn:
        product = conn.execute(
            "SELECT 1 FROM merchant_products WHERE uid=? AND id=?", (uid, product_id)
        ).fetchone()
        owned = conn.execute("SELECT 1 FROM my_threads WHERE uid=? AND tid=?", (uid, tid)).fetchone()
        if not product or not owned:
            return False
        old = conn.execute(
            "SELECT product_id FROM merchant_product_threads WHERE uid=? AND tid=?", (uid, tid)
        ).fetchone()
        conn.execute(
            """INSERT INTO merchant_product_threads
               (uid,product_id,tid,confidence,source,excluded,created_at,updated_at)
               VALUES (?,?,?,1,'manual',?,?,?)
               ON CONFLICT(uid,tid) DO UPDATE SET product_id=excluded.product_id,
                 confidence=1,source='manual',excluded=excluded.excluded,updated_at=excluded.updated_at""",
            (uid, product_id, tid, int(excluded), now, now),
        )
        if old and str(old["product_id"]) != product_id:
            conn.execute(
                """UPDATE merchant_products SET status='merged',updated_at=?
                   WHERE uid=? AND id=? AND NOT EXISTS (
                     SELECT 1 FROM merchant_product_threads a
                     WHERE a.uid=? AND a.product_id=merchant_products.id AND a.excluded=0
                   )""", (now, uid, str(old["product_id"]), uid),
            )
        return True


def seller_product_opportunities(uid: str, days: int = 30, limit: int = 100) -> list[dict]:
    """Match owned products to buyer requests through strong shared market topics."""
    cutoff = int(time.time()) - max(1, min(days, 3650)) * 86400
    with _db() as conn:
        rows = conn.execute(
            """SELECT p.id product_id,p.name product_name,b.tid,b.subject,b.seller_uid buyer_uid,
                      b.created_at,b.views,b.replies,topic.id topic_id,topic.name topic_name,
                      COUNT(DISTINCT supply.tid) matching_supply,
                      COUNT(DISTINCT buyers.seller_uid) unique_buyers,
                      COUNT(DISTINCT CASE WHEN contracts.status='6' THEN contracts.cid END) completed_contracts
               FROM merchant_products p
               JOIN merchant_product_threads own ON own.uid=p.uid AND own.product_id=p.id AND own.excluded=0
               JOIN market_thread_topics omt ON omt.tid=own.tid AND omt.confidence_band IN ('exact','strong')
               JOIN market_topics topic ON topic.id=omt.topic_id AND topic.status='active'
               JOIN market_thread_topics bmt ON bmt.topic_id=topic.id AND bmt.confidence_band IN ('exact','strong')
               JOIN market_threads b ON b.tid=bmt.tid AND b.market_type='wtb' AND b.created_at>=?
               LEFT JOIN market_thread_topics smt ON smt.topic_id=topic.id AND smt.confidence_band IN ('exact','strong')
               LEFT JOIN market_threads supply ON supply.tid=smt.tid AND supply.market_type='wts'
               LEFT JOIN market_threads buyers ON buyers.tid=bmt.tid AND buyers.market_type='wtb'
               LEFT JOIN market_contracts contracts ON contracts.tid=supply.tid
               WHERE p.uid=? AND p.status='active' AND b.closed=0
                 AND LOWER(TRIM(b.subject)) NOT LIKE 'delete%%'
                 AND LOWER(TRIM(b.subject)) NOT LIKE 'closed%%'
                 AND LOWER(TRIM(COALESCE(b.opening_post,''))) NOT IN ('[deleted]','deleted','closed')
               GROUP BY p.id,b.tid,topic.id
               ORDER BY b.created_at DESC LIMIT ?""",
            (cutoff, uid, max(1, min(int(limit), 250))),
        ).fetchall()
        return [dict(row) for row in rows]
