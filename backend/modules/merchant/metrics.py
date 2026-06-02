"""
modules/merchant/metrics.py — Pure aggregation over existing DB tables.

All functions take lists/dicts already fetched by service.py.
No DB calls here — keeps the router/service easy to test and reason about.
"""

import time

# ── Contract status codes ──────────────────────────────────────────────────────
# Confirmed from HF API + empirical DB data:
#   0=awaiting approval (live API returned this for an incoming pending contract;
#     treat identically to 1 — use istatus/ostatus for per-party approval state)
#   1=awaiting approval (but HF shows "Expired" if dateline > 90 days old)
#   2=cancelled, 3=unknown/voided, 4=cancelled (HF website confirms),
#   5=active deal, 6=complete, 7=disputed, 8=expired
STATUS_ACTIVE      = {'0', '1', '5'}
STATUS_COMPLETE    = {'6'}
STATUS_LOST        = {'2', '3', '4', '7', '8'}
STATUS_AWAITING    = {'0', '1'}
STATUS_FULFILLMENT = {'5'}
STATUS_DISPUTE     = {'7'}

_AGE_EXPIRED_S = 90 * 86400  # HF stops updating status 0/1 after ~90 days → "Expired"

_PENDING = frozenset(('0', '1'))


def contract_bucket(status_n: str, dateline: int = 0) -> str:
    s = str(status_n or '')
    now = int(time.time())
    if s in _PENDING:
        if dateline and (now - int(dateline)) > _AGE_EXPIRED_S:
            return 'expired'
        return 'awaiting_approval'
    if s == '5':  return 'active_fulfillment'
    if s == '6':  return 'completed'
    if s in ('2', '3', '4'):  return 'cancelled'
    if s == '7':  return 'disputed'
    if s == '8':  return 'expired'
    return 'other'


def classify_contract_stage(
    status_n: str,
    dateline: int,
    inituid: str,
    otheruid: str,
    my_uid: str,
    completed_side: bool,
    now: int,
    istatus: str = '',
    ostatus: str = '',
) -> str:
    """Map contract fields to a Seller HQ queue stage string."""
    s = str(status_n or '')
    if s in _PENDING:
        if dateline and (now - int(dateline)) > _AGE_EXPIRED_S:
            return 'problem'
        is_init  = (str(inituid)  == str(my_uid))
        is_other = (str(otheruid) == str(my_uid))
        my_flag    = istatus if is_init else (ostatus if is_other else '')
        their_flag = ostatus if is_init else (istatus if is_other else '')
        if my_flag == '0':
            return 'needs_review'
        if their_flag == '0':
            return 'waiting_on_approval'
        # Fallback for rows ingested before istatus/ostatus were stored
        return 'needs_review' if is_other else 'waiting_on_approval'
    if s == '5':
        return 'waiting_on_counterparty' if completed_side else 'active'
    if s == '6':
        return 'completed'
    return 'problem'


def counterparty_uid(contract: dict, my_uid: str) -> str:
    init = str(contract.get('inituid') or '')
    other = str(contract.get('otheruid') or '')
    return other if init == my_uid else init


def offer_stats_from_contracts(contracts: list, my_uid: str) -> dict:
    """
    Group contracts by tid, return per-tid stats dict.
    Returns: {tid: {total, complete, active, lost, last_contract_at, counterparties}}
    """
    from collections import defaultdict
    result: dict[str, dict] = defaultdict(lambda: {
        'total': 0, 'complete': 0, 'active': 0, 'lost': 0,
        'awaiting': 0, 'disputed': 0,
        'last_contract_at': 0, 'counterparties': set(),
    })
    now = int(time.time())
    for c in contracts:
        tid = str(c.get('tid') or '')
        if not tid:
            continue
        s = str(c.get('status_n') or '')
        dl = int(c.get('dateline') or 0)
        r = result[tid]
        r['total'] += 1
        # Treat stale pending (status 0/1) as expired — HF stops updating after ~90 days
        s_is_old_awaiting = (s in _PENDING and dl and (now - dl) > _AGE_EXPIRED_S)
        if s in STATUS_COMPLETE:
            r['complete'] += 1
        elif s in STATUS_FULFILLMENT:
            r['active'] += 1
        elif s in _PENDING and not s_is_old_awaiting:
            r['awaiting'] += 1
        if s in STATUS_DISPUTE:     r['disputed'] += 1
        if s in STATUS_LOST or s_is_old_awaiting:
            r['lost'] += 1
        if dl > r['last_contract_at']:
            r['last_contract_at'] = dl
        cp = counterparty_uid(c, my_uid)
        if cp:
            r['counterparties'].add(cp)
    # Convert sets to counts
    for r in result.values():
        r['unique_buyers'] = len(r['counterparties'])
        del r['counterparties']
    return dict(result)


