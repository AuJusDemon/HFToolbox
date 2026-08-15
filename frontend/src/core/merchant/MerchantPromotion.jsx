import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { relTime, absDate } from './merchantFormat.js'
import BumpDetail, { REC_LABEL, REC_COLOR, periodSummary } from './BumpDetail.jsx'

// ── Compact list card ─────────────────────────────────────────────────────────
function BumpCard({ offer, onSelect }) {
  const rec      = offer.recommendation
  const recColor = REC_COLOR[rec] || 'var(--dim)'
  const slb      = offer.since_last_bump || {}
  const periods  = offer.bump_periods    || []
  const skips    = offer.recent_skips    || []

  const statusLabel = offer.closed ? 'CLOSED' : offer.has_active_job ? 'ACTIVE' : 'PAUSED'
  const statusColor = offer.closed ? 'var(--red)' : offer.has_active_job ? 'var(--green)' : 'var(--dim)'

  // Compact timeline: last 3 entries, bumps + skips interleaved
  const timeline = [
    ...periods.map(p => ({ ...p, _type: 'bump' })),
    ...skips.map(s => ({ ...s, bump_ts: s.ts, _type: 'skip' })),
  ].sort((a, b) => b.bump_ts - a.bump_ts).slice(0, 3)

  return (
    <div
      className="mhq-offer-card"
      style={{
        background:'var(--s1)', padding:'11px 14px', cursor:'pointer',
        borderLeft: `3px solid ${recColor}`,
      }}
      onClick={() => onSelect(offer.tid)}
    >
      {/* Header */}
      <div style={{display:'flex', justifyContent:'space-between', alignItems:'flex-start', gap:8, marginBottom:4}}>
        <div style={{
          fontFamily:'var(--mono)', fontSize:12, color:'var(--text)',
          flex:1, minWidth:0, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap',
        }}>
          {offer.title || `TID ${offer.tid}`}
        </div>
        <div style={{display:'flex', gap:5, alignItems:'center', flexShrink:0}}>
          {slb.open_replies > 0 && (
            <span style={{
              fontSize:9, fontFamily:'var(--mono)',
              color:'var(--yellow)',
              background:'rgba(255,200,0,.08)',
              border:'1px solid rgba(255,200,0,.3)',
              padding:'1px 5px',
            }}>
              {slb.open_replies} OPEN
            </span>
          )}
          <span style={{fontSize:9, fontFamily:'var(--mono)', color: statusColor}}>{statusLabel}</span>
          <span style={{fontSize:9, fontFamily:'var(--mono)', color: recColor}}>{REC_LABEL[rec] || rec}</span>
        </div>
      </div>

      {/* Timing */}
      <div style={{fontSize:10, color:'var(--dim)', fontFamily:'var(--mono)', marginBottom:8}}>
        {offer.latest_bump_at > 0 ? `bumped ${relTime(offer.latest_bump_at)}` : 'never bumped'}
        {offer.job_interval_h > 0 && ` · every ${offer.job_interval_h}h`}
      </div>

      {/* Stats: two compact text lines */}
      <div style={{fontFamily:'var(--mono)', fontSize:10, marginBottom:8, display:'flex', flexDirection:'column', gap:2}}>
        {offer.latest_bump_at > 0 && (
          <div>
            <span style={{color:'var(--dim)', marginRight:8}}>since bump</span>
            <span style={{color:(slb.tracked_replies ?? 0) > 0 ? 'var(--text)' : 'var(--dim)'}}>{slb.tracked_replies ?? 0} replies</span>
            <span style={{color:'var(--dim)'}}> · </span>
            <span style={{color:(slb.open_replies ?? 0) > 0 ? 'var(--yellow)' : 'var(--dim)'}}>{slb.open_replies ?? 0} open</span>
            <span style={{color:'var(--dim)'}}> · </span>
            <span style={{color:(slb.contracts_completed ?? 0) > 0 ? 'var(--green)' : 'var(--dim)'}}>{slb.contracts_completed ?? 0} complete</span>
          </div>
        )}
        <div>
          <span style={{color:'var(--dim)', marginRight:8}}>all time</span>
          <span style={{color:'var(--acc)'}}>{offer.bump_count} bumps</span>
          <span style={{color:'var(--dim)'}}> · </span>
          <span style={{color:'var(--sub)'}}>{offer.reply_count} replies</span>
          <span style={{color:'var(--dim)'}}> · </span>
          <span style={{color: offer.contracts_complete > 0 ? 'var(--green)' : 'var(--dim)'}}>{offer.contracts_complete} complete</span>
          {offer.contracts_active > 0 && <>
            <span style={{color:'var(--dim)'}}> · </span>
            <span style={{color:'var(--yellow)'}}>{offer.contracts_active} active</span>
          </>}
        </div>
      </div>

      {/* Compact timeline */}
      {timeline.length > 0 && (
        <div>
          <div style={{fontSize:9, color:'var(--dim)', fontFamily:'var(--mono)', marginBottom:4}}>LAST BUMPS</div>
          {timeline.map((entry, i) => (
            <div key={i} style={{
              display:'flex', gap:8, alignItems:'baseline',
              fontSize:10, fontFamily:'var(--mono)', marginBottom:2,
              color: entry._type === 'skip' ? 'var(--dim)'
                : (entry.period_replies > 0 || entry.contracts_opened > 0) ? 'var(--sub)' : 'var(--dim)',
            }}>
              <span style={{color:'var(--dim)', flexShrink:0, minWidth:50}}>
                {entry.is_open ? 'now' : relTime(entry.bump_ts)}
              </span>
              <span>
                {entry._type === 'skip'
                  ? `skipped${entry.reason ? `: ${entry.reason}` : ''}`
                  : (entry.is_open ? '(current) ' : '') + periodSummary(entry)
                }
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────
export default function MerchantPromotion({ initialTid = null } = {}) {
  const [data, setData]       = useState(null)
  const [loading, setLoading] = useState(true)
  const [tab, setTab]         = useState('all')
  const [selected, setSelected] = useState(initialTid)

  useEffect(() => {
    api.get('/api/merchant/promotion')
      .then(d => { setData(d); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  if (selected) return <BumpDetail tid={selected} onBack={() => setSelected(null)} />

  if (loading) return <div className="empty"><div className="spin" /></div>
  if (!data)   return <div className="empty" style={{color:'var(--red)'}}>Failed to load bump data</div>

  const { offers = [], summary = {} } = data

  const visible =
    tab === 'review'   ? offers.filter(o => o.recommendation === 'review' || o.recommendation === 'pause_candidate')
    : tab === 'activity' ? offers.filter(o => o.since_last_bump?.has_activity)
    : tab === 'paused'   ? offers.filter(o => o.recommendation === 'paused' || o.recommendation === 'closed_thread')
    : offers

  return (
    <div className="mhq-shell">
      <div className="mhq-summary">
        {[
          { l:'NEEDS REVIEW',  v: summary.needs_review     ?? 0, c:'var(--red)'    },
          { l:'GOT ACTIVITY',  v: summary.got_activity     ?? 0, c:'var(--green)'  },
          { l:'OPEN REPLIES',  v: summary.open_replies     ?? 0, c:'var(--yellow)' },
          { l:'PAUSED/CLOSED', v: summary.paused_or_closed ?? 0                    },
        ].map(({ l, v, c }) => (
          <button key={l} type="button"><span className="mhq-summary-label">{l}</span><strong className="mhq-summary-value" style={{color:c||'var(--text)'}}>{v}</strong></button>
        ))}
      </div>

      {/* Tabs */}
      <div className="mhq-filterbar">
        {[
          { val:'all',      label:`All (${offers.length})`                       },
          { val:'review',   label:`Needs Review (${summary.needs_review ?? 0})`  },
          { val:'activity', label:`Got Activity (${summary.got_activity ?? 0})`  },
          { val:'paused',   label:`Paused (${summary.paused_or_closed  ?? 0})`   },
        ].map(f => (
          <button key={f.val}
            className={`tab${tab === f.val ? ' on' : ''}`}
            onClick={() => setTab(f.val)}
          >
            {f.label}
          </button>
        ))}
      </div>

      {visible.length === 0
        ? <div className="mhq-empty">
            {tab === 'all' ? 'No bumped threads.' : 'Nothing in this category.'}
          </div>
        : (
          <div className="mhq-table-wrap"><table className="mhq-table"><thead><tr><th>Sales Thread</th><th>State</th><th>Recommendation</th><th>Last Bump</th><th>Replies</th><th>Open</th><th>Completed</th><th>Total Bumps</th></tr></thead><tbody>
            {visible.map(offer => {
              const rec = offer.recommendation
              const recTone = rec === 'review' || rec === 'pause_candidate' ? 'warn' : rec === 'paused' || rec === 'closed_thread' ? '' : 'good'
              const state = offer.closed ? 'Closed' : offer.has_active_job ? 'Active' : 'Paused'
              return <tr key={offer.tid} onClick={() => setSelected(offer.tid)} style={{cursor:'pointer'}}>
                <td><span className="mhq-table-primary">{offer.title || `TID ${offer.tid}`}</span><span className="mhq-table-meta">TID {offer.tid} · every {offer.job_interval_h || '—'}h</span></td>
                <td><span className={`mhq-status ${state === 'Active' ? 'good' : ''}`}>{state}</span></td><td><span className={`mhq-status ${recTone}`}>{REC_LABEL[rec] || rec}</span></td>
                <td>{offer.latest_bump_at ? relTime(offer.latest_bump_at) : 'Never'}</td><td>{offer.reply_count || 0}</td><td>{offer.since_last_bump?.open_replies || 0}</td><td>{offer.contracts_complete || 0}</td><td>{offer.bump_count || 0}</td>
              </tr>
            })}
          </tbody></table></div>
        )
      }
    </div>
  )
}
