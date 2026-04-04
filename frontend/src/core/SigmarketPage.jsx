import { useState, useEffect, useCallback, useRef } from 'react'
import { api } from './api.js'

// ── Helpers ───────────────────────────────────────────────────────────────────
const fmtDate = ts => ts ? new Date(ts * 1000).toLocaleDateString(undefined, { month:'short', day:'numeric', year:'numeric' }) : '--'
const fmtCountdown = secs => {
  if (secs <= 0) return 'Expired'
  const d = Math.floor(secs / 86400)
  const h = Math.floor((secs % 86400) / 3600)
  if (d > 0) return `${d}d ${h}h`
  const m = Math.floor((secs % 3600) / 60)
  return `${h}h ${m}m`
}

function usePolling(fn, ms) {
  const ref = useRef(fn); ref.current = fn
  useEffect(() => {
    if (!ms) return
    const id = setInterval(() => ref.current(), ms)
    return () => clearInterval(id)
  }, [ms])
}

// ── BBCode editor (minimal inline — just a textarea with mono font) ────────────
function SigEditor({ value, onChange, placeholder }) {
  return (
    <textarea
      value={value}
      onChange={e => onChange(e.target.value)}
      placeholder={placeholder || 'BBCode…'}
      spellCheck={false}
      style={{
        width:'100%', minHeight:80, padding:'8px 10px', boxSizing:'border-box',
        background:'var(--bg)', border:'1px solid var(--b2)', borderRadius:4,
        color:'var(--text)', fontFamily:'var(--mono)', fontSize:12, lineHeight:1.6,
        resize:'vertical', outline:'none',
      }}
      onFocus={e => e.target.style.borderColor='var(--acc)'}
      onBlur={e  => e.target.style.borderColor='var(--b2)'}
    />
  )
}

