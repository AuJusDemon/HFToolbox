import { useEffect, useState } from 'react'
import { api } from '../api.js'
import {
  severityColor, stageLabel, stageColor,
  bucketLabel, bucketColor, relTime,
} from './merchantFormat.js'

const ACTION_TAB = {
  sla_breach:        'pipeline',
  awaiting_approval: 'deals',
  unread_replies:    'pipeline',
  active_contracts:  'deals',
  followup_due:      'pipeline',
  bump_waste:        'promotion',
}

// ── Stat chip (clickable, compact) ──────────────────────────────────────────
function Chip({ label, value, color, tab, setTab }) {
  return (
    <button
      className="btn"
      style={{ flex: '1 1 0', minWidth: 80, textAlign: 'left', padding: '7px 10px', display: 'block' }}
      onClick={() => setTab(tab)}
    >
      <div style={{ fontSize: 9, color: 'var(--dim)', fontFamily: 'var(--mono)', marginBottom: 1 }}>{label}</div>
      <div style={{ fontSize: 22, fontWeight: 700, color: color || 'var(--sub)', fontFamily: 'var(--mono)', lineHeight: 1.1 }}>{value}</div>
    </button>
  )
}

// ── Action item row (clickable) ──────────────────────────────────────────────
function ActionRow({ item, setTab }) {
  const tab = ACTION_TAB[item.type]
  return (
    <button
      className="btn"
      style={{
        display: 'flex', alignItems: 'center', gap: 10, width: '100%',
        padding: '7px 10px', marginBottom: 3, textAlign: 'left',
        borderLeft: `3px solid ${severityColor(item.severity)}`,
      }}
      onClick={() => tab && setTab(tab)}
    >
      <span style={{ fontSize: 13, fontFamily: 'var(--mono)', color: severityColor(item.severity), minWidth: 22, fontWeight: 700 }}>
        {item.count}
      </span>
      <span style={{ fontSize: 11, color: 'var(--text)', flex: 1 }}>{item.label}</span>
      {tab && <span style={{ fontSize: 9, color: 'var(--dim)', fontFamily: 'var(--mono)', flexShrink: 0 }}>{tab} →</span>}
    </button>
  )
}

// ── Pipeline stage bar ───────────────────────────────────────────────────────
function PipelineBar({ byStage }) {
  const ACTIVE = ['new', 'qualified', 'follow_up', 'contract_opened']
  const total = ACTIVE.reduce((s, k) => s + (byStage[k] || 0), 0)
  if (!total) return null
  return (
    <div style={{ marginTop: 10, paddingTop: 10, borderTop: '1px solid var(--b2)' }}>
      <div style={{ fontSize: 9, color: 'var(--dim)', fontFamily: 'var(--mono)', marginBottom: 5 }}>PIPELINE BY STAGE</div>
      <div style={{ display: 'flex', height: 6, overflow: 'hidden', gap: 1 }}>
        {ACTIVE.map(s => {
          const cnt = byStage[s] || 0
          if (!cnt) return null
          return (
            <div key={s}
              style={{ width: `${(cnt / total * 100).toFixed(1)}%`, background: stageColor(s), minWidth: 4 }}
              title={`${stageLabel(s)}: ${cnt}`}
            />
          )
        })}
      </div>
      <div style={{ display: 'flex', gap: 10, marginTop: 5, flexWrap: 'wrap' }}>
        {ACTIVE.filter(s => byStage[s]).map(s => (
          <span key={s} style={{ fontSize: 9, color: stageColor(s), fontFamily: 'var(--mono)' }}>
            {stageLabel(s)} {byStage[s]}
          </span>
        ))}
      </div>
    </div>
  )
}