def reply_stats_from_queue(replies: list) -> dict:
    """
    Group replies by tid.
    Returns: {tid: {total_replies, unread_replies, latest_reply_at}}
    """
    from collections import defaultdict
    result: dict[str, dict] = defaultdict(lambda: {
        'total_replies': 0, 'unread_replies': 0, 'latest_reply_at': 0,
    })
    for r in replies:
        tid = str(r.get('tid') or '')
        if not tid:
            continue
        s = str(r.get('status') or '')
        d = int(r.get('dateline') or 0)
        result[tid]['total_replies'] += 1
        if s == 'unread':
            result[tid]['unread_replies'] += 1
        if d > result[tid]['latest_reply_at']:
            result[tid]['latest_reply_at'] = d
    return dict(result)


def bump_stats_from_log(bump_logs: list) -> dict:
    """
    Group bump log entries by tid.
    Returns: {tid: {bump_count, skip_count, latest_bump_at, bumps_7d, bumps_30d}}
    """
    from collections import defaultdict
    now        = int(time.time())
    cutoff_7d  = now - 7  * 86400
    cutoff_30d = now - 30 * 86400
    result: dict[str, dict] = defaultdict(lambda: {
        'bump_count': 0, 'skip_count': 0, 'latest_bump_at': 0,
        'bumps_7d': 0, 'bumps_30d': 0,
    })
    for entry in bump_logs:
        tid = str(entry.get('tid') or '')
        if not tid:
            continue
        action = str(entry.get('action') or '')
        ts = int(entry.get('ts') or 0)
        if action == 'bumped':
            result[tid]['bump_count'] += 1
            if ts >= cutoff_7d:
                result[tid]['bumps_7d'] += 1
            if ts >= cutoff_30d:
                result[tid]['bumps_30d'] += 1
            if ts > result[tid]['latest_bump_at']:
                result[tid]['latest_bump_at'] = ts
        elif action in ('skipped', 'skip'):
            result[tid]['skip_count'] += 1
    return dict(result)


def bump_waste_score(bump_count: int, unread_replies: int, completed_contracts: int,
                     bumps_30d: int | None = None) -> int:
    """
    0-100 score: higher = more wasteful promotion spend.
    Uses bumps_30d when provided to avoid penalizing old active threads.
    """
    effective = bumps_30d if bumps_30d is not None else bump_count
    if effective == 0:
        return 0
    results = unread_replies + (completed_contracts * 3)
    if results == 0:
        return min(100, 40 + effective * 2)
    ratio = effective / max(results, 1)
    return min(100, int(ratio * 15))


def offer_health(thread: dict, cstats: dict, rstats: dict, bstats: dict,
                 sla_hours: int = 24) -> str:
    """
    Compute offer health label:
    needs_attention | wasting_spend | stale | healthy | new
    """
    now = int(time.time())
    unread = rstats.get('unread_replies', 0)
    complete = cstats.get('complete', 0)
    active = cstats.get('active', 0)
    bumps = bstats.get('bump_count', 0)
    last_reply = rstats.get('latest_reply_at', 0)
    last_contract = cstats.get('last_contract_at', 0)
    last_activity = max(
        int(thread.get('lastpost') or 0),
        last_reply,
        last_contract,
    )
    age_days = (now - last_activity) / 86400 if last_activity else 999

    if unread > 0 and (now - last_reply) > sla_hours * 3600:
        return 'needs_attention'
    if unread > 0:
        return 'needs_attention'
    if bumps >= 5 and unread == 0 and complete == 0 and active == 0:
        return 'wasting_spend'
    if age_days > 14 and complete == 0:
        return 'stale'
    if complete > 0 or active > 0:
        return 'healthy'
    if cstats.get('total', 0) == 0 and rstats.get('total_replies', 0) == 0:
        return 'new'
    return 'healthy'


