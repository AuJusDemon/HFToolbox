"""
modules/merchant/service.py — Joins existing DB tables into seller objects.

No HF API calls. All data comes from tables already populated by:
  - bytes/contracts crawler (contracts_history, bytes_history)
  - posting module (my_threads, reply_queue, scheduled_threads)
  - autobump module (bump_jobs, bump_log)
  - uid/tid caches (uid_usernames, tid_titles)
  - merchant local tables (merchant_leads, merchant_customers, merchant_offers)
"""

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
    counterparty_uid,
    STATUS_ACTIVE,
    STATUS_COMPLETE,
    STATUS_AWAITING,
    STATUS_LOST,
    STATUS_FULFILLMENT,
    _AGE_EXPIRED_S,
)
from modules.merchant.merchant_db import (
    get_all_offer_meta,
    get_customer_meta,
    get_goals,
    get_all_lead_group_metas,
    get_all_contract_workflows,
)


# ── Marketplace FID whitelist ──────────────────────────────────────────────────
# Only threads in HF Marketplace sections are treated as seller offers.
MARKETPLACE_FIDS: frozenset[str] = frozenset({
    # Bazaar
    '163', '402', '186', '205', '217', '111',
    # Premium Marketplace
    '107', '374', '299', '136', '182', '218',
    # Services Marketplace
    '145', '263', '106', '219', '171', '308',
    # Auxiliary Marketplace
    '44', '176', '291', '404', '339', '255', '225',
})


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

def get_overview(uid: str) -> dict:
    now              = int(time.time())
    marketplace_tids = _get_marketplace_tids(uid)
    contracts        = _get_contracts(uid)
    all_threads      = _get_my_threads(uid)
    threads          = [t for t in all_threads if str(t.get('tid','')) in marketplace_tids]
    # TIDs the user owns - used to filter seller-side contracts (excludes threads user bought on)
    own_thread_tids  = {str(t.get('tid','')) for t in all_threads} - {''}

    replies          = [r for r in _get_reply_queue(uid) if str(r.get('tid','')) in marketplace_tids]
    bump_logs        = _get_bump_log(uid, 200)
    goals            = get_goals(uid)
    sla_hours        = goals.get('reply_sla_hours', 24)
    lead_group_metas = {
        k: v for k, v in get_all_lead_group_metas(uid).items()
        if k[1] in marketplace_tids
    }

    def _old_awaiting(c: dict) -> bool:
        dl = int(c.get('dateline') or 0)
        return str(c.get('status_n','')) == '1' and dl and (now - dl) > _AGE_EXPIRED_S

    unread_replies   = [r for r in replies if r.get('status') == 'unread']
    active_contracts = [c for c in contracts
                        if str(c.get('status_n','')) in STATUS_FULFILLMENT
                        or (str(c.get('status_n','')) == '1' and not _old_awaiting(c))]
    awaiting         = [c for c in contracts
                        if str(c.get('status_n','')) == '1' and not _old_awaiting(c)]

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
        if u
    })
    name_cache = _get_usernames(all_lookup_uids) if all_lookup_uids else {}

    recent_contracts = []
    for c in recent_slice:
        cp = counterparty_uid(c, uid)
        recent_contracts.append({
            'cid': c.get('cid', ''),
            'cp_uid': cp,
            'cp_username': name_cache.get(cp, ''),
            'bucket': contract_bucket(str(c.get('status_n', '')), int(c.get('dateline') or 0)),
            'product': (c.get('iproduct') or c.get('oproduct') or '').strip(),
            'dateline': c.get('dateline', 0),
            'tid': str(c.get('tid', '')),
        })

    top_customers_out = [{
        'uid': cp,
        'username': name_cache.get(cp, ''),
        'complete': stats['complete'],
        'active': stats['active'],
        'is_repeat': stats['is_repeat'],
        'last_deal_at': stats['last_deal_at'],
    } for cp, stats in top_cp_pairs]

    return {
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
        'daily_completions': daily_completions,
    }


