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
    replies          = [r for r in _get_reply_queue(uid) if str(r.get('tid','')) in marketplace_tids]
    bump_logs        = _get_bump_log(uid, 200)
    goals            = get_goals(uid)
    sla_hours        = goals.get('reply_sla_hours', 24)
    lead_group_metas = get_all_lead_group_metas(uid)

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

    # Today/this week counts (UTC midnight)
    today_start = now - (now % 86400)
    week_start  = now - 7 * 86400
    completed_today = sum(
        1 for c in contracts
        if str(c.get('status_n','')) in STATUS_COMPLETE
        and int(c.get('dateline') or 0) >= today_start
    )
    completed_week = sum(
        1 for c in contracts
        if str(c.get('status_n','')) in STATUS_COMPLETE
        and int(c.get('dateline') or 0) >= week_start
    )
    new_leads_today = sum(
        1 for r in replies
        if int(r.get('dateline') or 0) >= today_start
    )

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

    # Pipeline stage breakdown from lead group metas (already fetched)
    pipeline_by_stage: dict[str, int] = {}
    for meta in lead_group_metas.values():
        s = meta.get('stage', 'new')
        pipeline_by_stage[s] = pipeline_by_stage.get(s, 0) + 1

    # Top customers by completed deal count
    cust_stats_map = customer_stats(contracts, uid)
    top_cp_pairs = sorted(
        cust_stats_map.items(),
        key=lambda x: (-x[1]['complete'], -(x[1]['last_deal_at'] or 0))
    )[:5]

    # Recent contracts - already sorted DESC by dateline from DB
    recent_slice = contracts[:5]

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
            'total': len(lead_group_metas),
            'sla_breaches': sla_breaches,
        },
        'recent_contracts': recent_contracts,
        'top_customers': top_customers_out,
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
    waste  = bump_waste_score(bs.get('bump_count',0), rs.get('unread_replies',0), cs.get('complete',0))

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

    return {
        'leads': leads,
        'summary': {
            'by_stage': stage_counts,
            'sla_breaches': sla_total,
            'total': len(leads),
        },
        'sla_hours': sla_hours,
    }


def get_deals(uid: str, bucket_filter: str | None = None) -> list[dict]:
    contracts = _get_contracts(uid)
    buyer_uids = list({counterparty_uid(c, uid) for c in contracts if counterparty_uid(c, uid)})
    names = _get_usernames(buyer_uids)

    # tid -> title from my_threads
    with _db() as conn:
        tid_rows = conn.execute(
            "SELECT tid, title FROM my_threads WHERE uid=?", (uid,)
        ).fetchall()
    tid_titles: dict[str, str] = {str(r['tid']): r['title'] for r in tid_rows}
    # Also check tid_titles cache table
    with _db() as conn:
        try:
            title_rows = conn.execute("SELECT tid, title FROM tid_titles").fetchall()
            for tr in title_rows:
                tid_titles.setdefault(str(tr['tid']), tr['title'])
        except Exception:
            pass

    result = []
    for c in contracts:
        bucket = contract_bucket(str(c.get('status_n', '')), int(c.get('dateline') or 0))
        if bucket_filter and bucket != bucket_filter:
            continue
        cp = counterparty_uid(c, uid)
        tid = str(c.get('tid', ''))
        result.append({
            'cid': c.get('cid', ''),
            'status_n': c.get('status_n', ''),
            'bucket': bucket,
            'counterparty_uid': cp,
            'counterparty_username': names.get(cp, ''),
            'tid': tid,
            'thread_title': tid_titles.get(tid, ''),
            'dateline': c.get('dateline', 0),
            'iproduct': c.get('iproduct', ''),
            'oproduct': c.get('oproduct', ''),
            'iprice': c.get('iprice', ''),
            'icurrency': c.get('icurrency', ''),
            'oprice': c.get('oprice', ''),
            'ocurrency': c.get('ocurrency', ''),
            'brating': c.get('brating', ''),
            'inituid': c.get('inituid', ''),
            'otheruid': c.get('otheruid', ''),
        })

    result.sort(key=lambda x: -(x['dateline'] or 0))
    return result


def get_customers(uid: str) -> list[dict]:
    contracts = _get_contracts(uid)
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
    threads   = _get_my_threads(uid)
    bump_jobs = _get_bump_jobs(uid)
    bump_logs = _get_bump_log(uid, 1000)
    contracts = _get_contracts(uid)
    replies   = _get_reply_queue(uid)

    bstats = bump_stats_from_log(bump_logs)
    rstats = reply_stats_from_queue(replies)
    cstats = offer_stats_from_contracts(contracts, uid)

    thread_map = {str(t.get('tid','')): t for t in threads}
    job_map    = {str(j.get('tid','')): j for j in bump_jobs}

    offers = []
    all_tids = set(bstats.keys()) | set(job_map.keys())
    for tid in all_tids:
        bs = bstats.get(tid, {})
        rs = rstats.get(tid, {})
        cs = cstats.get(tid, {})
        t  = thread_map.get(tid, {})
        job = job_map.get(tid)
        waste = bump_waste_score(
            bs.get('bump_count', 0),
            rs.get('unread_replies', 0),
            cs.get('complete', 0),
        )
        offers.append({
            'tid': tid,
            'title': t.get('title', '')[:80],
            'closed': bool(t.get('closed')),
            'bump_count': bs.get('bump_count', 0),
            'skip_count': bs.get('skip_count', 0),
            'latest_bump_at': bs.get('latest_bump_at', 0),
            'reply_count': rs.get('total_replies', 0),
            'unread_replies': rs.get('unread_replies', 0),
            'contracts_complete': cs.get('complete', 0),
            'contracts_active': cs.get('active', 0),
            'waste_score': waste,
            'has_active_job': job is not None and bool(job.get('enabled')),
            'job_interval_h': job.get('interval_h', 0) if job else 0,
        })

    offers.sort(key=lambda x: -x['bump_count'])

    waste_offers = [o for o in offers if o['waste_score'] >= 60]

    return {
        'offers': offers,
        'waste_warnings': waste_offers,
        'total_bumps': sum(o['bump_count'] for o in offers),
        'total_skips': sum(o['skip_count'] for o in offers),
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
