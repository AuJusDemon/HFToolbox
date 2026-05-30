import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { relTime } from './merchantFormat.js'

const REC_LABEL = {
  keep_bumping:    'Working',
  watch:           'Watch',
  review:          'Review',
  pause_candidate: 'Pause?',
  paused:          'Paused',
  closed_thread:   'Closed',
}

const REC_COLOR = {
  keep_bumping:    'var(--green)',
  watch:           'var(--dim)',
  review:          'var(--yellow)',
  pause_candidate: 'var(--red)',
  paused:          'var(--acc)',
  closed_thread:   'var(--red)',
}

function PeriodTimeline({ periods }) {
  if (!periods || periods.length === 0) return null
  return (
    <div>
      <div style={{fontSize:8, color:'var(--dim)', fontFamily:'var(--mono)', marginBottom:3}}>
        RECENT BUMPS (newest →)
      </div>
      <div style={{display:'flex', gap:3, alignItems:'flex-end', height:26}}>
        {periods.map((p, i) => {
          const isActive = (p.reply_gain != null && p.reply_gain > 0) || p.contracts_opened > 0
          const color    = p.is_open ? 'var(--dim)' : isActive ? 'var(--green)' : 'var(--red)'
          const opacity  = p.is_open ? 0.45 : 1
          const label    = p.is_open ? '…'
            : p.reply_gain != null ? (p.reply_gain > 0 ? `+${p.reply_gain}` : String(p.reply_gain))
            : '?'
          return (
            <div key={i} style={{flex:1, display:'flex', flexDirection:'column', alignItems:'center', gap:2, height:'100%', justifyContent:'flex-end'}}>
              <span style={{fontSize:7, fontFamily:'var(--mono)', color, lineHeight:1, opacity}}>{label}</span>
              <div style={{width:'100%', height:8, background:color, opacity}} />
            </div>
          )
        })}
      </div>
    </div>
  )
}

function BumpCard({ offer }) {
  const rec      = offer.recommendation
  const recColor = REC_COLOR[rec] || 'var(--dim)'
  const slb      = offer.since_last_bump  || {}
  const ps       = offer.period_summary   || {}
  const preview  = offer.bump_periods_preview || []

  return (
    <div style={{
      padding:'10px 14px', marginBottom:4, background:'var(--s1)',
      borderLeft: `3px solid ${recColor}`,
    }}>
      {/* Header */}
      <div style={{
        display:'flex', justifyContent:'space-between', alignItems:'flex-start',
        gap:8, marginBottom:6,
      }}>
        <div style={{
          fontFamily:'var(--mono)', fontSize:12, color:'var(--text)',
          flex:1, minWidth:0,
          overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap',
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
              padding:'1px 5px', whiteSpace:'nowrap',
            }}>
              {slb.open_replies} OPEN
            </span>
          )}
          <span style={{
            fontSize:9, fontFamily:'var(--mono)', letterSpacing:'.04em',
            color: recColor, whiteSpace:'nowrap',
          }}>
            {REC_LABEL[rec] || rec}
          </span>
        </div>
      </div>

      {/* Stats row */}
      <div style={{display:'flex', gap:10, flexWrap:'wrap', marginBottom: preview.length ? 8 : 0}}>
        {[
          { l:'BUMPS',  v: offer.bump_count,          c: offer.bump_count > 0 ? 'var(--acc)' : undefined },
          { l:'SKIPS',  v: offer.skip_count },
          { l:'REPLIES', v: slb.tracked_replies ?? offer.reply_count },
          { l:'DONE',   v: offer.contracts_complete,  c: offer.contracts_complete > 0 ? 'var(--green)' : undefined },
        ].map(({l, v, c}) => (
          <div key={l} style={{textAlign:'center', minWidth:40}}>
            <div style={{fontSize:9, color:'var(--dim)', fontFamily:'var(--mono)'}}>{l}</div>
            <div style={{fontSize:13, fontFamily:'var(--mono)', fontWeight:700, color: c || 'var(--sub)'}}>{v ?? 0}</div>
          </div>
        ))}
        {ps.avg_reply_gain != null && (
          <div style={{textAlign:'center', minWidth:44}}>
            <div style={{fontSize:9, color:'var(--dim)', fontFamily:'var(--mono)'}}>AVG GAIN</div>
            <div style={{
              fontSize:13, fontFamily:'var(--mono)', fontWeight:700,
              color: ps.avg_reply_gain > 0 ? 'var(--green)' : 'var(--dim)',
            }}>
              {ps.avg_reply_gain > 0 ? `+${ps.avg_reply_gain}` : ps.avg_reply_gain}
            </div>
          </div>
        )}
      </div>

      {/* Mini timeline */}
      {preview.length > 0 && (
        <div style={{marginBottom:6}}>
          <PeriodTimeline periods={preview} />
        </div>
      )}

      {/* Footer: timing + activity */}
      {offer.latest_bump_at > 0 && (
        <div style={{fontSize:10, color:'var(--dim)', fontFamily:'var(--mono)', marginTop:4}}>
          {'bumped '}
          {relTime(offer.latest_bump_at)}
          {slb.has_activity && slb.last_activity_at
            ? ` · activity ${relTime(slb.last_activity_at)}`
            : !slb.has_activity && offer.bump_count > 0
              ? ' · no activity since'
              : ''}
          {offer.job_interval_h > 0 && ` · every ${offer.job_interval_h}h`}
        </div>
      )}
    </div>
  )
}

export default function MerchantPromotion() {
  const [data, setData]     = useState(null)
  const [loading, setLoading] = useState(true)
  const [tab, setTab]       = useState('all')

  useEffect(() => {
    api.get('/api/merchant/promotion')
      .then(d => { setData(d); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  if (loading) return <div className="empty"><div className="spin" /></div>
  if (!data)   return <div className="empty" style={{color:'var(--red)'}}>Failed to load bump data</div>

  const { offers = [], summary = {}, total_bumps = 0, total_skips = 0 } = data

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
          { l:'NEEDS REVIEW',  v: summary.needs_review    ?? 0, c:'var(--red)'    },
          { l:'GOT ACTIVITY',  v: summary.got_activity    ?? 0, c:'var(--green)'  },
          { l:'OPEN REPLIES',  v: summary.open_replies    ?? 0, c:'var(--yellow)' },
          { l:'PAUSED/CLOSED', v: summary.paused_or_closed ?? 0                   },
        ].map(({l, v, c}) => (
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
          { val:'all',      label:`All (${offers.length})`                      },
          { val:'review',   label:`Needs Review (${summary.needs_review ?? 0})` },
          { val:'activity', label:`Got Activity (${summary.got_activity ?? 0})` },
          { val:'paused',   label:`Paused (${summary.paused_or_closed  ?? 0})`  },
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
            {visible.map(o => <BumpCard key={o.tid} offer={o} />)}
          </div>
        )
      }
    </div>
  )
}
