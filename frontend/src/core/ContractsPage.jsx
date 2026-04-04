import { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from './api.js'
import useStore from '../store.js'

const ago = ts => {
  if (!ts) return '--'
  const d = Math.floor(Date.now()/1000) - ts
  if (d < 60) return `${d}s ago`
  if (d < 3600) return `${Math.floor(d/60)}m ago`
  if (d < 86400) return `${Math.floor(d/3600)}h ago`
  return `${Math.floor(d/86400)}d ago`
}

function usePolling(fn, ms) {
  const ref = useRef(fn); ref.current = fn
  useEffect(() => {
    if (ms == null) return  // null = paused
    const id = setInterval(() => ref.current(), ms)
    return () => clearInterval(id)
  }, [ms])
}

const STATUS_COLORS = {
  'Active Deal':       'var(--acc)',
  'Complete':          'var(--sub)',
  'Awaiting Approval': 'var(--yellow)',
  'Disputed':          'var(--red)',
  'Expired':           'rgba(255,71,87,.55)',
  'Cancelled':         'var(--dim)',
  'Unknown':           'var(--dim)',
}
const STATUS_BORDER = {
  'Active Deal':       'var(--acc)',
  'Complete':          'var(--sub)',
  'Awaiting Approval': 'var(--yellow)',
  'Disputed':          'var(--red)',
  'Expired':           'rgba(255,71,87,.45)',
  'Cancelled':         'var(--dim)',
  'Unknown':           'transparent',
}
const STATUS_BG = {
  'Active Deal':       'rgba(0,212,180,.03)',
  'Disputed':          'rgba(255,71,87,.04)',
  'Awaiting Approval': 'rgba(255,165,2,.03)',
  'Expired':           'rgba(255,71,87,.02)',
}



// Display value for a contract — "None None" → "--", Vouch Copy label
function displayValue(c) {
  const v = c.value
  if (!v || v === 'None None' || v.toLowerCase() === 'none none' || v === '--') {
    return c.type === 'Vouch Copy' ? 'Vouch Copy' : '--'
  }
  return v
}

// ── Contract Templates ────────────────────────────────────────────────────────
const POSITIONS = ['selling','buying','exchanging','trading','vouchcopy']
const CURRENCIES = ['other','USD','BTC','ETH','LTC','bytes']

const POSITION_LABELS = {
  selling:    'Selling',
  buying:     'Buying',
  exchanging: 'Exchanging',
  trading:    'Trading',
  vouchcopy:  'Vouch Copy',
}

// What fields each position needs:
// selling:    yourproduct + theircurrency + theiramount
// buying:     yourcurrency + youramount + theirproduct
// exchanging: yourcurrency + youramount + theircurrency + theiramount
// trading:    yourproduct + theirproduct
// vouchcopy:  (nothing — no product/currency fields)

function CurrencyAmountFields({ label, currKey, amtKey, form, set, inp, lbl, sel }) {
  return (
    <div style={{ display:'flex', flexDirection:'column', gap:6 }}>
      <div style={{ fontSize:9, color:'var(--sub)', fontFamily:'var(--mono)', textTransform:'uppercase', letterSpacing:'.07em' }}>{label}</div>
      <div>
        <label {...lbl}>Currency</label>
        <select {...sel} value={form[currKey]} onChange={e => set(currKey, e.target.value)}>
          {CURRENCIES.map(c => <option key={c} value={c}>{c}</option>)}
        </select>
      </div>
      <div>
        <label {...lbl}>Amount</label>
        <input {...inp} value={form[amtKey]} onChange={e => set(amtKey, e.target.value)} placeholder="0" />
      </div>
    </div>
  )
}

function ProductField({ label, fieldKey, form, set, inp, lbl, placeholder }) {
  return (
    <div>
      <div style={{ fontSize:9, color:'var(--sub)', fontFamily:'var(--mono)', textTransform:'uppercase', letterSpacing:'.07em', marginBottom:4 }}>{label}</div>
      <label {...lbl}>Product / Description</label>
      <input {...inp} value={form[fieldKey]} onChange={e => set(fieldKey, e.target.value)} placeholder={placeholder} />
    </div>
  )
}

function TemplateForm({ initial, onSave, onCancel }) {
  const [form, setForm] = useState({
    name: '', position: 'selling', terms: '',
    yourproduct: '', yourcurrency: 'other', youramount: '0',
    theirproduct: '', theircurrency: 'other', theiramount: '0',
    address: '', middleman_uid: '',
    timeout_days: 14, is_public: false,
    ...initial,
  })
  const [busy, setBusy] = useState(false)
  const [err,  setErr]  = useState(null)
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const submit = async () => {
    if (!form.name.trim()) { setErr('Name is required'); return }
    if (!form.terms.trim()) { setErr('Terms are required'); return }
    setBusy(true); setErr(null)
    try { await onSave(form) }
    catch (e) { setErr(e.message || 'Error') }
    finally { setBusy(false) }
  }

  const inp = { className:'inp', style:{ fontSize:11, width:'100%', boxSizing:'border-box' } }
  const lbl = { style:{ fontSize:9, color:'var(--dim)', fontFamily:'var(--mono)', textTransform:'uppercase', letterSpacing:'.07em', marginBottom:4, display:'block' } }
  const sel = { className:'inp', style:{ fontSize:11, width:'100%', boxSizing:'border-box', cursor:'pointer' } }
  const pos = form.position
  const shared = { form, set, inp, lbl, sel }

  // Render the position-specific fields
  const renderPositionFields = () => {
    if (pos === 'vouchcopy') {
      return (
        <div style={{ padding:'10px 12px', background:'var(--s2)', border:'1px solid var(--b1)', borderRadius:4,
          fontSize:11, color:'var(--sub)', fontStyle:'italic', textAlign:'center' }}>
          Vouch Copy — no product or currency fields needed
        </div>
      )
    }
    if (pos === 'selling') {
      return (
        <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16 }}>
          <ProductField label="Your Product / Service" fieldKey="yourproduct" placeholder="e.g. 30-day Spotify slot" {...shared} />
          <CurrencyAmountFields label="Their Payment" currKey="theircurrency" amtKey="theiramount" {...shared} />
        </div>
      )
    }
    if (pos === 'buying') {
      return (
        <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16 }}>
          <CurrencyAmountFields label="Your Payment" currKey="yourcurrency" amtKey="youramount" {...shared} />
          <ProductField label="Their Product / Service" fieldKey="theirproduct" placeholder="e.g. 30-day Spotify slot" {...shared} />
        </div>
      )
    }
    if (pos === 'exchanging') {
      return (
        <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16 }}>
          <CurrencyAmountFields label="Your Currency / Amount" currKey="yourcurrency" amtKey="youramount" {...shared} />
          <CurrencyAmountFields label="Their Currency / Amount" currKey="theircurrency" amtKey="theiramount" {...shared} />
        </div>
      )
    }
    if (pos === 'trading') {
      return (
        <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16 }}>
          <ProductField label="Your Product / Service" fieldKey="yourproduct" placeholder="e.g. Your item" {...shared} />
          <ProductField label="Their Product / Service" fieldKey="theirproduct" placeholder="e.g. Their item" {...shared} />
        </div>
      )
    }
    return null
  }

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
      {/* Name + Position */}
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:10 }}>
        <div>
          <label {...lbl}>Template Name</label>
          <input {...inp} value={form.name} onChange={e => set('name', e.target.value)} placeholder="e.g. Standard Service Sale" />
        </div>
        <div>
          <label {...lbl}>Position</label>
          <select {...sel} value={form.position} onChange={e => set('position', e.target.value)}>
            {POSITIONS.map(p => <option key={p} value={p}>{POSITION_LABELS[p]}</option>)}
          </select>
        </div>
      </div>

      {/* Position-specific product/currency fields */}
      {renderPositionFields()}

      {/* Terms */}
      <div>
        <label {...lbl}>Contract Terms</label>
        <textarea {...inp} style={{ ...inp.style, minHeight:100, fontFamily:'var(--mono)', resize:'vertical' }}
          value={form.terms} onChange={e => set('terms', e.target.value)}
          placeholder="Full contract terms…" spellCheck={false}
          onFocus={e => e.target.style.borderColor='var(--acc)'}
          onBlur={e  => e.target.style.borderColor='var(--b2)'}
        />
      </div>

      {/* Address + Middleman */}
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:10 }}>
        <div>
          <label {...lbl}>Payment Address <span style={{ color:'var(--dim)' }}>(optional)</span></label>
          <input {...inp} value={form.address} onChange={e => set('address', e.target.value)} placeholder="e.g. crypto wallet / autobuy link" />
        </div>
        <div>
          <label {...lbl}>Middleman UID <span style={{ color:'var(--dim)' }}>(optional)</span></label>
          <input {...inp} value={form.middleman_uid} onChange={e => set('middleman_uid', e.target.value)} placeholder="UID of middleman/escrow" />
        </div>
      </div>

      {/* Timeout + Public */}
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:10 }}>
        <div>
          <label {...lbl}>Timeout (days)</label>
          <input {...inp} type="number" min="1" max="90" value={form.timeout_days}
            onChange={e => set('timeout_days', parseInt(e.target.value) || 14)} />
        </div>
        <div style={{ display:'flex', alignItems:'center', gap:8, paddingTop:16 }}>
          <button className={`tog${!form.is_public ? ' off' : ''}`}
            onClick={() => set('is_public', !form.is_public)} />
          <span style={{ fontSize:11, color:'var(--sub)' }}>
            {form.is_public ? 'Public (visible to all users)' : 'Private (only you)'}
          </span>
        </div>
      </div>

      {err && <div style={{ fontSize:11, color:'var(--red)', fontFamily:'var(--mono)' }}>✕ {err}</div>}
      <div style={{ display:'flex', gap:6 }}>
        <button className="btn btn-acc" style={{ fontSize:11 }} disabled={busy} onClick={submit}>
          {busy ? '…' : initial ? 'Save Changes' : 'Create Template'}
        </button>
        <button className="btn btn-ghost" style={{ fontSize:11 }} onClick={onCancel}>Cancel</button>
      </div>
    </div>
  )
}

