import { useEffect, useState } from 'react'
import { api } from '../api.js'
import {
  contractStageLabel, contractStageColor,
  healthLabel, healthColor,
  relTime,
} from './merchantFormat.js'

// ── Stat tile ─────────────────────────────────────────────────────────────────
function StatTile({ label, value, sub, color, onClick }) {
  return (
    <button
      className="btn"
      style={{
        flex: '1 1 0', minWidth: 90, textAlign: 'left',
        padding: '10px 12px', display: 'block',
        borderLeft: `2px solid ${color || 'var(--b3)'}`,
      }}
      onClick={onClick}
    >
      <div style={{ fontSize: 8, color: 'var(--dim)', fontFamily: 'var(--mono)', letterSpacing: '.1em', textTransform: 'uppercase', marginBottom: 4 }}>
        {label}
      </div>
      <div style={{ fontSize: 26, fontWeight: 700, color: color || 'var(--text)', fontFamily: 'var(--mono)', lineHeight: 1 }}>
        {value ?? 0}
      </div>
      {sub && (
        <div style={{ fontSize: 9, color: 'var(--dim)', fontFamily: 'var(--mono)', marginTop: 3 }}>{sub}</div>
      )}
    </button>
  )
}

// ── Contract pipeline bar ─────────────────────────────────────────────────────
// Primary (actionable) stages only — terminal states shown separately below
const PIPELINE_STAGES = [
  { key: 'needs_review',            label: 'Needs Review' },
  { key: 'in_progress',             label: 'In Progress'  },
  { key: 'waiting_on_counterparty', label: 'Waiting'      },
  { key: 'needs_rating',            label: 'Needs Rating' },
  { key: 'completed',               label: 'Completed'    },
]

function pipelineStageColor(key) {
  if (key === 'in_progress') return 'var(--acc)'
  return contractStageColor(key)
}

