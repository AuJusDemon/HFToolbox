import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { bucketLabel, bucketColor, contractTerms, relTime } from './merchantFormat.js'

const BUCKETS = [
  { val: null,                label: 'All' },
  { val: 'active_fulfillment',label: 'Active' },
  { val: 'awaiting_approval', label: 'Awaiting Approval' },
  { val: 'completed',         label: 'Completed' },
  { val: 'cancelled',         label: 'Cancelled' },
  { val: 'disputed',          label: 'Disputed' },
  { val: 'expired',           label: 'Expired' },
]

function DealCard({ deal }) {
  const bc = bucketColor(deal.bucket)
  const terms = contractTerms(deal)
  const product = deal.iproduct || deal.oproduct || '—'
  return (
    <div style={{
      background:'var(--s1)', padding:'11px 14px', marginBottom:4,
      display:'flex', alignItems:'center', gap:12,
      borderLeft: `3px solid ${bc}`,
    }}>
      <div style={{flex:1, minWidth:0}}>
        <div style={{display:'flex', gap:8, alignItems:'baseline', marginBottom:3}}>
          <a
            href={`/dashboard/contracts/${deal.cid}`}
            style={{fontSize:11, fontFamily:'var(--mono)', color:'var(--acc)'}}
          >
            #{deal.cid}
          </a>
          <span style={{fontSize:12, color:'var(--text)'}}>
            {deal.counterparty_username || deal.counterparty_uid || '?'}
          </span>
          <span style={{
            fontSize:9, fontFamily:'var(--mono)', color: bc,
            marginLeft:'auto', flexShrink:0,
          }}>{bucketLabel(deal.bucket)}</span>
        </div>

        <div style={{fontSize:11, color:'var(--sub)',
                     overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap'}}>
          {product.length > 60 ? product.slice(0,57)+'…' : product}
        </div>

        <div style={{display:'flex', gap:10, marginTop:4}}>
          {terms !== 'terms not recorded' && (
            <span style={{fontSize:10, color:'var(--dim)', fontFamily:'var(--mono)'}}>{terms}</span>
          )}
          {deal.thread_title && (
            <span style={{
              fontSize:10, color:'var(--dim)',
              overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap', flex:1,
            }}>
              {deal.thread_title.slice(0,50)}
            </span>
          )}
          <span style={{fontSize:10, color:'var(--dim)', fontFamily:'var(--mono)', flexShrink:0}}>
            {relTime(deal.dateline)}
          </span>
        </div>
      </div>
    </div>
  )
}

export default function MerchantDeals() {
  const [allDeals, setAllDeals] = useState([])
  const [loading, setLoading]   = useState(true)
  const [bucket, setBucket]     = useState(null)

  useEffect(() => {
    setLoading(true)
    api.get('/api/merchant/deals')
      .then(d => { setAllDeals(Array.isArray(d) ? d : []); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  const counts = allDeals.reduce((acc, d) => {
    acc[d.bucket] = (acc[d.bucket] || 0) + 1
    return acc
  }, {})

  const visible = bucket ? allDeals.filter(d => d.bucket === bucket) : allDeals

  return (
    <div>
      {/* Bucket tabs */}
      <div style={{display:'flex', gap:4, marginBottom:12, overflowX:'auto', whiteSpace:'nowrap'}}>
        {BUCKETS.map(b => {
          const cnt = b.val ? counts[b.val] ?? 0 : allDeals.length
          return (
            <button key={b.val || 'all'}
              className={`tab${bucket === b.val ? ' on' : ''}`}
              onClick={() => setBucket(b.val)}
            >
              {b.label}{!loading && cnt > 0 ? ` (${cnt})` : ''}
            </button>
          )
        })}
      </div>

      {loading
        ? <div className="empty"><div className="spin" /></div>
        : visible.length === 0
          ? <div className="empty" style={{color:'var(--dim)'}}>No deals found.</div>
          : visible.map(d => <DealCard key={d.cid} deal={d} />)
      }
    </div>
  )
}
