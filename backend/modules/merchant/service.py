"""
modules/merchant/service.py — Joins existing DB tables into seller objects.

No HF API calls. All data comes from tables already populated by:
  - bytes/contracts crawler (contracts_history, bytes_history)
  - posting module (my_threads, reply_queue, scheduled_threads)
  - autobump module (bump_jobs, bump_log)
  - uid/tid caches (uid_usernames, tid_titles)
  - merchant local tables (merchant_leads, merchant_customers, merchant_offers)
"""

import json as _json
import time
from _db_compat import _db
from modules.merchant.metrics import (
    offer_stats_from_contracts,
    reply_stats_from_queue,
    bump_stats_from_log,
    bump_waste_score,
    offer_health,
    customer_stats,
    pipeline_summary,
    overview_action_queue,
    contract_bucket,
    classify_contract_stage,
    counterparty_uid,
    STATUS_ACTIVE,
    STATUS_COMPLETE,
    STATUS_AWAITING,
    STATUS_LOST,
    STATUS_FULFILLMENT,
    _AGE_EXPIRED_S,
    _PENDING,
)
from modules.merchant.merchant_db import (
    get_all_offer_meta,
    get_customer_meta,
    get_goals,
    get_all_lead_group_metas,
    get_all_contract_workflows,
    get_bratings_by_cid,
    get_sent_brating_cids,
    list_thread_updates,
    mark_thread_update_result,
)
from modules.marketplace_defs import MARKET_FORUMS


# ── Marketplace FID whitelist ──────────────────────────────────────────────────
# Only threads in HF Marketplace sections are treated as seller offers.
MARKETPLACE_FIDS: frozenset[str] = frozenset(str(fid) for fid in MARKET_FORUMS)


# ── Low-level fetchers ─────────────────────────────────────────────────────────

def _get_contracts(uid: str) -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM contracts_history WHERE uid=? ORDER BY dateline DESC",
            (uid,)
        ).fetchall()
        return [dict(r) for r in rows]


def _get_my_threads(uid: str) -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM my_threads WHERE uid=? ORDER BY lastpost DESC",
            (uid,)
        ).fetchall()
        return [dict(r) for r in rows]


def _get_tid_titles(uid: str, tids: set[str] | None = None) -> dict[str, str]:
    """Resolve contract thread titles from owned, shared-title, and market caches."""
    titles: dict[str, str] = {}
    wanted = sorted({str(tid) for tid in (tids or set()) if str(tid)})
    with _db() as conn:
        queries = [("my_threads", "uid=?", (uid,))]
        if wanted:
            placeholders = ",".join("?" for _ in wanted)
            queries.extend([
                ("tid_titles", f"tid IN ({placeholders})", tuple(wanted)),
                ("market_threads", f"tid IN ({placeholders})", tuple(wanted)),
            ])
        for table, where, params in queries:
            try:
                rows = conn.execute(
                    f"SELECT tid,title FROM {table} WHERE {where}", params
                ).fetchall()
                for row in rows:
                    tid = str(row.get("tid") or "")
                    title = str(row.get("title") or "").strip()
                    if tid and title:
                        titles.setdefault(tid, title)
            except Exception:
                continue
    return titles


def _contract_product(c: dict, tid_titles: dict[str, str]) -> str:
    """Use explicit contract products first, then the linked thread title."""
    trivial = {"", "other", "n/a", "none", "null"}
    for value in (c.get("iproduct"), c.get("oproduct")):
        product = str(value or "").strip()
        if product.lower() not in trivial:
            return product
    return tid_titles.get(str(c.get("tid") or ""), "")


def _get_reply_queue(uid: str) -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM reply_queue WHERE uid=? ORDER BY dateline DESC",
            (uid,)
        ).fetchall()
        return [dict(r) for r in rows]


def _get_bump_jobs(uid: str) -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM bump_jobs WHERE uid=?", (uid,)
        ).fetchall()
        return [dict(r) for r in rows]


def _get_bump_log(uid: str, limit: int = 500) -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM bump_log WHERE uid=? ORDER BY ts DESC LIMIT ?",
            (uid, limit)
        ).fetchall()
        return [dict(r) for r in rows]


def _get_scheduled_threads(uid: str) -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM scheduled_threads WHERE uid=? ORDER BY fire_at DESC",
            (uid,)
        ).fetchall()
        return [dict(r) for r in rows]


def _get_marketplace_tids(uid: str) -> frozenset[str]:
    """
    Return TIDs of confirmed marketplace threads for this uid.
    A thread is "marketplace" if any of these are true:
      - Its FID in my_threads matches a known marketplace section
      - It has a bump_job (user is actively promoting it to sell)
      - It has at least one contract (contracts only happen in marketplace)
    """
    tids: set[str] = set()
    fids_list = list(MARKETPLACE_FIDS)
    with _db() as conn:
        if fids_list:
            ph = ','.join('?' * len(fids_list))
            for r in conn.execute(
                f"SELECT tid FROM my_threads WHERE uid=? AND fid IN ({ph})",
                [uid] + fids_list,
            ).fetchall():
                tids.add(str(r['tid']))

        for r in conn.execute(
            "SELECT DISTINCT tid FROM bump_jobs WHERE uid=?", (uid,)
        ).fetchall():
            tids.add(str(r['tid']))

        for r in conn.execute(
            "SELECT DISTINCT tid FROM contracts_history WHERE uid=?", (uid,)
        ).fetchall():
            tids.add(str(r['tid']))

    tids.discard('')
    return frozenset(tids)


def _get_username(uid_str: str) -> str | None:
    with _db() as conn:
        row = conn.execute(
            "SELECT username FROM uid_usernames WHERE uid=?", (uid_str,)
        ).fetchone()
        return row['username'] if row else None


def _get_usernames(uids: list[str]) -> dict[str, str]:
    if not uids:
        return {}
    placeholders = ','.join('?' * len(uids))
    with _db() as conn:
        rows = conn.execute(
            f"SELECT uid, username FROM uid_usernames WHERE uid IN ({placeholders})",
            uids
        ).fetchall()
        return {str(r['uid']): r['username'] for r in rows}


def _get_lead_metas(uid: str) -> dict[int, dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM merchant_leads WHERE uid=?", (uid,)
        ).fetchall()
        return {r['reply_id']: dict(r) for r in rows}


def _get_completion_events(uid: str, since: int) -> list[dict]:
    try:
        with _db() as conn:
            rows = conn.execute(
                "SELECT cid, detected_at FROM contract_status_events "
                "WHERE uid=? AND to_status='6' AND detected_at >= ?",
                (uid, since)
            ).fetchall()
            return [dict(r) for r in rows]
    except Exception:
        return []


def _get_crawl_freshness(uid: str) -> dict:
    """Return last-crawl timestamps from existing crawl state tables."""
    result = {
        'contracts_last_crawl': None,
        'bytes_last_crawl': None,
        'last_reply_at': None,
        'last_bump_at': None,
    }
    with _db() as conn:
        try:
            row = conn.execute(
                "SELECT last_crawl FROM contracts_crawl_state WHERE uid=?", (uid,)
            ).fetchone()
            if row:
                result['contracts_last_crawl'] = row['last_crawl']
        except Exception:
            pass
        try:
            row = conn.execute(
                "SELECT last_crawl FROM bytes_crawl_state WHERE uid=?", (uid,)
            ).fetchone()
            if row:
                result['bytes_last_crawl'] = row['last_crawl']
        except Exception:
            pass
        try:
            row = conn.execute(
                "SELECT MAX(dateline) AS mx FROM reply_queue WHERE uid=?", (uid,)
            ).fetchone()
            if row:
                result['last_reply_at'] = row['mx']
        except Exception:
            pass
        try:
            row = conn.execute(
                "SELECT MAX(ts) AS mx FROM bump_log WHERE uid=?", (uid,)
            ).fetchone()
            if row:
                result['last_bump_at'] = row['mx']
        except Exception:
            pass
    return result


# ── Public service functions ───────────────────────────────────────────────────

def _to_int(value, default: int = 0) -> int:
    try:
        return int(value or default)
    except Exception:
        return default


def _market_thread_stats(tid: str) -> dict:
    with _db() as conn:
        try:
            row = conn.execute(
                "SELECT views,replies,lastpost_at,closed FROM market_threads WHERE tid=?",
                (str(tid),),
            ).fetchone()
            if row:
                row = dict(row)
                replies = _to_int(row.get("replies"))
                return {
                    "views": _to_int(row.get("views")),
                    "replies": replies,
                    "posts": replies + 1,
                    "lastpost": _to_int(row.get("lastpost_at")),
                    "closed": bool(_to_int(row.get("closed"))),
                    "source": "market",
                }
        except Exception:
            pass
    return {}


def _observed_thread_stats(thread: dict, cstats: dict | None = None) -> dict:
    cstats = cstats or {}
    market = _market_thread_stats(str(thread.get("tid") or ""))
    replies = _to_int(market.get("replies"), _to_int(thread.get("numreplies")))
    return {
        "views": _to_int(market.get("views")),
        "replies": replies,
        "posts": replies + 1,
        "lastpost": max(_to_int(thread.get("lastpost")), _to_int(market.get("lastpost"))),
        "lastposteruid": str(thread.get("lastposteruid") or ""),
        "closed": bool(thread.get("closed")) or bool(market.get("closed")),
        "contracts_total": _to_int(cstats.get("total")),
        "contracts_active": _to_int(cstats.get("active")) + _to_int(cstats.get("awaiting")),
        "contracts_complete": _to_int(cstats.get("complete")),
        "source": market.get("source") or "local",
    }