// ── Section: Your Listing ─────────────────────────────────────────────────────
function ListingSection({ status, onRefresh }) {
  const listing = status?.listing
  const [mode,     setMode]     = useState('view') // view | setsale | changesig
  const [price,    setPrice]    = useState(listing?.price    || '')
  const [duration, setDuration] = useState(listing?.duration || '')
  const [sig,      setSig]      = useState(listing?.sig      || '')
  const [busy,     setBusy]     = useState(false)
  const [err,      setErr]      = useState(null)
  const [ok,       setOk]       = useState(null)

  useEffect(() => {
    setPrice(listing?.price    || '')
    setDuration(listing?.duration || '')
    setSig(listing?.sig        || '')
  }, [listing])

  const act = async (action, body) => {
    setBusy(true); setErr(null); setOk(null)
    try {
      await api.post('/api/sigmarket/listing', { action, ...body })
      setOk('Done'); setMode('view'); onRefresh()
    } catch (e) { setErr(e.message || 'Error') }
    finally { setBusy(false) }
  }

  const isListed = listing && parseInt(listing.active || 0)

  return (
    <div className="card" style={{ marginBottom:0 }}>
      <div className="card-head">
        <span className="card-icon">🏷</span>
        <span className="card-title">Your Listing</span>
        {isListed && (
          <span style={{ marginLeft:'auto', fontSize:10, padding:'2px 8px', borderRadius:3,
            background:'rgba(0,212,180,.1)', border:'1px solid rgba(0,212,180,.25)', color:'var(--acc)',
            fontFamily:'var(--mono)' }}>ACTIVE</span>
        )}
      </div>
      <div className="card-body">
        {!listing || !isListed ? (
          <>
            <div style={{ fontSize:12, color:'var(--dim)', marginBottom:12 }}>
              You don't have an active sig listing.
            </div>
            {mode !== 'setsale' ? (
              <button className="btn btn-acc" style={{ fontSize:11 }} onClick={() => setMode('setsale')}>
                List My Sig
              </button>
            ) : (
              <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
                <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:8 }}>
                  <div>
                    <div style={{ fontSize:10, color:'var(--dim)', fontFamily:'var(--mono)', marginBottom:4 }}>PRICE (bytes)</div>
                    <input className="inp" type="number" min="1" value={price}
                      onChange={e => setPrice(e.target.value)} placeholder="e.g. 500" />
                  </div>
                  <div>
                    <div style={{ fontSize:10, color:'var(--dim)', fontFamily:'var(--mono)', marginBottom:4 }}>DURATION (days)</div>
                    <input className="inp" type="number" min="1" value={duration}
                      onChange={e => setDuration(e.target.value)} placeholder="e.g. 30" />
                  </div>
                </div>
                {err && <div style={{ fontSize:11, color:'var(--red)', fontFamily:'var(--mono)' }}>✕ {err}</div>}
                <div style={{ display:'flex', gap:6 }}>
                  <button className="btn btn-acc" style={{ fontSize:11 }} disabled={busy || !price || !duration}
                    onClick={() => act('setsale', { price, duration })}>
                    {busy ? '…' : 'List Sig'}
                  </button>
                  <button className="btn btn-ghost" style={{ fontSize:11 }} onClick={() => setMode('view')}>Cancel</button>
                </div>
              </div>
            )}
          </>
        ) : (
          <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
            {/* Current listing info */}
            <div style={{ display:'grid', gridTemplateColumns:'repeat(3,1fr)', gap:1,
              background:'var(--b1)', borderRadius:6, overflow:'hidden', border:'1px solid var(--b1)' }}>
              {[
                { lbl:'Price',    val: `${listing.price} bytes` },
                { lbl:'Duration', val: `${listing.duration} days` },
                { lbl:'PPD',      val: listing.ppd ? `${listing.ppd} bytes/day` : '--' },
              ].map(({ lbl, val }) => (
                <div key={lbl} style={{ background:'var(--s2)', padding:'8px 12px' }}>
                  <div style={{ fontSize:13, fontWeight:600, fontFamily:'var(--mono)', color:'var(--text)' }}>{val}</div>
                  <div style={{ fontSize:9, color:'var(--sub)', textTransform:'uppercase', letterSpacing:'.07em' }}>{lbl}</div>
                </div>
              ))}
            </div>

            {/* Current sig content */}
            {listing.sig && (
              <div>
                <div style={{ fontSize:10, color:'var(--dim)', fontFamily:'var(--mono)', marginBottom:6 }}>CURRENT SIG</div>
                <div style={{ padding:'8px 10px', background:'var(--bg)', border:'1px solid var(--b2)',
                  borderRadius:4, fontSize:11, fontFamily:'var(--mono)', color:'var(--sub)',
                  whiteSpace:'pre-wrap', wordBreak:'break-all' }}>
                  {listing.sig}
                </div>
              </div>
            )}

            {mode === 'changesig' ? (
              <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
                <div style={{ fontSize:10, color:'var(--dim)', fontFamily:'var(--mono)' }}>NEW SIG CONTENT</div>
                <SigEditor value={sig} onChange={setSig} />
                {err && <div style={{ fontSize:11, color:'var(--red)', fontFamily:'var(--mono)' }}>✕ {err}</div>}
                <div style={{ display:'flex', gap:6 }}>
                  <button className="btn btn-acc" style={{ fontSize:11 }} disabled={busy || !sig.trim()}
                    onClick={() => act('changesig', { smid:'all', sig })}>
                    {busy ? '…' : 'Update All Orders'}
                  </button>
                  <button className="btn btn-ghost" style={{ fontSize:11 }} onClick={() => setMode('view')}>Cancel</button>
                </div>
              </div>
            ) : mode === 'setsale' ? (
              <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
                <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:8 }}>
                  <div>
                    <div style={{ fontSize:10, color:'var(--dim)', fontFamily:'var(--mono)', marginBottom:4 }}>NEW PRICE</div>
                    <input className="inp" type="number" min="1" value={price} onChange={e => setPrice(e.target.value)} />
                  </div>
                  <div>
                    <div style={{ fontSize:10, color:'var(--dim)', fontFamily:'var(--mono)', marginBottom:4 }}>NEW DURATION</div>
                    <input className="inp" type="number" min="1" value={duration} onChange={e => setDuration(e.target.value)} />
                  </div>
                </div>
                {err && <div style={{ fontSize:11, color:'var(--red)', fontFamily:'var(--mono)' }}>✕ {err}</div>}
                <div style={{ display:'flex', gap:6 }}>
                  <button className="btn btn-acc" style={{ fontSize:11 }} disabled={busy || !price || !duration}
                    onClick={() => act('setsale', { price, duration })}>
                    {busy ? '…' : 'Update Listing'}
                  </button>
                  <button className="btn btn-ghost" style={{ fontSize:11 }} onClick={() => setMode('view')}>Cancel</button>
                </div>
              </div>
            ) : (
              <div style={{ display:'flex', gap:6, flexWrap:'wrap' }}>
                <button className="btn btn-ghost" style={{ fontSize:11 }} onClick={() => setMode('changesig')}>Update Sig</button>
                <button className="btn btn-ghost" style={{ fontSize:11 }} onClick={() => setMode('setsale')}>Change Price</button>
                <button className="btn btn-danger" style={{ fontSize:11 }} disabled={busy}
                  onClick={() => { if(confirm('Remove your sig listing?')) act('removesale', {}) }}>
                  {busy ? '…' : 'Remove Listing'}
                </button>
              </div>
            )}
            {ok && <div style={{ fontSize:11, color:'var(--acc)', fontFamily:'var(--mono)' }}>✓ {ok}</div>}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Section: Active Orders ────────────────────────────────────────────────────
