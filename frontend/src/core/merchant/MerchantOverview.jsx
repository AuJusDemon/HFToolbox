import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { contractStageLabel, healthLabel, relTime } from './merchantFormat.js'

const WORKFLOW = [
  ['needs_review', 'Needs Review'],
  ['in_progress', 'Active'],
  ['waiting_on_counterparty', 'Waiting'],
  ['needs_rating', 'Needs Rating'],
  ['completed', 'Completed'],
  ['closed', 'Closed'],
]

function statusTone(stage) {
  if (stage === 'needs_review' || stage === 'waiting_on_approval' || stage === 'waiting_on_counterparty') return 'warn'
  if (stage === 'needs_rating') return 'info'
  if (stage === 'completed' || stage === 'active') return 'good'
  if (stage === 'disputed' || stage === 'problem') return 'bad'
  return ''
}

function Metric({ label, value, note, tone, onClick }) {
  return (
    <button type="button" onClick={onClick}>
      <span className="mhq-summary-label">{label}</span>
      <strong className="mhq-summary-value" style={{ color: tone }}>{value}</strong>
      <span className="mhq-summary-note">{note}</span>
    </button>
  )
}

function ActionRow({ item, onOpen }) {
  const buyer = item.cp_username || (item.cp_uid ? `UID ${item.cp_uid}` : 'Unknown buyer')
  const needsReview = item.type === 'needs_review'
  return (
    <div className="mhq-action-row">
      <span className={`mhq-status ${needsReview ? 'warn' : 'info'} mhq-action-kind`}>{needsReview ? 'Needs review' : 'Rating due'}</span>
      <span className="mhq-action-cid">#{item.cid}</span>
      <span className="mhq-action-buyer">{buyer}</span>
      <span className="mhq-action-product">{item.product || 'No product recorded'}</span>
      <span className="mhq-action-age">{relTime(item.dateline)}</span>
      <button className="btn btn-sm" onClick={() => onOpen(needsReview ? 'needs_review' : 'needs_rating')}>
        {needsReview ? 'Review' : 'Rate on HF'}
      </button>
    </div>
  )
}

function CompletionStrip({ daily = [] }) {
  const total = daily.reduce((sum, value) => sum + value, 0)
  const max = Math.max(...daily, 1)
  return (
    <div className="mhq-completion-strip">
      <span className="mhq-completion-total">{total}</span>
      <span className="mhq-table-meta">completed in 7 days</span>
      {total >= 3 && (
        <div className="mhq-completion-days" aria-label="Seven day completion activity">
          {daily.map((value, index) => (
            <span
              key={index}
              className="mhq-completion-day"
              title={`${value} completed`}
              style={{ height: `${Math.max(3, Math.round((value / max) * 32))}px`, background: value ? 'var(--green)' : 'var(--b2)' }}
            />
          ))}
        </div>
      )}
    </div>
  )
}