def _owned_thread(uid: str, tid: str) -> dict | None:
    with _db() as conn:
        row = conn.execute(
            "SELECT * FROM my_threads WHERE uid=? AND tid=?",
            (uid, str(tid)),
        ).fetchone()
        return dict(row) if row else None


def _stale_days(goals: dict) -> int:
    return max(1, _to_int(goals.get('max_stale_offer_days'), 30))


def _offer_last_activity(thread: dict, cstats: dict, rstats: dict, bstats: dict) -> int:
    return max(
        _to_int(thread.get('lastpost')),
        _to_int(rstats.get('latest_reply_at')),
        _to_int(cstats.get('last_contract_at')),
        _to_int(bstats.get('latest_bump_at')),
    )


def _is_recent(ts: int, now: int, days: int) -> bool:
    return bool(ts and ts >= now - (days * 86400))


def _offer_reasons(thread: dict, health: str, cstats: dict, rstats: dict,
                   bstats: dict, now: int, days: int,
                   active_bump_job: bool = False) -> list[str]:
    reasons: list[str] = []
    active_contracts = _to_int(cstats.get('active')) + _to_int(cstats.get('awaiting'))
    if _to_int(rstats.get('unread_replies')) > 0:
        reasons.append('Unread reply')
    if active_contracts > 0:
        reasons.append('Active contract')
    if _is_recent(_to_int(cstats.get('last_contract_at')), now, days):
        reasons.append('Recent contract')
    if _is_recent(_to_int(bstats.get('latest_bump_at')), now, days) or _to_int(bstats.get('bumps_7d')) > 0:
        reasons.append('Bumped recently')
    if _is_recent(_to_int(thread.get('lastpost')), now, days):
        reasons.append('Recent thread activity')
    if health == 'wasting_spend' and _to_int(bstats.get('bumps_30d')) > 0:
        reasons.append('Bump waste')
    if active_bump_job:
        reasons.append('Active bump job')
    return reasons


def _offer_archived(thread: dict, health: str, cstats: dict, rstats: dict,
                    bstats: dict, now: int, days: int,
                    active_bump_job: bool = False) -> bool:
    if health == 'needs_attention':
        return False
    active_contracts = _to_int(cstats.get('active')) + _to_int(cstats.get('awaiting'))
    if active_contracts > 0:
        return False
    if _offer_reasons(thread, health, cstats, rstats, bstats, now, days, active_bump_job):
        return False
    return True


