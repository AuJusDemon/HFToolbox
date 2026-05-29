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

function ClickChip({ label, value, color, tab, setTab, small }) {
  return (
    <button
      className="btn"
      style={{
        flex: 1, minWidth: 0, textAlign: 'left',
        padding: small ? '6px 8px' : '8px 10px',
        display: 'block',
      }}
      onClick={() => setTab(tab)}
    >
      <div style={{ fontSize: 9, color: 'var(--dim)', fontFamily: 'var(--mono)', marginBottom: 2 }}>{label}</div>
      <div style={{
        fontSize: small ? 15 : 20, fontWeight: 700,
        color: color || 'var(--sub)', fontFamily: 'var(--mono)',
      }}>{value}</div>
    </button>
  )
}

function ActionRow({ item, setTab }) {
  const tab = ACTION_TAB[item.type]
  return (
    <button
      className="btn"
      style={{
        display: 'flex', alignItems: 'center', gap: 8, width: '100%',
        padding: '7px 10px', marginBottom: 3, textAlign: 'left',
        borderLeft: `3px solid ${severityColor(item.severity)}`,
      }}
      onClick={() => tab && setTab(tab)}
    >
      <span style={{
        fontSize: 12, fontFamily: 'var(--mono)',
        color: severityColor(item.severity), minWidth: 20,
      }}>
        {item.count}
      </span>
      <span style={{ fontSize: 11, color: 'var(--text)', flex: 1 }}>{item.label}</span>
      {tab && (
        <span style={{ fontSize: 9, color: 'var(--dim)', fontFamily: 'var(--mono)', flexShrink: 0 }}>
          {tab} →
        </span>
      )}
    </button>
  )
}

