// merchantFormat.js — Display helpers for Merchant HQ

export function relTime(ts) {
  if (!ts) return '—'
  const diff = Math.floor(Date.now() / 1000) - ts
  if (diff < 60)     return 'just now'
  if (diff < 3600)   return `${Math.floor(diff/60)}m ago`
  if (diff < 86400)  return `${Math.floor(diff/3600)}h ago`
  if (diff < 604800) return `${Math.floor(diff/86400)}d ago`
  return new Date(ts * 1000).toLocaleDateString()
}

export function absDate(ts) {
  if (!ts) return '—'
  return new Date(ts * 1000).toLocaleDateString(undefined, {month:'short', day:'numeric', year:'numeric'})
}

export function bucketLabel(bucket) {
  const map = {
    awaiting_approval:  'Awaiting Approval',
    active_fulfillment: 'Active',
    completed:          'Completed',
    cancelled:          'Cancelled',
    disputed:           'Disputed',
    expired:            'Expired',
    other:              'Other',
  }
  return map[bucket] || bucket
}

export function bucketColor(bucket) {
  if (bucket === 'completed')         return 'var(--green)'
  if (bucket === 'active_fulfillment')return 'var(--acc)'
  if (bucket === 'awaiting_approval') return 'var(--yellow)'
  if (bucket === 'disputed')          return 'var(--red)'
  if (bucket === 'cancelled' || bucket === 'expired')
                                      return 'var(--dim)'
  return 'var(--sub)'
}

export function contractStageLabel(stage) {
  const map = {
    needs_review:            'Needs Review',
    waiting_on_approval:     'Waiting on Approval',
    active:                  'Active',
    waiting_on_counterparty: 'Waiting on Counterparty',
    needs_rating:            'Needs Rating',
    completed:               'Completed',
    disputed:                'Disputed',
    cancelled:               'Cancelled',
    expired:                 'Expired',
    problem:                 'Problem',
  }
  return map[stage] || stage || '—'
}

export function contractStageColor(stage) {
  if (stage === 'needs_review')            return 'var(--yellow)'
  if (stage === 'waiting_on_approval')     return 'var(--yellow)'
  if (stage === 'active')                  return 'var(--acc)'
  if (stage === 'waiting_on_counterparty') return 'var(--acc)'
  if (stage === 'needs_rating')            return 'var(--blue)'
  if (stage === 'completed')               return 'var(--green)'
  if (stage === 'disputed')                return 'var(--red)'
  if (stage === 'cancelled')               return 'var(--dim)'
  if (stage === 'expired')                 return 'var(--dim)'
  if (stage === 'problem')                 return 'var(--red)'
  return 'var(--sub)'
}

export function healthLabel(h) {
  const map = {
    needs_attention: 'Needs Reply',
    wasting_spend:   'Bump Waste',
    healthy:         'Active',
    stale:           'Stale',
    new:             'New Thread',
  }
  return map[h] || h
}

export function healthColor(h) {
  if (h === 'needs_attention') return 'var(--yellow)'
  if (h === 'wasting_spend')   return 'var(--orange, #f90)'
  if (h === 'healthy')         return 'var(--green)'
  if (h === 'stale')           return 'var(--dim)'
  return 'var(--sub)'
}

export function stageLabel(s) {
  const map = {
    new:              'New Reply',
    qualified:        'Interested',
    follow_up:        'Follow Up',
    contract_opened:  'Contract Open',
    won:              'Completed',
    lost:             'No Deal',
    ignored:          'Ignored',
  }
  return map[s] || s
}

export function stageColor(s) {
  if (s === 'won')              return 'var(--green)'
  if (s === 'lost')             return 'var(--dim)'
  if (s === 'ignored')          return 'var(--dim)'
  if (s === 'contract_opened')  return 'var(--acc)'
  if (s === 'qualified')        return 'var(--yellow)'
  if (s === 'follow_up')        return 'var(--yellow)'
  return 'var(--sub)'
}

export function severityColor(s) {
  if (s === 'high')   return 'var(--red)'
  if (s === 'medium') return 'var(--yellow)'
  return 'var(--dim)'
}

export function contractTerms(deal) {
  const ip = (deal.iprice || '').toString().trim()
  const ic = (deal.icurrency || '').toString().trim()
  const op = (deal.oprice || '').toString().trim()
  const oc = (deal.ocurrency || '').toString().trim()
  const parts = []
  if (ip && ip !== '0') parts.push(`${ip}${ic ? ` ${ic}` : ''}`)
  if (op && op !== '0') parts.push(`${op}${oc ? ` ${oc}` : ''}`)
  return parts.join(' / ') || 'terms not recorded'
}

export function parseTags(tagsJson) {
  if (!tagsJson) return []
  try { return JSON.parse(tagsJson) } catch { return [] }
}

export function serializeTags(tags) {
  return JSON.stringify(tags.filter(Boolean))
}