def get_overview(uid: str) -> dict:
    now              = int(time.time())
    marketplace_tids = _get_marketplace_tids(uid)
    contracts        = _get_contracts(uid)
    all_threads      = _get_my_threads(uid)
    threads          = [t for t in all_threads if str(t.get('tid','')) in marketplace_tids]
    # TIDs the user owns - used to filter seller-side contracts (excludes threads user bought on)
    own_thread_tids  = {str(t.get('tid','')) for t in all_threads} - {''}
    tid_titles       = _get_tid_titles(
        uid, {str(c.get('tid') or '') for c in contracts}
    )

    replies          = [r for r in _get_reply_queue(uid) if str(r.get('tid','')) in marketplace_tids]
    bump_logs        = _get_bump_log(uid, 200)
    active_bump_tids = {str(j.get('tid', '')) for j in _get_bump_jobs(uid) if _to_int(j.get('enabled')) == 1}
    goals            = get_goals(uid)
    sla_hours        = goals.get('reply_sla_hours', 24)
    stale_days       = _stale_days(goals)
    recv_fresh_at    = int(goals.get('received_ratings_fetched_at') or 0)
    recv_is_fresh    = recv_fresh_at > 0 and (now - recv_fresh_at) < 86400
    lead_group_metas = {
        k: v for k, v in get_all_lead_group_metas(uid).items()
        if k[1] in marketplace_tids
    }

    def _old_awaiting(c: dict) -> bool:
        dl = int(c.get('dateline') or 0)
        return str(c.get('status_n', '')) in _PENDING and dl and (now - dl) > _AGE_EXPIRED_S

    unread_replies   = [r for r in replies if r.get('status') == 'unread']
    active_contracts = [c for c in contracts
                        if str(c.get('status_n', '')) in STATUS_FULFILLMENT
                        or (str(c.get('status_n', '')) in _PENDING and not _old_awaiting(c))]
    awaiting         = [c for c in contracts
                        if str(c.get('status_n', '')) in _PENDING and not _old_awaiting(c)]

    # SLA breaches: unread leads older than sla_hours with stage not yet resolved
    sla_breaches = 0
    for r in unread_replies:
        age = now - int(r.get('dateline') or now)
        key = (str(r.get('from_uid', '') or ''), str(r.get('tid', '') or ''))
        meta = lead_group_metas.get(key, {})
        stage = meta.get('stage', 'new')
        if stage not in ('ignored', 'lost', 'won') and age > sla_hours * 3600:
            sla_breaches += 1

    # Follow-ups due
    followup_due = 0
    for meta in lead_group_metas.values():
        fa = meta.get('followup_at')
        stage = meta.get('stage', 'new')
        if fa and fa <= now and stage not in ('ignored', 'lost', 'won'):
            followup_due += 1

    # Waste warnings: offer with 5+ bumps, 0 unread leads, 0 active/complete contracts in 7 days
    bstats_by_tid = bump_stats_from_log(bump_logs)
    rstats_by_tid = reply_stats_from_queue(replies)
    cstats_by_tid = offer_stats_from_contracts(contracts, uid)
    waste_warnings = 0
    for t in threads:
        tid = str(t.get('tid',''))
        bs = bstats_by_tid.get(tid, {})
        rs = rstats_by_tid.get(tid, {})
        cs = cstats_by_tid.get(tid, {})
        w = bump_waste_score(
            bs.get('bump_count', 0),
            rs.get('unread_replies', 0),
            cs.get('complete', 0),
            bumps_30d=bs.get('bumps_30d', 0),
        )
        if w >= 60:
            waste_warnings += 1

    # ── Contract stage pipeline (mirrors Contracts tab classify logic) ──────────
    workflows       = get_all_contract_workflows(uid)
    sent_cids       = get_sent_brating_cids(uid)
    bratings_by_cid = get_bratings_by_cid(uid)

    contract_stage_counts: dict[str, int] = {}
    _needs_review_raw: list[dict] = []
    _needs_rating_raw: list[dict] = []

    for c in contracts:
        cid   = str(c.get('cid', ''))
        wf    = workflows.get(cid, {})
        s     = str(c.get('status_n', ''))
        dl    = int(c.get('dateline') or 0)
        stage = classify_contract_stage(
            s, dl,
            str(c.get('inituid', '') or ''), str(c.get('otheruid', '') or ''), uid,
            bool(wf.get('completed_side_at')), now,
            str(c.get('istatus', '') or ''), str(c.get('ostatus', '') or ''),
        )
        if stage == 'completed' and cid not in sent_cids:
            stage = 'needs_rating'
        contract_stage_counts[stage] = contract_stage_counts.get(stage, 0) + 1
        cp = counterparty_uid(c, uid)
        if stage == 'needs_review' and len(_needs_review_raw) < 5:
            _needs_review_raw.append({
                'cid': cid, 'cp_uid': cp,
                'product': _contract_product(c, tid_titles),
                'dateline': dl,
            })
        elif stage == 'needs_rating' and len(_needs_rating_raw) < 5:
            _needs_rating_raw.append({
                'cid': cid, 'cp_uid': cp,
                'product': _contract_product(c, tid_titles),
                'dateline': dl,
            })

    # Cross-check received-rating freshness against local data.
    # A prior bad sync may have called mark_received_ratings_fetched even when _to returned
    # 0 rows, leaving recv_is_fresh=True but bratings_by_cid nearly empty.  Override the
    # flag when local received-rating data is clearly incomplete relative to known context:
    #   - Empty (0 rows) while completed contracts exist, OR
    #   - Very sparse (< 3 rows) while user has rated more than 20 contracts themselves.
    # Either case means the UI would show a misleading "Waiting on Them" count; better to
    # show the "not synced" notice so the user knows to click Sync Ratings.
    if recv_is_fresh:
        n_recv = len(bratings_by_cid)
        n_sent = len(sent_cids)
        completions = contract_stage_counts.get('completed', 0) + contract_stage_counts.get('needs_rating', 0)
        if n_recv == 0 and completions > 0:
            recv_is_fresh = False
        elif n_recv < 3 and n_sent > 20:
            recv_is_fresh = False

    _rating_needs_mine   = contract_stage_counts.get('needs_rating', 0)
    _rating_waiting_them = 0
    _rating_both         = 0
    for c in contracts:
        if str(c.get('status_n', '')) == '6':
            cid = str(c.get('cid', ''))
            if cid in sent_cids:
                if cid in bratings_by_cid:
                    _rating_both += 1
                else:
                    _rating_waiting_them += 1

    # ── Thread health list ──────────────────────────────────────────────────────
    _health_order = {'needs_attention': 0, 'wasting_spend': 1, 'healthy': 2, 'new': 3, 'stale': 4}
    thread_health_list: list[dict] = []
    for t in threads:
        tid = str(t.get('tid', ''))
        rs  = rstats_by_tid.get(tid, {})
        cs  = cstats_by_tid.get(tid, {})
        bs  = bstats_by_tid.get(tid, {})
        health = offer_health(t, cs, rs, bs, sla_hours, stale_days)
        has_active_bump = tid in active_bump_tids
        archived = _offer_archived(t, health, cs, rs, bs, now, stale_days, has_active_bump)
        reasons = _offer_reasons(t, health, cs, rs, bs, now, stale_days, has_active_bump)
        if archived:
            continue
        thread_health_list.append({
            'tid':                tid,
            'title':              t.get('title', '')[:60],
            'health':             health,
            'reasons':            reasons,
            'archived':           archived,
            'last_activity_at':    _offer_last_activity(t, cs, rs, bs),
            'unread_replies':     rs.get('unread_replies', 0),
            'contracts_active':   cs.get('active', 0) + cs.get('awaiting', 0),
            'contracts_complete': cs.get('complete', 0),
            'latest_bump_at':     bs.get('latest_bump_at', 0),
            'bumps_7d':           bs.get('bumps_7d', 0),
        })
    thread_health_list.sort(key=lambda x: (_health_order.get(x['health'], 5), -x['unread_replies']))
    threads_needing_attention = sum(1 for th in thread_health_list if th['health'] == 'needs_attention')
    archived_thread_count = len(threads) - len(thread_health_list)
    thread_health_list = thread_health_list[:8]

    action_queue = overview_action_queue(
        unread_replies=len(unread_replies),
        active_contracts=len(active_contracts),
        awaiting_contracts=len(awaiting),
        sla_breaches=sla_breaches,
        waste_warnings=waste_warnings,
        followup_due=followup_due,
    )

    today_start = now - (now % 86400)
    week_start  = now - 7 * 86400
    new_leads_today = sum(
        1 for r in replies
        if int(r.get('dateline') or 0) >= today_start
    )

    completion_events = _get_completion_events(uid, week_start - 86400)
    if completion_events:
        completed_today = sum(1 for e in completion_events if e['detected_at'] >= today_start)
        completed_week  = sum(1 for e in completion_events if e['detected_at'] >= week_start)
        daily_completions = []
        for day_offset in range(6, -1, -1):
            ds = today_start - day_offset * 86400
            daily_completions.append(sum(
                1 for e in completion_events
                if ds <= e['detected_at'] < ds + 86400
            ))
    else:
        completed_today = sum(
            1 for c in contracts
            if str(c.get('status_n', '')) in STATUS_COMPLETE
            and int(c.get('dateline') or 0) >= today_start
        )
        completed_week = sum(
            1 for c in contracts
            if str(c.get('status_n', '')) in STATUS_COMPLETE
            and int(c.get('dateline') or 0) >= week_start
        )
        daily_completions = []
        for day_offset in range(6, -1, -1):
            ds = today_start - day_offset * 86400
            daily_completions.append(sum(
                1 for c in contracts
                if str(c.get('status_n', '')) in STATUS_COMPLETE
                and ds <= int(c.get('dateline') or 0) < ds + 86400
            ))

    # Top problems
    problems = []
    for t in threads:
        tid = str(t.get('tid',''))
        bs = bstats_by_tid.get(tid, {})
        rs = rstats_by_tid.get(tid, {})
        cs = cstats_by_tid.get(tid, {})
        if bs.get('bump_count', 0) >= 8 and rs.get('total_replies', 0) == 0 and cs.get('complete', 0) == 0:
            problems.append({'type': 'bump_no_leads', 'tid': tid,
                             'title': t.get('title','')[:60],
                             'bumps': bs['bump_count']})
        if rs.get('unread_replies', 0) >= 3:
            problems.append({'type': 'many_unanswered', 'tid': tid,
                             'title': t.get('title','')[:60],
                             'unread': rs['unread_replies']})
    problems = problems[:5]

    # Open reply groups: unique (from_uid, tid) with unread replies, non-terminal stage
    _open_keys: set[tuple] = set()
    for r in unread_replies:
        fu = str(r.get('from_uid', '') or '')
        t  = str(r.get('tid', '') or '')
        if fu and t:
            meta = lead_group_metas.get((fu, t), {})
            if meta.get('stage', 'new') not in ('ignored', 'lost', 'won'):
                _open_keys.add((fu, t))
    pipeline_open_count = len(_open_keys)

    # Pipeline stage breakdown (active stages only, for bar chart)
    pipeline_by_stage: dict[str, int] = {}
    for meta in lead_group_metas.values():
        s = meta.get('stage', 'new')
        pipeline_by_stage[s] = pipeline_by_stage.get(s, 0) + 1

    # Top customers by completed deal count - seller side only
    # (exclude contracts on threads the user doesn't own, i.e. where user is the buyer)
    seller_contracts = [c for c in contracts if str(c.get('tid','')) in own_thread_tids]
    cust_stats_map = customer_stats(seller_contracts, uid)
    top_cp_pairs = sorted(
        cust_stats_map.items(),
        key=lambda x: (-x[1]['complete'], -(x[1]['last_deal_at'] or 0))
    )[:5]

    # Recent contracts - already sorted DESC by dateline from DB
    recent_slice = contracts[:8]

    # Batch username fetch for recent contracts + top customers
    all_lookup_uids = list({
        u for u in
        [counterparty_uid(c, uid) for c in recent_slice]
        + [cp for cp, _ in top_cp_pairs]
        + [r['cp_uid'] for r in _needs_review_raw]
        + [r['cp_uid'] for r in _needs_rating_raw]
        if u
    })
    name_cache = _get_usernames(all_lookup_uids) if all_lookup_uids else {}

    recent_contracts = []
    for c in recent_slice:
        cid = str(c.get('cid', ''))
        cp  = counterparty_uid(c, uid)
        wf  = workflows.get(cid, {})
        s   = str(c.get('status_n', ''))
        dl  = int(c.get('dateline') or 0)
        rc_stage = classify_contract_stage(
            s, dl,
            str(c.get('inituid', '') or ''), str(c.get('otheruid', '') or ''), uid,
            bool(wf.get('completed_side_at')), now,
            str(c.get('istatus', '') or ''), str(c.get('ostatus', '') or ''),
        )
        if rc_stage == 'completed' and cid not in sent_cids:
            rc_stage = 'needs_rating'
        recent_contracts.append({
            'cid':         cid,
            'cp_uid':      cp,
            'cp_username': name_cache.get(cp, ''),
            'stage':       rc_stage,
            'bucket':      contract_bucket(s, dl),
            'product':     _contract_product(c, tid_titles),
            'dateline':    dl,
            'tid':         str(c.get('tid', '')),
        })

    top_customers_out = [{
        'uid': cp,
        'username': name_cache.get(cp, ''),
        'complete': stats['complete'],
        'active': stats['active'],
        'is_repeat': stats['is_repeat'],
        'last_deal_at': stats['last_deal_at'],
    } for cp, stats in top_cp_pairs]

    needs_review_items = [
        {**r, 'cp_username': name_cache.get(r['cp_uid'], '')}
        for r in _needs_review_raw
    ]
    needs_rating_items = [
        {**r, 'cp_username': name_cache.get(r['cp_uid'], '')}
        for r in _needs_rating_raw
    ]
    needs_action_total = (
        contract_stage_counts.get('needs_review', 0)
        + sla_breaches
        + _rating_needs_mine
    )
    active_pipeline_total = (
        contract_stage_counts.get('waiting_on_approval', 0)
        + contract_stage_counts.get('active', 0)
        + contract_stage_counts.get('waiting_on_counterparty', 0)
    )

    return {
        'username_map': name_cache,
        'action_queue': action_queue,
        'today': {
            'completed_deals': completed_today,
            'new_leads': new_leads_today,
            'active_contracts': len(active_contracts),
        },
        'week': {
            'completed_deals': completed_week,
        },
        'top_problems': problems,
        'totals': {
            'tracked_offers': len(threads),
            'total_contracts': len(contracts),
            'completed_contracts': sum(1 for c in contracts if str(c.get('status_n','')) in STATUS_COMPLETE),
        },
        'pipeline': {
            'by_stage': pipeline_by_stage,
            'total': pipeline_open_count,
            'sla_breaches': sla_breaches,
        },
        'recent_contracts': recent_contracts,
        'top_customers': top_customers_out,
        'daily_completions':         daily_completions,
        'contract_stage_counts':     contract_stage_counts,
        'rating_summary': {
            'needs_mine':          _rating_needs_mine,
            'waiting_theirs':      _rating_waiting_them,
            'both_rated':          _rating_both,
            'received_data_fresh': recv_is_fresh,
            'received_fetched_at': recv_fresh_at,
        },
        'needs_review_items':        needs_review_items,
        'needs_rating_items':        needs_rating_items,
        'thread_health':             thread_health_list,
        'archived_thread_count':     archived_thread_count,
        'stale_thread_days':         stale_days,
        'needs_action':              needs_action_total,
        'active_pipeline':           active_pipeline_total,
        'threads_needing_attention': threads_needing_attention,
    }