function FireModal({ template, onClose }) {
  const [cpUid,    setCpUid]    = useState('')
  const [threadId, setThreadId] = useState('')
  const [busy,     setBusy]     = useState(false)
  const [result,   setResult]   = useState(null)
  const [err,      setErr]      = useState(null)

  const fire = async () => {
    if (!cpUid) { setErr('Counterparty UID required'); return }
    setBusy(true); setErr(null)
    try {
      const d = await api.post(`/api/contracts/templates/${template.id}/fire`, {
        counterparty_uid: parseInt(cpUid),
        thread_id: threadId ? parseInt(threadId) : undefined,
      })
      setResult(d)
    } catch (e) { setErr(e.message || 'Failed to create contract') }
    finally { setBusy(false) }
  }

  return (
    <div style={{
      position:'fixed', inset:0, zIndex:500, background:'rgba(0,0,0,.65)',
      display:'flex', alignItems:'center', justifyContent:'center',
    }} onClick={e => { if(e.target===e.currentTarget) onClose() }}>
      <div style={{
        background:'var(--s2)', border:'1px solid var(--b2)', borderRadius:8,
        width:'min(420px,94vw)', padding:20, boxShadow:'0 12px 40px rgba(0,0,0,.6)',
      }}>
        {result ? (
          <div style={{ display:'flex', flexDirection:'column', gap:12, textAlign:'center' }}>
            <div style={{ fontSize:24 }}>✓</div>
            <div style={{ fontSize:14, fontWeight:600 }}>Contract Created</div>
            {result.cid && (
              <div style={{ fontSize:12, color:'var(--dim)', fontFamily:'var(--mono)' }}>CID: {result.cid}</div>
            )}
            {result.url && (
              <a href={result.url} target="_blank" rel="noreferrer"
                className="btn btn-acc" style={{ fontSize:12, textAlign:'center' }}>
                View on HF →
              </a>
            )}
            <button className="btn btn-ghost" style={{ fontSize:11 }} onClick={onClose}>Close</button>
          </div>
        ) : (
          <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
            <div style={{ fontSize:13, fontWeight:600 }}>
              Use Template: <span style={{ color:'var(--acc)' }}>{template.name}</span>
            </div>
            <div style={{ fontSize:11, color:'var(--dim)', padding:'6px 10px',
              background:'var(--s3)', border:'1px solid var(--b1)', borderRadius:4 }}>
              <strong style={{ color:'var(--sub)' }}>{template.position}</strong>
              {template.yourproduct && ` · ${template.yourproduct}`}
            </div>
            <div>
              <label style={{ fontSize:10, color:'var(--dim)', fontFamily:'var(--mono)',
                textTransform:'uppercase', letterSpacing:'.07em', marginBottom:4, display:'block' }}>
                Counterparty UID *
              </label>
              <input className="inp" style={{ fontSize:12, width:'100%', boxSizing:'border-box' }}
                value={cpUid} onChange={e => setCpUid(e.target.value)}
                placeholder="e.g. 123456" autoFocus
                onKeyDown={e => { if(e.key==='Enter') fire() }} />
            </div>
            <div>
              <label style={{ fontSize:10, color:'var(--dim)', fontFamily:'var(--mono)',
                textTransform:'uppercase', letterSpacing:'.07em', marginBottom:4, display:'block' }}>
                Thread ID (optional)
              </label>
              <input className="inp" style={{ fontSize:12, width:'100%', boxSizing:'border-box' }}
                value={threadId} onChange={e => setThreadId(e.target.value)}
                placeholder="e.g. 5847344" />
            </div>
            {err && <div style={{ fontSize:11, color:'var(--red)', fontFamily:'var(--mono)' }}>✕ {err}</div>}
            <div style={{ display:'flex', gap:6 }}>
              <button className="btn btn-acc" style={{ fontSize:12, flex:1 }} disabled={busy||!cpUid} onClick={fire}>
                {busy ? '…' : 'Create Contract'}
              </button>
              <button className="btn btn-ghost" style={{ fontSize:12 }} onClick={onClose}>Cancel</button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

function TemplatesPanel({ myUid }) {
  const [templates, setTemplates] = useState([])
  const [loading,   setLoading]   = useState(true)
  const [mode,      setMode]      = useState('list') // list | create | edit
  const [editing,   setEditing]   = useState(null)
  const [firing,    setFiring]    = useState(null)

  const load = useCallback(() => {
    api.get('/api/contracts/templates')
      .then(d => { setTemplates(d.templates || []); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  useEffect(() => { load() }, [load])

  const createTemplate = async (data) => {
    await api.post('/api/contracts/templates', data)
    load(); setMode('list')
  }

  const saveTemplate = async (data) => {
    await api.patch(`/api/contracts/templates/${editing.id}`, data)
    load(); setMode('list'); setEditing(null)
  }

  const deleteTemplate = async (id) => {
    if (!confirm('Delete this template?')) return
    await api.delete(`/api/contracts/templates/${id}`)
    load()
  }

  if (loading) return <div style={{ display:'flex', justifyContent:'center', padding:30 }}><div className="spin"/></div>

  if (mode === 'create') return (
    <div>
      <div style={{ fontSize:12, fontWeight:600, marginBottom:14 }}>New Template</div>
      <TemplateForm onSave={createTemplate} onCancel={() => setMode('list')} />
    </div>
  )

  if (mode === 'edit' && editing) return (
    <div>
      <div style={{ fontSize:12, fontWeight:600, marginBottom:14 }}>Edit Template</div>
      <TemplateForm initial={editing} onSave={saveTemplate} onCancel={() => { setMode('list'); setEditing(null) }} />
    </div>
  )

  const mine  = templates.filter(t => t.uid === myUid)
  const pub   = templates.filter(t => t.uid !== myUid && t.is_public)

  const TemplateCard = ({ t }) => (
    <div style={{
      padding:'12px 14px', background:'var(--s3)',
      border:'1px solid var(--b2)', borderRadius:6,
      display:'flex', flexDirection:'column', gap:8,
    }}>
      <div style={{ display:'flex', alignItems:'center', gap:8 }}>
        <span style={{ fontWeight:600, fontSize:12, flex:1 }}>{t.name}</span>
        {t.is_public && (
          <span style={{ fontSize:9, padding:'1px 6px', borderRadius:2, fontFamily:'var(--mono)',
            background:'rgba(75,140,245,.1)', border:'1px solid rgba(75,140,245,.2)', color:'var(--blue)' }}>
            PUBLIC
          </span>
        )}
        <span style={{ fontSize:9, padding:'1px 6px', borderRadius:2, fontFamily:'var(--mono)',
          background:'var(--s2)', border:'1px solid var(--b1)', color:'var(--sub)',
          textTransform:'uppercase' }}>
          {t.position}
        </span>
      </div>

      {(t.yourproduct || t.theirproduct) && (
        <div style={{ fontSize:11, color:'var(--dim)' }}>
          {t.yourproduct && <span>You: <span style={{ color:'var(--sub)' }}>{t.yourproduct}</span></span>}
          {t.yourproduct && t.theirproduct && <span style={{ margin:'0 6px' }}>·</span>}
          {t.theirproduct && <span>Them: <span style={{ color:'var(--sub)' }}>{t.theirproduct}</span></span>}
        </div>
      )}

      {t.terms && (
        <div style={{ fontSize:11, color:'var(--dim)', fontFamily:'var(--mono)',
          whiteSpace:'pre-wrap', wordBreak:'break-word',
          maxHeight:60, overflowY:'auto', lineHeight:1.5 }}>
          {t.terms.slice(0, 200)}{t.terms.length > 200 ? '…' : ''}
        </div>
      )}

      <div style={{ display:'flex', gap:6, flexWrap:'wrap' }}>
        <button className="btn btn-acc" style={{ fontSize:11 }}
          onClick={() => setFiring(t)}>
          Use Template
        </button>
        {t.uid === myUid && <>
          <button className="btn btn-ghost" style={{ fontSize:11 }}
            onClick={() => { setEditing(t); setMode('edit') }}>Edit</button>
          <button className="btn btn-danger" style={{ fontSize:11 }}
            onClick={() => deleteTemplate(t.id)}>Delete</button>
        </>}
      </div>
    </div>
  )

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:16 }}>
      <div style={{ display:'flex', alignItems:'center', gap:8 }}>
        <span style={{ fontSize:12, color:'var(--dim)' }}>
          {mine.length} template{mine.length !== 1 ? 's' : ''}
        </span>
        <button className="btn btn-acc" style={{ fontSize:11, marginLeft:'auto' }}
          onClick={() => setMode('create')}>
          + New Template
        </button>
      </div>

      {!templates.length ? (
        <div style={{ fontSize:12, color:'var(--dim)', fontStyle:'italic', textAlign:'center', padding:'20px 0' }}>
          No templates yet. Create one to speed up repeated contracts.
        </div>
      ) : (
        <>
          {mine.length > 0 && (
            <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
              <div style={{ fontSize:9, color:'var(--dim)', fontFamily:'var(--mono)',
                textTransform:'uppercase', letterSpacing:'.07em' }}>Your Templates</div>
              {mine.map(t => <TemplateCard key={t.id} t={t} />)}
            </div>
          )}
          {pub.length > 0 && (
            <div style={{ display:'flex', flexDirection:'column', gap:8 }}>
              <div style={{ fontSize:9, color:'var(--dim)', fontFamily:'var(--mono)',
                textTransform:'uppercase', letterSpacing:'.07em' }}>Public Templates</div>
              {pub.map(t => <TemplateCard key={t.id} t={t} />)}
            </div>
          )}
        </>
      )}

      {firing && <FireModal template={firing} onClose={() => { setFiring(null); load() }} />}
    </div>
  )
}

export default function ContractsPage() {
  const apiPaused = useStore(s => s.apiPaused)
  const settings  = useStore(s => s.settings)
  const myUid  = useStore(s => s.user?.uid)
  const [tab, setTab] = useState('contracts')
  const [data,       setData]       = useState(null)
  const [hist,       setHist]       = useState(null)
  const [filter,     setFilter]     = useState('all')
  const [page,       setPage]       = useState(1)
  const nav = useNavigate()
  const [sortCol,    setSortCol]    = useState(null)
  const [sortDir,    setSortDir]    = useState('asc')
  const [expanded,   setExpanded]   = useState(null)
  const PERPAGE = 15

  const loadDash  = useCallback(() =>
    api.get('/api/dash/contracts').then(d => { if(d) setData(d) }).catch(() => {})
  , [])
  const loadHist  = useCallback((pg = 1, f = null, sc = null, sd = null) => {
    const sp  = (f && f !== 'all') ? `&status=${f}` : ''
    const srt = sc ? `&sort_col=${sc}&sort_dir=${sd || 'desc'}` : ''
    api.get(`/api/contracts/history?page=${pg}&perpage=${PERPAGE}${sp}${srt}`)
      .then(d => { if(d) setHist(d) }).catch(() => {})
  }, [])

  useEffect(() => { loadDash(); loadHist(1, filter, sortCol, sortDir) }, [])
  usePolling(loadDash,  apiPaused ? null : settings.contractsInterval * 1000)
  usePolling(() => loadHist(page, filter, sortCol, sortDir), apiPaused ? null : 30000)

  const changeFilter = f => { setFilter(f); setPage(1); loadHist(1, f, sortCol, sortDir) }
  const changePage   = pg => { setPage(pg); loadHist(pg, filter, sortCol, sortDir) }

  const toggleSort = col => {
    const newDir = sortCol === col ? (sortDir === 'asc' ? 'desc' : 'asc') : 'desc'
    setSortCol(col)
    setSortDir(newDir)
    setPage(1)
    loadHist(1, filter, col, newDir)
  }

  const useDB      = hist && hist.total > 0
  const contracts  = useDB
    ? (hist.contracts || [])
    : (data?.contracts || []).filter(c => filter === 'all' || c.status_n === filter)
  const total      = useDB ? hist.total : contracts.length
  const totalPages = Math.max(1, Math.ceil(total / PERPAGE))
  const allC       = data?.contracts || []

  // Stats
  const sTotal     = allC.length
  const sActive    = allC.filter(c => c.status_n === '5').length
  const sDisputed  = allC.filter(c => c.status_n === '7').length
  const sExpired   = allC.filter(c => c.status_n === '8').length
  const sComplete  = allC.filter(c => c.status_n === '6').length
  const sCancelled = allC.filter(c => c.status_n === '2').length
  const compRate   = (
    (sTotal - sCancelled) > 0 ? Math.round(sComplete / (sTotal - sCancelled) * 100) : 0
  )

  const FILTERS = [
    ['all','All'],['5','Active'],['6','Complete'],['7','Disputed'],
    ['1','Awaiting'],['2','Cancelled'],['8','Expired'],
  ]

  const SortHdr = ({ col, children, style }) => (
    <span
      className="col-lbl"
      style={{ cursor: 'pointer', userSelect: 'none', ...style }}
      onClick={() => toggleSort(col)}
    >
      {children}{sortCol === col ? (sortDir === 'asc' ? ' ↑' : ' ↓') : ''}
    </span>
  )


  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>

      {/* Page-level tab bar */}
      <div style={{ display:'flex', borderBottom:'1px solid var(--b1)', marginBottom:0 }}>
        {[['contracts','📜 Contracts'],['templates','📋 Templates']].map(([k,l]) => (
          <button key={k} className={`tab${tab===k?' on':''}`} onClick={() => setTab(k)}>{l}</button>
        ))}
      </div>

      {tab === 'templates' ? (
        <div className="card">
          <div className="card-head">
            <span className="card-icon">📋</span>
            <span className="card-title">Contract Templates</span>
          </div>
          <div className="card-body">
            <TemplatesPanel myUid={myUid} />
          </div>
        </div>
      ) : (
        <div style={{ display:'flex', flexDirection:'column', gap:12 }}>

      {/* Stats bar */}
      <div style={{
        display: 'grid', gridTemplateColumns: 'repeat(5,1fr)',
        gap: 1, background: 'var(--b1)',
        border: '1px solid var(--b1)', borderRadius: 'var(--r)', overflow: 'hidden',
      }}>
        {/* Static tiles */}
        {[
          { lbl: 'Total',      val: sTotal,             color: 'var(--text)' },
          { lbl: 'Completion', val: `${compRate}%`,     color: 'var(--acc)'  },
          { lbl: 'Active',     val: sActive,            color: 'var(--acc)'  },
          { lbl: 'Disputed',   val: sDisputed,          color: sDisputed  > 0 ? 'var(--red)' : 'var(--sub)' },
          { lbl: 'Expired',    val: sExpired,           color: sExpired   > 0 ? 'var(--red)' : 'var(--sub)' },
        ].map(({ lbl, val, color }) => (
          <div key={lbl} style={{ background: 'var(--s2)', padding: '10px 12px' }}>
            <div style={{ fontFamily: 'var(--mono)', fontSize: 16, fontWeight: 600, color, lineHeight: 1.1, marginBottom: 2 }}>
              {val ?? '--'}
            </div>
            <div style={{ fontSize: 9, color: 'var(--sub)', textTransform: 'uppercase', letterSpacing: '.07em', fontFamily: 'var(--mono)' }}>
              {lbl}
            </div>
          </div>
        ))}

      </div>

      {/* Main list */}
      <div className="card">
        <div className="card-head">
          <span className="card-icon">📜</span>
          <span className="card-title">Contract History</span>
          {hist?.total > 0 && (
            <span style={{ fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)' }}>
              {hist.total} total{!hist.crawl?.done ? ' (crawling…)' : ''}
            </span>
          )}
        </div>
        <div className="card-body">

          {/* Filter pills */}
          <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginBottom: 12 }}>
            {FILTERS.map(([v, l]) => (
              <button key={v} onClick={() => changeFilter(v)}
                style={{
                  fontSize: 10.5, padding: '3px 10px', borderRadius: 12,
                  border: `1px solid ${filter === v ? 'rgba(0,212,180,.35)' : 'var(--b1)'}`,
                  background: filter === v ? 'var(--acc2)' : 'transparent',
                  color: filter === v ? 'var(--acc)' : 'var(--dim)',
                  cursor: 'pointer', fontFamily: 'var(--sans)', transition: 'all var(--ease)',
                }}>
                {l}
              </button>
            ))}
          </div>

          {/* Column headers */}
          <div style={{ display: 'grid', gridTemplateColumns: '62px 90px 90px 1fr', gap: 8, padding: '0 0 6px', borderBottom: '1px solid var(--b1)', marginBottom: 2 }}>
            <SortHdr col="cid">CID</SortHdr>
            <SortHdr col="status">Status</SortHdr>
            <SortHdr col="type">Type</SortHdr>
            <SortHdr col="value" style={{ textAlign: 'right' }}>Value / When</SortHdr>
          </div>

          {!data && !hist
            ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
                {[1,2,3,4,5].map(i => <div key={i} style={{ height: 22, background: 'var(--s3)', borderRadius: 2, opacity: .4 }} />)}
              </div>
            )
            : contracts.length === 0
              ? <div style={{ fontSize: 12, color: 'var(--sub)', fontStyle: 'italic', padding: '12px 0' }}>No contracts</div>
              : <>
                  {contracts.map(c => {
                    const borderColor = STATUS_BORDER[c.status] || 'transparent'
                    const bgTint      = STATUS_BG[c.status]    || 'transparent'
                    const isExpanded  = expanded === c.cid
                    const isInitiator = myUid && String(c.inituid) === String(myUid)
                    const cpUid       = isInitiator ? c.otheruid : c.inituid
                    const dVal        = displayValue(c)

                    return (
                      <div key={c.cid}>
                        <div
                          onClick={() => nav(`/dashboard/contracts/${c.cid}`)}
                          onMouseOver={e => e.currentTarget.style.filter='brightness(1.25)'}
                          onMouseOut={e => e.currentTarget.style.filter='none'}
                          style={{
                          display: 'grid', gridTemplateColumns: '62px 90px 90px 1fr',
                          gap: 8, alignItems: 'center',
                          padding: '6px 6px 6px 8px',
                          cursor: 'pointer',
                          borderBottom: '1px solid rgba(21,30,46,.5)',
                          borderLeft: `2px solid ${borderColor}`,
                          background: bgTint,
                          marginLeft: -2,
                        }}>
                          <a href={`https://hackforums.net/contracts.php?action=view&cid=${c.cid}`}
                             target="_blank" rel="noreferrer"
                             style={{ fontSize: 11, color: 'var(--acc)', fontFamily: 'var(--mono)' }}>
                            #{c.cid}
                          </a>
                          <span style={{ fontSize: 10, fontFamily: 'var(--mono)', fontWeight: 600, color: STATUS_COLORS[c.status] || 'var(--sub)' }}>
                            {c.status}
                          </span>
                          <span style={{ fontSize: 11, color: 'var(--sub)' }}>{c.type || '--'}</span>
                          <div style={{ textAlign: 'right' }}>
                            <div style={{ fontSize: 11, fontFamily: 'var(--mono)', color: 'var(--text)' }}>{dVal}</div>
                            <div style={{ fontSize: 9.5, color: 'var(--dim)', fontFamily: 'var(--mono)' }}>{ago(c.dateline)}</div>
                          </div>
                          
                        </div>

                        {isExpanded && (
                          <div style={{
                            padding: '10px 12px', margin: '0 0 1px',
                            background: 'var(--bg)', border: '1px solid var(--b1)',
                            borderRadius: 3, fontSize: 11, lineHeight: 1.6,
                          }}>
                            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: c.terms ? 8 : 0 }}>
                              <div>
                                <div style={{ fontSize: 9, color: 'var(--dim)', textTransform: 'uppercase', letterSpacing: '.07em', fontFamily: 'var(--mono)', marginBottom: 2 }}>
                                  {isInitiator ? 'You (initiator)' : 'You (counterparty)'}
                                </div>
                                <div style={{ color: 'var(--text)', fontFamily: 'var(--mono)', fontSize: 11 }}>UID {myUid || '--'}</div>
                              </div>
                              <div>
                                <div style={{ fontSize: 9, color: 'var(--dim)', textTransform: 'uppercase', letterSpacing: '.07em', fontFamily: 'var(--mono)', marginBottom: 2 }}>
                                  Counterparty
                                </div>
                                {cpUid
                                  ? <a href={`https://hackforums.net/member.php?action=profile&uid=${cpUid}`}
                                       target="_blank" rel="noreferrer"
                                       style={{ color: 'var(--acc)', fontFamily: 'var(--mono)', fontSize: 11 }}>
                                      UID {cpUid}
                                    </a>
                                  : <span style={{ color: 'var(--sub)' }}>--</span>
                                }
                              </div>
                            </div>

                            {c.terms && (
                              <div style={{ marginTop: 8, marginBottom: 8 }}>
                                <div style={{ fontSize: 9, color: 'var(--dim)', textTransform: 'uppercase', letterSpacing: '.07em', fontFamily: 'var(--mono)', marginBottom: 4 }}>
                                  Terms
                                </div>
                                <div style={{
                                  color: 'var(--muted)', fontSize: 11, background: 'var(--s2)',
                                  padding: '8px 10px', borderRadius: 3, border: '1px solid var(--b1)',
                                  maxHeight: 120, overflowY: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-word',
                                }}>
                                  {c.terms}
                                </div>
                              </div>
                            )}

                            <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginTop: 6 }}>
                              <div>
                                <span style={{ fontSize: 9, color: 'var(--dim)', fontFamily: 'var(--mono)' }}>Created </span>
                                <span style={{ fontFamily: 'var(--mono)', fontSize: 11, color: 'var(--sub)' }}>{ago(c.dateline)}</span>
                              </div>
                              <a href={`https://hackforums.net/contracts.php?action=view&cid=${c.cid}`}
                                 target="_blank" rel="noreferrer"
                                 style={{ fontSize: 11, color: 'var(--acc)', fontFamily: 'var(--mono)' }}>
                                View on HF →
                              </a>
                            </div>
                          </div>
                        )}
                      </div>
                    )
                  })}

                  {total > 0 && (
                    <div className="pg">
                      <button className="pg-btn" disabled={page <= 1} onClick={() => changePage(page - 1)}>←</button>
                      <span className="pg-info">{page} / {totalPages} <span style={{ color: 'var(--dim)' }}>({total})</span></span>
                      <button className="pg-btn" disabled={page >= totalPages} onClick={() => changePage(page + 1)}>→</button>
                    </div>
                  )}
                </>
          }
        </div>
      </div>
        </div>
      )}
    </div>
  )
}