// ── Recent contract row ──────────────────────────────────────────────────────
function RecentRow({ c }) {
  const name = c.cp_username || (c.cp_uid ? `UID ${c.cp_uid}` : '?')
  return (
    <div style={{
      display: 'flex', gap: 8, alignItems: 'center',
      padding: '5px 0', borderBottom: '1px solid var(--b2)',
    }}>
      <a href={`/dashboard/contracts/${c.cid}`}
         style={{ fontSize: 10, fontFamily: 'var(--mono)', color: 'var(--acc)', flexShrink: 0 }}>
        #{c.cid}
      </a>
      <span style={{ fontSize: 11, color: 'var(--sub)', flexShrink: 0, fontFamily: 'var(--mono)' }}>{name}</span>
      <span style={{
        fontSize: 10, color: 'var(--dim)', flex: 1, minWidth: 0,
        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
      }}>{c.product || '—'}</span>
      <span style={{ fontSize: 9, fontFamily: 'var(--mono)', color: bucketColor(c.bucket), flexShrink: 0 }}>
        {bucketLabel(c.bucket)}
      </span>
      <span style={{ fontSize: 9, color: 'var(--dim)', fontFamily: 'var(--mono)', flexShrink: 0 }}>
        {relTime(c.dateline)}
      </span>
    </div>
  )
}

// ── Top buyer row ────────────────────────────────────────────────────────────
function BuyerRow({ c, setTab }) {
  return (
    <button
      className="btn"
      style={{ display: 'flex', alignItems: 'center', gap: 8, width: '100%', padding: '6px 8px', marginBottom: 3, textAlign: 'left' }}
      onClick={() => setTab('customers')}
    >
      <span style={{
        fontSize: 12, fontFamily: 'var(--mono)', color: 'var(--text)',
        flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
      }}>
        {c.username || `UID ${c.uid}`}
      </span>
      {c.is_repeat && (
        <span style={{ fontSize: 9, color: 'var(--green)', fontFamily: 'var(--mono)', flexShrink: 0 }}>REPEAT</span>
      )}
      <span style={{ fontSize: 14, fontFamily: 'var(--mono)', color: 'var(--green)', flexShrink: 0, fontWeight: 700 }}>
        {c.complete}
      </span>
      {c.active > 0 && (
        <span style={{ fontSize: 11, fontFamily: 'var(--mono)', color: 'var(--yellow)', flexShrink: 0 }}>+{c.active}</span>
      )}
    </button>
  )
}

// ── 7-day bar chart ──────────────────────────────────────────────────────────
function WeekChart({ dailyDone }) {
  if (!dailyDone || dailyDone.length < 7) return null
  const max = Math.max(...dailyDone, 1)
  const total = dailyDone.reduce((a, b) => a + b, 0)
  const labels = ['6d', '5d', '4d', '3d', '2d', 'Yest', 'Today']

  return (
    <div>
      <div style={{ fontSize: 9, color: 'var(--dim)', fontFamily: 'var(--mono)', marginBottom: 8 }}>
        COMPLETED DEALS — LAST 7 DAYS
        <span style={{ marginLeft: 10, color: 'var(--green)' }}>{total} total</span>
      </div>
      <div style={{ display: 'flex', gap: 4, alignItems: 'flex-end', height: 72 }}>
        {dailyDone.map((count, i) => {
          const isToday = i === 6
          const barH = count === 0 ? 2 : Math.max((count / max) * 58, 6)
          return (
            <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 3, height: '100%', justifyContent: 'flex-end' }}>
              {count > 0 && (
                <span style={{ fontSize: 9, color: isToday ? 'var(--green)' : 'var(--acc)', fontFamily: 'var(--mono)', fontWeight: 700 }}>
                  {count}
                </span>
              )}
              <div style={{
                width: '100%', height: barH,
                background: isToday ? 'var(--green)' : 'var(--acc)',
                opacity: count === 0 ? 0.15 : (isToday ? 1 : 0.75),
              }} />
            </div>
          )
        })}
      </div>
      <div style={{ display: 'flex', gap: 4, marginTop: 5 }}>
        {labels.map((l, i) => (
          <div key={i} style={{ flex: 1, textAlign: 'center', fontSize: 8, color: 'var(--dim)', fontFamily: 'var(--mono)' }}>
            {l}
          </div>
        ))}
      </div>
    </div>
  )
}