def get_offers(uid: str, status_filter: str | None = None, sort: str = 'health') -> list[dict]:
    effective_filter = status_filter or 'active'
    marketplace_tids = _get_marketplace_tids(uid)
    threads   = [t for t in _get_my_threads(uid) if str(t.get('tid','')) in marketplace_tids]
    contracts = _get_contracts(uid)
    replies   = _get_reply_queue(uid)
    bump_logs = _get_bump_log(uid, 500)
    active_bump_tids = {str(j.get('tid', '')) for j in _get_bump_jobs(uid) if _to_int(j.get('enabled')) == 1}
    goals     = get_goals(uid)
    offer_meta = get_all_offer_meta(uid)
    now = int(time.time())

    cstats_by_tid = offer_stats_from_contracts(contracts, uid)
    rstats_by_tid = reply_stats_from_queue(replies)
    bstats_by_tid = bump_stats_from_log(bump_logs)
    sla_hours = goals.get('reply_sla_hours', 24)
    stale_days = _stale_days(goals)

    result = []
    for t in threads:
        tid = str(t.get('tid', ''))
        meta = offer_meta.get(tid, {})

        if meta.get('hidden'):
            continue

        cs = cstats_by_tid.get(tid, {})
        rs = rstats_by_tid.get(tid, {})
        bs = bstats_by_tid.get(tid, {})

        health = offer_health(t, cs, rs, bs, sla_hours, stale_days)
        has_active_bump = tid in active_bump_tids
        archived = _offer_archived(t, health, cs, rs, bs, now, stale_days, has_active_bump)
        reasons = _offer_reasons(t, health, cs, rs, bs, now, stale_days, has_active_bump)
        observed = _observed_thread_stats(t, cs)
        last_activity = max(_offer_last_activity(t, cs, rs, bs), _to_int(observed.get('lastpost')))

        if effective_filter:
            if effective_filter == 'active'          and (archived or health not in ('healthy', 'needs_attention', 'new', 'wasting_spend')):
                continue
            if effective_filter == 'needs_attention' and health != 'needs_attention':
                continue
            if effective_filter == 'wasting_spend'   and health != 'wasting_spend':
                continue
            if effective_filter == 'stale'           and not (archived or health == 'stale'):
                continue
            if effective_filter == 'no_contracts'    and cs.get('total', 0) > 0:
                continue

        waste = bump_waste_score(
            bs.get('bump_count', 0),
            rs.get('unread_replies', 0),
            cs.get('complete', 0),
            bumps_30d=bs.get('bumps_30d', 0),
        )

        result.append({
            'tid': tid,
            'title': meta.get('label') or t.get('title', ''),
            'raw_title': t.get('title', ''),
            'fid': t.get('fid', ''),
            'closed': observed.get('closed', bool(t.get('closed'))),
            'lastpost': observed.get('lastpost', t.get('lastpost', 0)),
            'lastposteruid': observed.get('lastposteruid', ''),
            'numreplies': observed.get('replies', t.get('numreplies', 0)),
            'views': observed.get('views', 0),
            'post_count': observed.get('posts', _to_int(t.get('numreplies')) + 1),
            'stats_source': observed.get('source', 'local'),
            'reply_count': rs.get('total_replies', 0),
            'unread_leads': rs.get('unread_replies', 0),
            'contracts_total': cs.get('total', 0),
            'contracts_complete': cs.get('complete', 0),
            'contracts_active': cs.get('active', 0),
            'contracts_awaiting': cs.get('awaiting', 0),
            'contracts_lost': cs.get('lost', 0),
            'unique_buyers': cs.get('unique_buyers', 0),
            'bump_count': bs.get('bump_count', 0),
            'bump_waste_score': waste,
            'last_contract_at': cs.get('last_contract_at', 0),
            'last_activity_at': last_activity,
            'health': health,
            'reasons': reasons,
            'archived': archived,
            'category': meta.get('category', ''),
            'status': meta.get('status', 'active'),
        })

    health_order = {'needs_attention': 0, 'wasting_spend': 1, 'healthy': 2, 'new': 3, 'stale': 4}
    if sort == 'health':
        result.sort(key=lambda x: (1 if x.get('archived') else 0, health_order.get(x['health'], 5), -(x['last_activity_at'] or 0)))
    elif sort == 'activity':
        result.sort(key=lambda x: -(x['last_activity_at'] or x['lastpost'] or 0))
    elif sort == 'contracts':
        result.sort(key=lambda x: -x['contracts_total'])

    return result


def get_offer_detail(uid: str, tid: str) -> dict | None:
    threads  = _get_my_threads(uid)
    thread   = next((t for t in threads if str(t.get('tid','')) == tid), None)
    if not thread:
        return None

    contracts = [c for c in _get_contracts(uid) if str(c.get('tid','')) == tid]
    replies   = [r for r in _get_reply_queue(uid) if str(r.get('tid','')) == tid]
    bump_log  = [b for b in _get_bump_log(uid) if str(b.get('tid','')) == tid]
    goals     = get_goals(uid)
    meta      = (get_all_offer_meta(uid)).get(tid, {})
    lead_metas = _get_lead_metas(uid)

    cs = offer_stats_from_contracts(contracts, uid).get(tid, {})
    rs = reply_stats_from_queue(replies).get(tid, {})
    bs = bump_stats_from_log(bump_log).get(tid, {})
    observed = _observed_thread_stats(thread, cs)
    health = offer_health(thread, cs, rs, bs, goals.get('reply_sla_hours', 24), _stale_days(goals))
    waste  = bump_waste_score(bs.get('bump_count',0), rs.get('unread_replies',0), cs.get('complete',0),
                              bumps_30d=bs.get('bumps_30d', 0))

    # Enrich counterparty names
    buyer_uids = list({counterparty_uid(c, uid) for c in contracts if counterparty_uid(c, uid)})
    names = _get_usernames(buyer_uids)

    enriched_contracts = []
    for c in contracts:
        cp = counterparty_uid(c, uid)
        enriched_contracts.append({
            **c,
            'counterparty_username': names.get(cp, ''),
            'bucket': contract_bucket(str(c.get('status_n','')), int(c.get('dateline') or 0)),
        })

    enriched_replies = []
    for r in replies:
        rid = r.get('id')
        lead_m = lead_metas.get(rid, {})
        enriched_replies.append({**r, 'lead_stage': lead_m.get('stage', 'new'),
                                  'lead_priority': lead_m.get('priority', 'normal')})

    return {
        'tid': tid,
        'title': meta.get('label') or thread.get('title', ''),
        'raw_title': thread.get('title', ''),
        'fid': thread.get('fid', ''),
        'closed': observed.get('closed', bool(thread.get('closed'))),
        'lastpost': observed.get('lastpost', thread.get('lastpost', 0)),
        'lastposteruid': observed.get('lastposteruid', ''),
        'numreplies': observed.get('replies', thread.get('numreplies', 0)),
        'views': observed.get('views', 0),
        'post_count': observed.get('posts', _to_int(thread.get('numreplies')) + 1),
        'stats_source': observed.get('source', 'local'),
        'health': health,
        'contracts_total': cs.get('total', 0),
        'contracts_complete': cs.get('complete', 0),
        'contracts_active': cs.get('active', 0),
        'contracts_lost': cs.get('lost', 0),
        'bump_count': bs.get('bump_count', 0),
        'bump_waste_score': waste,
        'unread_leads': rs.get('unread_replies', 0),
        'unique_buyers': cs.get('unique_buyers', 0),
        'contracts': enriched_contracts,
        'replies': enriched_replies,
        'bump_log': bump_log[:50],
        'meta': meta,
    }


