import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { healthLabel, healthColor, relTime, bucketLabel, bucketColor } from './merchantFormat.js'

const STATUS_FILTERS = [
  { val: null,             label: 'All' },
  { val: 'needs_attention',label: 'Needs Reply' },
  { val: 'wasting_spend',  label: 'Bump Waste' },
  { val: 'no_contracts',   label: 'No Contracts' },
  { val: 'stale',          label: 'Stale' },
]

function OfferCard({ offer, onSelect }) {
  const hc = healthColor(offer.health)
  return (
    <div
      className="mhq-offer-card"
      style={{
        background:'var(--s1)', padding:'12px 14px', cursor:'pointer',
        borderLeft: `3px solid ${hc}`,
      }}
      onClick={() => onSelect(offer.tid)}
    >
      <div style={{display:'flex', justifyContent:'space-between', alignItems:'flex-start', gap:8, marginBottom:6}}>
        <div style={{fontFamily:'var(--mono)', fontSize:12, color:'var(--text)', flex:1, minWidth:0,
                     overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap'}}>
          {offer.title || `TID ${offer.tid}`}
        </div>
        <span style={{
          fontSize:9, fontFamily:'var(--mono)', letterSpacing:'.04em',
          color: hc, whiteSpace:'nowrap', flexShrink:0,
        }}>
          {healthLabel(offer.health)}
        </span>
      </div>

      <div style={{display:'flex', gap:10, flexWrap:'wrap'}}>
        {[
          { label:'REPLIES',   val: offer.reply_count,         alert: offer.unread_leads > 0 },
          { label:'UNREAD',    val: offer.unread_leads,        alert: offer.unread_leads > 0 },
          { label:'CONTRACTS', val: offer.contracts_total },
          { label:'DONE',      val: offer.contracts_complete,  color:'var(--green)' },
          { label:'BUMPS',     val: offer.bump_count },
        ].map(({label, val, alert, color}) => (
          <div key={label} style={{textAlign:'center', minWidth:40}}>
            <div style={{fontSize:9, color:'var(--dim)', fontFamily:'var(--mono)'}}>{label}</div>
            <div style={{
              fontSize:14, fontFamily:'var(--mono)', fontWeight:700,
              color: alert ? 'var(--yellow)' : (color || 'var(--sub)'),
            }}>{val}</div>
          </div>
        ))}
        {offer.bump_waste_score >= 60 && (
          <div style={{textAlign:'center', minWidth:40}}>
            <div style={{fontSize:9, color:'var(--dim)', fontFamily:'var(--mono)'}}>BUMP WASTE</div>
            <div style={{fontSize:14, fontFamily:'var(--mono)', fontWeight:700, color:'var(--red)'}}>{offer.bump_waste_score}</div>
          </div>
        )}
      </div>

      {offer.lastpost > 0 && (
        <div style={{fontSize:10, color:'var(--dim)', fontFamily:'var(--mono)', marginTop:6}}>
          last post {relTime(offer.lastpost)}
          {offer.closed && <span style={{color:'var(--red)', marginLeft:8}}>CLOSED</span>}
        </div>
      )}
    </div>
  )
}

function OfferDetail({ tid, onBack }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    setLoading(true)
    api.get(`/api/merchant/offers/${tid}`)
      .then(d => { setData(d); setLoading(false) })
      .catch(() => setLoading(false))
  }, [tid])

  if (loading) return <div className="empty"><div className="spin" /></div>
  if (!data)   return <div className="empty" style={{color:'var(--red)'}}>Failed to load offer</div>

  return (
    <div>
      <button className="btn" style={{marginBottom:10, fontSize:11}} onClick={onBack}>← Back to Sales Threads</button>
      <div className="card" style={{marginBottom:12}}>
        <div className="card-head">
          <span>{data.title || `TID ${data.tid}`}</span>
          <a
            href={`https://hackforums.net/showthread.php?tid=${data.tid}`}
            target="_blank" rel="noopener noreferrer"
            style={{fontSize:10, fontFamily:'var(--mono)', color:'var(--acc)'}}
          >
            VIEW →
          </a>
        </div>
        <div className="card-body">
          <div style={{display:'flex', gap:10, flexWrap:'wrap', marginBottom:12}}>
            {[
              { l:'HEALTH',    v: healthLabel(data.health),           c: healthColor(data.health) },
              { l:'CONTRACTS', v: data.contracts_total },
              { l:'COMPLETED', v: data.contracts_complete,            c:'var(--green)' },
              { l:'ACTIVE',    v: data.contracts_active,              c:'var(--yellow)' },
              { l:'LOST',      v: data.contracts_lost },
              { l:'BUMPS',     v: data.bump_count },
              { l:'UNREAD',    v: data.unread_leads,                  c: data.unread_leads > 0 ? 'var(--yellow)' : undefined },
            ].map(({l,v,c}) => (
              <div key={l} style={{textAlign:'center', minWidth:50}}>
                <div style={{fontSize:9, color:'var(--dim)', fontFamily:'var(--mono)'}}>{l}</div>
                <div style={{fontSize:16, fontFamily:'var(--mono)', fontWeight:700, color: c||'var(--sub)'}}>{v}</div>
              </div>
            ))}
          </div>

          {data.contracts.length > 0 && (
            <>
              <div style={{fontSize:10, color:'var(--dim)', fontFamily:'var(--mono)', marginBottom:6}}>CONTRACTS</div>
              {data.contracts.map(c => (
                <div key={c.cid} style={{
                  padding:'5px 10px', background:'var(--s2)', marginBottom:3,
                  display:'flex', alignItems:'center', gap:8,
                }}>
                  <a
                    href={`/dashboard/contracts/${c.cid}`}
                    style={{fontSize:11, fontFamily:'var(--mono)', color:'var(--acc)', flexShrink:0, width:62}}
                  >
                    #{c.cid}
                  </a>
                  <span style={{
                    fontSize:11, color:'var(--sub)', fontFamily:'var(--mono)',
                    flexShrink:0, width:130,
                    overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap',
                  }}>
                    {c.counterparty_username || c.counterparty_uid || '—'}
                  </span>
                  <span style={{
                    fontSize:11, color:'var(--dim)', fontFamily:'var(--mono)',
                    flex:1, minWidth:0,
                    overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap',
                  }}>
                    {c.iproduct || c.oproduct || '—'}
                  </span>
                  <span style={{
                    fontSize:10, fontFamily:'var(--mono)', flexShrink:0,
                    color: bucketColor(c.bucket),
                  }}>
                    {bucketLabel(c.bucket)}
                  </span>
                </div>
              ))}
            </>
          )}
        </div>
      </div>
    </div>
  )
}

