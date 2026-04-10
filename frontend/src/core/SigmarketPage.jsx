import { useState, useEffect, useCallback, useRef } from 'react'
import { api, throttledInterval } from './api.js'
import useStore from '../store.js'

// ── Helpers ───────────────────────────────────────────────────────────────────
const fmtDate = ts => ts ? new Date(ts * 1000).toLocaleDateString(undefined, {
  month: 'short', day: 'numeric', year: 'numeric'
}) : '--'

const fmtCountdown = secs => {
  if (secs <= 0) return 'Expired'
  const d = Math.floor(secs / 86400)
  const h = Math.floor((secs % 86400) / 3600)
  if (d > 0) return `${d}d ${h}h`
  return `${h}h ${Math.floor((secs % 3600) / 60)}m`
}

const ago = ts => {
  if (!ts) return '--'
  const d = Math.floor(Date.now() / 1000) - ts
  if (d < 3600)  return `${Math.floor(d / 60)}m ago`
  if (d < 86400) return `${Math.floor(d / 3600)}h ago`
  return `${Math.floor(d / 86400)}d ago`
}

const stripBBCode = s => (s || '').replace(/\[.*?\]/g, '').replace(/\s+/g, ' ').trim()

function usePolling(fn, ms) {
  const ref = useRef(fn); ref.current = fn
  useEffect(() => {
    if (!ms) return
    const id = setInterval(() => ref.current(), ms)
    return () => clearInterval(id)
  }, [ms])
}

function SigEditor({ value, onChange, placeholder }) {
  return (
    <textarea value={value} onChange={e => onChange(e.target.value)}
      placeholder={placeholder || 'BBCode\u2026'} spellCheck={false}
      style={{ width: '100%', minHeight: 80, padding: '8px 10px', boxSizing: 'border-box',
        background: 'var(--bg)', border: '1px solid var(--b2)', borderRadius: 4,
        color: 'var(--text)', fontFamily: 'var(--mono)', fontSize: 12, lineHeight: 1.6,
        resize: 'vertical', outline: 'none' }}
      onFocus={e => e.target.style.borderColor = 'var(--acc)'}
      onBlur={e  => e.target.style.borderColor = 'var(--b2)'} />
  )
}