// ── Main component ───────────────────────────────────────────────────────────
export default function MerchantOverview({ setTab }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get('/api/merchant/overview')
      .then(d => { setData(d); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  if (loading) return <div className="empty"><div className="spin" /></div>
  if (!data)   return <div className="empty" style={{ color: 'var(--red)' }}>Failed to load overview</div>

  const {
    action_queue      = [],
    today             = {},
    week              = {},
    totals            = {},
    pipeline          = {},
    recent_contracts  = [],
    top_customers     = [],
    daily_completions = [],
  } = data

  const slaBreaches   = pipeline.sla_breaches ?? 0
  const pipelineTotal = pipeline.total ?? 0

  return (
    <div>

      {/* Stat strip */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 12, flexWrap: 'wrap' }}>
        <Chip label="ACTIVE DEALS"   value={today.active_contracts ?? 0} color="var(--yellow)" tab="deals"    setTab={setTab} />
        <Chip label="PIPELINE LEADS" value={pipelineTotal}               color="var(--acc)"    tab="pipeline" setTab={setTab} />
        <Chip label="SLA BREACHES"   value={slaBreaches}
          color={slaBreaches > 0 ? 'var(--red)' : 'var(--green)'}
          tab="pipeline" setTab={setTab} />
        <Chip label="DONE THIS WEEK" value={week.completed_deals ?? 0} color="var(--green)" tab="deals"   setTab={setTab} />
        <Chip label="TOTAL"          value={totals.total_contracts ?? 0}    tab="deals"   setTab={setTab} />
        <Chip label="COMPLETED"      value={totals.completed_contracts ?? 0} color="var(--green)" tab="deals" setTab={setTab} />
        <Chip label="OFFERS"         value={totals.tracked_offers ?? 0}     tab="offers"  setTab={setTab} />
      </div>

      {/* Row 1: Needs Attention | Recent Activity */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 12, alignItems: 'flex-start' }}>

        <div className="card" style={{ flex: '1 1 0', minWidth: 0 }}>
          <div className="card-head">
            <span>Needs Attention</span>
            {action_queue.length === 0 && (
              <span style={{ fontSize: 10, color: 'var(--green)', fontFamily: 'var(--mono)' }}>all clear</span>
            )}
          </div>
          <div className="card-body" style={{ padding: '8px 10px' }}>
            {action_queue.length === 0
              ? <div style={{ color: 'var(--dim)', fontSize: 12 }}>Nothing urgent right now.</div>
              : action_queue.map((item, i) => <ActionRow key={i} item={item} setTab={setTab} />)
            }
            <PipelineBar byStage={pipeline.by_stage || {}} />
          </div>
        </div>

        <div className="card" style={{ flex: '1 1 0', minWidth: 0 }}>
          <div className="card-head">
            <span>Recent Activity</span>
            <button className="btn" style={{ fontSize: 9, padding: '2px 8px' }} onClick={() => setTab('deals')}>All Deals</button>
          </div>
          <div className="card-body" style={{ padding: '8px 10px' }}>
            {recent_contracts.length === 0
              ? <div style={{ color: 'var(--dim)', fontSize: 12 }}>No contract history yet.</div>
              : recent_contracts.map(c => <RecentRow key={c.cid} c={c} />)
            }
          </div>
        </div>

      </div>

      {/* Row 2: Top Buyers | 7-day chart */}
      <div style={{ display: 'flex', gap: 12, alignItems: 'flex-start' }}>

        <div className="card" style={{ flex: '1 1 0', minWidth: 0 }}>
          <div className="card-head">
            <span>Top Buyers</span>
            <button className="btn" style={{ fontSize: 9, padding: '2px 8px' }} onClick={() => setTab('customers')}>All Customers</button>
          </div>
          <div className="card-body" style={{ padding: '8px 10px' }}>
            {top_customers.length === 0
              ? <div style={{ color: 'var(--dim)', fontSize: 12 }}>No customers on your threads yet.</div>
              : top_customers.map(c => <BuyerRow key={c.uid} c={c} setTab={setTab} />)
            }
          </div>
        </div>

        <div className="card" style={{ flex: '1 1 0', minWidth: 0 }}>
          <div className="card-head">Weekly Activity</div>
          <div className="card-body" style={{ padding: '8px 10px' }}>
            <WeekChart dailyDone={daily_completions} />
            {daily_completions.every(n => n === 0) && (
              <div style={{ color: 'var(--dim)', fontSize: 12 }}>No completed deals in the last 7 days.</div>
            )}
          </div>
        </div>

      </div>

    </div>
  )
}
