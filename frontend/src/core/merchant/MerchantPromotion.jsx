import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { relTime } from './merchantFormat.js'

function WasteBar({ score }) {
  const color = score >= 80 ? 'var(--red)' : score >= 60 ? 'var(--yellow)' : 'var(--green)'
  return (
    <div style={{display:'flex', alignItems:'center', gap:8}}>
      <div style={{
        flex:1, height:6, background:'var(--b2)', position:'relative',
      }}>
        <div style={{
          position:'absolute', left:0, top:0, bottom:0,
          width:`${score}%`, background: color, transition:'width .3s',
        }} />
      </div>
      <span style={{fontSize:10, fontFamily:'var(--mono)', color, minWidth:28}}>{score}</span>
    </div>
  )
}

function OfferRow({ offer }) {
  const hasWaste = offer.waste_score >= 60
  return (
    <div style={{
      padding:'10px 14px', marginBottom:4, background:'var(--s1)',
      borderLeft: `3px solid ${hasWaste ? 'var(--red)' : offer.has_active_job ? 'var(--acc)' : 'var(--b2)'}`,
    }}>
      <div style={{
        display:'flex', justifyContent:'space-between', alignItems:'flex-start',
        gap:8, marginBottom:6,
      }}>
        <div style={{
          fontFamily:'var(--mono)', fontSize:12, color:'var(--text)', flex:1, minWidth:0,
          overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap',
        }}>
          {offer.title || `TID ${offer.tid}`}
          {offer.closed && <span style={{color:'var(--red)', marginLeft:8, fontSize:9}}>CLOSED</span>}
        </div>
        {offer.has_active_job && (
          <span style={{fontSize:9, color:'var(--acc)', fontFamily:'var(--mono)', flexShrink:0}}>
            ACTIVE JOB
          </span>
        )}
      </div>

      <div style={{display:'flex', gap:12, flexWrap:'wrap', marginBottom:6}}>
        {[
          { l:'BUMPS',   v: offer.bump_count,           c: offer.bump_count > 0 ? 'var(--acc)' : 'var(--dim)' },
          { l:'SKIPPED', v: offer.skip_count },
          { l:'REPLIES', v: offer.reply_count },
          { l:'UNREAD',  v: offer.unread_replies,       c: offer.unread_replies > 0 ? 'var(--yellow)' : 'var(--dim)' },
          { l:'DONE',    v: offer.contracts_complete,   c: offer.contracts_complete > 0 ? 'var(--green)' : 'var(--dim)' },
        ].map(({l,v,c}) => (
          <div key={l} style={{textAlign:'center', minWidth:44}}>
            <div style={{fontSize:9, color:'var(--dim)', fontFamily:'var(--mono)'}}>{l}</div>
            <div style={{fontSize:14, fontFamily:'var(--mono)', fontWeight:700, color:c||'var(--sub)'}}>{v}</div>
          </div>
        ))}
      </div>

      {offer.bump_count > 0 && (
        <div>
          <div style={{fontSize:9, color:'var(--dim)', fontFamily:'var(--mono)', marginBottom:3}}>
            WASTE SCORE
          </div>
          <WasteBar score={offer.waste_score} />
          {hasWaste && (
            <div style={{fontSize:10, color:'var(--red)', marginTop:4}}>
              {offer.bump_count} bumps with low reply/contract activity
              {offer.has_active_job && offer.closed ? ' — job active on closed thread' : ''}
            </div>
          )}
        </div>
      )}

      {offer.latest_bump_at > 0 && (
        <div style={{fontSize:10, color:'var(--dim)', fontFamily:'var(--mono)', marginTop:5}}>
          last bumped {relTime(offer.latest_bump_at)}
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

  const { offers = [], waste_warnings = [], total_bumps = 0, total_skips = 0 } = data
  const visible = tab === 'waste' ? waste_warnings : offers

  return (
    <div>
      <div style={{display:'flex', gap:10, flexWrap:'wrap', marginBottom:12}}>
        {[
          { l:'TOTAL BUMPS',  v: total_bumps },
          { l:'TOTAL SKIPS',  v: total_skips },
          { l:'BUMP WASTE', v: waste_warnings.length, c:'var(--red)' },
        ].map(({l,v,c}) => (
          <div key={l} style={{background:'var(--s1)', padding:'7px 14px', flex:1, minWidth:80, textAlign:'center'}}>
            <div style={{fontSize:9, color:'var(--dim)', fontFamily:'var(--mono)'}}>{l}</div>
            <div style={{fontSize:18, fontFamily:'var(--mono)', fontWeight:700, color:c||'var(--sub)'}}>{v}</div>
          </div>
        ))}
      </div>

      <div style={{display:'flex', gap:4, marginBottom:12}}>
        <button className={`tab${tab==='all'?' on':''}`} onClick={() => setTab('all')}>
          All ({offers.length})
        </button>
        <button className={`tab${tab==='waste'?' on':''}`} onClick={() => setTab('waste')}>
          Bump Waste ({waste_warnings.length})
        </button>
      </div>

      {visible.length === 0
        ? <div className="empty" style={{color:'var(--dim)'}}>
            {tab === 'waste' ? 'No bump waste showing right now.' : 'No bumped threads.'}
          </div>
        : visible.map(o => <OfferRow key={o.tid} offer={o} />)
      }
    </div>
  )
}