// ── Your Listing ──────────────────────────────────────────────────────────────
function ListingSection({ status, onRefresh }) {
  const listing = status?.listing
  const [mode, setMode]    = useState('view')
  const [price, setPrice]  = useState('')
  const [dur, setDur]      = useState('')
  const [sig, setSig]      = useState('')
  const [busy, setBusy]    = useState(false)
  const [err, setErr]      = useState(null)
  const [ok, setOk]        = useState(null)

  useEffect(() => {
    setPrice(listing?.price || '')
    setDur(listing?.duration || '')
    setSig(listing?.sig || '')
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
    <div className="card">
      <div className="card-head">
        <span className="card-icon">&#x1F3F7;</span>
        <span className="card-title">Your Listing</span>
        {isListed && (
          <span style={{ marginLeft: 'auto', fontSize: 10, padding: '2px 8px', borderRadius: 3,
            background: 'rgba(0,212,180,.1)', border: '1px solid rgba(0,212,180,.25)',
            color: 'var(--acc)', fontFamily: 'var(--mono)' }}>ACTIVE</span>
        )}
      </div>
      <div className="card-body">
        {!listing || !isListed ? (
          <div>
            <div style={{ fontSize: 12, color: 'var(--dim)', marginBottom: 12 }}>
              You don't have an active sig listing.
            </div>
            {mode !== 'setsale' ? (
              <button className="btn btn-acc" style={{ fontSize: 11 }} onClick={() => setMode('setsale')}>List My Sig</button>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                  <div>
                    <div style={{ fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)', marginBottom: 4 }}>PRICE (bytes)</div>
                    <input className="inp" type="number" min="1" value={price}
                      onChange={e => setPrice(e.target.value)} placeholder="e.g. 500" />
                  </div>
                  <div>
                    <div style={{ fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)', marginBottom: 4 }}>DURATION (days)</div>
                    <input className="inp" type="number" min="1" value={dur}
                      onChange={e => setDur(e.target.value)} placeholder="e.g. 30" />
                  </div>
                </div>
                {err && <div style={{ fontSize: 11, color: 'var(--red)', fontFamily: 'var(--mono)' }}>&#x2715; {err}</div>}
                <div style={{ display: 'flex', gap: 6 }}>
                  <button className="btn btn-acc" style={{ fontSize: 11 }} disabled={busy || !price || !dur}
                    onClick={() => act('setsale', { price, duration: dur })}>
                    {busy ? '\u2026' : 'List Sig'}
                  </button>
                  <button className="btn btn-ghost" style={{ fontSize: 11 }} onClick={() => setMode('view')}>Cancel</button>
                </div>
              </div>
            )}
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 1,
              background: 'var(--b1)', borderRadius: 6, overflow: 'hidden', border: '1px solid var(--b1)' }}>
              {[
                { lbl: 'Price',    val: `${listing.price} bytes` },
                { lbl: 'Duration', val: `${listing.duration} days` },
                { lbl: 'PPD',      val: listing.ppd ? `${listing.ppd} bytes/day` : '--' },
              ].map(({ lbl, val }) => (
                <div key={lbl} style={{ background: 'var(--s2)', padding: '8px 12px' }}>
                  <div style={{ fontSize: 13, fontWeight: 600, fontFamily: 'var(--mono)', color: 'var(--text)' }}>{val}</div>
                  <div style={{ fontSize: 9, color: 'var(--sub)', textTransform: 'uppercase', letterSpacing: '.07em' }}>{lbl}</div>
                </div>
              ))}
            </div>
            {listing.sig && (
              <div>
                <div style={{ fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)', marginBottom: 6 }}>CURRENT SIG</div>
                <div style={{ padding: '8px 10px', background: 'var(--bg)', border: '1px solid var(--b2)',
                  borderRadius: 4, fontSize: 11, fontFamily: 'var(--mono)', color: 'var(--sub)',
                  whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>{listing.sig}</div>
              </div>
            )}
            {mode === 'changesig' ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <div style={{ fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)' }}>NEW SIG CONTENT</div>
                <SigEditor value={sig} onChange={setSig} />
                {err && <div style={{ fontSize: 11, color: 'var(--red)', fontFamily: 'var(--mono)' }}>&#x2715; {err}</div>}
                <div style={{ display: 'flex', gap: 6 }}>
                  <button className="btn btn-acc" style={{ fontSize: 11 }} disabled={busy || !sig.trim()}
                    onClick={() => act('changesig', { smid: 'all', sig })}>
                    {busy ? '\u2026' : 'Update All Orders'}
                  </button>
                  <button className="btn btn-ghost" style={{ fontSize: 11 }} onClick={() => setMode('view')}>Cancel</button>
                </div>
              </div>
            ) : mode === 'setsale' ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                  <div>
                    <div style={{ fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)', marginBottom: 4 }}>NEW PRICE</div>
                    <input className="inp" type="number" min="1" value={price} onChange={e => setPrice(e.target.value)} />
                  </div>
                  <div>
                    <div style={{ fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)', marginBottom: 4 }}>NEW DURATION</div>
                    <input className="inp" type="number" min="1" value={dur} onChange={e => setDur(e.target.value)} />
                  </div>
                </div>
                {err && <div style={{ fontSize: 11, color: 'var(--red)', fontFamily: 'var(--mono)' }}>&#x2715; {err}</div>}
                <div style={{ display: 'flex', gap: 6 }}>
                  <button className="btn btn-acc" style={{ fontSize: 11 }} disabled={busy || !price || !dur}
                    onClick={() => act('setsale', { price, duration: dur })}>
                    {busy ? '\u2026' : 'Update Listing'}
                  </button>
                  <button className="btn btn-ghost" style={{ fontSize: 11 }} onClick={() => setMode('view')}>Cancel</button>
                </div>
              </div>
            ) : (
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                <button className="btn btn-ghost" style={{ fontSize: 11 }} onClick={() => setMode('changesig')}>Update Sig</button>
                <button className="btn btn-ghost" style={{ fontSize: 11 }} onClick={() => setMode('setsale')}>Change Price</button>
                <button className="btn btn-danger" style={{ fontSize: 11 }} disabled={busy}
                  onClick={() => { if (window.confirm('Remove your sig listing?')) act('removesale', {}) }}>
                  {busy ? '\u2026' : 'Remove Listing'}
                </button>
              </div>
            )}
            {ok && <div style={{ fontSize: 11, color: 'var(--acc)', fontFamily: 'var(--mono)' }}>&#x2713; {ok}</div>}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Orders table ──────────────────────────────────────────────────────────────
function OrdersTable({ orders, partyKey, partyLabel, icon, title, count }) {
  const [now, setNow] = useState(Math.floor(Date.now() / 1000))
  useEffect(() => {
    const id = setInterval(() => setNow(Math.floor(Date.now() / 1000)), 60000)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="card">
      <div className="card-head">
        <span className="card-icon" dangerouslySetInnerHTML={{ __html: icon }} />
        <span className="card-title">{title}</span>
        <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)' }}>
          {count ?? 0} active
        </span>
      </div>
      <div className="card-body" style={{ padding: orders.length ? 0 : undefined }}>
        {!orders.length ? (
          <div style={{ fontSize: 12, color: 'var(--dim)', fontStyle: 'italic' }}>No orders yet</div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--b1)' }}>
                {[partyLabel, 'Started', 'Expires', 'Time Left', 'Price'].map(h => (
                  <th key={h} style={{ padding: '7px 14px', textAlign: 'left', fontSize: 9,
                    color: 'var(--dim)', fontFamily: 'var(--mono)', textTransform: 'uppercase',
                    letterSpacing: '.07em', fontWeight: 600 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {orders.map((o, i) => {
                const rem   = o.enddate - now
                const party = o[partyKey] || {}
                return (
                  <tr key={o.smid || i} style={{ borderBottom: '1px solid var(--b1)', opacity: rem <= 0 ? .5 : 1 }}>
                    <td style={{ padding: '8px 14px', fontWeight: 600 }}>
                      {party.username || `UID ${party.uid}` || '--'}
                    </td>
                    <td style={{ padding: '8px 14px', color: 'var(--sub)' }}>{fmtDate(o.startdate)}</td>
                    <td style={{ padding: '8px 14px', color: 'var(--sub)' }}>{fmtDate(o.enddate)}</td>
                    <td style={{ padding: '8px 14px' }}>
                      <span style={{ fontFamily: 'var(--mono)', fontSize: 11, fontWeight: 600,
                        color: rem <= 0 ? 'var(--red)' : rem < 86400 * 3 ? 'var(--yellow)' : 'var(--acc)' }}>
                        {fmtCountdown(rem)}
                      </span>
                    </td>
                    <td style={{ padding: '8px 14px', color: 'var(--sub)', fontFamily: 'var(--mono)' }}>
                      {o.price ? `${o.price}b` : '--'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

// ── My Purchases ──────────────────────────────────────────────────────────────
// Shows sig slots you've purchased from other users.
// Each order has an inline sig editor so you can push content into that slot
// via the sigmarket changesig API without leaving the dashboard.
function MyPurchasesSection({ orders, count, onRefresh }) {
  const [now, setNow] = useState(Math.floor(Date.now() / 1000))
  // Per-order sig editor state: { [smid]: { open, value, busy, ok, err } }
  const [editors, setEditors] = useState({})
  // Bulk "set all" editor state
  const [bulkOpen,  setBulkOpen]  = useState(false)
  const [bulkValue, setBulkValue] = useState('')
  const [bulkBusy,  setBulkBusy]  = useState(false)
  const [bulkOk,    setBulkOk]    = useState(false)
  const [bulkErr,   setBulkErr]   = useState(null)

  useEffect(() => {
    const id = setInterval(() => setNow(Math.floor(Date.now() / 1000)), 60000)
    return () => clearInterval(id)
  }, [])

  const setEditor = (smid, patch) =>
    setEditors(prev => ({ ...prev, [smid]: { ...(prev[smid] || {}), ...patch } }))

  const openEditor = (smid) => setEditor(smid, { open: true, value: '', ok: null, err: null })
  const closeEditor = (smid) => setEditor(smid, { open: false })

  const pushSig = async (smid) => {
    const ed = editors[smid] || {}
    setEditor(smid, { busy: true, ok: null, err: null })
    try {
      await api.post('/api/sigmarket/listing', {
        action: 'changesig',
        smid:   String(smid),
        sig:    ed.value || '',
      })
      setEditor(smid, { busy: false, ok: 'Signature updated!', open: false })
      setTimeout(() => setEditor(smid, { ok: null }), 4000)
      onRefresh()
    } catch (e) {
      setEditor(smid, { busy: false, err: e.message || 'Failed to update' })
    }
  }

  const pushAll = async () => {
    setBulkBusy(true); setBulkErr(null); setBulkOk(false)
    try {
      await api.post('/api/sigmarket/listing', {
        action: 'changesig',
        smid:   'all',
        sig:    bulkValue,
      })
      setBulkOk(true); setBulkOpen(false); setBulkValue('')
      setTimeout(() => setBulkOk(false), 4000)
      onRefresh()
    } catch (e) {
      setBulkErr(e.message || 'Failed to update')
    } finally {
      setBulkBusy(false)
    }
  }

  const activeCount = orders.filter(o => (o.enddate - now) > 0).length

  return (
    <div className="card">
      <div className="card-head">
        <span className="card-icon">🛒</span>
        <span className="card-title">My Purchases</span>
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
          {bulkOk && (
            <span style={{ fontSize: 11, color: 'var(--acc)', fontFamily: 'var(--mono)' }}>✓ All updated</span>
          )}
          <span style={{ fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)' }}>
            {count ?? 0} active
          </span>
          {activeCount > 1 && (
            <button className="btn btn-ghost" style={{ fontSize: 11, whiteSpace: 'nowrap' }}
              onClick={() => { setBulkOpen(o => !o); setBulkErr(null) }}>
              {bulkOpen ? 'Cancel' : 'Set All Sigs'}
            </button>
          )}
        </div>
      </div>
      {bulkOpen && (
        <div style={{ padding: '12px 14px', borderBottom: '1px solid var(--b1)',
          background: 'var(--s3)' }}>
          <div style={{ fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)',
            textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 6 }}>
            Push to all {activeCount} active slots (BBCode, max 255 chars)
          </div>
          <textarea
            value={bulkValue}
            onChange={e => setBulkValue(e.target.value)}
            placeholder="[align=center][img]https://...[/img][/align]"
            maxLength={255}
            spellCheck={false}
            style={{ width: '100%', minHeight: 72, padding: '8px 10px', boxSizing: 'border-box',
              background: 'var(--bg)', border: '1px solid var(--b2)', borderRadius: 4,
              color: 'var(--text)', fontFamily: 'var(--mono)', fontSize: 12,
              lineHeight: 1.6, resize: 'vertical', outline: 'none' }}
            onFocus={e => { e.target.style.borderColor = 'var(--acc)' }}
            onBlur={e  => { e.target.style.borderColor = 'var(--b2)'  }}
          />
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 8 }}>
            <button className="btn btn-acc" style={{ fontSize: 11 }}
              disabled={bulkBusy || !bulkValue.trim()}
              onClick={pushAll}>
              {bulkBusy ? '…' : `Update All ${activeCount} Slots`}
            </button>
            <span style={{ fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)' }}>
              {bulkValue.length}/255
            </span>
            {bulkErr && <span style={{ fontSize: 11, color: 'var(--red)' }}>{bulkErr}</span>}
          </div>
        </div>
      )}

      <div className="card-body" style={{ padding: orders.length ? 0 : undefined }}>
        {!orders.length ? (
          <div style={{ fontSize: 12, color: 'var(--dim)', fontStyle: 'italic' }}>
            No purchased sig slots yet.
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {orders.map((o, i) => {
              const rem     = o.enddate - now
              const seller  = o.seller || {}
              const ed      = editors[o.smid] || {}
              const expired = rem <= 0
              const urgent  = !expired && rem < 86400 * 3

              return (
                <div key={o.smid || i} style={{
                  borderBottom: '1px solid var(--b1)',
                  opacity: expired ? 0.55 : 1,
                }}>
                  {/* Order summary row */}
                  <div style={{
                    display: 'grid',
                    gridTemplateColumns: 'minmax(0,1.4fr) minmax(0,1fr) minmax(0,1fr) minmax(0,1fr) auto',
                    gap: 8, alignItems: 'center', padding: '10px 14px',
                  }}>
                    {/* Seller */}
                    <div>
                      <div style={{ fontSize: 12, fontWeight: 600 }}>
                        <a href={`https://hackforums.net/member.php?action=profile&uid=${seller.uid}`}
                          target="_blank" rel="noreferrer"
                          style={{ color: 'var(--acc)', textDecoration: 'none' }}>
                          {seller.username || `UID ${seller.uid}` || '--'}
                        </a>
                      </div>
                      <div style={{ fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)', marginTop: 2 }}>
                        {o.price ? `${o.price}b` : '--'} · {o.duration}d
                      </div>
                    </div>
                    {/* Started */}
                    <div style={{ fontSize: 11, color: 'var(--sub)' }}>
                      <div style={{ fontSize: 9, color: 'var(--dim)', fontFamily: 'var(--mono)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 2 }}>Started</div>
                      {fmtDate(o.startdate)}
                    </div>
                    {/* Expires */}
                    <div style={{ fontSize: 11, color: 'var(--sub)' }}>
                      <div style={{ fontSize: 9, color: 'var(--dim)', fontFamily: 'var(--mono)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 2 }}>Expires</div>
                      {fmtDate(o.enddate)}
                    </div>
                    {/* Time left */}
                    <div>
                      <div style={{ fontSize: 9, color: 'var(--dim)', fontFamily: 'var(--mono)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 2 }}>Time Left</div>
                      <span style={{
                        fontFamily: 'var(--mono)', fontSize: 11, fontWeight: 600,
                        color: expired ? 'var(--red)' : urgent ? 'var(--yellow)' : 'var(--acc)',
                      }}>
                        {fmtCountdown(rem)}
                      </span>
                    </div>
                    {/* Actions */}
                    <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                      {ed.ok && (
                        <span style={{ fontSize: 11, color: 'var(--acc)', fontFamily: 'var(--mono)' }}>✓</span>
                      )}
                      {!expired && (
                        <button
                          className="btn btn-ghost"
                          style={{ fontSize: 11, whiteSpace: 'nowrap' }}
                          onClick={() => ed.open ? closeEditor(o.smid) : openEditor(o.smid)}
                        >
                          {ed.open ? 'Cancel' : 'Set Sig'}
                        </button>
                      )}
                    </div>
                  </div>

                  {/* Inline sig editor */}
                  {ed.open && (
                    <div style={{ padding: '0 14px 14px', borderTop: '1px solid var(--b1)' }}>
                      <div style={{ fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)',
                        textTransform: 'uppercase', letterSpacing: '.06em', margin: '10px 0 6px' }}>
                        Sig content for {seller.username || seller.uid}'s slot (BBCode, max 255 chars)
                      </div>
                      <textarea
                        value={ed.value || ''}
                        onChange={e => setEditor(o.smid, { value: e.target.value })}
                        placeholder="[align=center][img]https://...[/img][/align]"
                        maxLength={255}
                        spellCheck={false}
                        style={{
                          width: '100%', minHeight: 72, padding: '8px 10px',
                          boxSizing: 'border-box', background: 'var(--bg)',
                          border: '1px solid var(--b2)', borderRadius: 4,
                          color: 'var(--text)', fontFamily: 'var(--mono)',
                          fontSize: 12, lineHeight: 1.6, resize: 'vertical', outline: 'none',
                        }}
                        onFocus={e => { e.target.style.borderColor = 'var(--acc)' }}
                        onBlur={e  => { e.target.style.borderColor = 'var(--b2)' }}
                      />
                      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 8 }}>
                        <button
                          className="btn btn-acc"
                          style={{ fontSize: 11 }}
                          disabled={ed.busy || !(ed.value || '').trim()}
                          onClick={() => pushSig(o.smid)}
                        >
                          {ed.busy ? '…' : 'Update Signature'}
                        </button>
                        <span style={{ fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)' }}>
                          {(ed.value || '').length}/255
                        </span>
                        {ed.err && (
                          <span style={{ fontSize: 11, color: 'var(--red)' }}>{ed.err}</span>
                        )}
                      </div>
                    </div>
                  )}

                  {/* Inline success toast */}
                  {ed.ok && !ed.open && (
                    <div style={{ padding: '6px 14px 10px' }}>
                      <span style={{ fontSize: 11, color: 'var(--acc)', fontFamily: 'var(--mono)' }}>
                        ✓ {ed.ok}
                      </span>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Buy modal ─────────────────────────────────────────────────────────────────
function BuyModal({ listing, onClose, onDone }) {
  const [busy, setBusy] = useState(false)
  const [err,  setErr]  = useState(null)

  const confirm = async () => {
    setBusy(true); setErr(null)
    try {
      await api.post('/api/sigmarket/buy', { uid: listing.uid, max_price: listing.price })
      onDone()
    } catch (e) { setErr(e.message || 'Purchase failed'); setBusy(false) }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.65)', zIndex: 200,
      display: 'flex', alignItems: 'center', justifyContent: 'center' }}
      onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      <div style={{ background: 'var(--s2)', border: '1px solid var(--b2)', borderRadius: 8,
        padding: 24, maxWidth: 380, width: '90%', display: 'flex', flexDirection: 'column', gap: 16 }}>
        <div style={{ fontSize: 15, fontWeight: 700, color: 'var(--text)' }}>Buy Sig Slot</div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {[
            ['Seller',   listing.username],
            ['Price',    `${listing.price} bytes`],
            ['Duration', `${listing.duration} days`],
            listing.ppd ? ['Per day', `${listing.ppd} bytes`] : null,
          ].filter(Boolean).map(([label, value]) => (
            <div key={label} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <span style={{ fontSize: 12, color: 'var(--sub)' }}>{label}</span>
              <span style={{ fontSize: 12, fontFamily: 'var(--mono)',
                fontWeight: label === 'Price' ? 700 : 400,
                color: label === 'Price' ? 'var(--acc)' : 'var(--text)' }}>{value}</span>
            </div>
          ))}
        </div>
        {listing.sig && (
          <div style={{ padding: '8px 10px', background: 'var(--bg)', border: '1px solid var(--b2)',
            borderRadius: 4, fontSize: 11, fontFamily: 'var(--mono)', color: 'var(--sub)',
            maxHeight: 80, overflow: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>
            {listing.sig}
          </div>
        )}
        <div style={{ fontSize: 11, color: 'var(--dim)', background: 'var(--s3)',
          border: '1px solid var(--b1)', borderRadius: 4, padding: '7px 10px' }}>
          Your ad will appear in <strong style={{ color: 'var(--sub)' }}>{listing.username}</strong>'s
          signature for {listing.duration} days.
        </div>
        {err && <div style={{ fontSize: 11, color: 'var(--red)', fontFamily: 'var(--mono)' }}>&#x2715; {err}</div>}
        <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
          <button className="btn btn-ghost" style={{ fontSize: 12 }} onClick={onClose} disabled={busy}>Cancel</button>
          <button className="btn btn-acc"   style={{ fontSize: 12 }} onClick={confirm} disabled={busy}>
            {busy ? '\u2026' : `Buy for ${listing.price}b`}
          </button>
        </div>
      </div>
    </div>
  )
}

// ── Browse Market ─────────────────────────────────────────────────────────────
function InfoModal({ listing, onClose, onBuyDone }) {
  const [busy, setBusy] = useState(false)
  const [err,  setErr]  = useState(null)
  const [ok,   setOk]   = useState(false)

  const ppd   = listing.ppd   ? parseFloat(listing.ppd).toFixed(2)   : '--'
  const pricePerDay = listing.price && listing.duration
    ? (parseInt(listing.price) / parseInt(listing.duration)).toFixed(2)
    : '--'

  const buy = async () => {
    setBusy(true); setErr(null)
    try {
      await api.post('/api/sigmarket/buy', { uid: listing.uid, max_price: listing.price })
      setOk(true)
      setTimeout(() => { onBuyDone(); onClose() }, 1200)
    } catch (e) { setErr(e.message || 'Purchase failed'); setBusy(false) }
  }

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.7)', zIndex: 200,
      display: 'flex', alignItems: 'center', justifyContent: 'center' }}
      onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      <div style={{ background: 'var(--s2)', border: '1px solid var(--b2)', borderRadius: 8,
        padding: 0, maxWidth: 420, width: '92%', overflow: 'hidden' }}>

        {/* Header */}
        <div style={{ padding: '14px 18px', borderBottom: '1px solid var(--b1)',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--text)' }}>Details</span>
          <button className="btn btn-ghost" style={{ fontSize: 11, padding: '2px 8px' }}
            onClick={onClose}>✕</button>
        </div>

        {/* User Stats */}
        <div style={{ padding: '12px 18px', borderBottom: '1px solid var(--b1)' }}>
          <div style={{ fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)',
            textTransform: 'uppercase', letterSpacing: '.07em', marginBottom: 10 }}>User Stats</div>
          {[
            ['User',        listing.username],
            ['UID',         listing.uid],
            ['Post Count',  parseInt(listing.postnum || 0).toLocaleString()],
            ['Reputation',  parseInt(listing.reputation || 0).toLocaleString()],
            ['Avg PPD',     `${ppd} posts/day`],
          ].map(([label, value]) => (
            <div key={label} style={{ display: 'flex', justifyContent: 'space-between',
              padding: '5px 0', borderBottom: '1px solid rgba(255,255,255,.04)' }}>
              <span style={{ fontSize: 12, color: 'var(--sub)' }}>{label}</span>
              <span style={{ fontSize: 12, color: 'var(--text)', fontWeight: label === 'User' ? 700 : 400 }}>{value}</span>
            </div>
          ))}
        </div>

        {/* Order Info */}
        <div style={{ padding: '12px 18px', borderBottom: '1px solid var(--b1)' }}>
          <div style={{ fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)',
            textTransform: 'uppercase', letterSpacing: '.07em', marginBottom: 10 }}>Order Information</div>
          {[
            ['Duration',    `${listing.duration} days`],
            ['Price',       `${parseInt(listing.price).toLocaleString()} bytes`],
            ['Rate',        `${parseInt(pricePerDay).toLocaleString()} bytes/day`],
          ].map(([label, value]) => (
            <div key={label} style={{ display: 'flex', justifyContent: 'space-between',
              padding: '5px 0', borderBottom: '1px solid rgba(255,255,255,.04)' }}>
              <span style={{ fontSize: 12, color: 'var(--sub)' }}>{label}</span>
              <span style={{ fontSize: 12, color: label === 'Price' ? 'var(--acc)' : 'var(--text)',
                fontFamily: 'var(--mono)', fontWeight: label === 'Price' ? 700 : 400 }}>{value}</span>
            </div>
          ))}
          {listing.sig && (
            <div style={{ marginTop: 10 }}>
              <div style={{ fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)', marginBottom: 5 }}>Sig Content</div>
              <div style={{ padding: '7px 10px', background: 'var(--bg)', border: '1px solid var(--b1)',
                borderRadius: 4, fontSize: 11, fontFamily: 'var(--mono)', color: 'var(--sub)',
                whiteSpace: 'pre-wrap', wordBreak: 'break-all', maxHeight: 90, overflow: 'auto' }}>
                {listing.sig}
              </div>
            </div>
          )}
        </div>

        {/* Buy */}
        <div style={{ padding: '14px 18px', display: 'flex', alignItems: 'center', gap: 12 }}>
          {ok ? (
            <span style={{ fontSize: 12, color: 'var(--acc)', fontFamily: 'var(--mono)' }}>✓ Purchase successful!</span>
          ) : (
            <>
              {err && <span style={{ fontSize: 11, color: 'var(--red)', fontFamily: 'var(--mono)', flex: 1 }}>✕ {err}</span>}
              <button className="btn btn-ghost" style={{ fontSize: 12 }} onClick={onClose} disabled={busy}>Cancel</button>
              <button className="btn btn-acc" style={{ fontSize: 12 }} onClick={buy} disabled={busy}>
                {busy ? '…' : `Buy — ${parseInt(listing.price).toLocaleString()}b`}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

function BrowseSection({ myUid }) {
  const browseData          = useStore(s => s.sigmarketBrowse)
  const fetchBrowse         = useStore(s => s.fetchSigmarketBrowse)
  const [loading,  setLoading]  = useState(!browseData)
  const [info,     setInfo]     = useState(null)
  const [buyOk,    setBuyOk]    = useState(null)
  const [err,      setErr]      = useState(null)

  const load = useCallback(async (force = false) => {
    if (!force && browseData) { setLoading(false); return }
    setLoading(true); setErr(null)
    try {
      await fetchBrowse(force)
    } catch (e) { setErr(e.message || 'Failed to load') }
    finally { setLoading(false) }
  }, [browseData])

  useEffect(() => { load(false) }, [])

  const listings = browseData?.listings || []
  const visible = listings.filter(l => String(l.uid) !== String(myUid))
  const hasOwn  = listings.some(l => String(l.uid) === String(myUid))

  const TH = ({ children, right }) => (
    <th style={{ padding: '8px 14px', textAlign: right ? 'right' : 'left', fontSize: 9,
      color: 'var(--dim)', fontFamily: 'var(--mono)', textTransform: 'uppercase',
      letterSpacing: '.07em', fontWeight: 600, borderBottom: '1px solid var(--b1)',
      whiteSpace: 'nowrap' }}>{children}</th>
  )

  return (
    <>
      {info && (
        <InfoModal
          listing={info}
          onClose={() => setInfo(null)}
          onBuyDone={() => { setBuyOk(info.username); setInfo(null); load(true) }}
        />
      )}
      <div className="card">
        <div className="card-head">
          <span className="card-icon">🛍</span>
          <span className="card-title">Browse Market</span>
          {!loading && (
            <span style={{ marginLeft: 8, fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)' }}>
              {visible.length} active
            </span>
          )}
          <button className="btn btn-ghost" style={{ marginLeft: 'auto', fontSize: 11 }}
            onClick={() => load(true)} disabled={loading}>
            {loading ? '…' : '↻'}
          </button>
        </div>
        <div className="card-body" style={{ padding: 0 }}>
          {buyOk && (
            <div style={{ margin: '12px 14px 0', fontSize: 12, color: 'var(--acc)',
              padding: '8px 12px', background: 'rgba(0,212,180,.08)',
              border: '1px solid rgba(0,212,180,.2)', borderRadius: 4, fontFamily: 'var(--mono)' }}>
              ✓ Purchased {buyOk}'s sig slot!
            </div>
          )}
          {err && (
            <div style={{ margin: '12px 14px 0', fontSize: 12, color: 'var(--red)' }}>✕ {err}</div>
          )}
          {hasOwn && (
            <div style={{ margin: '12px 14px 0', fontSize: 11, color: 'var(--dim)', padding: '6px 10px',
              background: 'var(--s3)', border: '1px solid var(--b1)', borderRadius: 4 }}>
              Your own listing is hidden.
            </div>
          )}
          {loading ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: 32 }}><div className="spin" /></div>
          ) : !visible.length ? (
            <div style={{ padding: '14px', fontSize: 12, color: 'var(--dim)', fontStyle: 'italic' }}>
              No active listings found.
            </div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                <thead>
                  <tr>
                    <TH>Username</TH>
                    <TH right>Posts</TH>
                    <TH right>Rep</TH>
                    <TH right>PPD</TH>
                    <TH right>Duration</TH>
                    <TH right>Price</TH>
                    <TH right>Price/Day</TH>
                    <TH></TH>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((l, i) => {
                    const pricePerDay = l.price && l.duration
                      ? Math.round(parseInt(l.price) / parseInt(l.duration)).toLocaleString()
                      : '--'
                    return (
                      <tr key={l.uid || i}
                        style={{ borderBottom: '1px solid var(--b1)', cursor: 'pointer' }}
                        onMouseEnter={e => e.currentTarget.style.background = 'var(--s3)'}
                        onMouseLeave={e => e.currentTarget.style.background = ''}>
                        <td style={{ padding: '10px 14px' }}>
                          <a href={`https://hackforums.net/member.php?action=profile&uid=${l.uid}`}
                            target="_blank" rel="noreferrer"
                            style={{ fontWeight: 700, color: 'var(--acc)', textDecoration: 'none' }}
                            onMouseEnter={e => e.target.style.textDecoration = 'underline'}
                            onMouseLeave={e => e.target.style.textDecoration = 'none'}>
                            {l.username}
                          </a>
                        </td>
                        <td style={{ padding: '10px 14px', textAlign: 'right', color: 'var(--sub)',
                          fontFamily: 'var(--mono)', fontSize: 11 }}>
                          {parseInt(l.postnum || 0).toLocaleString()}
                        </td>
                        <td style={{ padding: '10px 14px', textAlign: 'right', color: 'var(--sub)',
                          fontFamily: 'var(--mono)', fontSize: 11 }}>
                          {parseInt(l.reputation || 0).toLocaleString()}
                        </td>
                        <td style={{ padding: '10px 14px', textAlign: 'right', color: 'var(--sub)',
                          fontFamily: 'var(--mono)', fontSize: 11 }}>
                          {l.ppd ? `${parseFloat(l.ppd).toFixed(2)} ppd` : '--'}
                        </td>
                        <td style={{ padding: '10px 14px', textAlign: 'right', color: 'var(--sub)',
                          fontFamily: 'var(--mono)', fontSize: 11 }}>
                          {l.duration} days
                        </td>
                        <td style={{ padding: '10px 14px', textAlign: 'right',
                          fontFamily: 'var(--mono)', fontWeight: 700, color: 'var(--acc)' }}>
                          {parseInt(l.price).toLocaleString()}b
                        </td>
                        <td style={{ padding: '10px 14px', textAlign: 'right', color: 'var(--sub)',
                          fontFamily: 'var(--mono)', fontSize: 11 }}>
                          {pricePerDay}b/d
                        </td>
                        <td style={{ padding: '10px 14px', textAlign: 'right' }}>
                          <button className="btn btn-acc" style={{ fontSize: 11, padding: '3px 12px' }}
                            onClick={() => setInfo(l)}>
                            Info
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </>
  )
}


// ── Main Page ─────────────────────────────────────────────────────────────────
export default function SigmarketPage() {
  const [tab,        setTab]        = useState('mine')
  const [refreshing, setRefreshing] = useState(false)

  const myUid             = useStore(s => s.user?.uid)
  const throttle          = useStore(s => s.throttle)
  const status            = useStore(s => s.sigmarketStatus)
  const statusAt          = useStore(s => s.sigmarketStatusAt)
  const fetchStatus       = useStore(s => s.fetchSigmarketStatus)
  const invalidateStatus  = useStore(s => s.invalidateSigmarketStatus)

  // Initial load — serve from store if fresh, otherwise fetch
  useEffect(() => { fetchStatus(false) }, [])

  // Background polling — only re-fetches if TTL expired
  usePolling(() => fetchStatus(false), throttledInterval(300000, throttle))

  const refresh = async () => {
    setRefreshing(true)
    invalidateStatus()
    await fetchStatus(true)
    setTimeout(() => setRefreshing(false), 1500)
  }

  const ts = statusAt ? statusAt * 1000 : null

  // Show spinner only on true first load (no data at all yet)
  if (!status) return (
    <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}>
      <div className="spin" />
    </div>
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <div style={{ display: 'flex', gap: 4 }}>
          {[
            { id: 'mine',      label: 'My Listing' },
            { id: 'browse',    label: 'Browse Market' },
            { id: 'purchases', label: 'My Purchases' },
          ].map(t => (
            <button key={t.id} className={`tab${tab === t.id ? ' on' : ''}`}
              style={{ fontSize: 12 }} onClick={() => setTab(t.id)}>
              {t.label}
            </button>
          ))}
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
          {ts && (
            <span style={{ fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)' }}>
              {new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
          )}
          <button className="btn btn-ghost" style={{ fontSize: 11 }} disabled={refreshing} onClick={refresh}>
            {refreshing ? '\u2026' : '\u21bb Refresh'}
          </button>
        </div>
      </div>

      {tab === 'mine' && (
        <>
          <ListingSection status={status} onRefresh={refresh} />
          <OrdersTable
            orders={status?.seller_orders || []}
            partyKey="buyer" partyLabel="Buyer"
            icon="&#x1F4CB;" title="Active Orders"
            count={status?.active_order_count}
          />

        </>
      )}

      {tab === 'browse' && <BrowseSection myUid={myUid} />}

      {tab === 'purchases' && (
        <MyPurchasesSection
          orders={status?.buyer_orders || []}
          count={status?.active_buys}
          onRefresh={refresh}
        />
      )}
    </div>
  )
}