def get_pipeline(uid: str) -> dict:
    # Replies only exist in pipeline from when the user first authed with the dashboard.
    # created_at is set by upsert_user() on first login; fall back to last_seen for
    # existing accounts that predate the fix.
    with _db() as conn:
        user_row = conn.execute(
            "SELECT created_at, last_seen FROM users WHERE uid=?", (uid,)
        ).fetchone()
    if user_row:
        pipeline_since = int(user_row['created_at'] or user_row['last_seen'] or 0)
    else:
        pipeline_since = 0

    marketplace_tids = _get_marketplace_tids(uid)
    all_replies = [r for r in _get_reply_queue(uid) if str(r.get('tid','')) in marketplace_tids]
    replies = [r for r in all_replies
               if not pipeline_since or int(r.get('dateline') or 0) >= pipeline_since]
    lead_group_metas = get_all_lead_group_metas(uid)
    contracts        = _get_contracts(uid)
    goals            = get_goals(uid)
    now              = int(time.time())
    sla_hours        = goals.get('reply_sla_hours', 24)

    # Contracts by (tid, from_uid) to flag conversions
    converted: set[tuple] = set()
    for c in contracts:
        cp = counterparty_uid(c, uid)
        t  = str(c.get('tid', ''))
        if cp and t:
            converted.add((t, cp))

    # Group replies by (from_uid, tid) - one card per person per thread
    from collections import defaultdict
    groups: dict[tuple, list] = defaultdict(list)
    for r in replies:
        fu = str(r.get('from_uid', '') or '')
        t  = str(r.get('tid', '') or '')
        if fu:
            groups[(fu, t)].append(r)

    all_from_uids = list({k[0] for k in groups})
    names = _get_usernames(all_from_uids)

    leads = []
    for (from_uid_str, tid_str), grp in groups.items():
        grp.sort(key=lambda r: int(r.get('dateline') or 0))
        first_r  = grp[0]
        latest_r = grp[-1]

        unread_in_grp   = [r for r in grp if r.get('status') == 'unread']
        latest_unread_ts = max((int(r.get('dateline') or 0) for r in unread_in_grp), default=0)

        meta       = lead_group_metas.get((from_uid_str, tid_str), {})
        stage      = meta.get('stage', 'new')
        priority   = meta.get('priority', 'normal')
        note       = meta.get('note')
        followup_at = meta.get('followup_at')

        first_dl = int(first_r.get('dateline') or 0)
        sla_breached = (
            stage not in ('ignored', 'lost', 'won', 'contract_opened')
            and bool(unread_in_grp)
            and bool(latest_unread_ts)
            and (now - latest_unread_ts) > sla_hours * 3600
        )

        leads.append({
            'from_uid':        from_uid_str,
            'tid':             tid_str,
            'from_username':   names.get(from_uid_str) or latest_r.get('from_username', ''),
            'thread_title':    first_r.get('thread_title', ''),
            'first_reply_id':  first_r.get('id'),
            'latest_reply_id': latest_r.get('id'),
            'latest_pid':      latest_r.get('pid', ''),
            'dateline':        first_dl,
            'latest_dateline': int(latest_r.get('dateline') or 0),
            'age_seconds':     now - first_dl if first_dl else 0,
            'reply_count':     len(grp),
            'unread_count':    len(unread_in_grp),
            'message_preview': latest_r.get('message_preview', ''),
            'stage':           stage,
            'priority':        priority,
            'note':            note,
            'followup_at':     followup_at,
            'sla_breached':    sla_breached,
            'likely_converted': (tid_str, from_uid_str) in converted,
        })

    # SLA breached first, then most recent activity
    leads.sort(key=lambda x: (not x['sla_breached'], -(x['latest_dateline'] or 0)))

    stage_counts: dict[str, int] = {}
    sla_total = 0
    for lead in leads:
        s = lead['stage']
        stage_counts[s] = stage_counts.get(s, 0) + 1
        if lead['sla_breached']:
            sla_total += 1

    open_count = sum(1 for l in leads if l['unread_count'] > 0)

    return {
        'leads': leads,
        'summary': {
            'by_stage': stage_counts,
            'sla_breaches': sla_total,
            'open': open_count,
            'total': len(leads),
        },
        'sla_hours': sla_hours,
    }


def get_deals(uid: str, bucket_filter: str | None = None) -> list[dict]:
    now       = int(time.time())
    contracts = _get_contracts(uid)
    buyer_uids = list({counterparty_uid(c, uid) for c in contracts if counterparty_uid(c, uid)})
    names = _get_usernames(buyer_uids)
    workflows = get_all_contract_workflows(uid)
    # Received ratings (counterparty rated me): {contractid: row}
    bratings  = get_bratings_by_cid(uid)
    # Sent ratings (I rated): set of contractids.
    # A status-6 contract is only truly Completed once I have left a rating.
    # Default to needs_rating for any unrated status-6; sync populates this set.
    sent_cids = get_sent_brating_cids(uid)

    # Received-rating freshness — same sparse-data cross-check as get_overview.
    # Only claim waiting_on_them when received data is trusted fresh.
    goals         = get_goals(uid)
    recv_fresh_at = int(goals.get('received_ratings_fetched_at') or 0)
    recv_is_fresh = recv_fresh_at > 0 and (now - recv_fresh_at) < 86400
    if recv_is_fresh and len(bratings) < 3 and len(sent_cids) > 20:
        recv_is_fresh = False

    tid_titles = _get_tid_titles(
        uid, {str(c.get('tid') or '') for c in contracts}
    )

    result = []
    for c in contracts:
        status_n = str(c.get('status_n', ''))
        dateline = int(c.get('dateline') or 0)
        cid      = str(c.get('cid', ''))
        inituid  = str(c.get('inituid', '') or '')
        otheruid = str(c.get('otheruid', '') or '')
        wf       = workflows.get(cid, {})
        completed_side_at = wf.get('completed_side_at')

        stage = classify_contract_stage(
            status_n, dateline, inituid, otheruid, uid,
            bool(completed_side_at), now,
            str(c.get('istatus', '') or ''),
            str(c.get('ostatus', '') or ''),
        )
        # Status 6 = both sides marked complete, but not truly finished until I leave a rating.
        # Mirrors HF: Awaiting Approval -> Active Deal -> Credibility -> Completed.
        # Default is needs_rating; moves to completed only once rating is confirmed via Sync.
        if stage == 'completed' and cid not in sent_cids:
            stage = 'needs_rating'

        bucket = contract_bucket(status_n, dateline)
        if bucket_filter and bucket != bucket_filter:
            continue

        def _parse_dispute(v):
            if not v: return None
            try: return _json.loads(v)
            except Exception: return None

        cp      = counterparty_uid(c, uid)
        tid     = str(c.get('tid', ''))
        brating = bratings.get(cid)

        if status_n != '6':
            rating_state = 'not_applicable'
        elif cid not in sent_cids:
            rating_state = 'needs_my_rating'
        elif bool(brating):
            rating_state = 'both_rated'
        elif recv_is_fresh:
            rating_state = 'waiting_on_them'
        else:
            rating_state = 'not_applicable'

        result.append({
            'cid':                            cid,
            'type_n':                         str(c.get('type_n', '') or ''),
            'status_n':                       status_n,
            'bucket':                         bucket,
            'stage':                          stage,
            'counterparty_uid':               cp,
            'counterparty_username':          names.get(cp, ''),
            'tid':                            tid,
            'thread_title':                   tid_titles.get(tid, ''),
            'product':                        _contract_product(c, tid_titles),
            'dateline':                       c.get('dateline', 0),
            'iproduct':                       c.get('iproduct', ''),
            'oproduct':                       c.get('oproduct', ''),
            'iprice':                         c.get('iprice', ''),
            'icurrency':                      c.get('icurrency', ''),
            'oprice':                         c.get('oprice', ''),
            'ocurrency':                      c.get('ocurrency', ''),
            'inituid':                        inituid,
            'otheruid':                       otheruid,
            'istatus':                        str(c.get('istatus', '') or ''),
            'ostatus':                        str(c.get('ostatus', '') or ''),
            'iaddress':                       str(c.get('iaddress', '') or ''),
            'oaddress':                       str(c.get('oaddress', '') or ''),
            'terms':                          str(c.get('terms', '') or ''),
            'timeout_days':                   str(c.get('timeout_days', '') or ''),
            'timeout':                        str(c.get('timeout', '') or ''),
            'public':                         str(c.get('public', '') or ''),
            'idispute':                       _parse_dispute(c.get('idispute', '')),
            'odispute':                       _parse_dispute(c.get('odispute', '')),
            'completed_side_at':              completed_side_at,
            'has_sent_rating':                cid in sent_cids,
            'has_received_rating':            bool(brating),
            'rating_state':                   rating_state,
            'received_rating_amount':         brating.get('amount') if brating else None,
            'received_rating_from_uid':       brating.get('fromid', '') if brating else '',
            'received_rating_from_username':  brating.get('from_username', '') if brating else '',
            'received_rating_message':        (brating.get('message', '') or '')[:200] if brating else '',
        })

    result.sort(key=lambda x: -(x['dateline'] or 0))
    return result


def get_customers(uid: str, seller_only: bool = True) -> list[dict]:
    contracts = _get_contracts(uid)
    if seller_only:
        own_tids = {str(t.get('tid', '')) for t in _get_my_threads(uid)} - {''}
        contracts = [c for c in contracts if str(c.get('tid', '')) in own_tids]
    cstats = customer_stats(contracts, uid)

    all_cp_uids = list(cstats.keys())
    names = _get_usernames(all_cp_uids)

    result = []
    for cp_uid, stats in cstats.items():
        meta = get_customer_meta(uid, cp_uid) or {}
        result.append({
            'uid': cp_uid,
            'username': names.get(cp_uid, ''),
            'completed_deals': stats['complete'],
            'active_deals': stats['active'],
            'lost_deals': stats['lost'],
            'total_deals': stats['total'],
            'last_deal_at': stats['last_deal_at'],
            'top_products': stats['products'],
            'is_repeat': stats['is_repeat'],
            'label': meta.get('label', ''),
            'note': meta.get('note', ''),
            'tags_json': meta.get('tags_json', ''),
            'followup_at': meta.get('followup_at'),
        })

    result.sort(key=lambda x: (-x['completed_deals'], -(x['last_deal_at'] or 0)))
    return result


