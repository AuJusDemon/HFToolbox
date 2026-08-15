import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { healthLabel, healthColor, relTime, bucketLabel, bucketColor } from './merchantFormat.js'

const STATUS_FILTERS = [
  { val: 'active',         label: 'Active' },
  { val: 'needs_attention', label: 'Needs Action' },
  { val: 'wasting_spend',  label: 'Bump Waste' },
  { val: 'no_contracts',   label: 'No Contracts' },
  { val: 'stale',          label: 'Stale / Archived' },
  { val: 'all',            label: 'Archive / All' },
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
        <div style={{display:'flex', gap:5, alignItems:'center', flexShrink:0}}>
          {offer.unread_leads > 0 && (
            <span style={{
              fontSize:9, fontFamily:'var(--mono)',
              color:'var(--yellow)',
              background:'rgba(255,200,0,.08)',
              border:'1px solid rgba(255,200,0,.3)',
              padding:'1px 5px', whiteSpace:'nowrap',
            }}>
              {offer.unread_leads} NEW
            </span>
          )}
          <span style={{
            fontSize:9, fontFamily:'var(--mono)', letterSpacing:'.04em',
            color: hc, whiteSpace:'nowrap',
          }}>
            {healthLabel(offer.health)}
          </span>
        </div>
      </div>

      <div style={{display:'flex', gap:10, flexWrap:'wrap'}}>
        {[
          { label:'VIEWS',     val: offer.views || 0 },
          { label:'POSTS',     val: offer.post_count || ((offer.reply_count || 0) + 1) },
          { label:'REPLIES',   val: offer.reply_count },
          { label:'NEW',       val: offer.unread_leads,        alert: offer.unread_leads > 0 },
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
      <button className="btn" style={{marginBottom:10, fontSize:11}} onClick={onBack}>Back to Sales Threads</button>
      <div className="card" style={{marginBottom:12}}>
        <div className="card-head">
          <span>{data.title || `TID ${data.tid}`}</span>
          <a
            href={`https://hackforums.net/showthread.php?tid=${data.tid}`}
            target="_blank" rel="noopener noreferrer"
            style={{fontSize:10, fontFamily:'var(--mono)', color:'var(--acc)'}}
          >
            VIEW
          </a>
        </div>
        <div className="card-body">
          <div style={{display:'flex', gap:10, flexWrap:'wrap', marginBottom:12}}>
            {[
              { l:'HEALTH',    v: healthLabel(data.health),           c: healthColor(data.health) },
              { l:'VIEWS',     v: data.views || 0 },
              { l:'POSTS',     v: data.post_count || ((data.reply_count || 0) + 1) },
              { l:'REPLIES',   v: data.reply_count || 0 },
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
                    {c.counterparty_username || c.counterparty_uid || '-'}
                  </span>
                  <span style={{
                    fontSize:11, color:'var(--dim)', fontFamily:'var(--mono)',
                    flex:1, minWidth:0,
                    overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap',
                  }}>
                    {c.iproduct || c.oproduct || '-'}
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

function ProductAssignments({products,onChanged}) {
  const [editing,setEditing]=useState(null)
  const [name,setName]=useState('')
  const [newName,setNewName]=useState('')
  const [deleting,setDeleting]=useState(null)
  const [message,setMessage]=useState('')
  const [error,setError]=useState('')
  const rename=async product=>{
    const clean=name.trim()
    if(!clean)return
    try{
      await api.patch(`/api/merchant/products/${product.id}`,{name:clean})
      setEditing(null);setName('');setError('');setMessage('Group renamed');await onChanged()
    }catch(err){setMessage('');setError(err.message||'Could not rename group')}
  }
  const create=async()=>{
    const clean=newName.trim()
    if(!clean){setMessage('');setError('Enter a group name first');return}
    try{
      const product=await api.post('/api/merchant/products',{name:clean})
      setNewName('');setError('');setMessage(`Added ${product?.name||clean}. Assign a sales thread below.`);await onChanged()
    }catch(err){setMessage('');setError(err.message||'Could not add group')}
  }
  const remove=async product=>{
    try{
      await api.delete(`/api/merchant/products/${product.id}`)
      setDeleting(null);setError('');setMessage(`Deleted ${product.name}. Assigned threads were set back to Unclassified.`);await onChanged()
    }catch(err){setMessage('');setError(err.message||'Could not delete group')}
  }
  return <section className="mhq-section">
    <div className="mhq-section-head">
      <div>
        <h3>Product Groups</h3>
        <p>Create private buckets for your sales threads. Use the Product column below to move a thread into a group.</p>
      </div>
      <span>{products.length} groups</span>
    </div>
    <div className="mhq-inline-edit">
      <input className="inp" value={newName} onChange={e=>setNewName(e.target.value)} placeholder="Group name"/>
      <button className="btn btn-sm" onClick={create}>Add group</button>
    </div>
    {message&&<div className="mhq-note">{message}</div>}
    {error&&<div className="mhq-note warn">{error}</div>}
    <div className="mhq-table-wrap" style={{marginTop:10}}>
      <table className="mhq-table">
        <thead><tr><th>Current Group</th><th>Assigned Threads</th><th>Action</th></tr></thead>
        <tbody>
          {products.length===0
            ? <tr><td colSpan="3">No groups created yet.</td></tr>
            : products.map(product=><tr key={product.id}>
              <td>{editing===product.id?<div className="mhq-inline-edit"><input className="inp" value={name} onChange={e=>setName(e.target.value)}/><button className="btn btn-sm" onClick={()=>rename(product)}>Save</button><button className="btn btn-sm" onClick={()=>setEditing(null)}>Cancel</button></div>:<span className="mhq-table-primary">{product.name}</span>}</td>
              <td>{product.thread_count||0}</td>
              <td>{deleting===product.id
                ? <div className="mhq-inline-edit"><button className="btn btn-sm btn-danger" onClick={()=>remove(product)}>Delete</button><button className="btn btn-sm" onClick={()=>setDeleting(null)}>Cancel</button></div>
                : <div className="mhq-inline-edit"><button className="btn btn-sm" onClick={()=>{setEditing(product.id);setName(product.name)}}>Rename</button><button className="btn btn-sm btn-danger" onClick={()=>setDeleting(product.id)}>Delete</button></div>}
              </td>
            </tr>)
          }
        </tbody>
      </table>
    </div>
  </section>
}

export default function MerchantOffers() {
  const [offers, setOffers]         = useState([])
  const [products,setProducts]      = useState([])
  const [loading, setLoading]       = useState(true)
  const [statusFilter, setStatus]   = useState('active')
  const [sort, setSort]             = useState('health')
  const [selectedTid, setSelected]  = useState(null)
  const [assignError,setAssignError]= useState('')

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
  const loadProducts=()=>api.get('/api/merchant/products').then(d=>setProducts(d.products||[])).catch(()=>setProducts([]))
  useEffect(() => { loadProducts() }, [])
  const assignOfferProduct=async(offer,productId)=>{
    if(!productId)return
    try{
      await api.put(`/api/merchant/products/${productId}/thread`,{tid:String(offer.tid),excluded:false})
      setAssignError('')
      await loadProducts()
    }catch(err){setAssignError(err.message||'Could not assign thread')}
  }

  if (selectedTid) return <OfferDetail tid={selectedTid} onBack={() => setSelected(null)} />

  return (
    <div className="mhq-shell">
      <ProductAssignments products={products} onChanged={loadProducts}/>
      {assignError&&<div className="mhq-note warn">{assignError}</div>}
      <div className="mhq-filterbar">
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
          style={{width:'auto', marginLeft:'auto'}}
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
          ? <div className="mhq-empty">No sales threads found.</div>
            : (
            <div className="mhq-table-wrap"><table className="mhq-table"><thead><tr><th>Sales Thread</th><th>Product</th><th>Status</th><th>Views</th><th>Posts</th><th>Replies</th><th>Contracts</th><th>Completed</th><th>Bumps</th><th>Last Activity</th></tr></thead><tbody>
              {offers.map(offer => {const product=products.find(p=>(p.threads||[]).some(t=>String(t.tid)===String(offer.tid)&&!t.excluded));return <tr key={offer.tid} onClick={() => setSelected(offer.tid)} style={{cursor:'pointer'}}>
                <td><span className="mhq-table-primary">{offer.title || `TID ${offer.tid}`}</span><span className="mhq-table-meta">TID {offer.tid}{offer.unread_leads > 0 ? ` - ${offer.unread_leads} unread` : ''}{offer.archived ? ' - archived' : ''}{(offer.reasons || []).length ? ` - ${offer.reasons.join(', ')}` : ''}</span></td><td><select className="inp" value={product?.id||''} onClick={e=>e.stopPropagation()} onChange={e=>assignOfferProduct(offer,e.target.value)}><option value="">Unclassified</option>{products.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></td>
                <td><span className={`mhq-status ${offer.health === 'needs_attention' || offer.health === 'wasting_spend' ? 'warn' : offer.health === 'healthy' ? 'good' : ''}`}>{healthLabel(offer.health)}</span></td>
                <td>{offer.views || 0}</td><td>{offer.post_count || ((offer.reply_count || 0) + 1)}</td><td>{offer.reply_count || 0}</td><td>{offer.contracts_total || 0}</td><td>{offer.contracts_complete || 0}</td><td>{offer.bump_count || 0}</td>
                <td>{offer.last_activity_at ? relTime(offer.last_activity_at) : 'No activity'}</td>
              </tr>})}
            </tbody></table></div>
          )
      }
    </div>
  )
}
