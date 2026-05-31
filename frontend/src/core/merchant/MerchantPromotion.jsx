import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { relTime, absDate } from './merchantFormat.js'

const REC_LABEL = {
  keep_bumping:    'Keep Bumping',
  watch:           'Watch',
  review:          'Review',
  pause_candidate: 'Pause Candidate',
  paused:          'Paused',
  closed_thread:   'Closed Thread',
}

const REC_COLOR = {
  keep_bumping:    'var(--green)',
  watch:           'var(--dim)',
  review:          'var(--yellow)',
  pause_candidate: 'var(--red)',
  paused:          'var(--acc)',
  closed_thread:   'var(--red)',
}

function periodSummary(p) {
  const parts = []
  if ((p.period_replies      || 0) > 0) parts.push(`${p.period_replies} ${p.period_replies === 1 ? 'reply' : 'replies'}`)
  if ((p.contracts_opened    || 0) > 0) parts.push(`${p.contracts_opened} contract${p.contracts_opened > 1 ? 's' : ''}`)
  if ((p.contracts_completed || 0) > 0) parts.push(`${p.contracts_completed} complete`)
  return parts.length ? parts.join(' · ') : 'No activity'
}

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

// ── Full detail page ──────────────────────────────────────────────────────────
function BumpDetail({ tid, onBack }) {
  const [data, setData]     = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    api.get(`/api/merchant/promotion/${tid}`)
      .then(d => { setData(d); setLoading(false) })
      .catch(() => setLoading(false))
  }, [tid])

  if (loading) return <div className="empty"><div className="spin" /></div>
  if (!data)   return <div className="empty" style={{color:'var(--red)'}}>Failed to load</div>

  const rec      = data.recommendation
  const recColor = REC_COLOR[rec] || 'var(--dim)'
  const slb      = data.since_last_bump || {}
  const tot      = data.totals          || {}
  const periods  = data.periods         || []   // newest first
  const weekly   = data.weekly          || []

  const statusLabel = data.closed ? 'CLOSED' : data.has_active_job ? 'ACTIVE' : 'PAUSED'
  const statusColor = data.closed ? 'var(--red)' : data.has_active_job ? 'var(--green)' : 'var(--dim)'

  return (
    <div>
      <button className="btn" style={{marginBottom:10, fontSize:11}} onClick={onBack}>
        ← Back to Bumps
      </button>

      {/* Header card */}
      <div className="card" style={{marginBottom:12}}>
        <div className="card-head">
          <span style={{flex:1, minWidth:0, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap'}}>
            {data.title || `TID ${data.tid}`}
          </span>
          <div style={{display:'flex', gap:8, alignItems:'center', flexShrink:0}}>
            <span style={{fontSize:10, fontFamily:'var(--mono)', color: statusColor}}>{statusLabel}</span>
            <span style={{fontSize:10, fontFamily:'var(--mono)', color: recColor}}>{REC_LABEL[rec]}</span>
            <a
              href={`https://hackforums.net/showthread.php?tid=${data.tid}`}
              target="_blank" rel="noopener noreferrer"
              style={{fontSize:10, fontFamily:'var(--mono)', color:'var(--acc)'}}
            >
              VIEW →
            </a>
          </div>
        </div>
        <div className="card-body">

          {/* Job info */}
          <div style={{fontSize:11, color:'var(--dim)', fontFamily:'var(--mono)', marginBottom:12}}>
            {data.latest_bump_at > 0 ? `Last bumped ${relTime(data.latest_bump_at)}` : 'Never bumped'}
            {data.job_interval_h > 0 && ` · every ${data.job_interval_h}h`}
            {data.job_next_bump > 0 && data.job_next_bump > Math.floor(Date.now()/1000) && (
              <span style={{color:'var(--acc)'}}>{` · next ${relTime(data.job_next_bump)}`}</span>
            )}
          </div>

          {/* All-time stats */}
          <div style={{fontSize:9, color:'var(--dim)', fontFamily:'var(--mono)', marginBottom:6}}>ALL TIME</div>
          <div style={{display:'flex', gap:10, flexWrap:'wrap', marginBottom:14}}>
            {[
              { l:'BUMPS',       v: tot.bumps,              c:'var(--acc)'   },
              { l:'SKIPS',       v: tot.skips                                },
              { l:'REPLIES',     v: tot.replies                              },
              { l:'CONTRACTS',   v: tot.contracts_total                      },
              { l:'COMPLETE',        v: tot.contracts_complete, c:'var(--green)' },
              { l:'ACTIVE',      v: tot.contracts_active,   c: tot.contracts_active > 0 ? 'var(--yellow)' : undefined },
              { l:'AVG GAIN',    v: tot.avg_reply_gain != null ? (tot.avg_reply_gain > 0 ? `+${tot.avg_reply_gain}` : tot.avg_reply_gain) : '—' },
              { l:'ACTIVE PERIODS', v: tot.active_periods, c:'var(--green)' },
              { l:'DEAD PERIODS',   v: tot.dead_periods,   c: tot.dead_periods > 0 ? 'var(--red)' : undefined },
            ].map(({ l, v, c }) => (
              <div key={l} style={{textAlign:'center', minWidth:52}}>
                <div style={{fontSize:9, color:'var(--dim)', fontFamily:'var(--mono)'}}>{l}</div>
                <div style={{fontSize:14, fontFamily:'var(--mono)', fontWeight:700, color: c || 'var(--sub)'}}>{v ?? 0}</div>
              </div>
            ))}
          </div>

          {/* Since last bump */}
          {data.latest_bump_at > 0 && (
            <>
              <div style={{fontSize:9, color:'var(--dim)', fontFamily:'var(--mono)', marginBottom:6}}>SINCE LAST BUMP</div>
              <div style={{display:'flex', gap:10, flexWrap:'wrap', marginBottom:14}}>
                {[
                  { l:'REPLIES',   v: slb.tracked_replies    ?? 0 },
                  { l:'OPEN',      v: slb.open_replies        ?? 0, c: (slb.open_replies ?? 0) > 0 ? 'var(--yellow)' : undefined },
                  { l:'CONTRACTS', v: slb.contracts_opened    ?? 0 },
                  { l:'COMPLETE',      v: slb.contracts_completed ?? 0, c: (slb.contracts_completed ?? 0) > 0 ? 'var(--green)' : undefined },
                  { l:'REPLY GAIN', v: slb.reply_gain != null ? (slb.reply_gain > 0 ? `+${slb.reply_gain}` : slb.reply_gain) : '—' },
                ].map(({ l, v, c }) => (
                  <div key={l} style={{textAlign:'center', minWidth:52}}>
                    <div style={{fontSize:9, color:'var(--dim)', fontFamily:'var(--mono)'}}>{l}</div>
                    <div style={{fontSize:16, fontFamily:'var(--mono)', fontWeight:700, color: c || 'var(--sub)'}}>{v ?? 0}</div>
                  </div>
                ))}
              </div>
            </>
          )}

        </div>
      </div>

      {/* Weekly breakdown */}
      {weekly.some(w => w.bumps > 0 || w.replies > 0 || w.contracts_opened > 0) && (
        <div className="card" style={{marginBottom:12}}>
          <div className="card-head">Weekly Breakdown</div>
          <div className="card-body" style={{padding:'8px 10px'}}>
            <div style={{display:'grid', gridTemplateColumns:'120px repeat(5, 1fr)', gap:'4px 8px', fontSize:9, fontFamily:'var(--mono)'}}>
              {/* Header */}
              {['WEEK', 'BUMPS', 'SKIPS', 'REPLIES', 'CONTRACTS', 'COMPLETE'].map(h => (
                <div key={h} style={{color:'var(--dim)', paddingBottom:4}}>{h}</div>
              ))}
              {/* Rows */}
              {[...weekly].reverse().map((w, i) => {
                const isThisWeek = i === weekly.length - 1
                const label = isThisWeek ? 'This week' : `${Math.round((Date.now()/1000 - w.week_start) / 604800)}w ago`
                return (
                  <>{
                    [
                      <div key="l"  style={{color:'var(--dim)'}}>{label}</div>,
                      <div key="b"  style={{color: w.bumps > 0 ? 'var(--acc)' : 'var(--dim)'}}>{w.bumps}</div>,
                      <div key="sk" style={{color:'var(--dim)'}}>{w.skips}</div>,
                      <div key="r"  style={{color: w.replies > 0 ? 'var(--text)' : 'var(--dim)'}}>{w.replies}</div>,
                      <div key="c"  style={{color: w.contracts_opened > 0 ? 'var(--sub)' : 'var(--dim)'}}>{w.contracts_opened}</div>,
                      <div key="d"  style={{color: w.contracts_completed > 0 ? 'var(--green)' : 'var(--dim)'}}>{w.contracts_completed}</div>,
                    ]
                  }</>
                )
              })}
            </div>
          </div>
        </div>
      )}

      {/* Full period timeline */}
      {periods.length > 0 && (
        <div className="card">
          <div className="card-head">Bump History ({periods.length} bumps)</div>
          <div className="card-body" style={{padding:'8px 10px'}}>
            {periods.map((p, i) => (
              <div key={i} style={{
                marginBottom:8, paddingBottom:8,
                borderBottom: i < periods.length - 1 ? '1px solid var(--b2)' : 'none',
              }}>
                {/* Bump header row */}
                <div style={{
                  display:'flex', justifyContent:'space-between', alignItems:'center',
                  marginBottom: (p.period_replies > 0 || p.contracts_opened > 0 || p.contracts_completed > 0 || p.period_skips?.length > 0) ? 5 : 0,
                }}>
                  <span style={{fontSize:11, fontFamily:'var(--mono)', color:'var(--sub)', fontWeight:600}}>
                    {p.is_open ? 'Current period' : `Bumped ${relTime(p.bump_ts)}`}
                  </span>
                  <span style={{
                    fontSize:10, fontFamily:'var(--mono)',
                    color: (p.period_replies > 0 || p.contracts_opened > 0) ? 'var(--green)' : 'var(--dim)',
                  }}>
                    {periodSummary(p)}
                  </span>
                </div>

                {/* Detail breakdown */}
                {(p.period_replies > 0 || p.period_open_replies > 0 || p.contracts_opened > 0 || p.contracts_completed > 0) && (
                  <div style={{fontSize:10, color:'var(--dim)', fontFamily:'var(--mono)', marginBottom:4, paddingLeft:10}}>
                    {[
                      p.period_replies      > 0 && `${p.period_replies} repl${p.period_replies === 1 ? 'y' : 'ies'} tracked`,
                      p.period_open_replies > 0 && `${p.period_open_replies} open`,
                      p.contracts_opened    > 0 && `${p.contracts_opened} contract${p.contracts_opened > 1 ? 's' : ''} opened`,
                      p.contracts_completed > 0 && `${p.contracts_completed} complete`,
                      p.reply_gain != null      && `${p.reply_gain >= 0 ? '+' : ''}${p.reply_gain} thread replies`,
                    ].filter(Boolean).join(' · ')}
                  </div>
                )}

                {/* Skips within period */}
                {p.period_skips?.map((s, si) => (
                  <div key={si} style={{
                    fontSize:9, fontFamily:'var(--mono)', color:'var(--dim)',
                    paddingLeft:10, marginBottom:2,
                  }}>
                    {relTime(s.ts)} — skipped{s.reason ? `: ${s.reason}` : ''}
                  </div>
                ))}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────
export default function MerchantPromotion() {
  const [data, setData]       = useState(null)
  const [loading, setLoading] = useState(true)
  const [tab, setTab]         = useState('all')
  const [selected, setSelected] = useState(null)

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
    <div>
      {/* Stat strip */}
      <div style={{display:'flex', gap:6, marginBottom:12, flexWrap:'wrap'}}>
        {[
          { l:'NEEDS REVIEW',  v: summary.needs_review     ?? 0, c:'var(--red)'    },
          { l:'GOT ACTIVITY',  v: summary.got_activity     ?? 0, c:'var(--green)'  },
          { l:'OPEN REPLIES',  v: summary.open_replies     ?? 0, c:'var(--yellow)' },
          { l:'PAUSED/CLOSED', v: summary.paused_or_closed ?? 0                    },
        ].map(({ l, v, c }) => (
          <div key={l} style={{
            background:'var(--s1)', padding:'7px 14px',
            flex:'1 1 0', minWidth:80, textAlign:'center',
          }}>
            <div style={{fontSize:9, color:'var(--dim)', fontFamily:'var(--mono)'}}>{l}</div>
            <div style={{fontSize:18, fontFamily:'var(--mono)', fontWeight:700, color: c || 'var(--sub)'}}>{v}</div>
          </div>
        ))}
      </div>

      {/* Tabs */}
      <div style={{display:'flex', gap:4, marginBottom:12, flexWrap:'wrap'}}>
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
        ? <div className="empty" style={{color:'var(--dim)'}}>
            {tab === 'all' ? 'No bumped threads.' : 'Nothing in this category.'}
          </div>
        : (
          <div className="mhq-card-list">
            {visible.map(o => <BumpCard key={o.tid} offer={o} onSelect={setSelected} />)}
          </div>
        )
      }
    </div>
  )
}