function OrdersSection({ status }) {
  const orders = status?.seller_orders || []
  const [now, setNow] = useState(Math.floor(Date.now() / 1000))
  useEffect(() => {
    const id = setInterval(() => setNow(Math.floor(Date.now()/1000)), 60000)
    return () => clearInterval(id)
  }, [])

  if (!orders.length) {
    return (
      <div className="card">
        <div className="card-head"><span className="card-icon">📋</span><span className="card-title">Active Orders</span></div>
        <div className="card-body">
          <div style={{ fontSize:12, color:'var(--dim)', fontStyle:'italic' }}>No active orders</div>
        </div>
      </div>
    )
  }

  return (
    <div className="card">
      <div className="card-head">
        <span className="card-icon">📋</span>
        <span className="card-title">Active Orders</span>
        <span style={{ marginLeft:'auto', fontSize:10, color:'var(--dim)', fontFamily:'var(--mono)' }}>
          {status.active_order_count} active
        </span>
      </div>
      <div className="card-body" style={{ padding:0 }}>
        <table style={{ width:'100%', borderCollapse:'collapse', fontSize:12 }}>
          <thead>
            <tr style={{ borderBottom:'1px solid var(--b1)' }}>
              {['Buyer','Started','Expires','Days Left','Price'].map(h => (
                <th key={h} style={{ padding:'7px 14px', textAlign:'left', fontSize:9,
                  color:'var(--dim)', fontFamily:'var(--mono)', textTransform:'uppercase',
                  letterSpacing:'.07em', fontWeight:600 }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {orders.map((o, i) => {
              const remaining = o.enddate - now
              const expired   = remaining <= 0
              return (
                <tr key={o.smid || i} style={{ borderBottom:'1px solid var(--b1)',
                  opacity: expired ? .5 : 1 }}>
                  <td style={{ padding:'8px 14px', fontWeight:600 }}>
                    {o.buyer?.username || `UID ${o.buyer?.uid}` || '--'}
                  </td>
                  <td style={{ padding:'8px 14px', color:'var(--sub)' }}>{fmtDate(o.startdate)}</td>
                  <td style={{ padding:'8px 14px', color:'var(--sub)' }}>{fmtDate(o.enddate)}</td>
                  <td style={{ padding:'8px 14px' }}>
                    <span style={{
                      fontFamily:'var(--mono)', fontSize:11, fontWeight:600,
                      color: expired ? 'var(--red)' : remaining < 86400*3 ? 'var(--yellow)' : 'var(--acc)',
                    }}>
                      {fmtCountdown(remaining)}
                    </span>
                  </td>
                  <td style={{ padding:'8px 14px', color:'var(--sub)', fontFamily:'var(--mono)' }}>
                    {o.price ? `${o.price}b` : '--'}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}

// ── Section: Auto-Rotate ──────────────────────────────────────────────────────
function RotationSection({ activeOrderCount }) {
  const [rot,      setRot]      = useState(null)
  const [loading,  setLoading]  = useState(true)
  const [sigs,     setSigs]     = useState([])
  const [interval, setInterval_] = useState(6)
  const [enabled,  setEnabled]  = useState(false)
  const [editing,  setEditing]  = useState(null) // index being edited
  const [editVal,  setEditVal]  = useState('')
  const [busy,     setBusy]     = useState(false)
  const [saved,    setSaved]    = useState(false)
  const [err,      setErr]      = useState(null)
  const dragIdx   = useRef(null)

  const load = useCallback(() => {
    api.get('/api/sigmarket/rotation')
      .then(d => {
        setRot(d)
        setSigs(d.sigs || [])
        setInterval_(d.interval_h || 6)
        setEnabled(!!d.enabled)
        setLoading(false)
      }).catch(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

  const save = async () => {
    setBusy(true); setErr(null); setSaved(false)
    try {
      await api.post('/api/sigmarket/rotation', { sigs, interval_h: interval, enabled })
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (e) { setErr(e.message || 'Error') }
    finally { setBusy(false) }
  }

  const toggle = async (val) => {
    setEnabled(val)
    try { await api.post('/api/sigmarket/rotation/toggle', { enabled: val }) }
    catch { setEnabled(!val) }
  }

  const addSig   = ()      => setSigs(s => [...s, ''])
  const removeSig = idx    => setSigs(s => s.filter((_, i) => i !== idx))
  const updateSig = (idx, v) => setSigs(s => s.map((x, i) => i === idx ? v : x))

  const onDragStart = idx => { dragIdx.current = idx }
  const onDragOver  = (e, idx) => {
    e.preventDefault()
    if (dragIdx.current === null || dragIdx.current === idx) return
    const next = [...sigs]
    const [moved] = next.splice(dragIdx.current, 1)
    next.splice(idx, 0, moved)
    dragIdx.current = idx
    setSigs(next)
  }
  const onDragEnd = () => { dragIdx.current = null }

  if (loading) return <div className="card"><div className="card-body"><div className="spin"/></div></div>

  const canEnable = sigs.filter(s => s.trim()).length >= 2

  return (
    <div className="card">
      <div className="card-head">
        <span className="card-icon">🔄</span>
        <span className="card-title">Auto-Rotate</span>
        <div style={{ marginLeft:'auto', display:'flex', alignItems:'center', gap:8 }}>
          {!canEnable && (
            <span style={{ fontSize:10, color:'var(--dim)', fontFamily:'var(--mono)' }}>
              need ≥2 sigs
            </span>
          )}
          <button
            className={`tog${!enabled ? ' off' : ''}`}
            disabled={!canEnable}
            onClick={() => toggle(!enabled)}
            title={canEnable ? (enabled ? 'Disable rotation' : 'Enable rotation') : 'Add at least 2 sigs first'}
          />
        </div>
      </div>
      <div className="card-body" style={{ display:'flex', flexDirection:'column', gap:14 }}>

        {/* Info banner */}
        <div style={{ fontSize:11, color:'var(--dim)', padding:'7px 10px',
          background:'var(--s3)', border:'1px solid var(--b1)', borderRadius:4 }}>
          Rotation only fires when you have <strong style={{color:'var(--sub)'}}>active orders</strong> and
          the interval has elapsed. Currently{' '}
          <strong style={{ color: activeOrderCount > 0 ? 'var(--acc)' : 'var(--dim)' }}>
            {activeOrderCount} active order{activeOrderCount !== 1 ? 's' : ''}
          </strong>.
        </div>

        {/* Interval */}
        <div style={{ display:'flex', alignItems:'center', gap:10 }}>
          <span style={{ fontSize:11, color:'var(--sub)', minWidth:80 }}>Rotate every</span>
          <input className="inp" type="number" min="1" max="168" value={interval}
            onChange={e => setInterval_(Math.max(1, parseInt(e.target.value) || 1))}
            style={{ width:64 }} />
          <span style={{ fontSize:11, color:'var(--sub)' }}>hours</span>
        </div>

        {/* Last rotated */}
        {rot?.last_rotated > 0 && (
          <div style={{ fontSize:11, color:'var(--dim)', fontFamily:'var(--mono)' }}>
            Last rotated: {fmtDate(rot.last_rotated)} · Current idx: {rot.current_idx}
          </div>
        )}

        {/* Sig list */}
        <div>
          <div style={{ fontSize:10, color:'var(--dim)', fontFamily:'var(--mono)',
            textTransform:'uppercase', letterSpacing:'.07em', marginBottom:8 }}>
            Sig Variants (drag to reorder)
          </div>
          <div style={{ display:'flex', flexDirection:'column', gap:6 }}>
            {sigs.map((s, i) => (
              <div key={i} draggable
                onDragStart={() => onDragStart(i)}
                onDragOver={e => onDragOver(e, i)}
                onDragEnd={onDragEnd}
                style={{ display:'flex', gap:6, alignItems:'flex-start',
                  padding:'8px 10px', background:'var(--s3)',
                  border:`1px solid ${rot?.current_idx === i && enabled ? 'var(--acc)' : 'var(--b2)'}`,
                  borderRadius:4, cursor:'grab' }}>
                <div style={{ display:'flex', flexDirection:'column', alignItems:'center',
                  gap:2, paddingTop:2, minWidth:18 }}>
                  <span style={{ fontSize:9, color:'var(--dim)', fontFamily:'var(--mono)', fontWeight:700 }}>
                    {i + 1}
                  </span>
                  {rot?.current_idx === i && enabled && (
                    <span style={{ fontSize:8, color:'var(--acc)', fontFamily:'var(--mono)' }}>NOW</span>
                  )}
                </div>
                {editing === i ? (
                  <div style={{ flex:1, display:'flex', flexDirection:'column', gap:6 }}>
                    <SigEditor value={editVal} onChange={setEditVal} />
                    <div style={{ display:'flex', gap:5 }}>
                      <button className="btn btn-acc" style={{ fontSize:10, padding:'2px 10px' }}
                        onClick={() => { updateSig(i, editVal); setEditing(null) }}>Save</button>
                      <button className="btn btn-ghost" style={{ fontSize:10, padding:'2px 10px' }}
                        onClick={() => setEditing(null)}>Cancel</button>
                    </div>
                  </div>
                ) : (
                  <div style={{ flex:1, fontFamily:'var(--mono)', fontSize:11, color:'var(--sub)',
                    whiteSpace:'pre-wrap', wordBreak:'break-all', minHeight:24 }}>
                    {s || <em style={{ color:'var(--dim)' }}>empty</em>}
                  </div>
                )}
                <div style={{ display:'flex', gap:4, paddingTop:2 }}>
                  <button className="btn btn-ghost" style={{ fontSize:10, padding:'1px 7px' }}
                    onClick={() => { setEditVal(s); setEditing(i) }}>Edit</button>
                  <button className="btn btn-danger" style={{ fontSize:10, padding:'1px 7px' }}
                    onClick={() => removeSig(i)}>✕</button>
                </div>
              </div>
            ))}
            <button className="btn btn-ghost" style={{ fontSize:11, alignSelf:'flex-start' }}
              onClick={addSig}>+ Add Sig Variant</button>
          </div>
        </div>

        {err    && <div style={{ fontSize:11, color:'var(--red)',  fontFamily:'var(--mono)' }}>✕ {err}</div>}
        {saved  && <div style={{ fontSize:11, color:'var(--acc)',  fontFamily:'var(--mono)' }}>✓ Saved</div>}

        <button className="btn btn-acc" style={{ fontSize:11, alignSelf:'flex-start' }}
          disabled={busy} onClick={save}>
          {busy ? '…' : 'Save Config'}
        </button>
      </div>
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function SigmarketPage() {
  const [status,     setStatus]     = useState(null)
  const [loading,    setLoading]    = useState(true)
  const [ts,         setTs]         = useState(null)
  const [refreshing, setRefreshing] = useState(false)

  const load = useCallback((force = false) => {
    const url = '/api/sigmarket/status' + (force ? '?force=true' : '')
    api.get(url)
      .then(d => { setStatus(d); setLoading(false); setTs(Date.now()) })
      .catch(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])
  usePolling(() => load(false), 300000)

  const refresh = () => { setRefreshing(true); load(true); setTimeout(() => setRefreshing(false), 2000) }

  if (loading) return (
    <div style={{ display:'flex', justifyContent:'center', padding:40 }}>
      <div className="spin" />
    </div>
  )

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
      <div style={{ display:'flex', alignItems:'center', justifyContent:'flex-end', gap:8 }}>
        {ts && <span style={{ fontSize:10, color:'var(--dim)', fontFamily:'var(--mono)' }}>
          cached · {new Date(ts).toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'})}
        </span>}
        <button className="btn btn-ghost" style={{ fontSize:11 }} disabled={refreshing} onClick={refresh}>
          {refreshing ? '…' : '↻ Refresh'}
        </button>
      </div>
      <ListingSection  status={status} onRefresh={refresh} />
      <OrdersSection   status={status} />
      <RotationSection activeOrderCount={status?.active_order_count || 0} />
    </div>
  )
}