def customer_stats(contracts: list, my_uid: str) -> dict:
    """
    Group all contracts by counterparty UID.
    Returns: {counterparty_uid: {complete, active, lost, total, last_deal_at, products}}
    """
    from collections import defaultdict
    result: dict[str, dict] = defaultdict(lambda: {
        'complete': 0, 'active': 0, 'lost': 0, 'total': 0,
        'last_deal_at': 0, 'products': [],
    })
    for c in contracts:
        cp = counterparty_uid(c, my_uid)
        if not cp:
            continue
        s = str(c.get('status_n') or '')
        r = result[cp]
        r['total'] += 1
        if s in STATUS_COMPLETE:
            r['complete'] += 1
        elif s in STATUS_ACTIVE:
            r['active'] += 1
        if s in STATUS_LOST:
            r['lost'] += 1
        dl = int(c.get('dateline') or 0)
        if dl > r['last_deal_at']:
            r['last_deal_at'] = dl
        for prod_field in ('iproduct', 'oproduct'):
            p = str(c.get(prod_field) or '').strip()
            trivial = {'', 'other', 'n/a', 'none', 'null'}
            if p.lower() not in trivial and p not in r['products']:
                r['products'].append(p)
    for r in result.values():
        r['products'] = r['products'][:5]
        r['is_repeat'] = r['complete'] >= 2
    return dict(result)


def pipeline_summary(replies: list, leads_meta: dict, contracts: list, my_uid: str,
                     sla_hours: int = 24) -> dict:
    """
    Build pipeline summary: count by stage, SLA breach count.
    leads_meta: {reply_id: merchant_lead_row}
    """
    from collections import defaultdict
    now = int(time.time())
    stages: dict[str, int] = defaultdict(int)
    sla_breaches = 0

    for r in replies:
        rid = r.get('id')
        meta = leads_meta.get(rid) or {}
        stage = meta.get('stage', 'new')
        stages[stage] += 1
        if stage in ('new', 'qualified'):
            age = now - int(r.get('dateline') or now)
            if age > sla_hours * 3600:
                sla_breaches += 1

    return {
        'by_stage': dict(stages),
        'sla_breaches': sla_breaches,
        'total': len(replies),
    }


def overview_action_queue(
    unread_replies: int,
    active_contracts: int,
    awaiting_contracts: int,
    sla_breaches: int,
    waste_warnings: int,
    followup_due: int,
) -> list:
    """Return ordered list of action items with severity."""
    items = []
    if sla_breaches:
        items.append({'type': 'sla_breach', 'count': sla_breaches,
                      'label': f'{sla_breaches} late repl{"ies" if sla_breaches>1 else "y"}',
                      'severity': 'high'})
    if awaiting_contracts:
        items.append({'type': 'awaiting_approval', 'count': awaiting_contracts,
                      'label': f'{awaiting_contracts} contract{"s" if awaiting_contracts>1 else ""} awaiting approval',
                      'severity': 'high'})
    if unread_replies:
        items.append({'type': 'unread_replies', 'count': unread_replies,
                      'label': f'{unread_replies} unread repl{"ies" if unread_replies>1 else "y"}',
                      'severity': 'medium'})
    if active_contracts:
        items.append({'type': 'active_contracts', 'count': active_contracts,
                      'label': f'{active_contracts} active contract{"s" if active_contracts>1 else ""} in progress',
                      'severity': 'medium'})
    if followup_due:
        items.append({'type': 'followup_due', 'count': followup_due,
                      'label': f'{followup_due} follow-up{"s" if followup_due>1 else ""} due',
                      'severity': 'medium'})
    if waste_warnings:
        items.append({'type': 'bump_waste', 'count': waste_warnings,
                      'label': f'{waste_warnings} bumped thread{"s" if waste_warnings>1 else ""} need{"" if waste_warnings>1 else "s"} review',
                      'severity': 'low'})
    return items