def get_offers(uid: str, status_filter: str | None = None, sort: str = 'health') -> list[dict]:
    marketplace_tids = _get_marketplace_tids(uid)
    threads   = [t for t in _get_my_threads(uid) if str(t.get('tid','')) in marketplace_tids]
    contracts = _get_contracts(uid)
    replies   = _get_reply_queue(uid)
    bump_logs = _get_bump_log(uid, 500)
    goals     = get_goals(uid)
    offer_meta = get_all_offer_meta(uid)

    cstats_by_tid = offer_stats_from_contracts(contracts, uid)
    rstats_by_tid = reply_stats_from_queue(replies)
    bstats_by_tid = bump_stats_from_log(bump_logs)
    sla_hours = goals.get('reply_sla_hours', 24)

    result = []
    for t in threads:
        tid = str(t.get('tid', ''))
        meta = offer_meta.get(tid, {})

        if meta.get('hidden'):
            continue

        cs = cstats_by_tid.get(tid, {})
        rs = rstats_by_tid.get(tid, {})
        bs = bstats_by_tid.get(tid, {})

        health = offer_health(t, cs, rs, bs, sla_hours)

        if status_filter:
            if status_filter == 'active'          and health not in ('healthy', 'needs_attention', 'new'):
                continue
            if status_filter == 'needs_attention' and health != 'needs_attention':
                continue
            if status_filter == 'wasting_spend'   and health != 'wasting_spend':
                continue
            if status_filter == 'stale'           and health != 'stale':
                continue
            if status_filter == 'no_contracts'    and cs.get('total', 0) > 0:
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
            'closed': bool(t.get('closed')),
            'lastpost': t.get('lastpost', 0),
            'numreplies': t.get('numreplies', 0),
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
            'health': health,
            'category': meta.get('category', ''),
            'status': meta.get('status', 'active'),
        })

    health_order = {'needs_attention': 0, 'wasting_spend': 1, 'healthy': 2, 'new': 3, 'stale': 4}
    if sort == 'health':
        result.sort(key=lambda x: (health_order.get(x['health'], 5), -(x['lastpost'] or 0)))
    elif sort == 'activity':
        result.sort(key=lambda x: -(x['lastpost'] or 0))
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
    health = offer_health(thread, cs, rs, bs, goals.get('reply_sla_hours', 24))
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
        'closed': bool(thread.get('closed')),
        'lastpost': thread.get('lastpost', 0),
        'numreplies': thread.get('numreplies', 0),
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

    # tid -> title from my_threads + tid_titles cache
    with _db() as conn:
        tid_rows = conn.execute(
            "SELECT tid, title FROM my_threads WHERE uid=?", (uid,)
        ).fetchall()
    tid_titles: dict[str, str] = {str(r['tid']): r['title'] for r in tid_rows}
    with _db() as conn:
        try:
            title_rows = conn.execute("SELECT tid, title FROM tid_titles").fetchall()
            for tr in title_rows:
                tid_titles.setdefault(str(tr['tid']), tr['title'])
        except Exception:
            pass

    result = []
    for c in contracts:
        status_n = str(c.get('status_n', ''))
        dateline = int(c.get('dateline') or 0)
        cid      = str(c.get('cid', ''))
        inituid  = str(c.get('inituid', '') or '')
        otheruid = str(c.get('otheruid', '') or '')
        wf       = workflows.get(cid, {})
        completed_side_at = wf.get('completed_side_at')

        # Map to queue stage
        if status_n == '1':
            if dateline and (now - dateline) > _AGE_EXPIRED_S:
                stage = 'problem'
            elif otheruid == uid:
                # Current user is the counterparty - we need to approve
                stage = 'needs_review'
            else:
                stage = 'waiting_on_approval'
        elif status_n == '5':
            stage = 'waiting_on_counterparty' if completed_side_at else 'active'
        elif status_n == '6':
            stage = 'completed'
        else:
            # status 2,3,4,7,8 or unknown
            stage = 'problem'

        bucket = contract_bucket(status_n, dateline)
        if bucket_filter and bucket != bucket_filter:
            continue

        cp  = counterparty_uid(c, uid)
        tid = str(c.get('tid', ''))
        result.append({
            'cid':                    cid,
            'status_n':               status_n,
            'bucket':                 bucket,
            'stage':                  stage,
            'counterparty_uid':       cp,
            'counterparty_username':  names.get(cp, ''),
            'tid':                    tid,
            'thread_title':           tid_titles.get(tid, ''),
            'dateline':               c.get('dateline', 0),
            'iproduct':               c.get('iproduct', ''),
            'oproduct':               c.get('oproduct', ''),
            'iprice':                 c.get('iprice', ''),
            'icurrency':              c.get('icurrency', ''),
            'oprice':                 c.get('oprice', ''),
            'ocurrency':              c.get('ocurrency', ''),
            'brating':                c.get('brating', ''),
            'inituid':                inituid,
            'otheruid':               otheruid,
            'completed_side_at':      completed_side_at,
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
    with _db() as conn:
        for t in conn.execute("SELECT tid, title FROM my_threads WHERE uid=?", (uid,)).fetchall():
            tid_titles[str(t['tid'])] = t['title']

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
    }


def get_freshness(uid: str) -> dict:
    return _get_crawl_freshness(uid)