export default function MerchantOverview({ setTab, onGoToDeals }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  const load = () => api.get('/api/merchant/overview').then(setData).finally(() => setLoading(false))
  useEffect(() => { load() }, [])
  useEffect(() => {
    let last = null
    const poll = () => api.get('/api/merchant/freshness').then(fresh => {
      const next = JSON.stringify(fresh || {})
      if (last !== null && next !== last) load()
      last = next
    }).catch(() => {})
    const timer = setInterval(poll, 30000)
    return () => clearInterval(timer)
  }, [])

  if (loading) return <div className="empty"><div className="spin" /></div>
  if (!data) return <div className="mhq-empty" style={{ color: 'var(--red)' }}>The business summary could not be loaded.</div>

  const counts = data.contract_stage_counts || {}
  const rating = data.rating_summary || {}
  const actions = [
    ...(data.needs_review_items || []).map(item => ({ ...item, type: 'needs_review' })),
    ...(data.needs_rating_items || []).map(item => ({ ...item, type: 'needs_rating' })),
  ]
  const stageCounts = {
    ...counts,
    in_progress: (counts.waiting_on_approval || 0) + (counts.active || 0),
    closed: (counts.cancelled || 0) + (counts.expired || 0) + (counts.disputed || 0) + (counts.problem || 0),
  }
  const openDeals = stage => onGoToDeals?.(stage)
  const primaryActionStage = (counts.needs_review || 0) > 0
    ? 'needs_review'
    : (rating.needs_mine || 0) > 0
      ? 'needs_rating'
      : null

  return (
    <div className="mhq-shell">
      <div className="mhq-summary">
        <Metric label="Needs Action" value={data.needs_action || 0} note="replies, ratings, or contracts waiting on you" tone={(data.needs_action || 0) ? 'var(--red)' : 'var(--text)'} onClick={() => primaryActionStage ? openDeals(primaryActionStage) : setTab('pipeline')} />
        <Metric label="Active Contracts" value={data.active_pipeline || 0} note="open deals still moving" tone={(data.active_pipeline || 0) ? 'var(--yellow)' : 'var(--text)'} onClick={() => openDeals('in_progress')} />
        <Metric label="Completed This Week" value={data.week?.completed_deals || 0} note="contracts closed this week" tone="var(--green)" onClick={() => openDeals('completed')} />
        <Metric label="Ratings Due" value={rating.needs_mine || 0} note="completed contracts waiting for rating" tone={(rating.needs_mine || 0) ? 'var(--blue)' : 'var(--text)'} onClick={() => openDeals('needs_rating')} />
      </div>

      <section>
        <div className="mhq-section-head">
          <div><h3>Action Queue</h3><p>Start here. These rows need a review, rating, or reply before the rest of the dashboard matters.</p></div>
          <button className="btn btn-sm" onClick={() => openDeals(null)}>All Contracts</button>
        </div>
        {actions.length || data.pipeline?.sla_breaches ? (
          <div className="mhq-action-list">
            {actions.map(item => <ActionRow key={`${item.type}-${item.cid}`} item={item} onOpen={openDeals} />)}
            {(data.pipeline?.sla_breaches || 0) > 0 && (
              <div className="mhq-action-row">
                <span className="mhq-status bad mhq-action-kind">Late Reply</span><span className="mhq-action-cid">{data.pipeline.sla_breaches}</span>
                <span className="mhq-action-buyer">lead conversations</span><span className="mhq-action-product">Past your reply SLA</span><span className="mhq-action-age">overdue</span>
                <button className="btn btn-sm" onClick={() => setTab('pipeline')}>View Leads</button>
              </div>
            )}
          </div>
        ) : <div className="mhq-empty">Nothing is waiting on you right now. Check Sales Threads for stale bumps or Leads for older buyer messages.</div>}
      </section>

      <section className="mhq-section">
        <div className="mhq-section-head"><div><h3>Contract Workflow</h3><p>Jump to one contract state without digging through the full list.</p></div></div>
        <div className="mhq-workflow">
          {WORKFLOW.map(([key, label]) => (
            <button className="btn" key={key} onClick={() => openDeals(key)}>{label}<span className="mhq-workflow-count">{stageCounts[key] || 0}</span></button>
          ))}
        </div>
      </section>

      <div className="mhq-grid">
        <section>
          <div className="mhq-section-head"><div><h3>Recent Contract Activity</h3><p>Newest contracts, including normal rows that do not need work yet.</p></div></div>
          {(data.recent_contracts || []).length ? (
            <div className="mhq-table-wrap"><table className="mhq-table"><thead><tr><th>CID</th><th>Buyer</th><th>Product</th><th>Status</th><th>Created</th><th>Next Action</th></tr></thead><tbody>
              {data.recent_contracts.map(contract => {
                const actionable = ['needs_review', 'active', 'needs_rating'].includes(contract.stage)
                return <tr key={contract.cid}>
                  <td><span className="mhq-action-cid">#{contract.cid}</span></td>
                  <td>{contract.cp_username || `UID ${contract.cp_uid || 'unknown'}`}</td>
                  <td><span className="mhq-table-primary">{contract.product || 'No product recorded'}</span></td>
                  <td><span className={`mhq-status ${statusTone(contract.stage)}`}>{contractStageLabel(contract.stage)}</span></td>
                  <td>{relTime(contract.dateline)}</td>
                  <td><button className="btn btn-sm" onClick={() => openDeals(contract.stage)}>{actionable ? 'Open' : 'View'}</button></td>
                </tr>
              })}
            </tbody></table></div>
          ) : <div className="mhq-empty">No contract history has been indexed.</div>}
        </section>

        <section>
          <div className="mhq-section-head"><div><h3>Weekly Output</h3><p>Completed contracts detected each day this week.</p></div></div>
          <CompletionStrip daily={data.daily_completions || []} />
        </section>
      </div>

      <section className="mhq-section">
        <div className="mhq-section-head"><div><h3>Sales Thread Health</h3><p>Only threads with current seller work appear here. Older quiet threads stay in All Threads.</p></div><button className="btn btn-sm" onClick={() => setTab('offers')}>All Threads</button></div>
        {(data.thread_health || []).length ? <div className="mhq-health-list">
          {data.thread_health.map(thread => <button className="mhq-health-row" key={thread.tid} onClick={() => setTab('offers')}>
            <span><span className="mhq-health-title">{thread.title || `TID ${thread.tid}`}</span><span className="mhq-table-meta">{healthLabel(thread.health)}</span>{(thread.reasons || []).length > 0 && <span className="mhq-reason-list">{thread.reasons.map(reason => <b key={reason}>{reason}</b>)}</span>}</span>
            <span className="mhq-health-stat">{thread.unread_replies || 0} unread</span>
            <span className="mhq-health-stat">{thread.contracts_active || 0} active</span>
            <span className="mhq-health-stat">{thread.contracts_complete || 0} complete</span>
            <span className="mhq-health-stat">{thread.last_activity_at ? `Active ${relTime(thread.last_activity_at)}` : 'No activity'}</span>
          </button>)}
        </div> : <div className="mhq-empty">No indexed sales threads yet.</div>}
        {(data.archived_thread_count || 0) > 0 && <div className="mhq-table-meta">{data.archived_thread_count} stale thread{data.archived_thread_count === 1 ? '' : 's'} hidden from this queue. Open All Threads and use the Stale filter to review them.</div>}
      </section>
    </div>
  )
}