function PipelineBar({ byStage }) {
  const ACTIVE = ['new', 'qualified', 'follow_up', 'contract_opened']
  const total = ACTIVE.reduce((s, k) => s + (byStage[k] || 0), 0)
  if (!total) return null
  return (
    <div style={{ marginTop: 12, paddingTop: 10, borderTop: '1px solid var(--b2)' }}>
      <div style={{ fontSize: 9, color: 'var(--dim)', fontFamily: 'var(--mono)', marginBottom: 5 }}>
        PIPELINE BY STAGE
      </div>
      <div style={{ display: 'flex', height: 6, overflow: 'hidden', gap: 1 }}>
        {ACTIVE.map(s => {
          const cnt = byStage[s] || 0
          if (!cnt) return null
          return (
            <div
              key={s}
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

function RecentRow({ c }) {
  const name = c.cp_username || (c.cp_uid ? `UID ${c.cp_uid}` : '?')
  return (
    <div style={{
      display: 'flex', gap: 8, alignItems: 'center',
      padding: '6px 0', borderBottom: '1px solid var(--b2)',
    }}>
      <a
        href={`/dashboard/contracts/${c.cid}`}
        style={{ fontSize: 11, fontFamily: 'var(--mono)', color: 'var(--acc)', flexShrink: 0 }}
      >
        #{c.cid}
      </a>
      <span style={{ fontSize: 11, color: 'var(--sub)', flexShrink: 0, fontFamily: 'var(--mono)' }}>
        {name}
      </span>
      <span style={{
        fontSize: 10, color: 'var(--dim)', flex: 1, minWidth: 0,
        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
      }}>
        {c.product || '—'}
      </span>
      <span style={{ fontSize: 9, fontFamily: 'var(--mono)', color: bucketColor(c.bucket), flexShrink: 0 }}>
        {bucketLabel(c.bucket)}
      </span>
      <span style={{ fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)', flexShrink: 0 }}>
        {relTime(c.dateline)}
      </span>
    </div>
  )
}

function BuyerRow({ c, setTab }) {
  return (
    <button
      className="btn"
      style={{
        display: 'flex', alignItems: 'center', gap: 8, width: '100%',
        padding: '6px 8px', marginBottom: 3, textAlign: 'left',
      }}
      onClick={() => setTab('customers')}
    >
      <span style={{
        fontSize: 12, fontFamily: 'var(--mono)', color: 'var(--text)',
        flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
      }}>
        {c.username || `UID ${c.uid}`}
      </span>
      {c.is_repeat && (
        <span style={{ fontSize: 9, color: 'var(--green)', fontFamily: 'var(--mono)', flexShrink: 0 }}>
          REPEAT
        </span>
      )}
      <span style={{ fontSize: 13, fontFamily: 'var(--mono)', color: 'var(--green)', flexShrink: 0, fontWeight: 700 }}>
        {c.complete}
      </span>
      {c.active > 0 && (
        <span style={{ fontSize: 11, fontFamily: 'var(--mono)', color: 'var(--yellow)', flexShrink: 0 }}>
          +{c.active}
        </span>
      )}
    </button>
  )
}

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
    action_queue    = [],
    today           = {},
    week            = {},
    totals          = {},
    pipeline        = {},
    recent_contracts = [],
    top_customers   = [],
  } = data

  const slaBreaches   = pipeline.sla_breaches ?? 0
  const pipelineTotal = pipeline.total ?? 0

  return (
    <div>
      <div style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
        gap: 12,
      }}>

        {/* Status */}
        <div className="card">
          <div className="card-head">Status</div>
          <div className="card-body" style={{ padding: '8px 10px' }}>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6, marginBottom: 8 }}>
              <ClickChip
                label="ACTIVE DEALS" value={today.active_contracts ?? 0}
                color="var(--yellow)" tab="deals" setTab={setTab}
              />
              <ClickChip
                label="PIPELINE LEADS" value={pipelineTotal}
                color="var(--acc)" tab="pipeline" setTab={setTab}
              />
              <ClickChip
                label="SLA BREACHES" value={slaBreaches}
                color={slaBreaches > 0 ? 'var(--red)' : 'var(--green)'}
                tab="pipeline" setTab={setTab}
              />
              <ClickChip
                label="DONE THIS WEEK" value={week.completed_deals ?? 0}
                color="var(--green)" tab="deals" setTab={setTab}
              />
            </div>
            <div style={{ display: 'flex', gap: 6 }}>
              <ClickChip
                label="TOTAL" value={totals.total_contracts ?? 0}
                tab="deals" setTab={setTab} small
              />
              <ClickChip
                label="COMPLETED" value={totals.completed_contracts ?? 0}
                color="var(--green)" tab="deals" setTab={setTab} small
              />
              <ClickChip
                label="OFFERS" value={totals.tracked_offers ?? 0}
                tab="offers" setTab={setTab} small
              />
            </div>
          </div>
        </div>

        {/* Needs Attention */}
        <div className="card">
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

        {/* Recent Activity */}
        <div className="card">
          <div className="card-head">
            <span>Recent Activity</span>
            <button
              className="btn"
              style={{ fontSize: 9, padding: '2px 8px' }}
              onClick={() => setTab('deals')}
            >
              All Deals
            </button>
          </div>
          <div className="card-body" style={{ padding: '8px 10px' }}>
            {recent_contracts.length === 0
              ? <div style={{ color: 'var(--dim)', fontSize: 12 }}>No contract history yet.</div>
              : recent_contracts.map(c => <RecentRow key={c.cid} c={c} />)
            }
          </div>
        </div>

        {/* Top Buyers */}
        <div className="card">
          <div className="card-head">
            <span>Top Buyers</span>
            <button
              className="btn"
              style={{ fontSize: 9, padding: '2px 8px' }}
              onClick={() => setTab('customers')}
            >
              All Customers
            </button>
          </div>
          <div className="card-body" style={{ padding: '8px 10px' }}>
            {top_customers.length === 0
              ? <div style={{ color: 'var(--dim)', fontSize: 12 }}>No customer history yet.</div>
              : top_customers.map(c => <BuyerRow key={c.uid} c={c} setTab={setTab} />)
            }
          </div>
        </div>

      </div>
    </div>
  )
}