def get_customer_detail(uid: str, cp_uid: str) -> dict | None:
    contracts = [c for c in _get_contracts(uid) if counterparty_uid(c, uid) == cp_uid]
    if not contracts:
        return None

    names = _get_usernames([cp_uid])
    stats = customer_stats(contracts, uid).get(cp_uid, {})
    meta  = get_customer_meta(uid, cp_uid) or {}

    tid_set = {str(c.get('tid','')) for c in contracts if c.get('tid')}
    tid_titles: dict[str, str] = {}
    with _db() as conn:
        for t in conn.execute("SELECT tid, title FROM my_threads WHERE uid=?", (uid,)).fetchall():
            tid_titles[str(t['tid'])] = t['title']

    enriched = []
    for c in contracts:
        enriched.append({
            **c,
            'bucket': contract_bucket(str(c.get('status_n', '')), int(c.get('dateline') or 0)),
            'thread_title': tid_titles.get(str(c.get('tid','')), ''),
        })

    return {
        'uid': cp_uid,
        'username': names.get(cp_uid, ''),
        'completed_deals': stats.get('complete', 0),
        'active_deals': stats.get('active', 0),
        'lost_deals': stats.get('lost', 0),
        'total_deals': stats.get('total', 0),
        'last_deal_at': stats.get('last_deal_at', 0),
        'top_products': stats.get('products', []),
        'is_repeat': stats.get('is_repeat', False),
        'label': meta.get('label', ''),
        'note': meta.get('note', ''),
        'tags_json': meta.get('tags_json', ''),
        'followup_at': meta.get('followup_at'),
        'contracts': enriched,
        'offer_tids': list(tid_set),
    }


def get_thread_updates(uid: str) -> dict:
    offers = get_offers(uid, 'active', 'activity')
    _refresh_thread_update_observations(uid, offers)
    editable = []
    for offer in offers:
        if offer.get('closed'):
            continue
        replies = _to_int(offer.get('numreplies'), _to_int(offer.get('replies')))
        posts = _to_int(offer.get('post_count'), _to_int(offer.get('posts'), replies + 1))
        editable.append({
            'tid': offer['tid'],
            'title': offer.get('title') or offer.get('raw_title') or f"TID {offer['tid']}",
            'views': offer.get('views', 0),
            'replies': replies,
            'posts': posts,
            'contracts_total': offer.get('contracts_total', 0),
            'contracts_active': offer.get('contracts_active', 0) + offer.get('contracts_awaiting', 0),
            'contracts_complete': offer.get('contracts_complete', 0),
            'last_activity_at': offer.get('last_activity_at', 0),
            'closed': offer.get('closed', False),
            'reasons': offer.get('reasons', []),
        })
    updates = list_thread_updates(uid, limit=50)
    return {
        'threads': editable,
        'updates': updates,
        'summary': {
            'thread_count': len(editable),
            'posted_updates': sum(1 for item in updates if item.get('status') == 'posted'),
            'failed_updates': sum(1 for item in updates if item.get('status') == 'failed'),
        },
    }


def _refresh_thread_update_observations(uid: str, offers: list[dict] | None = None) -> None:
    """Refresh posted-update movement from local thread snapshots only."""
    offers = offers if offers is not None else get_offers(uid, 'active', 'activity')
    offer_by_tid = {str(offer.get('tid')): offer for offer in offers}
    for item in list_thread_updates(uid, limit=100):
        if item.get('status') != 'posted':
            continue
        offer = offer_by_tid.get(str(item.get('tid')))
        if not offer:
            continue
        replies = _to_int(offer.get('numreplies'), _to_int(offer.get('replies'), item.get('observed_replies', 0)))
        posts = _to_int(offer.get('post_count'), _to_int(offer.get('posts'), item.get('observed_posts', replies + 1)))
        observed = {
            'views': offer.get('views', item.get('observed_views', 0)),
            'replies': replies,
            'posts': posts,
            'contracts': offer.get('contracts_total', item.get('observed_contracts', 0)),
            'observed_at': int(time.time()),
        }
        mark_thread_update_result(uid, item['id'], status='posted',
                                  result_message=item.get('result_message', ''),
                                  hf_pid=item.get('hf_pid', ''),
                                  posted_at=item.get('posted_at') or item.get('created_at'),
                                  observed=observed)


