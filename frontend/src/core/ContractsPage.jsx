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

const fmtDate = ts => {
  if (!ts) return '--'
  return new Date(ts * 1000).toLocaleDateString('en-US', { month:'short', day:'numeric', year:'numeric' })
}

function usePolling(fn, ms) {
  const ref = useRef(fn); ref.current = fn
  useEffect(() => {
    if (ms == null) return
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

// Known payment methods that should show as "via X" rather than as a denomination
const PAYMENT_METHODS = new Set(['btc','eth','ltc','xmr','usdt','usdc','paypal','pp',
  'cryptocurrency','crypto','bitcoin','ethereum','litecoin'])

function parseValue(v) {
  // Returns {amount, via} or null
  if (!v) return null
  const parts = v.trim().split(/\s+/)
  if (parts.length < 2) return null
  const last = parts[parts.length - 1].toLowerCase()
  // If last word is a known payment method, split it
  if (PAYMENT_METHODS.has(last) || last.includes('paypal') || last.includes('crypto')) {
    const amount = parts.slice(0, -1).join(' ')
    const via = parts[parts.length - 1].toUpperCase()
    return { amount, via }
  }
  return null
}

function displayValue(c) {
  const v = c.value
  if (!v || v === 'None None' || v.toLowerCase() === 'none none' || v === '--') {
    return c.type === 'Vouch Copy' ? 'Vouch Copy' : ''
  }
  return v
}

// HF max contract timeout is 90 days. Any "Awaiting Approval" older than that
// is definitively expired — the API stopped returning it before updating status.
const NINETY_DAYS = 90 * 86400
function resolveStatus(c) {
  if (c.status === 'Awaiting Approval' && c.dateline) {
    const age = Math.floor(Date.now() / 1000) - Number(c.dateline)
    if (age > NINETY_DAYS) return 'Expired'
  }
  return c.status
}


// ── Shared helpers ───────────────────────────────────────────────────────────
const fmtDateShort = ts => ts ? new Date(ts*1000).toLocaleDateString('en-US',{month:'short',year:'numeric'}) : '--'
const fmtFull      = ts => ts ? new Date(ts*1000).toLocaleDateString('en-US',{month:'short',day:'numeric',year:'numeric'}) : '--'

const STATUS_COL_MAP = {
  'Complete':'var(--acc)', 'Active Deal':'#4b8cf5',
  'Awaiting Approval':'var(--yellow)', 'Disputed':'var(--red)',
  'Expired':'rgba(255,71,87,.65)', 'Cancelled':'var(--dim)',
}

function buildPreviewParams(status, dateFrom, dateTo) {
  const p = new URLSearchParams()
  if (status)   p.set('status', status)
  if (dateFrom) {
    const ts = Math.floor(new Date(dateFrom + 'T00:00:00').getTime() / 1000)
    if (!isNaN(ts)) p.set('date_from', ts)
  }
  if (dateTo) {
    const ts = Math.floor(new Date(dateTo + 'T23:59:59').getTime() / 1000)
    if (!isNaN(ts)) p.set('date_to', ts)
  }
  return p
}

// ── Inline presets dropdown ───────────────────────────────────────────────────
function PresetPicker({ onSelect }) {
  const [open, setOpen] = useState(false)
  const ref = useRef(null)
  const now = new Date(); const yr = now.getFullYear()

  useEffect(() => {
    const handler = e => { if (ref.current && !ref.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const pick = (f, t) => { onSelect(f, t); setOpen(false) }
  const yrs  = Array.from({length: yr - 2017}, (_, i) => yr - i)

  return (
    <div ref={ref} style={{ position:'relative' }}>
      <button
        onClick={() => setOpen(o => !o)}
        className="btn btn-ghost"
        style={{ fontSize:10, padding:'4px 9px', whiteSpace:'nowrap' }}
      >
        Presets ▾
      </button>
      {open && (
        <div style={{
          position:'absolute', top:'calc(100% + 4px)', left:0, zIndex:200,
          background:'var(--s2)', border:'1px solid var(--b2)', borderRadius:6,
          boxShadow:'0 8px 24px rgba(0,0,0,.5)', minWidth:140, padding:'4px 0',
        }}>
          {[
            { lbl:'All time',  f:'', t:'' },
            { lbl:'This year', f:`${yr}-01-01`, t:`${yr}-12-31` },
            { lbl:'Last 90d',  f:new Date(Date.now()-90*86400000).toISOString().slice(0,10), t:'' },
            { lbl:'Last 30d',  f:new Date(Date.now()-30*86400000).toISOString().slice(0,10), t:'' },
          ].map(p => (
            <button key={p.lbl} onClick={() => pick(p.f, p.t)} style={{
              display:'block', width:'100%', textAlign:'left',
              padding:'6px 12px', fontSize:11, background:'none', border:'none',
              color:'var(--sub)', cursor:'pointer', fontFamily:'var(--sans)',
            }}
              onMouseOver={e=>e.target.style.background='var(--hover)'}
              onMouseOut={e=>e.target.style.background='none'}
            >{p.lbl}</button>
          ))}
          <div style={{ height:1, background:'var(--b1)', margin:'4px 0' }}/>
          <div style={{ padding:'4px 12px', fontSize:9, color:'var(--dim)', fontFamily:'var(--mono)', textTransform:'uppercase', letterSpacing:'.06em' }}>By year (since contracts launched)</div>
          {yrs.slice(1).map(y => (
            <button key={y} onClick={() => pick(`${y}-01-01`, `${y}-12-31`)} style={{
              display:'block', width:'100%', textAlign:'left',
              padding:'5px 12px', fontSize:11, background:'none', border:'none',
              color:'var(--sub)', cursor:'pointer', fontFamily:'var(--mono)',
            }}
              onMouseOver={e=>e.target.style.background='var(--hover)'}
              onMouseOut={e=>e.target.style.background='none'}
            >{y}</button>
          ))}
        </div>
      )}
    </div>
  )
}

// ── Export + Preview panel ────────────────────────────────────────────────────
function ExportPanel({ crawlDone, crawlPage, totalCount, myUid }) {
  const [fmt,      setFmt]      = useState('csv')
  const [status,   setStatus]   = useState('')
  const [dateFrom, setDateFrom] = useState('')
  const [dateTo,   setDateTo]   = useState('')
  const [dlLoading, setDlLoading] = useState(false)
  const [dlErr,     setDlErr]     = useState(null)

  // Preview data
  const [preview,   setPreview]   = useState(null)
  const [prevLoad,  setPrevLoad]  = useState(true)
  const [prevErr,   setPrevErr]   = useState(null)
  const [usernames, setUsernames] = useState({})

  const STATUS_OPTS = [
    ['','All Statuses'],['6','Complete'],['5','Active Deal'],
    ['7','Disputed'],['1','Awaiting'],['2','Cancelled'],['8','Expired'],
  ]

  // Fetch preview whenever filters change
  useEffect(() => {
    if (!crawlDone) return
    setPrevLoad(true); setPrevErr(null)
    const params = buildPreviewParams(status, dateFrom, dateTo)
    params.set('limit', '10')
    fetch(`/api/contracts/preview?${params}`, { credentials:'include' })
      .then(async r => {
        if (!r.ok) { const t = await r.text(); throw new Error(`${r.status}: ${t.slice(0,120)}`) }
        return r.json()
      })
      .then(d => {
        setPreview(d); setPrevLoad(false)
        // /api/users/resolve is DB-only — call freely, no HF API cost
        const allUids = [...new Set((d.rows||[]).flatMap(r=>[r.inituid,r.otheruid]).filter(Boolean))]
        if (allUids.length) {
          fetch(`/api/users/resolve?uids=${allUids.join(',')}`, { credentials:'include' })
            .then(r=>r.json()).then(m=>setUsernames(prev=>({...prev,...(m||{})}))).catch(()=>{})
        }
      })
      .catch(e => { setPrevErr(e.message||'Failed'); setPrevLoad(false) })
  }, [status, dateFrom, dateTo, crawlDone])

  const doDownload = async () => {
    setDlLoading(true); setDlErr(null)
    try {
      const params = buildPreviewParams(status, dateFrom, dateTo)
      params.set('format', fmt)
      const res = await fetch(`/api/contracts/export?${params}`, { credentials:'include' })
      if (res.status === 409) { const j = await res.json(); setDlErr(j.error||'Crawl not complete'); return }
      if (!res.ok) { setDlErr(`Export failed (${res.status})`); return }
      const blob = await res.blob()
      const url  = URL.createObjectURL(blob)
      const a    = document.createElement('a')
      a.href = url; a.download = `hf_contracts.${fmt}`; a.click()
      URL.revokeObjectURL(url)
    } catch(e) { setDlErr(e.message||'Export failed') }
    finally   { setDlLoading(false) }
  }

  // Crawling — show progress only
  if (!crawlDone) {
    const circ = 2*Math.PI*15
    const pct  = totalCount>0 ? Math.min(90, Math.round((crawlPage/Math.max(crawlPage+3,8))*100)) : 5
    return (
      <div style={{ padding:'12px 14px', borderRadius:6, background:'rgba(75,140,245,.05)', border:'1px solid rgba(75,140,245,.15)', display:'flex', alignItems:'center', gap:12 }}>
        <svg width="28" height="28" viewBox="0 0 36 36" style={{ flexShrink:0, transform:'rotate(-90deg)' }}>
          <circle cx="18" cy="18" r="15" fill="none" stroke="var(--b2)" strokeWidth="3"/>
          <circle cx="18" cy="18" r="15" fill="none" stroke="var(--blue)" strokeWidth="3"
            strokeDasharray={`${(pct/100*circ).toFixed(1)} ${circ.toFixed(1)}`} strokeLinecap="round"/>
        </svg>
        <div style={{ flex:1 }}>
          <div style={{ fontSize:11, fontWeight:600, color:'var(--text)', marginBottom:2 }}>Indexing contract history…</div>
          <div style={{ fontSize:10, color:'var(--dim)', fontFamily:'var(--mono)' }}>
            {totalCount.toLocaleString()} indexed · page {crawlPage} fetched · export unlocks when complete
          </div>
        </div>
        <button className="btn btn-ghost" style={{ opacity:.4, cursor:'not-allowed', fontSize:10 }} disabled>↓ Export</button>
      </div>
    )
  }

  const p = preview
  return (
    <div style={{ borderRadius:6, background:'rgba(36,201,140,.04)', border:'1px solid rgba(36,201,140,.2)', overflow:'hidden' }}>

      {/* ── Controls row ── */}
      <div style={{ padding:'12px 16px', display:'flex', gap:10, flexWrap:'wrap', alignItems:'flex-end', borderBottom:'1px solid rgba(36,201,140,.12)' }}>

        {/* Header */}
        <div style={{ flex:'0 0 100%', display:'flex', alignItems:'center', gap:8, marginBottom:2 }}>
          <span style={{ fontSize:12, fontWeight:700, color:'var(--acc)' }}>↓ Export & Preview</span>
          <span style={{ fontSize:10, color:'var(--dim)', fontFamily:'var(--mono)' }}>
            {p ? `${p.total.toLocaleString()} contracts match` : `${totalCount.toLocaleString()} total`}
            {' · '}fully indexed ✓
          </span>
          <span style={{ fontSize:9, color:'var(--dim)', fontFamily:'var(--mono)', marginLeft:'auto' }}>
            CSV columns: CID · Status · Type · Value · Counterparty · Thread · Date
          </span>
        </div>

        {/* Format toggle */}
        <div>
          <div style={{ fontSize:9, color:'var(--dim)', fontFamily:'var(--mono)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:3 }}>Format</div>
          <div style={{ display:'flex', borderRadius:4, overflow:'hidden', border:'1px solid var(--b2)' }}>
            {['csv','json'].map(f => (
              <button key={f} onClick={() => setFmt(f)} style={{
                padding:'4px 12px', fontSize:10, fontFamily:'var(--mono)', fontWeight:700,
                cursor:'pointer', border:'none', outline:'none',
                background: fmt===f ? 'var(--acc)' : 'var(--s3)',
                color: fmt===f ? 'var(--bg)' : 'var(--sub)', textTransform:'uppercase',
              }}>{f}</button>
            ))}
          </div>
        </div>

        {/* Status */}
        <div>
          <div style={{ fontSize:9, color:'var(--dim)', fontFamily:'var(--mono)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:3 }}>Status</div>
          <select className="inp" value={status} onChange={e=>setStatus(e.target.value)}
            style={{ fontSize:11, padding:'4px 8px', cursor:'pointer', minWidth:130 }}>
            {STATUS_OPTS.map(([v,l])=><option key={v} value={v}>{l}</option>)}
          </select>
        </div>

        {/* Date range + presets */}
        <div>
          <div style={{ fontSize:9, color:'var(--dim)', fontFamily:'var(--mono)', textTransform:'uppercase', letterSpacing:'.06em', marginBottom:3 }}>Date range</div>
          <div style={{ display:'flex', gap:4, alignItems:'center' }}>
            <input className="inp" type="date" value={dateFrom} onChange={e=>setDateFrom(e.target.value)}
              style={{ fontSize:11, padding:'4px 8px', width:130 }} />
            <span style={{ fontSize:10, color:'var(--dim)' }}>→</span>
            <input className="inp" type="date" value={dateTo} onChange={e=>setDateTo(e.target.value)}
              style={{ fontSize:11, padding:'4px 8px', width:130 }} />
            <PresetPicker onSelect={(f,t)=>{setDateFrom(f);setDateTo(t)}} />
          </div>
        </div>

        {/* Download */}
        <button className="btn btn-acc" style={{ fontSize:11, padding:'5px 18px', alignSelf:'flex-end' }}
          onClick={doDownload} disabled={dlLoading}>
          {dlLoading ? <span className="spin" style={{width:10,height:10}}/> : `↓ Download ${fmt.toUpperCase()}`}
        </button>
      </div>

      {dlErr && <div style={{ padding:'6px 16px', fontSize:11, color:'var(--red)', fontFamily:'var(--mono)', background:'rgba(232,84,84,.08)' }}>✕ {dlErr}</div>}

      {/* ── Preview body ── */}
      <div style={{ padding:'14px 16px' }}>
        {prevLoad ? (
          <div style={{ display:'flex', alignItems:'center', gap:8, color:'var(--dim)', fontSize:11 }}>
            <div className="spin"/> Loading preview…
          </div>
        ) : prevErr ? (
          <div style={{ fontSize:11, color:'var(--red)', fontFamily:'var(--mono)' }}>Preview error: {prevErr}</div>
        ) : !p || !p.total ? (
          <div style={{ fontSize:11, color:'var(--dim)', fontStyle:'italic' }}>No contracts match the selected filters.</div>
        ) : (
          <>
            {/* KPI strip */}
            <div style={{ display:'grid', gridTemplateColumns:'repeat(5,1fr)', gap:1, background:'var(--b2)', borderRadius:6, overflow:'hidden', marginBottom:12 }}>
              {[
                { lbl:'Contracts',       val: p.total.toLocaleString(),   color:'var(--text)', sub: `${fmtDateShort(p.date_min)} – ${fmtDateShort(p.date_max)}` },
                { lbl:'Complete',        val: (p.by_status.find(s=>s.label==='Complete')?.count||0).toLocaleString(), color:'var(--acc)', sub:'confirmed' },
                { lbl:'Completion rate', val: `${p.comp_rate}%`,           color: p.comp_rate>=90?'var(--acc)':p.comp_rate>=70?'var(--yellow)':'var(--red)', sub:'excl. cancelled' },
                { lbl:'Disputed',        val: (p.by_status.find(s=>s.label==='Disputed')?.count||0).toLocaleString(), color:(p.by_status.find(s=>s.label==='Disputed')?.count||0)>0?'var(--red)':'var(--sub)', sub:'of total' },
                { lbl:'Active',          val: (p.by_status.find(s=>s.label==='Active Deal')?.count||0).toLocaleString(), color:'#4b8cf5', sub:'open now' },
              ].map(({lbl,val,color,sub}) => (
                <div key={lbl} style={{ background:'var(--s2)', padding:'9px 12px' }}>
                  <div style={{ fontFamily:'var(--mono)', fontSize:17, fontWeight:700, color, lineHeight:1.1, marginBottom:2 }}>{val}</div>
                  <div style={{ fontSize:9, color:'var(--sub)', textTransform:'uppercase', letterSpacing:'.06em', fontFamily:'var(--mono)' }}>{lbl}</div>
                  <div style={{ fontSize:9, color:'var(--dim)', marginTop:1 }}>{sub}</div>
                </div>
              ))}
            </div>

            {/* Breakdown bars */}
            <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:10, marginBottom:14 }}>
              {[
                { title:'By Status', rows:p.by_status, colorFn: r=>STATUS_COL_MAP[r.label]||'var(--sub)', maxC:'var(--sub)' },
                { title:'By Type',   rows:p.by_type,   colorFn: ()=>'var(--blue)',                         maxC:'var(--blue)' },
              ].map(({title,rows,colorFn}) => {
                const mx = Math.max(...rows.map(r=>r.count),1)
                return (
                  <div key={title} style={{ background:'var(--s2)', border:'1px solid var(--b1)', borderRadius:6, padding:'10px 12px' }}>
                    <div style={{ fontSize:9, color:'var(--dim)', fontFamily:'var(--mono)', textTransform:'uppercase', letterSpacing:'.07em', marginBottom:8 }}>{title}</div>
                    {rows.map(r => (
                      <div key={r.label} style={{ display:'flex', alignItems:'center', gap:7, marginBottom:5 }}>
                        <span style={{ fontSize:9.5, color:colorFn(r), fontFamily:'var(--mono)', width:115, flexShrink:0, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{r.label}</span>
                        <div style={{ flex:1, background:'var(--b2)', borderRadius:2, height:5, overflow:'hidden' }}>
                          <div style={{ width:`${Math.max(r.count/mx*100,1.5)}%`, height:'100%', background:colorFn(r), borderRadius:2 }}/>
                        </div>
                        <span style={{ fontSize:9.5, fontFamily:'var(--mono)', color:'var(--sub)', width:26, textAlign:'right', flexShrink:0 }}>{r.count}</span>
                        <span style={{ fontSize:9, color:'var(--dim)', width:28, textAlign:'right', flexShrink:0 }}>{Math.round(r.count/p.total*100)}%</span>
                      </div>
                    ))}
                  </div>
                )
              })}
            </div>

            {/* Top threads */}
            {(() => {
              const threads = p.top_threads || []
              const maxT = Math.max(...threads.map(r=>r.count), 1)
              const withThread = p.with_thread || 0
              const noThread   = p.total - withThread
              const TYPE_COLORS = {'Selling':'var(--acc)','Purchasing':'#4b8cf5','Exchanging':'var(--yellow)','Trading':'var(--sub)','Vouch Copy':'var(--dim)'}
              return (
                <div style={{ background:'var(--s2)', border:'1px solid var(--b1)', borderRadius:6, padding:'12px 14px' }}>
                  {/* Header */}
                  <div style={{ display:'flex', alignItems:'center', marginBottom:12 }}>
                    <div style={{ fontSize:9, color:'var(--dim)', fontFamily:'var(--mono)', textTransform:'uppercase', letterSpacing:'.07em' }}>Top Sales Threads</div>
                    <div style={{ marginLeft:'auto', display:'flex', gap:14 }}>
                      <span style={{ fontSize:9.5, color:'var(--acc)', fontFamily:'var(--mono)' }}>
                        {withThread.toLocaleString()} tied to thread · {Math.round(withThread/p.total*100)}%
                      </span>
                      <span style={{ fontSize:9.5, color:'var(--dim)', fontFamily:'var(--mono)' }}>
                        {noThread.toLocaleString()} direct
                      </span>
                    </div>
                  </div>

                  {threads.length === 0 ? (
                    <div style={{ fontSize:11, color:'var(--dim)', fontStyle:'italic' }}>
                      Thread data populates after next crawl cycle — contracts with a thread linked will appear here.
                    </div>
                  ) : (
                    <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
                      {threads.map((r, i) => (
                        <div key={r.tid} style={{
                          background:'var(--s3)', border:'1px solid var(--b1)', borderRadius:5, padding:'9px 12px',
                        }}>
                          {/* Thread header row */}
                          <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:6 }}>
                            <span style={{ fontSize:9, color:'var(--dim)', fontFamily:'var(--mono)', flexShrink:0 }}>#{i+1}</span>
                            <a href={`https://hackforums.net/showthread.php?tid=${r.tid}`}
                               target="_blank" rel="noreferrer"
                               style={{ fontSize:11, color:'var(--yellow)', fontFamily:'var(--mono)', fontWeight:600, flexShrink:0 }}>
                              #{r.tid}
                            </a>
                            {r.title ? (
                              <span style={{ fontSize:11, color:'var(--text)', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap', flex:1 }}>
                                {r.title}
                              </span>
                            ) : (
                              <span style={{ fontSize:10, color:'var(--dim)', fontStyle:'italic', flex:1 }}>title loading…</span>
                            )}
                            <span style={{ fontSize:11, fontFamily:'var(--mono)', color:'var(--text)', fontWeight:700, flexShrink:0 }}>
                              {r.count} <span style={{ fontSize:9, color:'var(--dim)', fontWeight:400 }}>contracts</span>
                            </span>
                            <span style={{ fontSize:10, color:'var(--dim)', fontFamily:'var(--mono)', flexShrink:0, width:32, textAlign:'right' }}>
                              {Math.round(r.count/p.total*100)}%
                            </span>
                          </div>

                          {/* Volume bar */}
                          <div style={{ background:'var(--b2)', borderRadius:2, height:4, overflow:'hidden', marginBottom:7 }}>
                            <div style={{ width:`${Math.max(r.count/maxT*100,1.5)}%`, height:'100%', background:'var(--yellow)', borderRadius:2 }}/>
                          </div>

                          {/* Type pills + top value */}
                          <div style={{ display:'flex', alignItems:'center', gap:8, flexWrap:'wrap' }}>
                            {(r.types||[]).map(t => (
                              <span key={t.type} style={{
                                fontSize:9.5, padding:'1px 7px', borderRadius:10,
                                border:`1px solid ${TYPE_COLORS[t.type]||'var(--b2)'}40`,
                                background:`${TYPE_COLORS[t.type]||'var(--dim)'}12`,
                                color: TYPE_COLORS[t.type]||'var(--dim)',
                                fontFamily:'var(--mono)',
                              }}>
                                {t.type} · {t.count}
                              </span>
                            ))}
                            {r.top_value && (
                              <span style={{ fontSize:9.5, color:'var(--sub)', fontFamily:'var(--mono)', marginLeft:'auto' }}>
                                {r.top_value}
                              </span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )
            })()}

          </>
        )}
      </div>
    </div>
  )
}

// ── Contract Templates (unchanged logic) ─────────────────────────────────────
const POSITIONS  = ['selling','buying','exchanging','trading','vouchcopy']
const CURRENCIES = ['other','USD','BTC','ETH','LTC','bytes']
const POSITION_LABELS = {
  selling:'Selling', buying:'Buying', exchanging:'Exchanging', trading:'Trading', vouchcopy:'Vouch Copy',
}

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
    name:'', position:'selling', terms:'',
    yourproduct:'', yourcurrency:'other', youramount:'0',
    theirproduct:'', theircurrency:'other', theiramount:'0',
    address:'', middleman_uid:'', timeout_days:14, is_public:false,
    ...initial,
  })
  const [busy, setBusy] = useState(false)
  const [err,  setErr]  = useState(null)
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))
  const submit = async () => {
    if (!form.name.trim())  { setErr('Name is required'); return }
    if (!form.terms.trim()) { setErr('Terms are required'); return }
    setBusy(true); setErr(null)
    try { await onSave(form) } catch (e) { setErr(e.message || 'Error') } finally { setBusy(false) }
  }
  const inp = { className:'inp', style:{ fontSize:11, width:'100%', boxSizing:'border-box' } }
  const lbl = { style:{ fontSize:9, color:'var(--dim)', fontFamily:'var(--mono)', textTransform:'uppercase', letterSpacing:'.07em', marginBottom:4, display:'block' } }
  const sel = { className:'inp', style:{ fontSize:11, width:'100%', boxSizing:'border-box', cursor:'pointer' } }
  const pos = form.position; const shared = { form, set, inp, lbl, sel }

  const renderPositionFields = () => {
    if (pos === 'vouchcopy') return <div style={{ padding:'10px 12px', background:'var(--s2)', border:'1px solid var(--b1)', borderRadius:4, fontSize:11, color:'var(--sub)', fontStyle:'italic', textAlign:'center' }}>Vouch Copy — no product or currency fields needed</div>
    if (pos === 'selling')   return <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16 }}><ProductField label="Your Product / Service" fieldKey="yourproduct" placeholder="e.g. 30-day Spotify slot" {...shared} /><CurrencyAmountFields label="Their Payment" currKey="theircurrency" amtKey="theiramount" {...shared} /></div>
    if (pos === 'buying')    return <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16 }}><CurrencyAmountFields label="Your Payment" currKey="yourcurrency" amtKey="youramount" {...shared} /><ProductField label="Their Product / Service" fieldKey="theirproduct" placeholder="e.g. 30-day Spotify slot" {...shared} /></div>
    if (pos === 'exchanging') return <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16 }}><CurrencyAmountFields label="Your Currency / Amount" currKey="yourcurrency" amtKey="youramount" {...shared} /><CurrencyAmountFields label="Their Currency / Amount" currKey="theircurrency" amtKey="theiramount" {...shared} /></div>
    if (pos === 'trading')   return <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:16 }}><ProductField label="Your Product / Service" fieldKey="yourproduct" placeholder="e.g. Your item" {...shared} /><ProductField label="Their Product / Service" fieldKey="theirproduct" placeholder="e.g. Their item" {...shared} /></div>
    return null
  }

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:12 }}>
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:10 }}>
        <div><label {...lbl}>Template Name</label><input {...inp} value={form.name} onChange={e => set('name', e.target.value)} placeholder="e.g. Standard Service Sale" /></div>
        <div><label {...lbl}>Position</label><select {...sel} value={form.position} onChange={e => set('position', e.target.value)}>{POSITIONS.map(p => <option key={p} value={p}>{POSITION_LABELS[p]}</option>)}</select></div>
      </div>
      {renderPositionFields()}
      <div>
        <label {...lbl}>Contract Terms</label>
        <textarea {...inp} style={{ ...inp.style, minHeight:100, fontFamily:'var(--mono)', resize:'vertical' }}
          value={form.terms} onChange={e => set('terms', e.target.value)} placeholder="Full contract terms…" spellCheck={false}
          onFocus={e => e.target.style.borderColor='var(--acc)'} onBlur={e => e.target.style.borderColor='var(--b2)'} />
      </div>
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:10 }}>
        <div><label {...lbl}>Payment Address <span style={{ color:'var(--dim)' }}>(optional)</span></label><input {...inp} value={form.address} onChange={e => set('address', e.target.value)} placeholder="e.g. crypto wallet / autobuy link" /></div>
        <div><label {...lbl}>Middleman UID <span style={{ color:'var(--dim)' }}>(optional)</span></label><input {...inp} value={form.middleman_uid} onChange={e => set('middleman_uid', e.target.value)} placeholder="UID of middleman/escrow" /></div>
      </div>
      <div style={{ display:'grid', gridTemplateColumns:'1fr 1fr', gap:10 }}>
        <div><label {...lbl}>Timeout (days)</label><input {...inp} type="number" min="1" max="90" value={form.timeout_days} onChange={e => set('timeout_days', parseInt(e.target.value) || 14)} /></div>
        <div style={{ display:'flex', alignItems:'center', gap:8, paddingTop:16 }}>
          <button className={`tog${!form.is_public ? ' off' : ''}`} onClick={() => set('is_public', !form.is_public)} />
          <span style={{ fontSize:11, color:'var(--sub)' }}>{form.is_public ? 'Public (visible to all users)' : 'Private (only you)'}</span>
        </div>
      </div>
      {err && <div style={{ fontSize:11, color:'var(--red)', fontFamily:'var(--mono)' }}>✕ {err}</div>}
      <div style={{ display:'flex', gap:6 }}>
        <button className="btn btn-acc" style={{ fontSize:11 }} disabled={busy} onClick={submit}>{busy ? '…' : initial ? 'Save Changes' : 'Create Template'}</button>
        <button className="btn btn-ghost" style={{ fontSize:11 }} onClick={onCancel}>Cancel</button>
      </div>
    </div>
  )
}