export default function MerchantOffers() {
  const [offers, setOffers]         = useState([])
  const [loading, setLoading]       = useState(true)
  const [statusFilter, setStatus]   = useState(null)
  const [sort, setSort]             = useState('health')
  const [selectedTid, setSelected]  = useState(null)

  const load = (sf, s) => {
    setLoading(true)
    const params = new URLSearchParams()
    if (sf)          params.set('status', sf)
    if (s !== 'health') params.set('sort', s)
    api.get(`/api/merchant/offers?${params}`)
      .then(d => { setOffers(Array.isArray(d) ? d : []); setLoading(false) })
      .catch(() => setLoading(false))
  }

  useEffect(() => { load(statusFilter, sort) }, [statusFilter, sort])

  if (selectedTid) return <OfferDetail tid={selectedTid} onBack={() => setSelected(null)} />

  return (
    <div>
      {/* Filter bar */}
      <div style={{display:'flex', gap:6, flexWrap:'wrap', marginBottom:12, alignItems:'center'}}>
        <div style={{display:'flex', gap:4, flexWrap:'wrap'}}>
          {STATUS_FILTERS.map(f => (
            <button key={f.val || 'all'}
              className={`tab${statusFilter === f.val ? ' on' : ''}`}
              onClick={() => setStatus(f.val)}
            >
              {f.label}
            </button>
          ))}
        </div>
        <select
          className="inp"
          style={{fontSize:11, fontFamily:'var(--mono)', width:'auto', marginLeft:'auto'}}
          value={sort}
          onChange={e => setSort(e.target.value)}
        >
          <option value="health">Sort: Status</option>
          <option value="activity">Sort: Activity</option>
          <option value="contracts">Sort: Contracts</option>
        </select>
      </div>

      {loading
        ? <div className="empty"><div className="spin" /></div>
        : offers.length === 0
          ? <div className="empty" style={{color:'var(--dim)'}}>No sales threads found.</div>
          : (
            <div className="mhq-card-list">
              {offers.map(o => (
                <OfferCard key={o.tid} offer={o} onSelect={setSelected} />
              ))}
            </div>
          )
      }
    </div>
  )
}