def get_promotion(uid: str) -> dict:
    from collections import defaultdict

    now       = int(time.time())
    threads   = _get_my_threads(uid)
    bump_jobs = _get_bump_jobs(uid)
    bump_logs = _get_bump_log(uid, 1000)
    contracts = _get_contracts(uid)
    replies   = _get_reply_queue(uid)
    completion_events = _get_completion_events(uid, 0)

    bstats = bump_stats_from_log(bump_logs)
    rstats = reply_stats_from_queue(replies)
    cstats = offer_stats_from_contracts(contracts, uid)

    thread_map = {str(t.get('tid','')): t for t in threads}
    job_map    = {str(j.get('tid','')): j for j in bump_jobs}

    # Group bumps by tid sorted ASC; collect skips as list sorted DESC
    bumps_by_tid: dict[str, list[dict]] = defaultdict(list)
    skips_list_by_tid: dict[str, list[dict]] = defaultdict(list)
    for b in bump_logs:
        tid = str(b.get('tid', '') or '')
        if not tid:
            continue
        if b.get('action') == 'bumped':
            bumps_by_tid[tid].append(b)
        else:
            skips_list_by_tid[tid].append({
                'ts':     int(b.get('ts', 0)),
                'reason': b.get('reason', '') or '',
            })
    for tid in bumps_by_tid:
        bumps_by_tid[tid].sort(key=lambda b: int(b.get('ts', 0)))
    for tid in skips_list_by_tid:
        skips_list_by_tid[tid].sort(key=lambda s: -s['ts'])

    # Group contracts and replies by tid
    contracts_by_tid: dict[str, list[dict]] = defaultdict(list)
    for c in contracts:
        contracts_by_tid[str(c.get('tid', '') or '')].append(c)

    replies_by_tid: dict[str, list[dict]] = defaultdict(list)
    for r in replies:
        replies_by_tid[str(r.get('tid', '') or '')].append(r)

    # Map completion events by cid -> detected_at
    completion_by_cid: dict[str, int] = {
        str(e['cid']): int(e['detected_at']) for e in completion_events
    }

    thirty_days_ago = now - 30 * 86400

    offers = []
    needs_review_count  = 0
    got_activity_count  = 0
    open_replies_total  = 0
    paused_count        = 0

    all_tids = set(bumps_by_tid.keys()) | set(job_map.keys())

    for tid in all_tids:
        bs = bstats.get(tid, {})
        rs = rstats.get(tid, {})
        cs = cstats.get(tid, {})
        t  = thread_map.get(tid, {})
        job = job_map.get(tid)

        bumps         = bumps_by_tid.get(tid, [])         # ASC
        tid_skips     = skips_list_by_tid.get(tid, [])   # DESC
        skip_count    = len(tid_skips)
        tid_contracts = contracts_by_tid.get(tid, [])
        tid_replies   = replies_by_tid.get(tid, [])

        waste = bump_waste_score(
            bs.get('bump_count', 0),
            rs.get('unread_replies', 0),
            cs.get('complete', 0),
            bumps_30d=bs.get('bumps_30d', 0),
        )

        # Build bump periods (each bump to the next, last is open)
        periods = []
        for i, bump in enumerate(bumps):
            bump_ts = int(bump.get('ts', 0))
            next_bump = bumps[i + 1] if i + 1 < len(bumps) else None
            end_ts  = int(next_bump['ts']) if next_bump else now
            is_open = next_bump is None

            curr_nr = bump.get('numreplies')
            if is_open:
                next_nr = t.get('numreplies')
            else:
                next_nr = next_bump.get('numreplies') if next_bump else None

            if curr_nr is not None and next_nr is not None:
                reply_gain = int(next_nr) - int(curr_nr)
            else:
                reply_gain = None

            period_replies = sum(
                1 for r in tid_replies
                if bump_ts <= int(r.get('dateline') or 0) < end_ts
            )
            period_open_replies = sum(
                1 for r in tid_replies
                if r.get('status') == 'unread'
                and bump_ts <= int(r.get('dateline') or 0) < end_ts
            )
            opened = sum(
                1 for c in tid_contracts
                if bump_ts <= int(c.get('dateline') or 0) < end_ts
            )
            completed = sum(
                1 for c in tid_contracts
                if completion_by_cid.get(str(c.get('cid', ''))) is not None
                and bump_ts <= completion_by_cid[str(c.get('cid', ''))] < end_ts
            )
            periods.append({
                'bump_ts':            bump_ts,
                'end_ts':             end_ts,
                'is_open':            is_open,
                'reply_gain':         reply_gain,
                'period_replies':     period_replies,
                'period_open_replies': period_open_replies,
                'contracts_opened':   opened,
                'contracts_completed': completed,
            })

        # since_last_bump stats
        last_bump_ts = int(bumps[-1]['ts']) if bumps else 0
        last_bump_nr = bumps[-1].get('numreplies') if bumps else None
        curr_nr_thread = t.get('numreplies')

        if last_bump_ts:
            slb_replies  = [r for r in tid_replies if int(r.get('dateline') or 0) >= last_bump_ts]
            slb_open     = [r for r in slb_replies  if r.get('status') == 'unread']
            slb_contracts = [c for c in tid_contracts if int(c.get('dateline') or 0) >= last_bump_ts]
            slb_completed = sum(
                1 for c in tid_contracts
                if completion_by_cid.get(str(c.get('cid', ''))) is not None
                and completion_by_cid[str(c.get('cid', ''))] >= last_bump_ts
            )
            last_reply_ts    = max((int(r.get('dateline') or 0) for r in slb_replies),    default=0)
            last_contract_ts = max((int(c.get('dateline') or 0) for c in slb_contracts),  default=0)
            last_activity_at = max(last_reply_ts, last_contract_ts) or None

            if last_bump_nr is not None and curr_nr_thread is not None:
                slb_reply_gain = int(curr_nr_thread) - int(last_bump_nr)
            else:
                slb_reply_gain = None

            since_last_bump = {
                'tracked_replies':    len(slb_replies),
                'open_replies':       len(slb_open),
                'contracts_opened':   len(slb_contracts),
                'contracts_completed': slb_completed,
                'reply_gain':         slb_reply_gain,
                'last_activity_at':   last_activity_at,
                'has_activity':       len(slb_replies) > 0 or len(slb_contracts) > 0,
            }
        else:
            since_last_bump = {
                'tracked_replies': 0, 'open_replies': 0,
                'contracts_opened': 0, 'contracts_completed': 0,
                'reply_gain': None, 'last_activity_at': None, 'has_activity': False,
            }

        # period_summary (use period_replies, not reply_gain, for active/dead)
        recent_bumps   = sum(1 for b in bumps if int(b.get('ts', 0)) >= thirty_days_ago)
        active_periods = sum(
            1 for p in periods
            if p['period_replies'] > 0 or p['contracts_opened'] > 0
        )
        dead_periods = sum(
            1 for p in periods
            if not p['is_open'] and p['period_replies'] == 0 and p['contracts_opened'] == 0
        )
        closed_gains = [p['reply_gain'] for p in periods if not p['is_open'] and p['reply_gain'] is not None]
        avg_reply_gain = round(sum(closed_gains) / len(closed_gains), 1) if closed_gains else None

        period_summary = {
            'recent_bumps':   recent_bumps,
            'active_periods': active_periods,
            'dead_periods':   dead_periods,
            'skip_count':     skip_count,
            'avg_reply_gain': avg_reply_gain,
        }

        # bump_periods: all periods newest first (up to 20); skips list for expand drawer
        bump_periods  = list(reversed(periods))[:20]
        recent_skips  = tid_skips[:20]

        # recommendation
        is_closed      = bool(t.get('closed'))
        has_active_job = job is not None and bool(job.get('enabled'))
        has_activity   = since_last_bump['has_activity']

        if is_closed:
            recommendation = 'closed_thread'
        elif not has_active_job:
            recommendation = 'paused'
        elif waste >= 80 and not has_activity:
            recommendation = 'pause_candidate'
        elif waste >= 60:
            recommendation = 'review'
        elif has_activity and recent_bumps > 0 and active_periods >= dead_periods:
            recommendation = 'keep_bumping'
        else:
            recommendation = 'watch'

        if recommendation in ('review', 'pause_candidate'):
            needs_review_count += 1
        if has_activity:
            got_activity_count += 1
        open_replies_total += since_last_bump['open_replies']
        if recommendation in ('paused', 'closed_thread'):
            paused_count += 1

        offers.append({
            'tid': tid,
            'title': t.get('title', '')[:80],
            'closed': is_closed,
            'bump_count': bs.get('bump_count', 0),
            'skip_count': skip_count,
            'latest_bump_at': bs.get('latest_bump_at', 0),
            'reply_count': rs.get('total_replies', 0),
            'contracts_complete': cs.get('complete', 0),
            'contracts_active': cs.get('active', 0),
            'waste_score': waste,
            'has_active_job': has_active_job,
            'job_interval_h': job.get('interval_h', 0) if job else 0,
            'since_last_bump': since_last_bump,
            'period_summary': period_summary,
            'bump_periods': bump_periods,
            'recent_skips': recent_skips,
            'recommendation': recommendation,
        })

    rec_order = {'pause_candidate': 0, 'review': 1, 'watch': 2, 'keep_bumping': 3, 'paused': 4, 'closed_thread': 5}
    offers.sort(key=lambda x: (rec_order.get(x['recommendation'], 9), -x['bump_count']))

    waste_offers = [o for o in offers if o['waste_score'] >= 60]

    return {
        'offers': offers,
        'waste_warnings': waste_offers,
        'total_bumps': sum(o['bump_count'] for o in offers),
        'total_skips': sum(o['skip_count'] for o in offers),
        'summary': {
            'needs_review':    needs_review_count,
            'got_activity':    got_activity_count,
            'open_replies':    open_replies_total,
            'paused_or_closed': paused_count,
        },
    }


def _get_bump_log_for_tid(uid: str, tid: str) -> list[dict]:
    with _db() as conn:
        rows = conn.execute(
            "SELECT * FROM bump_log WHERE uid=? AND tid=? ORDER BY ts ASC",
            (uid, tid)
        ).fetchall()
        return [dict(r) for r in rows]


