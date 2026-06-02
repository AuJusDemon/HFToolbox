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
        for _col in [
            "ALTER TABLE merchant_goals ADD COLUMN weekly_completed_deal_goal INT NOT NULL DEFAULT 0",
            "ALTER TABLE merchant_goals ADD COLUMN max_stale_offer_days INT NOT NULL DEFAULT 30",
            "ALTER TABLE merchant_goals ADD COLUMN max_bumps_without_lead INT NOT NULL DEFAULT 10",
            "ALTER TABLE merchant_goals ADD COLUMN weekly_new_lead_goal INT NOT NULL DEFAULT 0",
            "ALTER TABLE merchant_goals ADD COLUMN templates_seeded TINYINT NOT NULL DEFAULT 0",
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
