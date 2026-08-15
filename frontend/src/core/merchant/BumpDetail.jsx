// Full bump-performance detail for a single thread. Shared by My Business.
// and the Autobump page's per-job stats popup — one implementation, shown in place
// on whichever page opened it (no cross-page navigation).
import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { relTime } from './merchantFormat.js'

export const REC_LABEL = {
  keep_bumping:    'Keep Bumping',
  watch:           'Watch',
  review:          'Review',
  pause_candidate: 'Pause Candidate',
  paused:          'Paused',
  closed_thread:   'Closed Thread',
}

export const REC_COLOR = {
  keep_bumping:    'var(--green)',
  watch:           'var(--dim)',
  review:          'var(--yellow)',
  pause_candidate: 'var(--red)',
  paused:          'var(--acc)',
  closed_thread:   'var(--red)',
}

export function periodSummary(p) {
  const parts = []
  if ((p.period_replies      || 0) > 0) parts.push(`${p.period_replies} ${p.period_replies === 1 ? 'reply' : 'replies'}`)
  if ((p.contracts_opened    || 0) > 0) parts.push(`${p.contracts_opened} contract${p.contracts_opened > 1 ? 's' : ''}`)
  if ((p.contracts_completed || 0) > 0) parts.push(`${p.contracts_completed} complete`)
  return parts.length ? parts.join(' · ') : 'No activity'
}

export default function BumpDetail({ tid, onBack, backLabel = '← Back to Bumps' }) {
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
      {onBack && (
        <button className="btn" style={{marginBottom:10, fontSize:11}} onClick={onBack}>
          {backLabel}
        </button>
      )}

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
