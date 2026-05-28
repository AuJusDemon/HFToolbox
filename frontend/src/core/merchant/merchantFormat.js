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
    declined:           'Declined',
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
  if (bucket === 'cancelled' || bucket === 'declined' || bucket === 'expired')
                                      return 'var(--dim)'
  return 'var(--sub)'
}

export function healthLabel(h) {
  const map = {
    needs_attention: 'Needs Attention',
    wasting_spend:   'Wasting Spend',
    healthy:         'Healthy',
    stale:           'Stale',
    new:             'New',
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
    new:              'New',
    qualified:        'Qualified',
    follow_up:        'Follow-Up',
    contract_opened:  'Contract Opened',
    won:              'Won',
    lost:             'Lost',
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