function FireModal({ template, onClose }) {
  const [cpUid, setCpUid]       = useState('')
  const [threadId, setThreadId] = useState('')
  const [busy, setBusy]         = useState(false)
  const [result, setResult]     = useState(null)
  const [err, setErr]           = useState(null)

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
    <div style={{ position:'fixed', inset:0, zIndex:500, background:'rgba(0,0,0,.65)', display:'flex', alignItems:'center', justifyContent:'center' }}
      onClick={e => { if(e.target===e.currentTarget) onClose() }}>
      <div style={{ background:'var(--s2)', border:'1px solid var(--b2)', borderRadius:8, width:'min(420px,94vw)', padding:20, boxShadow:'0 12px 40px rgba(0,0,0,.6)' }}>
        {result ? (
          <div style={{ display:'flex', flexDirection:'column', gap:12, textAlign:'center' }}>
            <div style={{ fontSize:24 }}>✓</div>
            <div style={{ fontSize:14, fontWeight:600 }}>Contract Created</div>
            {result.cid && <div style={{ fontSize:12, color:'var(--dim)', fontFamily:'var(--mono)' }}>CID: {result.cid}</div>}
            {result.url && <a href={result.url} target="_blank" rel="noreferrer" className="btn btn-acc" style={{ fontSize:12, textAlign:'center' }}>View on HF →</a>}
            <button className="btn btn-ghost" style={{ fontSize:11 }} onClick={onClose}>Close</button>
          </div>
        ) : (
          <div style={{ display:'flex', flexDirection:'column', gap:14 }}>
            <div style={{ fontSize:13, fontWeight:600 }}>Use Template: <span style={{ color:'var(--acc)' }}>{template.name}</span></div>
            <div style={{ fontSize:11, color:'var(--dim)', padding:'6px 10px', background:'var(--s3)', border:'1px solid var(--b1)', borderRadius:4 }}>
              <strong style={{ color:'var(--sub)' }}>{template.position}</strong>{template.yourproduct && ` · ${template.yourproduct}`}
            </div>
            <div>
              <label style={{ fontSize:10, color:'var(--dim)', fontFamily:'var(--mono)', textTransform:'uppercase', letterSpacing:'.07em', marginBottom:4, display:'block' }}>Counterparty UID *</label>
              <input className="inp" style={{ fontSize:12, width:'100%', boxSizing:'border-box' }}
                value={cpUid} onChange={e => setCpUid(e.target.value)} placeholder="e.g. 123456" autoFocus
                onKeyDown={e => { if(e.key==='Enter') fire() }} />
            </div>
            <div>
              <label style={{ fontSize:10, color:'var(--dim)', fontFamily:'var(--mono)', textTransform:'uppercase', letterSpacing:'.07em', marginBottom:4, display:'block' }}>Thread ID (optional)</label>
              <input className="inp" style={{ fontSize:12, width:'100%', boxSizing:'border-box' }}
                value={threadId} onChange={e => setThreadId(e.target.value)} placeholder="e.g. 5847344" />
            </div>
            {err && <div style={{ fontSize:11, color:'var(--red)', fontFamily:'var(--mono)' }}>✕ {err}</div>}
            <div style={{ display:'flex', gap:6 }}>
              <button className="btn btn-acc" style={{ fontSize:12, flex:1 }} disabled={busy||!cpUid} onClick={fire}>{busy ? '…' : 'Create Contract'}</button>
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
  const [loading, setLoading]     = useState(true)
  const [mode, setMode]           = useState('list')
  const [editing, setEditing]     = useState(null)
  const [firing, setFiring]       = useState(null)

  const load = useCallback(() => {
    api.get('/api/contracts/templates')
      .then(d => { setTemplates(d.templates || []); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])
  useEffect(() => { load() }, [load])

  const createTemplate = async (data) => { await api.post('/api/contracts/templates', data); load(); setMode('list') }
  const saveTemplate   = async (data) => { await api.patch(`/api/contracts/templates/${editing.id}`, data); load(); setMode('list'); setEditing(null) }
  const deleteTemplate = async (id)   => { if (!confirm('Delete this template?')) return; await api.delete(`/api/contracts/templates/${id}`); load() }

  if (loading) return <div style={{ display:'flex', justifyContent:'center', padding:30 }}><div className="spin"/></div>
  if (mode === 'create') return <div><div style={{ fontSize:12, fontWeight:600, marginBottom:14 }}>New Template</div><TemplateForm onSave={createTemplate} onCancel={() => setMode('list')} /></div>
  if (mode === 'edit' && editing) return <div><div style={{ fontSize:12, fontWeight:600, marginBottom:14 }}>Edit Template</div><TemplateForm initial={editing} onSave={saveTemplate} onCancel={() => { setMode('list'); setEditing(null) }} /></div>

  const mine = templates.filter(t => t.uid === myUid)
  const pub  = templates.filter(t => t.uid !== myUid && t.is_public)

  const TemplateCard = ({ t }) => (
    <div style={{ padding:'12px 14px', background:'var(--s3)', border:'1px solid var(--b2)', borderRadius:6, display:'flex', flexDirection:'column', gap:8 }}>
      <div style={{ display:'flex', alignItems:'center', gap:8 }}>
        <span style={{ fontWeight:600, fontSize:12, flex:1 }}>{t.name}</span>
        {t.is_public && <span style={{ fontSize:9, padding:'1px 6px', borderRadius:2, fontFamily:'var(--mono)', background:'rgba(75,140,245,.1)', border:'1px solid rgba(75,140,245,.2)', color:'var(--blue)' }}>PUBLIC</span>}
        <span style={{ fontSize:9, padding:'1px 6px', borderRadius:2, fontFamily:'var(--mono)', background:'var(--s2)', border:'1px solid var(--b1)', color:'var(--sub)', textTransform:'uppercase' }}>{t.position}</span>
      </div>
      {(t.yourproduct || t.theirproduct) && (
        <div style={{ fontSize:11, color:'var(--dim)' }}>
          {t.yourproduct && <span>You: <span style={{ color:'var(--sub)' }}>{t.yourproduct}</span></span>}
          {t.yourproduct && t.theirproduct && <span style={{ margin:'0 6px' }}>·</span>}
          {t.theirproduct && <span>Them: <span style={{ color:'var(--sub)' }}>{t.theirproduct}</span></span>}
        </div>
      )}
      {t.terms && <div style={{ fontSize:11, color:'var(--dim)', fontFamily:'var(--mono)', whiteSpace:'pre-wrap', wordBreak:'break-word', maxHeight:60, overflowY:'auto', lineHeight:1.5 }}>{t.terms.slice(0, 200)}{t.terms.length > 200 ? '…' : ''}</div>}
      <div style={{ display:'flex', gap:6, flexWrap:'wrap' }}>
        <button className="btn btn-acc" style={{ fontSize:11 }} onClick={() => setFiring(t)}>Use Template</button>
        {t.uid === myUid && <>
          <button className="btn btn-ghost" style={{ fontSize:11 }} onClick={() => { setEditing(t); setMode('edit') }}>Edit</button>
          <button className="btn btn-danger" style={{ fontSize:11 }} onClick={() => deleteTemplate(t.id)}>Delete</button>
        </>}
      </div>
    </div>
  )

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:16 }}>
      <div style={{ display:'flex', alignItems:'center', gap:8 }}>
        <span style={{ fontSize:12, color:'var(--dim)' }}>{mine.length} template{mine.length !== 1 ? 's' : ''}</span>
        <button className="btn btn-acc" style={{ fontSize:11, marginLeft:'auto' }} onClick={() => setMode('create')}>+ New Template</button>
      </div>
      {!templates.length ? (
        <div style={{ fontSize:12, color:'var(--dim)', fontStyle:'italic', textAlign:'center', padding:'20px 0' }}>No templates yet. Create one to speed up repeated contracts.</div>
      ) : (
        <>
          {mine.length > 0 && <div style={{ display:'flex', flexDirection:'column', gap:8 }}><div style={{ fontSize:9, color:'var(--dim)', fontFamily:'var(--mono)', textTransform:'uppercase', letterSpacing:'.07em' }}>Your Templates</div>{mine.map(t => <TemplateCard key={t.id} t={t} />)}</div>}
          {pub.length > 0  && <div style={{ display:'flex', flexDirection:'column', gap:8 }}><div style={{ fontSize:9, color:'var(--dim)', fontFamily:'var(--mono)', textTransform:'uppercase', letterSpacing:'.07em' }}>Public Templates</div>{pub.map(t => <TemplateCard key={t.id} t={t} />)}</div>}
        </>
      )}
      {firing && <FireModal template={firing} onClose={() => { setFiring(null); load() }} />}
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function ContractsPage() {
  const apiPaused = useStore(s => s.apiPaused)
  const settings  = useStore(s => s.settings)
  const myUid     = useStore(s => s.user?.uid)
  const nav       = useNavigate()

  const [tab,       setTab]       = useState('contracts')
  const [data,      setData]      = useState(null)
  const [hist,      setHist]      = useState(null)
  const [stats,     setStats]     = useState(null)
  const [filter,    setFilter]    = useState('all')
  const [page,      setPage]      = useState(1)
  const [sortCol,   setSortCol]   = useState(null)
  const [sortDir,   setSortDir]   = useState('desc')
  const [search,    setSearch]    = useState('')
  const [usernames, setUsernames] = useState({})

  const PERPAGE = 20

  const loadDash  = useCallback(() =>
    api.get('/api/dash/contracts').then(d => { if(d) setData(d) }).catch(() => {})
  , [])
  const loadHist  = useCallback((pg = 1, f = null, sc = null, sd = null) => {
    const sp  = (f && f !== 'all') ? `&status=${f}` : ''
    const srt = sc ? `&sort_col=${sc}&sort_dir=${sd||'desc'}` : ''
    api.get(`/api/contracts/history?page=${pg}&perpage=${PERPAGE}${sp}${srt}`)
      .then(d => { if(d) setHist(d) }).catch(() => {})
  }, [])
  const loadStats = useCallback(() =>
    api.get('/api/contracts/stats').then(d => { if(d) setStats(d) }).catch(() => {})
  , [])

  useEffect(() => { loadDash(); loadHist(1, filter, sortCol, sortDir); loadStats() }, [])
  usePolling(loadDash,  apiPaused ? null : (settings?.contractsInterval||300) * 1000)
  usePolling(() => loadHist(page, filter, sortCol, sortDir), apiPaused ? null : 30000)
  usePolling(loadStats, apiPaused ? null : 60000)

  // Resolve counterparty usernames — DB-only, no HF API cost.
  // Deps: page/filter so it fires when user navigates, NOT on every 30s poll.
  useEffect(() => {
    const visibleContracts = hist?.contracts || data?.contracts || []
    const uids = [...new Set(
      visibleContracts.flatMap(c => [c.inituid, c.otheruid]).filter(Boolean).map(String)
    )]
    if (!uids.length) return
    fetch(`/api/users/resolve?uids=${uids.join(',')}`, { credentials: 'include' })
      .then(r => r.json())
      .then(m => setUsernames(prev => ({ ...prev, ...(m || {}) })))
      .catch(() => {})
  }, [page, filter, sortCol, sortDir])

  const changeFilter = f  => { setFilter(f); setPage(1); loadHist(1, f, sortCol, sortDir) }
  const changePage   = pg => { setPage(pg); loadHist(pg, filter, sortCol, sortDir) }
  const toggleSort   = col => {
    const newDir = sortCol === col ? (sortDir === 'asc' ? 'desc' : 'asc') : 'desc'
    setSortCol(col); setSortDir(newDir); setPage(1)
    loadHist(1, filter, col, newDir)
  }

  const useDB        = hist && hist.total > 0
  const rawContracts = useDB
    ? (hist.contracts || [])
    : (data?.contracts || []).filter(c => filter === 'all' || c.status_n === filter)

  // Post-filter using resolveStatus so stale "Awaiting" contracts don't appear
  // under the Awaiting pill when they're actually expired (> 90 days old).
  const STATUS_N_LABEL = {'1':'Awaiting Approval','2':'Cancelled','5':'Active Deal','6':'Complete','7':'Disputed','8':'Expired'}
  const filterLabel = filter !== 'all' ? STATUS_N_LABEL[filter] : null
  const resolvedContracts = filterLabel
    ? rawContracts.filter(c => resolveStatus(c) === filterLabel)
    : rawContracts

  // Client-side search
  const contracts = search.trim()
    ? resolvedContracts.filter(c =>
        String(c.cid).includes(search) ||
        (c.value  || '').toLowerCase().includes(search.toLowerCase()) ||
        (resolveStatus(c) || '').toLowerCase().includes(search.toLowerCase()) ||
        (c.type   || '').toLowerCase().includes(search.toLowerCase()) ||
        String(c.otheruid || '').includes(search) ||
        String(c.inituid  || '').includes(search)
      )
    : resolvedContracts

  const total      = search.trim() ? contracts.length : (useDB ? hist.total : resolvedContracts.length)
  const totalPages = Math.max(1, Math.ceil(total / PERPAGE))

  // Stats — prefer API stats endpoint (full DB counts), fall back to dash cache
  const s          = stats || {}
  const sTotal     = s.total     ?? (data?.contracts||[]).length
  const sActive    = s.active    ?? 0
  const sComplete  = s.complete  ?? 0
  const sDisputed  = s.disputed  ?? 0
  const sExpired   = s.expired   ?? 0
  const sCancelled = s.cancelled ?? 0
  const compRate   = s.completion_rate ?? (
    (sTotal - sCancelled) > 0 ? Math.round(sComplete / (sTotal - sCancelled) * 100) : 0
  )

  const crawlDone = !!hist?.crawl?.done
  const crawlPage = hist?.crawl?.page ?? 0

  const FILTERS = [
    ['all','All'],['5','Active'],['6','Complete'],['7','Disputed'],
    ['1','Awaiting'],['2','Cancelled'],['8','Expired'],
  ]

  const SortHdr = ({ col, children, style }) => (
    <span className="col-lbl" style={{ cursor:'pointer', userSelect:'none', ...style }}
      onClick={() => toggleSort(col)}>
      {children}{sortCol === col ? (sortDir === 'asc' ? ' ↑' : ' ↓') : ''}
    </span>
  )

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:12 }}>

      {/* Tab bar */}
      <div style={{ display:'flex', borderBottom:'1px solid var(--b1)' }}>
        {[['contracts','📜 Contracts']].map(([k,l]) => (
          <button key={k} className={`tab${tab===k?' on':''}`} onClick={() => setTab(k)}>{l}</button>
        ))}
      </div>

      {tab === 'templates' ? (
        <div className="card">
          <div className="card-head">
            <span className="card-icon">📋</span>
            <span className="card-title">Contract Templates</span>
          </div>
          <div className="card-body"><TemplatesPanel myUid={myUid} /></div>
        </div>
      ) : (
        <div style={{ display:'flex', flexDirection:'column', gap:12 }}>

          {/* Stats bar — 6 tiles */}
          <div style={{
            display:'grid', gridTemplateColumns:'repeat(6,1fr)',
            gap:1, background:'var(--b1)',
            border:'1px solid var(--b1)', borderRadius:'var(--r)', overflow:'hidden',
          }}>
            {[
              { lbl:'Total',    val: sTotal,        color:'var(--text)' },
              { lbl:'Complete', val: sComplete,      color:'var(--acc)'  },
              { lbl:'Rate',     val: `${compRate}%`, color:'var(--acc)'  },
              { lbl:'Active',   val: sActive,        color: sActive   > 0 ? 'var(--acc)' : 'var(--sub)' },
              { lbl:'Disputed', val: sDisputed,      color: sDisputed > 0 ? 'var(--red)' : 'var(--sub)' },
              { lbl:'Expired',  val: sExpired,       color: sExpired  > 0 ? 'rgba(255,71,87,.7)' : 'var(--sub)' },
            ].map(({ lbl, val, color }) => (
              <div key={lbl} style={{ background:'var(--s2)', padding:'10px 12px' }}>
                <div style={{ fontFamily:'var(--mono)', fontSize:15, fontWeight:600, color, lineHeight:1.1, marginBottom:2 }}>
                  {val ?? '--'}
                </div>
                <div style={{ fontSize:9, color:'var(--sub)', textTransform:'uppercase', letterSpacing:'.07em', fontFamily:'var(--mono)' }}>
                  {lbl}
                </div>
              </div>
            ))}
          </div>

          {/* Export panel — gated on crawl state */}
          <ExportPanel crawlDone={crawlDone} crawlPage={crawlPage} totalCount={sTotal} myUid={myUid} />

          {/* Contract list */}
          <div className="card">
            <div className="card-head">
              <span className="card-icon">📜</span>
              <span className="card-title">Contract History</span>
              {hist?.total > 0 && (
                <span style={{ fontSize:10, color:'var(--dim)', fontFamily:'var(--mono)' }}>
                  {hist.total.toLocaleString()} total{!crawlDone ? ' · indexing…' : ''}
                </span>
              )}
            </div>
            <div className="card-body">

              {/* Filter + search row */}
              <div style={{ display:'flex', gap:8, flexWrap:'wrap', alignItems:'center', marginBottom:10 }}>
                <div style={{ display:'flex', gap:4, flexWrap:'wrap', flex:1 }}>
                  {FILTERS.map(([v, l]) => (
                    <button key={v} onClick={() => changeFilter(v)}
                      style={{
                        fontSize:10.5, padding:'3px 10px', borderRadius:12,
                        border:`1px solid ${filter === v ? 'rgba(0,212,180,.35)' : 'var(--b1)'}`,
                        background: filter === v ? 'var(--acc2)' : 'transparent',
                        color: filter === v ? 'var(--acc)' : 'var(--dim)',
                        cursor:'pointer', fontFamily:'var(--sans)', transition:'all var(--ease)',
                      }}>
                      {l}
                    </button>
                  ))}
                </div>
                <input
                  className="inp"
                  placeholder="Search CID, value, UID…"
                  value={search}
                  onChange={e => setSearch(e.target.value)}
                  style={{ fontSize:11, padding:'4px 9px', width:185 }}
                />
              </div>

              {/* Column headers */}
              <div style={{ display:'grid', gridTemplateColumns:'58px 108px 90px 1fr 72px 88px', gap:8, padding:'0 8px 6px', borderBottom:'1px solid var(--b1)', marginBottom:2 }}>
                <SortHdr col="cid">CID</SortHdr>
                <SortHdr col="status">Status</SortHdr>
                <SortHdr col="type">Type</SortHdr>
                <span className="col-lbl">Value</span>
                <span className="col-lbl" style={{ textAlign:'right' }}>Party</span>
                <SortHdr col="value" style={{ textAlign:'right' }}>Date</SortHdr>
              </div>

              {!data && !hist ? (
                <div style={{ display:'flex', flexDirection:'column', gap:5 }}>
                  {[1,2,3,4,5,6].map(i => <div key={i} style={{ height:26, background:'var(--s3)', borderRadius:2, opacity:.35 }}/>)}
                </div>
              ) : contracts.length === 0 ? (
                <div style={{ fontSize:12, color:'var(--sub)', fontStyle:'italic', padding:'12px 0' }}>No contracts</div>
              ) : (
                <>
                  {contracts.map(c => {
                    const status     = resolveStatus(c)
                    const borderColor = STATUS_BORDER[status] || 'transparent'
                    const bgTint      = STATUS_BG[status]    || 'transparent'
                    const isInit      = myUid && String(c.inituid) === String(myUid)
                    const cpUid       = isInit ? c.otheruid : c.inituid
                    const dVal        = displayValue(c)

                    return (
                      <div
                        key={c.cid}
                        onClick={() => nav(`/dashboard/contracts/${c.cid}`)}
                        onMouseOver={e => e.currentTarget.style.filter='brightness(1.18)'}
                        onMouseOut={e  => e.currentTarget.style.filter='none'}
                        style={{
                          display:'grid', gridTemplateColumns:'58px 108px 90px 1fr 72px 88px',
                          gap:8, alignItems:'center',
                          padding:'7px 8px',
                          cursor:'pointer',
                          borderBottom:'1px solid rgba(21,30,46,.5)',
                          borderLeft:`2px solid ${borderColor}`,
                          background: bgTint,
                          marginLeft:-2,
                        }}
                      >
                        {/* CID */}
                        <a
                          href={`https://hackforums.net/contracts.php?action=view&cid=${c.cid}`}
                          target="_blank" rel="noreferrer"
                          onClick={e => e.stopPropagation()}
                          style={{ fontSize:11, color:'var(--acc)', fontFamily:'var(--mono)', fontWeight:600 }}
                        >#{c.cid}</a>

                        {/* Status */}
                        <div style={{ display:'flex', alignItems:'center', gap:5 }}>
                          <span style={{ width:5, height:5, borderRadius:'50%', flexShrink:0, display:'inline-block', background:STATUS_COLORS[status]||'var(--dim)' }}/>
                          <span style={{ fontSize:10, fontFamily:'var(--mono)', fontWeight:600, color:STATUS_COLORS[status]||'var(--sub)', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
                            {status}
                          </span>
                        </div>

                        {/* Type */}
                        <span style={{ fontSize:10, color:'var(--sub)', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
                          {c.type || '--'}
                        </span>

                        {/* Value */}
                        {(() => {
                          if (!dVal) return <span style={{ fontSize:11, color:'var(--dim)', fontFamily:'var(--mono)' }}>--</span>
                          const parsed = parseValue(dVal)
                          if (parsed) return (
                            <span style={{ fontFamily:'var(--mono)', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
                              <span style={{ fontSize:11, color:'var(--text)' }}>{parsed.amount}</span>
                              <span style={{ fontSize:9, color:'var(--dim)', marginLeft:4 }}>via {parsed.via}</span>
                            </span>
                          )
                          return <span style={{ fontSize:11, color:'var(--text)', fontFamily:'var(--mono)', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{dVal}</span>
                        })()}

                        {/* Counterparty UID + username */}
                        <div style={{ textAlign:'right' }}>
                          {cpUid ? (
                            <a
                              href={`https://hackforums.net/member.php?action=profile&uid=${cpUid}`}
                              target="_blank" rel="noreferrer"
                              onClick={e => e.stopPropagation()}
                              style={{ fontSize:10, color:'var(--blue)', fontFamily:'var(--mono)' }}
                            >
                              {usernames[String(cpUid)] || cpUid}
                            </a>
                          ) : <span style={{ fontSize:10, color:'var(--dim)' }}>--</span>}
                        </div>

                        {/* Date */}
                        <div style={{ textAlign:'right' }}>
                          <div style={{ fontSize:10, color:'var(--sub)', fontFamily:'var(--mono)' }}>{ago(c.dateline)}</div>
                          <div style={{ fontSize:9, color:'var(--dim)', fontFamily:'var(--mono)' }}>{fmtDate(c.dateline)}</div>
                        </div>
                      </div>
                    )
                  })}

                  {total > 0 && (
                    <div className="pg">
                      <button className="pg-btn" disabled={page <= 1} onClick={() => changePage(page - 1)}>←</button>
                      <span className="pg-info">{page} / {totalPages} <span style={{ color:'var(--dim)' }}>({total.toLocaleString()})</span></span>
                      <button className="pg-btn" disabled={page >= totalPages} onClick={() => changePage(page + 1)}>→</button>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