function ContractPipeline({ stageCounts, onGoToDeals }) {
  const counts = {
    ...stageCounts,
    in_progress: (stageCounts.waiting_on_approval || 0) + (stageCounts.active || 0),
  }

  const pipelineTotal = PIPELINE_STAGES.reduce((s, st) => s + (counts[st.key] || 0), 0)
  const disputed  = stageCounts.disputed  || 0
  const cancelled = stageCounts.cancelled || 0
  const expired   = stageCounts.expired   || 0
  const problem   = stageCounts.problem   || 0

  if (!pipelineTotal && !disputed && !cancelled && !expired && !problem) {
    return <div style={{ fontSize: 12, color: 'var(--dim)' }}>No contract data yet.</div>
  }

  const hasTerminal = disputed > 0 || cancelled > 0 || expired > 0 || problem > 0

  return (
    <div>
      {/* Proportional bar — actionable stages only */}
      {pipelineTotal > 0 && (
        <>
          <div style={{ display: 'flex', height: 6, gap: 1, overflow: 'hidden', marginBottom: 10 }}>
            {PIPELINE_STAGES.map(({ key, label }) => {
              const cnt = counts[key] || 0
              if (!cnt) return null
              const color = pipelineStageColor(key)
              return (
                <div
                  key={key}
                  style={{ width: `${(cnt / pipelineTotal * 100).toFixed(1)}%`, background: color, minWidth: 4, cursor: 'pointer' }}
                  title={`${label}: ${cnt}`}
                  onClick={() => onGoToDeals(key)}
                />
              )
            })}
          </div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: hasTerminal ? 10 : 0 }}>
            {PIPELINE_STAGES.map(({ key, label }) => {
              const cnt = counts[key] || 0
              const color = pipelineStageColor(key)
              return (
                <button
                  key={key}
                  className="btn"
                  style={{ padding: '3px 8px', display: 'flex', alignItems: 'center', gap: 5 }}
                  onClick={() => onGoToDeals(key)}
                >
                  <span style={{ width: 7, height: 7, background: cnt ? color : 'var(--b3)', display: 'inline-block', flexShrink: 0 }} />
                  <span style={{ fontSize: 9, color: 'var(--dim)', fontFamily: 'var(--mono)' }}>{label}</span>
                  <span style={{ fontSize: 13, fontWeight: 700, color: cnt ? color : 'var(--b3)', fontFamily: 'var(--mono)' }}>{cnt}</span>
                </button>
              )
            })}
          </div>
        </>
      )}

      {/* Archive/outcome row — same button structure as primary, no opacity hack */}
      {hasTerminal && (
        <div style={{
          display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap',
          borderTop: pipelineTotal > 0 ? '1px solid var(--b2)' : undefined,
          paddingTop: pipelineTotal > 0 ? 8 : 0,
        }}>
          {disputed > 0 && (
            <button
              className="btn"
              style={{ padding: '3px 8px', display: 'flex', alignItems: 'center', gap: 5 }}
              onClick={() => onGoToDeals('disputed')}
            >
              <span style={{ width: 7, height: 7, background: 'var(--red)', display: 'inline-block', flexShrink: 0 }} />
              <span style={{ fontSize: 9, color: 'var(--red)', fontFamily: 'var(--mono)', fontWeight: 700 }}>DISPUTED</span>
              <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--red)', fontFamily: 'var(--mono)' }}>{disputed}</span>
            </button>
          )}
          {cancelled > 0 && (
            <button
              className="btn"
              style={{ padding: '3px 8px', display: 'flex', alignItems: 'center', gap: 5 }}
              onClick={() => onGoToDeals('cancelled')}
            >
              <span style={{ width: 7, height: 7, background: 'var(--dim)', display: 'inline-block', flexShrink: 0 }} />
              <span style={{ fontSize: 9, color: 'var(--dim)', fontFamily: 'var(--mono)' }}>Cancelled</span>
              <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--dim)', fontFamily: 'var(--mono)' }}>{cancelled}</span>
            </button>
          )}
          {expired > 0 && (
            <button
              className="btn"
              style={{ padding: '3px 8px', display: 'flex', alignItems: 'center', gap: 5 }}
              onClick={() => onGoToDeals('expired')}
            >
              <span style={{ width: 7, height: 7, background: 'var(--dim)', display: 'inline-block', flexShrink: 0 }} />
              <span style={{ fontSize: 9, color: 'var(--dim)', fontFamily: 'var(--mono)' }}>Expired</span>
              <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--dim)', fontFamily: 'var(--mono)' }}>{expired}</span>
            </button>
          )}
          {problem > 0 && (
            <button
              className="btn"
              style={{ padding: '3px 8px', display: 'flex', alignItems: 'center', gap: 5 }}
              onClick={() => onGoToDeals('problem')}
            >
              <span style={{ width: 7, height: 7, background: 'var(--dim)', display: 'inline-block', flexShrink: 0 }} />
              <span style={{ fontSize: 9, color: 'var(--dim)', fontFamily: 'var(--mono)' }}>Other</span>
              <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--dim)', fontFamily: 'var(--mono)' }}>{problem}</span>
            </button>
          )}
        </div>
      )}
    </div>
  )
}

// ── Action queue row ──────────────────────────────────────────────────────────
function ActionItem({ type, cid, cpUsername, cpUid, product, dateline }) {
  const name  = cpUsername || (cpUid ? `UID ${cpUid}` : '?')
  const color = type === 'needs_review' ? 'var(--yellow)' : 'var(--blue)'
  const badge = type === 'needs_review' ? 'REVIEW' : 'RATE'

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 8,
      padding: '7px 0', borderBottom: '1px solid var(--b2)',
    }}>
      <span style={{
        fontSize: 8, fontFamily: 'var(--mono)', color,
        padding: '1px 5px', border: `1px solid ${color}`,
        background: `${color}1a`, flexShrink: 0, letterSpacing: '.04em',
      }}>
        {badge}
      </span>
      <a
        href={`/dashboard/contracts/${cid}`}
        style={{ fontSize: 10, fontFamily: 'var(--mono)', color: 'var(--acc)', flexShrink: 0, textDecoration: 'none' }}
      >
        #{cid}
      </a>
      <span style={{ fontSize: 11, color: 'var(--sub)', flexShrink: 0, fontFamily: 'var(--mono)' }}>
        {name}
      </span>
      {product && (
        <span style={{ fontSize: 10, color: 'var(--dim)', flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {product}
        </span>
      )}
      <span style={{ fontSize: 9, color: 'var(--dim)', fontFamily: 'var(--mono)', flexShrink: 0 }}>
        {relTime(dateline)}
      </span>
      {type === 'needs_review' ? (
        <a
          href={`/dashboard/contracts/${cid}`}
          style={{ fontSize: 9, color: 'var(--yellow)', fontFamily: 'var(--mono)', flexShrink: 0, textDecoration: 'none', whiteSpace: 'nowrap' }}
        >
          Open →
        </a>
      ) : (
        <a
          href={`https://hackforums.net/contracts.php?action=view&cid=${cid}`}
          target="_blank"
          rel="noopener noreferrer"
          style={{ fontSize: 9, color: 'var(--blue)', fontFamily: 'var(--mono)', flexShrink: 0, textDecoration: 'none', whiteSpace: 'nowrap' }}
        >
          Rate on HF →
        </a>
      )}
    </div>
  )
}

