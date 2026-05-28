import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { relTime, absDate, parseTags, serializeTags } from './merchantFormat.js'

function TagList({ tags }) {
  if (!tags.length) return null
  return (
    <div style={{display:'flex', gap:4, flexWrap:'wrap', marginTop:4}}>
      {tags.map(t => (
        <span key={t} style={{
          fontSize:9, fontFamily:'var(--mono)', background:'var(--b2)',
          color:'var(--sub)', padding:'1px 6px',
        }}>{t}</span>
      ))}
    </div>
  )
}

function CustomerCard({ c, onSelect }) {
  const color = c.is_repeat ? 'var(--green)' : 'var(--sub)'
  const tags  = parseTags(c.tags_json)
  return (
    <div
      style={{
        background:'var(--s1)', padding:'11px 14px', cursor:'pointer', marginBottom:4,
        borderLeft: `3px solid ${c.completed_deals > 0 ? 'var(--acc)' : 'var(--b2)'}`,
      }}
      onClick={() => onSelect(c.uid)}
    >
      <div style={{display:'flex', justifyContent:'space-between', alignItems:'flex-start', gap:8, marginBottom:4}}>
        <div style={{fontFamily:'var(--mono)', fontSize:13, color:'var(--text)'}}>
          {c.username || c.uid}
          {c.label && <span style={{fontSize:10, color:'var(--dim)', marginLeft:8}}>{c.label}</span>}
        </div>
        {c.is_repeat && (
          <span style={{fontSize:9, color:'var(--green)', fontFamily:'var(--mono)', flexShrink:0}}>
            REPEAT
          </span>
        )}
      </div>

      <div style={{display:'flex', gap:12, flexWrap:'wrap'}}>
        {[
          { l:'DONE',   v: c.completed_deals, c:'var(--green)' },
          { l:'ACTIVE', v: c.active_deals,    c:'var(--yellow)' },
          { l:'LOST',   v: c.lost_deals },
          { l:'TOTAL',  v: c.total_deals },
        ].map(({l,v,c: col}) => (
          <div key={l} style={{textAlign:'center', minWidth:40}}>
            <div style={{fontSize:9, color:'var(--dim)', fontFamily:'var(--mono)'}}>{l}</div>
            <div style={{fontSize:14, fontFamily:'var(--mono)', fontWeight:700, color: col||'var(--sub)'}}>{v}</div>
          </div>
        ))}
        <div style={{marginLeft:'auto', textAlign:'right'}}>
          <div style={{fontSize:9, color:'var(--dim)', fontFamily:'var(--mono)'}}>LAST DEAL</div>
          <div style={{fontSize:11, color:'var(--dim)', fontFamily:'var(--mono)'}}>{relTime(c.last_deal_at)}</div>
        </div>
      </div>

      {c.top_products.length > 0 && (
        <div style={{fontSize:10, color:'var(--dim)', marginTop:5,
                     overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap'}}>
          {c.top_products.slice(0,3).join(', ')}
        </div>
      )}

      <TagList tags={tags} />

      {c.followup_at && c.followup_at > Math.floor(Date.now()/1000) - 86400 && (
        <div style={{fontSize:10, color:'var(--yellow)', fontFamily:'var(--mono)', marginTop:4}}>
          follow-up: {absDate(c.followup_at)}
        </div>
      )}
    </div>
  )
}

function CustomerDetail({ cpUid, onBack }) {
  const [data, setData]     = useState(null)
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(false)
  const [note, setNote]       = useState('')
  const [label, setLabel]     = useState('')
  const [tagInput, setTagInput] = useState('')
  const [tags, setTags]       = useState([])
  const [saving, setSaving]   = useState(false)

  const load = () => {
    setLoading(true)
    api.get(`/api/merchant/customers/${cpUid}`)
      .then(d => {
        setData(d)
        setNote(d.note || '')
        setLabel(d.label || '')
        setTags(parseTags(d.tags_json))
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }
  useEffect(load, [cpUid])

  const save = () => {
    setSaving(true)
    api.patch(`/api/merchant/customers/${cpUid}`, {
      note, label, tags_json: serializeTags(tags),
    })
      .then(() => { setSaving(false); setEditing(false); load() })
      .catch(() => setSaving(false))
  }

  const addTag = () => {
    const t = tagInput.trim()
    if (t && !tags.includes(t)) setTags(ts => [...ts, t])
    setTagInput('')
  }

  if (loading) return <div className="empty"><div className="spin" /></div>
  if (!data)   return <div className="empty" style={{color:'var(--red)'}}>Customer not found</div>

  return (
    <div>
      <button className="btn" style={{marginBottom:10, fontSize:11}} onClick={onBack}>← Back</button>

      <div className="card" style={{marginBottom:12}}>
        <div className="card-head">
          <span>{data.username || data.uid}</span>
          {data.is_repeat && <span style={{fontSize:10, color:'var(--green)', fontFamily:'var(--mono)'}}>REPEAT BUYER</span>}
        </div>
        <div className="card-body">
          <div style={{display:'flex', gap:10, flexWrap:'wrap', marginBottom:12}}>
            {[
              { l:'COMPLETED', v: data.completed_deals, c:'var(--green)' },
              { l:'ACTIVE',    v: data.active_deals,    c:'var(--yellow)' },
              { l:'LOST',      v: data.lost_deals },
              { l:'TOTAL',     v: data.total_deals },
            ].map(({l,v,c}) => (
              <div key={l} style={{textAlign:'center', minWidth:56}}>
                <div style={{fontSize:9, color:'var(--dim)', fontFamily:'var(--mono)'}}>{l}</div>
                <div style={{fontSize:18, fontFamily:'var(--mono)', fontWeight:700, color:c||'var(--sub)'}}>{v}</div>
              </div>
            ))}
          </div>

          {data.top_products.length > 0 && (
            <div style={{fontSize:11, color:'var(--sub)', marginBottom:8}}>
              Products: {data.top_products.join(', ')}
            </div>
          )}

          {!editing ? (
            <div>
              {data.note && <div style={{fontSize:12, color:'var(--text)', marginBottom:6, fontStyle:'italic'}}>{data.note}</div>}
              {data.label && <div style={{fontSize:11, color:'var(--dim)'}}>Label: {data.label}</div>}
              <TagList tags={tags} />
              <button className="btn" style={{marginTop:10, fontSize:11}} onClick={() => setEditing(true)}>Edit Notes</button>
            </div>
          ) : (
            <div style={{display:'flex', flexDirection:'column', gap:8}}>
              <input className="inp" style={{fontSize:12}} placeholder="Label (short name)…"
                value={label} onChange={e => setLabel(e.target.value)} />
              <textarea className="inp" style={{minHeight:72, fontSize:12, resize:'vertical'}}
                placeholder="Private note…"
                value={note} onChange={e => setNote(e.target.value)} />
              <div style={{display:'flex', gap:6}}>
                <input className="inp" style={{flex:1, fontSize:11}} placeholder="Add tag…"
                  value={tagInput} onChange={e => setTagInput(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && addTag()} />
                <button className="btn" style={{fontSize:11}} onClick={addTag}>+</button>
              </div>
              {tags.length > 0 && (
                <div style={{display:'flex', gap:4, flexWrap:'wrap'}}>
                  {tags.map(t => (
                    <span key={t} style={{
                      fontSize:9, fontFamily:'var(--mono)', background:'var(--b2)',
                      color:'var(--sub)', padding:'1px 6px', cursor:'pointer',
                    }} onClick={() => setTags(ts => ts.filter(x => x !== t))}>
                      {t} ×
                    </span>
                  ))}
                </div>
              )}
              <div style={{display:'flex', gap:8}}>
                <button className="btn" style={{fontSize:11}} disabled={saving} onClick={save}>Save</button>
                <button className="btn" style={{fontSize:11}} onClick={() => setEditing(false)}>Cancel</button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Contract history */}
      {data.contracts.length > 0 && (
        <div className="card">
          <div className="card-head">Contract History</div>
          <div className="card-body" style={{padding:'8px 10px'}}>
            {data.contracts.map(c => (
              <div key={c.cid} style={{
                display:'flex', gap:8, padding:'5px 8px', marginBottom:3,
                background:'var(--s2)', alignItems:'center',
              }}>
                <a href={`/dashboard/contracts/${c.cid}`}
                   style={{fontSize:11, fontFamily:'var(--mono)', color:'var(--acc)', flexShrink:0}}>
                  #{c.cid}
                </a>
                <span style={{fontSize:11, color:'var(--sub)', flex:1, minWidth:0,
                               overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap'}}>
                  {c.iproduct || c.oproduct || '—'}
                </span>
                {c.thread_title && (
                  <span style={{fontSize:10, color:'var(--dim)', flex:1, minWidth:0,
                                 overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap'}}>
                    {c.thread_title.slice(0,40)}
                  </span>
                )}
                <span style={{
                  fontSize:9, fontFamily:'var(--mono)', flexShrink:0,
                  color: c.bucket === 'completed' ? 'var(--green)' : c.bucket === 'disputed' ? 'var(--red)' : 'var(--dim)',
                }}>
                  {c.bucket.replace('_',' ')}
                </span>
                <span style={{fontSize:10, color:'var(--dim)', fontFamily:'var(--mono)', flexShrink:0}}>
                  {relTime(c.dateline)}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

export default function MerchantCustomers() {
  const [customers, setCustomers] = useState([])
  const [loading, setLoading]     = useState(true)
  const [selected, setSelected]   = useState(null)
  const [search, setSearch]       = useState('')

  useEffect(() => {
    api.get('/api/merchant/customers')
      .then(d => { setCustomers(Array.isArray(d) ? d : []); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  if (selected) return <CustomerDetail cpUid={selected} onBack={() => setSelected(null)} />

  const filtered = search
    ? customers.filter(c =>
        (c.username || '').toLowerCase().includes(search.toLowerCase()) ||
        (c.uid || '').includes(search) ||
        (c.label || '').toLowerCase().includes(search.toLowerCase())
      )
    : customers

  return (
    <div>
      <input
        className="inp"
        style={{width:'100%', marginBottom:12, fontSize:12, boxSizing:'border-box'}}
        placeholder="Search by username, UID, or label…"
        value={search}
        onChange={e => setSearch(e.target.value)}
      />

      {loading
        ? <div className="empty"><div className="spin" /></div>
        : filtered.length === 0
          ? <div className="empty" style={{color:'var(--dim)'}}>No customers found.</div>
          : (
            <div className="mhq-card-list">
              {filtered.map(c => (
                <CustomerCard key={c.uid} c={c} onSelect={setSelected} />
              ))}
            </div>
          )
      }
    </div>
  )
}