def get_promotion_detail(uid: str, tid: str) -> dict | None:
    now = int(time.time())

    all_log      = _get_bump_log_for_tid(uid, tid)
    all_threads  = _get_my_threads(uid)
    t            = next((x for x in all_threads if str(x.get('tid','')) == tid), {})
    bump_jobs    = _get_bump_jobs(uid)
    job          = next((j for j in bump_jobs if str(j.get('tid','')) == tid), None)
    tid_contracts = [c for c in _get_contracts(uid) if str(c.get('tid','')) == tid]
    tid_replies   = [r for r in _get_reply_queue(uid) if str(r.get('tid','')) == tid]
    completion_events = _get_completion_events(uid, 0)
    completion_by_cid = {str(e['cid']): int(e['detected_at']) for e in completion_events}

    if not t and not all_log:
        return None

    bumps     = [b for b in all_log if b.get('action') == 'bumped']
    all_skips = [b for b in all_log if b.get('action') != 'bumped']

    # Build complete period timeline
    periods = []
    for i, bump in enumerate(bumps):
        bump_ts   = int(bump.get('ts', 0))
        next_bump = bumps[i + 1] if i + 1 < len(bumps) else None
        end_ts    = int(next_bump['ts']) if next_bump else now
        is_open   = next_bump is None

        curr_nr = bump.get('numreplies')
        next_nr = (next_bump.get('numreplies') if next_bump else t.get('numreplies')) if not is_open else t.get('numreplies')
        reply_gain = (int(next_nr) - int(curr_nr)) if (curr_nr is not None and next_nr is not None) else None

        period_replies      = sum(1 for r in tid_replies if bump_ts <= int(r.get('dateline') or 0) < end_ts)
        period_open_replies = sum(1 for r in tid_replies if r.get('status') == 'unread' and bump_ts <= int(r.get('dateline') or 0) < end_ts)
        opened    = sum(1 for c in tid_contracts if bump_ts <= int(c.get('dateline') or 0) < end_ts)
        completed = sum(
            1 for c in tid_contracts
            if completion_by_cid.get(str(c.get('cid',''))) is not None
            and bump_ts <= completion_by_cid[str(c.get('cid',''))] < end_ts
        )
        period_skips = sorted([
            {'ts': int(s.get('ts', 0)), 'reason': s.get('reason', '') or ''}
            for s in all_skips
            if bump_ts < int(s.get('ts', 0)) < end_ts
        ], key=lambda x: x['ts'])

        periods.append({
            'bump_ts':             bump_ts,
            'end_ts':              end_ts,
            'is_open':             is_open,
            'reply_gain':          reply_gain,
            'period_replies':      period_replies,
            'period_open_replies': period_open_replies,
            'contracts_opened':    opened,
            'contracts_completed': completed,
            'period_skips':        period_skips,
        })

    # since_last_bump
    last_bump_ts   = int(bumps[-1]['ts']) if bumps else 0
    last_bump_nr   = bumps[-1].get('numreplies') if bumps else None
    curr_nr_thread = t.get('numreplies')

    if last_bump_ts:
        slb_replies   = [r for r in tid_replies if int(r.get('dateline') or 0) >= last_bump_ts]
        slb_open      = [r for r in slb_replies  if r.get('status') == 'unread']
        slb_contracts = [c for c in tid_contracts if int(c.get('dateline') or 0) >= last_bump_ts]
        slb_completed = sum(
            1 for c in tid_contracts
            if completion_by_cid.get(str(c.get('cid',''))) is not None
            and completion_by_cid[str(c.get('cid',''))] >= last_bump_ts
        )
        last_reply_ts    = max((int(r.get('dateline') or 0) for r in slb_replies),   default=0)
        last_contract_ts = max((int(c.get('dateline') or 0) for c in slb_contracts), default=0)
        slb_reply_gain   = (int(curr_nr_thread) - int(last_bump_nr)) if (last_bump_nr is not None and curr_nr_thread is not None) else None
        since_last_bump  = {
            'tracked_replies':     len(slb_replies),
            'open_replies':        len(slb_open),
            'contracts_opened':    len(slb_contracts),
            'contracts_completed': slb_completed,
            'reply_gain':          slb_reply_gain,
            'last_activity_at':    max(last_reply_ts, last_contract_ts) or None,
            'has_activity':        len(slb_replies) > 0 or len(slb_contracts) > 0,
        }
    else:
        since_last_bump = {
            'tracked_replies': 0, 'open_replies': 0, 'contracts_opened': 0,
            'contracts_completed': 0, 'reply_gain': None, 'last_activity_at': None, 'has_activity': False,
        }

    # All-time totals
    total_bumps      = len(bumps)
    total_skips      = len(all_skips)
    total_replies    = len(tid_replies)
    contracts_total    = len(tid_contracts)
    contracts_complete = sum(1 for c in tid_contracts if str(c.get('status_n','')) in STATUS_COMPLETE)
    contracts_active   = sum(1 for c in tid_contracts if str(c.get('status_n','')) in STATUS_ACTIVE)

    closed_gains   = [p['reply_gain'] for p in periods if not p['is_open'] and p['reply_gain'] is not None]
    avg_reply_gain = round(sum(closed_gains) / len(closed_gains), 1) if closed_gains else None
    active_periods = sum(1 for p in periods if p['period_replies'] > 0 or p['contracts_opened'] > 0)
    dead_periods   = sum(1 for p in periods if not p['is_open'] and p['period_replies'] == 0 and p['contracts_opened'] == 0)

    # Weekly breakdown: last 8 weeks (only weeks with any activity)
    today_start = now - (now % 86400)
    weekly = []
    for week_i in range(7, -1, -1):
        ws = today_start - week_i * 7 * 86400
        we = ws + 7 * 86400
        wk_bumps       = sum(1 for b in bumps     if ws <= int(b.get('ts', 0))          < we)
        wk_skips       = sum(1 for s in all_skips  if ws <= int(s.get('ts', 0))          < we)
        wk_replies     = sum(1 for r in tid_replies if ws <= int(r.get('dateline') or 0) < we)
        wk_contracts   = sum(1 for c in tid_contracts if ws <= int(c.get('dateline') or 0) < we)
        wk_completed   = sum(
            1 for c in tid_contracts
            if completion_by_cid.get(str(c.get('cid',''))) is not None
            and ws <= completion_by_cid[str(c.get('cid',''))] < we
        )
        weekly.append({
            'week_start':          ws,
            'bumps':               wk_bumps,
            'skips':               wk_skips,
            'replies':             wk_replies,
            'contracts_opened':    wk_contracts,
            'contracts_completed': wk_completed,
        })

    # Recommendation
    thirty_days_ago = now - 30 * 86400
    recent_bumps = sum(1 for b in bumps if int(b.get('ts', 0)) >= thirty_days_ago)
    waste = bump_waste_score(total_bumps, since_last_bump['open_replies'], contracts_complete, bumps_30d=recent_bumps)
    is_closed      = bool(t.get('closed'))
    has_active_job = job is not None and bool(job.get('enabled'))
    has_activity   = since_last_bump['has_activity']

    if is_closed:
        recommendation = 'closed_thread'
    elif not has_active_job:
        recommendation = 'paused'
    elif waste >= 80 and not has_activity:
        recommendation = 'pause_candidate'
    elif waste >= 60:
        recommendation = 'review'
    elif has_activity and recent_bumps > 0 and active_periods >= dead_periods:
        recommendation = 'keep_bumping'
    else:
        recommendation = 'watch'

    return {
        'tid':           tid,
        'title':         t.get('title', '')[:120],
        'closed':        is_closed,
        'has_active_job': has_active_job,
        'job_interval_h': job.get('interval_h', 0) if job else 0,
        'job_next_bump':  job.get('next_bump', 0)  if job else 0,
        'latest_bump_at': int(bumps[-1]['ts']) if bumps else 0,
        'recommendation': recommendation,
        'waste_score':    waste,
        'totals': {
            'bumps':             total_bumps,
            'skips':             total_skips,
            'replies':           total_replies,
            'contracts_total':   contracts_total,
            'contracts_complete': contracts_complete,
            'contracts_active':  contracts_active,
            'avg_reply_gain':    avg_reply_gain,
            'active_periods':    active_periods,
            'dead_periods':      dead_periods,
        },
        'since_last_bump': since_last_bump,
        'weekly':          weekly,
        'periods':         list(reversed(periods)),  # newest first
    }


def get_reports_weekly(uid: str, week_offset: int = 0) -> dict:
    now = int(time.time())
    week_end   = now - (week_offset * 7 * 86400)
    week_start = week_end - 7 * 86400

    contracts = _get_contracts(uid)
    replies   = _get_reply_queue(uid)
    threads   = _get_my_threads(uid)
    goals     = get_goals(uid)
    lead_metas = _get_lead_metas(uid)
    sla_hours = goals.get('reply_sla_hours', 24)
    _refresh_thread_update_observations(uid)

    week_contracts = [c for c in contracts if week_start <= int(c.get('dateline') or 0) <= week_end]
    week_replies   = [r for r in replies if week_start <= int(r.get('dateline') or 0) <= week_end]

    completed = [c for c in week_contracts if str(c.get('status_n','')) in STATUS_COMPLETE]
    new_contracts = week_contracts
    all_active = [c for c in contracts if str(c.get('status_n','')) in STATUS_ACTIVE]

    cstats = offer_stats_from_contracts(contracts, uid)
    best_tid = max(cstats, key=lambda t: cstats[t]['complete'], default=None)
    bstats   = bump_stats_from_log(_get_bump_log(uid, 500))
    worst_tid = max(bstats, key=lambda t: bstats[t]['bump_count'] - cstats.get(t, {}).get('complete', 0), default=None)

    cust_stats = customer_stats(contracts, uid)
    repeat_customers = sum(1 for s in cust_stats.values() if s['is_repeat'])

    # SLA breaches this week
    sla_count = 0
    for r in week_replies:
        rid = r.get('id')
        meta = lead_metas.get(rid, {})
        stage = meta.get('stage', 'new') if meta else 'new'
        age = int(r.get('dateline') or 0)
        if stage not in ('ignored', 'lost', 'won') and age and (now - age) > sla_hours * 3600:
            sla_count += 1

    tid_titles: dict[str, str] = {}
    week_updates: list[dict] = []
    with _db() as conn:
        for t in conn.execute("SELECT tid, title FROM my_threads WHERE uid=?", (uid,)).fetchall():
            tid_titles[str(t['tid'])] = t['title']
        try:
            rows = conn.execute(
                """SELECT * FROM merchant_thread_updates
                   WHERE uid=? AND COALESCE(NULLIF(posted_at,0), created_at) BETWEEN ? AND ?
                   ORDER BY COALESCE(NULLIF(posted_at,0), created_at) DESC""",
                (uid, week_start, week_end),
            ).fetchall()
            week_updates = [dict(row) for row in rows]
        except Exception:
            week_updates = []

    update_rows = []
    for item in week_updates[:12]:
        update_rows.append({
            'id': item.get('id'),
            'tid': str(item.get('tid') or ''),
            'title': tid_titles.get(str(item.get('tid') or ''), ''),
            'posted_at': item.get('posted_at') or item.get('created_at') or 0,
            'status': item.get('status', ''),
            'views_gained': _to_int(item.get('observed_views')) - _to_int(item.get('baseline_views')),
            'replies_gained': _to_int(item.get('observed_replies')) - _to_int(item.get('baseline_replies')),
            'posts_gained': _to_int(item.get('observed_posts')) - _to_int(item.get('baseline_posts')),
            'contracts_gained': _to_int(item.get('observed_contracts')) - _to_int(item.get('baseline_contracts')),
        })

    return {
        'week_start': week_start,
        'week_end': week_end,
        'completed_deals': len(completed),
        'new_contracts': len(new_contracts),
        'active_pipeline': len(all_active),
        'new_leads': len(week_replies),
        'repeat_customers': repeat_customers,
        'sla_breaches': sla_count,
        'best_offer': {
            'tid': best_tid,
            'title': tid_titles.get(best_tid or '', ''),
            'completed': cstats[best_tid]['complete'] if best_tid else 0,
        } if best_tid else None,
        'worst_spend_offer': {
            'tid': worst_tid,
            'title': tid_titles.get(worst_tid or '', ''),
            'bumps': bstats[worst_tid]['bump_count'] if worst_tid else 0,
        } if worst_tid else None,
        'needs_attention': len([t for t in threads
                                 if offer_health(t,
                                     cstats.get(str(t.get('tid','')), {}),
                                     {},
                                     bstats.get(str(t.get('tid','')), {})) == 'needs_attention']),
        'thread_updates': {
            'posted': sum(1 for item in week_updates if item.get('status') == 'posted'),
            'failed': sum(1 for item in week_updates if item.get('status') == 'failed'),
            'rows': update_rows,
        },
    }


def get_freshness(uid: str) -> dict:
    return _get_crawl_freshness(uid)