// ── Rating bucket ─────────────────────────────────────────────────────────────
function RatingBucket({ label, count, color }) {
  return (
    <div style={{
      flex: 1, padding: '8px 10px',
      background: 'var(--bg)', border: '1px solid var(--b2)',
      borderLeft: `2px solid ${color}`,
    }}>
      <div style={{ fontSize: 8, color: 'var(--dim)', fontFamily: 'var(--mono)', letterSpacing: '.1em', textTransform: 'uppercase', marginBottom: 4 }}>
        {label}
      </div>
      <div style={{ fontSize: 22, fontWeight: 700, fontFamily: 'var(--mono)', color }}>{count}</div>
    </div>
  )
}

// ── Thread health row ─────────────────────────────────────────────────────────
function ThreadHealthRow({ t, setTab }) {
  const color = healthColor(t.health)
  return (
    <button
      className="btn"
      style={{ display: 'flex', alignItems: 'center', gap: 8, width: '100%', padding: '6px 8px', marginBottom: 3, textAlign: 'left' }}
      onClick={() => setTab('offers')}
    >
      <span style={{
        fontSize: 8, fontFamily: 'var(--mono)', color,
        padding: '1px 5px', border: `1px solid ${color}`,
        background: `${color}1a`, flexShrink: 0, letterSpacing: '.04em',
      }}>
        {healthLabel(t.health).toUpperCase()}
      </span>
      <span style={{ fontSize: 11, color: 'var(--text)', flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {t.title || `TID ${t.tid}`}
      </span>
      {t.unread_replies > 0 && (
        <span style={{ fontSize: 9, color: 'var(--yellow)', fontFamily: 'var(--mono)', flexShrink: 0 }}>
          {t.unread_replies} unread
        </span>
      )}
      {t.contracts_complete > 0 && (
        <span style={{ fontSize: 9, color: 'var(--green)', fontFamily: 'var(--mono)', flexShrink: 0 }}>
          {t.contracts_complete} done
        </span>
      )}
    </button>
  )
}

// ── 7-day bar chart ───────────────────────────────────────────────────────────
function WeekChart({ dailyDone }) {
  if (!dailyDone || dailyDone.length < 7) return null
  const max    = Math.max(...dailyDone, 1)
  const total  = dailyDone.reduce((a, b) => a + b, 0)
  const labels = ['6d', '5d', '4d', '3d', '2d', 'Yest', 'Today']

  return (
    <div>
      <div style={{ fontSize: 9, color: 'var(--dim)', fontFamily: 'var(--mono)', marginBottom: 8 }}>
        COMPLETED — LAST 7 DAYS
        <span style={{ marginLeft: 10, color: 'var(--green)' }}>{total} total</span>
      </div>
      <div style={{ display: 'flex', gap: 4, alignItems: 'flex-end', height: 64 }}>
        {dailyDone.map((count, i) => {
          const isToday = i === 6
          const barH = count === 0 ? 2 : Math.max((count / max) * 50, 6)
          return (
            <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 2, height: '100%', justifyContent: 'flex-end' }}>
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
      <div style={{ display: 'flex', gap: 4, marginTop: 4 }}>
        {labels.map((l, i) => (
          <div key={i} style={{ flex: 1, textAlign: 'center', fontSize: 8, color: 'var(--dim)', fontFamily: 'var(--mono)' }}>{l}</div>
        ))}
      </div>
    </div>
  )
}

// ── Recent movement row ───────────────────────────────────────────────────────
function MovementRow({ c }) {
  const name  = c.cp_username || (c.cp_uid ? `UID ${c.cp_uid}` : '?')
  const color = contractStageColor(c.stage)

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 8,
      padding: '5px 0', borderBottom: '1px solid var(--b2)',
    }}>
      <a
        href={`/dashboard/contracts/${c.cid}`}
        style={{ fontSize: 10, fontFamily: 'var(--mono)', color: 'var(--acc)', flexShrink: 0, textDecoration: 'none' }}
      >
        #{c.cid}
      </a>
      <span style={{ fontSize: 11, color: 'var(--sub)', flexShrink: 0, fontFamily: 'var(--mono)', minWidth: 80, maxWidth: 120, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {name}
      </span>
      <span style={{ fontSize: 10, color: 'var(--dim)', flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
        {c.product || '—'}
      </span>
      <span style={{
        fontSize: 8, fontFamily: 'var(--mono)', color,
        padding: '1px 5px', border: `1px solid ${color}`,
        background: `${color}1a`, flexShrink: 0, whiteSpace: 'nowrap',
      }}>
        {contractStageLabel(c.stage).toUpperCase()}
      </span>
      <span style={{ fontSize: 9, color: 'var(--dim)', fontFamily: 'var(--mono)', flexShrink: 0, whiteSpace: 'nowrap' }}>
        {relTime(c.dateline)}
      </span>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────
export default function MerchantOverview({ setTab, onGoToDeals }) {
  const [data, setData]       = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get('/api/merchant/overview')
      .then(d  => { setData(d); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  if (loading) return <div className="empty"><div className="spin" /></div>
  if (!data)   return <div className="empty" style={{ color: 'var(--red)' }}>Failed to load overview</div>

  const {
    today                     = {},
    week                      = {},
    pipeline                  = {},
    recent_contracts          = [],
    top_customers             = [],
    daily_completions         = [],
    contract_stage_counts     = {},
    rating_summary            = {},
    needs_review_items        = [],
    needs_rating_items        = [],
    thread_health             = [],
    needs_action              = 0,
    active_pipeline           = 0,
    threads_needing_attention = 0,
  } = data

  const pipelineTotal = pipeline.total        ?? 0
  const slaBreaches   = pipeline.sla_breaches ?? 0
  const needsMine          = rating_summary.needs_mine          ?? 0
  const waitingTheirs      = rating_summary.waiting_theirs      ?? 0
  const bothRated          = rating_summary.both_rated          ?? 0
  const receivedDataFresh  = rating_summary.received_data_fresh ?? false
  const receivedFetchedAt  = rating_summary.received_fetched_at ?? 0

  // Needs Review first (urgent — waiting for my approval), then Needs Rating
  const queueItems = [
    ...needs_review_items.map(r => ({ ...r, type: 'needs_review' })),
    ...needs_rating_items.map(r => ({ ...r, type: 'needs_rating' })),
  ]

  const queueOverflow = needs_action - queueItems.length

  // Fallback if onGoToDeals not provided (shouldn't happen but defensive)
  const goToDeals = onGoToDeals || ((s) => setTab('deals'))

  return (
    <div>

      {/* Stat row */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 12, flexWrap: 'wrap' }}>
        <StatTile
          label="Needs Action"
          value={needs_action}
          sub={needs_action > 0 ? 'contracts + replies' : 'all clear'}
          color={needs_action > 0 ? 'var(--red)' : 'var(--green)'}
          onClick={() => goToDeals('needs_review')}
        />
        <StatTile
          label="Active Pipeline"
          value={active_pipeline}
          sub="contracts in motion"
          color={active_pipeline > 0 ? 'var(--yellow)' : 'var(--dim)'}
          onClick={() => goToDeals('in_progress')}
        />
        <StatTile
          label="Done This Week"
          value={week.completed_deals ?? 0}
          color="var(--green)"
          onClick={() => goToDeals('completed')}
        />
        <StatTile
          label="Open Replies"
          value={pipelineTotal}
          sub={slaBreaches > 0 ? `${slaBreaches} past SLA` : undefined}
          color={slaBreaches > 0 ? 'var(--red)' : pipelineTotal > 0 ? 'var(--acc)' : 'var(--dim)'}
          onClick={() => setTab('pipeline')}
        />
        <StatTile
          label="Ratings Due"
          value={needsMine}
          sub="leave b-rating"
          color={needsMine > 0 ? 'var(--blue)' : 'var(--dim)'}
          onClick={() => goToDeals('needs_rating')}
        />
        <StatTile
          label="Thread Health"
          value={threads_needing_attention}
          sub={threads_needing_attention === 1 ? 'thread needs reply' : 'threads need reply'}
          color={threads_needing_attention > 0 ? 'var(--yellow)' : 'var(--dim)'}
          onClick={() => setTab('offers')}
        />
      </div>

      {/* Contract pipeline */}
      <div className="card" style={{ marginBottom: 12 }}>
        <div className="card-head">
          <span className="card-title">Contract Pipeline</span>
          <button className="btn" style={{ fontSize: 9, padding: '2px 8px' }} onClick={() => goToDeals(null)}>
            All Contracts
          </button>
        </div>
        <div className="card-body" style={{ padding: '10px 12px' }}>
          <ContractPipeline stageCounts={contract_stage_counts} onGoToDeals={goToDeals} />
        </div>
      </div>

      {/* Row: Action queue + Weekly chart */}
      <div className="mhq-overview-row">

        <div className="card">
          <div className="card-head">
            <span className="card-title">Action Queue</span>
            {queueItems.length > 0
              ? <span className="badge badge-yel">{queueItems.length}</span>
              : <span style={{ fontSize: 10, color: 'var(--green)', fontFamily: 'var(--mono)' }}>all clear</span>
            }
          </div>
          <div className="card-body" style={{ padding: '8px 12px' }}>
            {queueItems.length === 0 && slaBreaches === 0
              ? <div style={{ color: 'var(--dim)', fontSize: 12 }}>No urgent contracts.</div>
              : queueItems.map(item => (
                  <ActionItem
                    key={`${item.type}-${item.cid}`}
                    type={item.type}
                    cid={item.cid}
                    cpUsername={item.cp_username}
                    cpUid={item.cp_uid}
                    product={item.product}
                    dateline={item.dateline}
                  />
                ))
            }
            {slaBreaches > 0 && (
              <button
                className="btn"
                style={{ display: 'block', width: '100%', textAlign: 'left', padding: '7px 0', marginTop: queueItems.length > 0 ? 6 : 0, borderTop: queueItems.length > 0 ? '1px solid var(--b2)' : undefined }}
                onClick={() => setTab('pipeline')}
              >
                <span style={{ fontSize: 11, color: 'var(--red)', fontFamily: 'var(--mono)' }}>
                  {slaBreaches} repl{slaBreaches !== 1 ? 'ies' : 'y'} past SLA — View Replies →
                </span>
              </button>
            )}
            {queueOverflow > 0 && (
              <button
                className="btn"
                style={{ display: 'block', width: '100%', textAlign: 'left', padding: '6px 0', marginTop: 4, fontSize: 10, color: 'var(--dim)' }}
                onClick={() => goToDeals(null)}
              >
                +{queueOverflow} more — View All Contracts →
              </button>
            )}
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <span className="card-title">Weekly Completions</span>
          </div>
          <div className="card-body" style={{ padding: '10px 12px' }}>
            <WeekChart dailyDone={daily_completions} />
            {(!daily_completions.length || daily_completions.every(n => n === 0)) && (
              <div style={{ color: 'var(--dim)', fontSize: 12 }}>No completed contracts in the last 7 days.</div>
            )}
          </div>
        </div>

      </div>

      {/* Row: Rating status + Thread health */}
      <div className="mhq-overview-row">

        <div className="card">
          <div className="card-head">
            <span className="card-title">Rating Status</span>
          </div>
          <div className="card-body" style={{ padding: '10px 12px' }}>
            <div style={{ display: 'flex', gap: 6, marginBottom: (needsMine > 0 || !receivedDataFresh) ? 10 : 0 }}>
              <RatingBucket label="Needs My Rating" count={needsMine}     color={needsMine     > 0 ? 'var(--blue)'   : 'var(--dim)'} />
              <RatingBucket label="Waiting on Them" count={receivedDataFresh ? waitingTheirs : '?'} color={receivedDataFresh && waitingTheirs > 0 ? 'var(--yellow)' : 'var(--dim)'} />
              <RatingBucket label="Both Rated"      count={receivedDataFresh ? bothRated     : '?'} color={receivedDataFresh && bothRated     > 0 ? 'var(--green)'  : 'var(--dim)'} />
            </div>
            {!receivedDataFresh && (
              <div style={{
                fontSize: 10, color: 'var(--yellow)', fontFamily: 'var(--mono)',
                padding: '5px 8px', background: 'var(--yellow2)', marginBottom: needsMine > 0 ? 10 : 0,
              }}>
                Received-rating data not yet synced. Click Sync Ratings in the Contracts tab to update.
              </div>
            )}
            {needsMine > 0 && needs_rating_items.length > 0 && (
              <>
                <div style={{ fontSize: 9, color: 'var(--dim)', fontFamily: 'var(--mono)', marginBottom: 6, letterSpacing: '.08em' }}>PENDING RATINGS</div>
                {needs_rating_items.map(r => {
                  const name = r.cp_username || (r.cp_uid ? `UID ${r.cp_uid}` : '?')
                  return (
                    <div key={r.cid} style={{ display: 'flex', alignItems: 'center', gap: 8, padding: '5px 0', borderBottom: '1px solid var(--b2)' }}>
                      <span style={{ fontSize: 10, fontFamily: 'var(--mono)', color: 'var(--acc)', flexShrink: 0 }}>#{r.cid}</span>
                      <span style={{ fontSize: 11, color: 'var(--sub)', flexShrink: 0, fontFamily: 'var(--mono)' }}>{name}</span>
                      {r.product && (
                        <span style={{ fontSize: 10, color: 'var(--dim)', flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {r.product}
                        </span>
                      )}
                      <a
                        href={`https://hackforums.net/contracts.php?action=view&cid=${r.cid}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        style={{ fontSize: 9, color: 'var(--blue)', fontFamily: 'var(--mono)', flexShrink: 0, textDecoration: 'none', whiteSpace: 'nowrap' }}
                      >
                        Leave Rating →
                      </a>
                    </div>
                  )
                })}
              </>
            )}
          </div>
        </div>

        <div className="card">
          <div className="card-head">
            <span className="card-title">Sales Thread Health</span>
            <button className="btn" style={{ fontSize: 9, padding: '2px 8px' }} onClick={() => setTab('offers')}>
              All Threads
            </button>
          </div>
          <div className="card-body" style={{ padding: '8px 10px' }}>
            {thread_health.length === 0
              ? <div style={{ color: 'var(--dim)', fontSize: 12 }}>No marketplace threads yet.</div>
              : thread_health.map(t => <ThreadHealthRow key={t.tid} t={t} setTab={setTab} />)
            }
          </div>
        </div>

      </div>

      {/* Recent contracts */}
      <div className="card">
        <div className="card-head">
          <span className="card-title">Recent Contracts</span>
          <button className="btn" style={{ fontSize: 9, padding: '2px 8px' }} onClick={() => goToDeals(null)}>
            All Contracts
          </button>
        </div>
        <div className="card-body" style={{ padding: '8px 12px' }}>
          {recent_contracts.length === 0
            ? <div style={{ color: 'var(--dim)', fontSize: 12 }}>No contract history yet.</div>
            : recent_contracts.map(c => <MovementRow key={c.cid} c={c} />)
          }
        </div>
      </div>

    </div>
  )
}
