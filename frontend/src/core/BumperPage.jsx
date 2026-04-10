import { useState, useEffect, useCallback, useRef } from 'react'
import { createPortal } from 'react-dom'
import { api } from './api.js'
import useStore from '../store.js'

const isUpgraded = (groups) => (groups || []).some(g => ['9','28','67'].includes(String(g)))

const ago = ts => {
  if (!ts) return null
  const d = Math.floor(Date.now()/1000) - ts
  if (d < 60)    return `${d}s ago`
  if (d < 3600)  return `${Math.floor(d/60)}m ago`
  if (d < 86400) return `${Math.floor(d/3600)}h ago`
  return `${Math.floor(d/86400)}d ago`
}
const fmtDate = ts => ts ? new Date(ts*1000).toLocaleDateString('en-US',{month:'short',day:'numeric'}) : '--'
const fmtDuration = s => {
  if (!s || s < 0) return '—'
  const d = Math.floor(s/86400), h = Math.floor((s%86400)/3600)
  if (d >= 2) return `${d}d`
  if (d === 1) return h > 0 ? `1d ${h}h` : '1d'
  return `${h}h`
}
const fmtCd = s => {
  if (s === null || s === undefined) return '--'
  if (s <= 0) return 'Due now'
  const d = Math.floor(s/86400), h = Math.floor((s%86400)/3600), m = Math.floor((s%3600)/60)
  if (d > 0) return `${d}d ${h}h`
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}
const fmtInterval = h => (!h ? '--' : h < 24 ? `${h}h` : `${Math.round(h/24)}d`)
const fmt = n => Number(n||0).toLocaleString()

const STATUS_COLOR = { '5':'var(--yellow)','6':'var(--acc)','7':'var(--red)','1':'var(--sub)','2':'var(--sub)','8':'var(--sub)' }
const STATUS_LABEL = { '1':'Awaiting','2':'Cancelled','5':'Active','6':'Complete','7':'Disputed','8':'Expired' }
const TYPE_LABEL   = { '1':'Sale','2':'Purchase','3':'Exchange','4':'Trade','5':'Vouch' }

const INTERVAL_OPTIONS = [
  { value: 6,   label: '6 hours'  },
  { value: 8,   label: '8 hours'  },
  { value: 12,  label: '12 hours' },
  { value: 16,  label: '16 hours' },
  { value: 24,  label: '1 day'    },
  { value: 48,  label: '2 days'   },
  { value: 72,  label: '3 days'   },
  { value: 120, label: '5 days'   },
  { value: 168, label: '1 week'   },
]

function usePolling(fn, ms) {
  const ref = useRef(fn); ref.current = fn
  useEffect(() => {
    if (ms == null) return
    const id = setInterval(() => ref.current(), ms)
    return () => clearInterval(id)
  }, [ms])
}
function Tog({ on, onChange }) { return <button className={`tog${on?'':' off'}`} onClick={onChange}/> }

// ── Access Denied ─────────────────────────────────────────────────────────────
function AccessDenied({ feature }) {
  return (
    <div style={{padding:'22px 20px',fontFamily:'var(--mono)',borderRadius:'var(--r)',background:'rgba(232,84,84,.04)',border:'1px solid rgba(232,84,84,.18)'}}>
      <div style={{fontSize:10,color:'var(--red)',letterSpacing:'.1em',marginBottom:8,textTransform:'uppercase'}}>// permission denied</div>
      <div style={{fontSize:20,fontWeight:700,color:'var(--text)',letterSpacing:'.04em',marginBottom:10}}>ACCESS DENIED</div>
      <div style={{fontSize:11,color:'var(--sub)',lineHeight:1.9,marginBottom:18}}>
        <div><span style={{color:'var(--dim)'}}>$ check_access --feature=</span><span style={{color:'var(--yellow)'}}>{feature}</span></div>
        <div><span style={{color:'var(--red)'}}>  ✕ DENIED</span><span style={{color:'var(--dim)'}}> — requires usergroup </span><span style={{color:'var(--acc)'}}>L33t</span><span style={{color:'var(--dim)'}}> or </span><span style={{color:'var(--acc)'}}>Ub3r</span></div>
      </div>
      <a href="https://hackforums.net/upgrade.php" target="_blank" rel="noreferrer"
        style={{display:'inline-flex',alignItems:'center',gap:6,textDecoration:'none',fontSize:11,fontFamily:'var(--mono)',padding:'6px 14px',borderRadius:'var(--r)',background:'rgba(232,84,84,.12)',border:'1px solid rgba(232,84,84,.35)',color:'var(--red)',fontWeight:600}}
        onMouseOver={e=>e.currentTarget.style.background='rgba(232,84,84,.22)'}
        onMouseOut={e=>e.currentTarget.style.background='rgba(232,84,84,.12)'}
      >↗ hackforums.net/upgrade.php</a>
    </div>
  )
}

// ── How It Works ──────────────────────────────────────────────────────────────
function HowItWorks() {
  const [open, setOpen] = useState(false)
  return (
    <div style={{marginBottom:12}}>
      <button onClick={() => setOpen(o=>!o)}
        style={{background:'none',border:'none',color:'var(--sub)',fontSize:11,fontFamily:'var(--sans)',cursor:'pointer',display:'flex',alignItems:'center',gap:5,padding:0}}>
        <span style={{fontFamily:'var(--mono)',fontSize:10}}>{open?'▾':'▸'}</span>
        How bump scheduling works
      </button>
      {open && (
        <div style={{marginTop:8,padding:'10px 12px',background:'var(--bg)',border:'1px solid var(--b1)',borderRadius:'var(--r)',fontSize:11.5,color:'var(--sub)',lineHeight:1.7}}>
          <p style={{marginBottom:6,fontWeight:600,color:'var(--text)'}}>⏱ Timer</p>
          <p style={{marginBottom:10}}>
            Bumps on a fixed schedule. If someone else posted within your window the bump is{' '}
            <strong style={{color:'var(--yellow)'}}>skipped</strong> and rescheduled to{' '}
            <code style={{fontFamily:'var(--mono)',fontSize:10,background:'var(--s3)',padding:'1px 4px',borderRadius:2}}>last post + interval</code>.
          </p>
          <p style={{marginBottom:6,fontWeight:600,color:'var(--text)'}}>📄 Page 1 Watch</p>
          <p style={{marginBottom:0}}>
            Checks every 30 min — bumps the moment your thread leaves page 1.
            HF limits bumps to once every 6h, so 6h is the fastest this can fire.
          </p>
        </div>
      )}
    </div>
  )
}

// ── Budget Bar + Settings ─────────────────────────────────────────────────────
function BudgetSettings({ budgetData, onSave }) {
  const [open,   setOpen]   = useState(false)
  const [val,    setVal]    = useState('')
  const [saving, setSaving] = useState(false)
  const [saved,  setSaved]  = useState(false)

  useEffect(() => { if (budgetData) setVal(String(budgetData.weekly_budget || 0)) }, [budgetData])

  const save = async () => {
    setSaving(true)
    try {
      await api.put('/api/autobump/settings', { weekly_budget: Number(val) || 0 })
      setSaved(true); setTimeout(() => setSaved(false), 2000); onSave()
    } catch {}
    finally { setSaving(false) }
  }

  const budget = budgetData?.weekly_budget || 0
  const used   = budgetData?.bytes_this_week || 0
  const pct    = budget > 0 ? Math.min(100, Math.round((used / budget) * 100)) : 0
  const over   = budget > 0 && used >= budget

  return (
    <div style={{marginBottom:12}}>
      <button onClick={() => setOpen(o=>!o)}
        style={{background:'none',border:'none',color:'var(--sub)',fontSize:11,fontFamily:'var(--sans)',cursor:'pointer',display:'flex',alignItems:'center',gap:5,padding:0}}>
        <span style={{fontFamily:'var(--mono)',fontSize:10}}>{open?'▾':'▸'}</span>
        Weekly byte budget
        {budget > 0 && <span style={{fontFamily:'var(--mono)',fontSize:10,color:over?'var(--red)':'var(--acc)',marginLeft:4}}>({fmt(used)}/{fmt(budget)} bytes{over?' — PAUSED':''})</span>}
      </button>

      {budget > 0 && (
        <div style={{marginTop:6,height:3,background:'var(--b2)',borderRadius:2,overflow:'hidden'}}>
          <div style={{height:'100%',width:`${pct}%`,background:over?'var(--red)':pct>75?'var(--yellow)':'var(--acc)',borderRadius:2,transition:'width .3s'}}/>
        </div>
      )}

      {open && (
        <div style={{marginTop:8,padding:'10px 12px',background:'var(--bg)',border:'1px solid var(--b1)',borderRadius:'var(--r)'}}>
          <p style={{fontSize:11.5,color:'var(--sub)',lineHeight:1.6,marginBottom:8}}>
            Max bytes to spend on bumps per week. Each bump costs <strong style={{color:'var(--text)'}}>~50 bytes</strong> + 10 byte automation fee.
            Set to <strong style={{color:'var(--text)'}}>0</strong> for no limit.
          </p>
          <div style={{display:'flex',gap:6,alignItems:'center'}}>
            <input className="inp" type="number" min="0" step="50" value={val}
              onChange={e=>setVal(e.target.value)} style={{width:100}} placeholder="0 = unlimited"/>
            <button className="btn btn-acc" onClick={save} disabled={saving} style={{fontSize:11}}>
              {saving?<span className="spin"/>:saved?'✓ Saved':'Save'}
            </button>
            {Number(val) > 0 && (
              <span style={{fontSize:10,color:'var(--dim)',fontFamily:'var(--mono)'}}>
                = max {Math.floor(Number(val)/50)} bumps/week
              </span>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ── Stats Modal ───────────────────────────────────────────────────────────────
function contractValue(c) {
  if (c.iprice && c.iprice !== '0' && c.icurrency?.toLowerCase() !== 'other') return `${c.iprice} ${c.icurrency}`
  if (c.oprice && c.oprice !== '0' && c.ocurrency?.toLowerCase() !== 'other') return `${c.oprice} ${c.ocurrency}`
  if (c.iproduct && !['','other','n/a'].includes(c.iproduct.toLowerCase())) return c.iproduct
  if (c.oproduct && !['','other','n/a'].includes(c.oproduct.toLowerCase())) return c.oproduct
  return '—'
}

function PeriodRow({ p, bumpNum, total }) {
  const [expanded, setExpanded] = useState(false)
  const hasContracts = p.contracts.length > 0
  const typeLabel = p.is_current ? 'current' : null

  // Color-code the row by activity
  const activityColor = hasContracts
    ? 'rgba(0,212,180,.12)'
    : 'transparent'

  return (
    <div style={{borderBottom:'1px solid var(--b1)',background:activityColor,borderRadius:4}}>
      {/* Main row */}
      <div style={{display:'grid',gridTemplateColumns:'70px 55px 1fr auto',gap:8,alignItems:'center',padding:'10px 8px',cursor:hasContracts?'pointer':'default',minHeight:44}}
        onClick={() => hasContracts && setExpanded(e=>!e)}>

        {/* Date */}
        <span style={{fontSize:11,fontFamily:'var(--mono)',color:'var(--text)',fontWeight:600}}>
          {fmtDate(p.ts)}
        </span>

        {/* Duration */}
        <span style={{fontSize:10,fontFamily:'var(--mono)',color:p.is_current?'var(--acc)':'var(--dim)'}}>
          {p.is_current ? '▶ now' : fmtDuration(p.duration_s)}
        </span>

        {/* Contracts */}
        <span style={{fontSize:11,color:hasContracts?'var(--acc)':'var(--dim)',fontFamily:'var(--mono)'}}>
          {hasContracts
            ? `${p.contracts.length} contract${p.contracts.length>1?'s':''}`
            : '—'
          }
        </span>

        {/* Reply gain */}
        <span style={{fontSize:11,fontFamily:'var(--mono)',color:
          p.reply_gain == null ? 'var(--dim)'
          : p.reply_gain > 0   ? 'var(--acc)'
          : 'var(--sub)',
          minWidth:40, textAlign:'right'
        }}>
          {p.reply_gain == null ? '—' : p.reply_gain > 0 ? `+${p.reply_gain}` : p.reply_gain}
        </span>
      </div>

      {/* Expanded contracts */}
      {expanded && hasContracts && (
        <div style={{padding:'0 8px 8px',display:'flex',flexDirection:'column',gap:3}}>
          {p.contracts.map(c => (
            <a key={c.cid}
              href={`https://hackforums.net/contracts.php?action=view&cid=${c.cid}`}
              target="_blank" rel="noreferrer"
              style={{display:'grid',gridTemplateColumns:'54px 1fr 60px 64px',gap:6,padding:'4px 6px',background:'var(--bg)',borderRadius:3,textDecoration:'none',border:'1px solid var(--b1)'}}>
              <span style={{fontSize:10,color:'var(--dim)',fontFamily:'var(--mono)'}}>#{c.cid}</span>
              <span style={{fontSize:11,color:'var(--text)',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{contractValue(c)}</span>
              <span style={{fontSize:10,color:'var(--sub)',fontFamily:'var(--mono)'}}>{TYPE_LABEL[c.type_n]||'—'}</span>
              <span style={{fontSize:10,fontFamily:'var(--mono)',color:STATUS_COLOR[c.status_n]||'var(--dim)',textAlign:'right'}}>{STATUS_LABEL[c.status_n]||'—'}</span>
            </a>
          ))}
        </div>
      )}
    </div>
  )
}

function StatsModal({ job, onClose }) {
  const [stats,   setStats]   = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get(`/api/autobump/jobs/${job.tid}/stats`)
      .then(d => { setStats(d); setLoading(false) })
      .catch(() => setLoading(false))
  }, [job.tid])

  const periods      = stats?.bump_periods || []
  const hasReplyData = stats?.has_reply_data

  const contractsPerBump = stats && stats.total_bumps > 0
    ? (stats.total_contracts / stats.total_bumps).toFixed(1)
    : null

  return createPortal(
    <>
      {/* Backdrop — renders at body level so fixed positioning always works */}
      <div onClick={onClose}
        style={{position:'fixed',inset:0,background:'rgba(0,0,0,.7)',zIndex:9000}}/>

      {/* Modal */}
      <div onClick={e => e.stopPropagation()}
        style={{
          position:'fixed', top:8, left:'50%', transform:'translateX(-50%)',
          zIndex:9001,
          width:'calc(100vw - 16px)', maxWidth:580,
          maxHeight:'calc(100vh - 16px)',
          background:'var(--s2)', border:'1px solid var(--b2)',
          borderRadius:'var(--r)', display:'flex', flexDirection:'column',
          overflow:'hidden',
        }}>

        {/* Header */}
        <div style={{padding:'11px 14px',borderBottom:'1px solid var(--b1)',display:'flex',alignItems:'center',gap:8,flexShrink:0}}>
          <div style={{flex:1,minWidth:0}}>
            <div style={{fontSize:12,fontWeight:600,color:'var(--acc)',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>
              {job.thread_title || `Thread #${job.tid}`}
            </div>
            <div style={{fontSize:10,color:'var(--dim)',fontFamily:'var(--mono)',marginTop:2}}>
              TID {job.tid} · FID {job.fid || '—'} · {(job.mode||'timer').toUpperCase()}
            </div>
          </div>
          <button onClick={onClose}
            style={{background:'none',border:'none',color:'var(--sub)',cursor:'pointer',fontSize:20,lineHeight:1,padding:'6px 8px',flexShrink:0,minWidth:36,minHeight:36,display:'flex',alignItems:'center',justifyContent:'center'}}>×</button>
        </div>

        {/* Body */}
        <div style={{overflowY:'auto',flex:1}}>
          {loading ? (
            <div style={{display:'flex',justifyContent:'center',padding:32}}><div className="spin"/></div>
          ) : !stats ? (
            <div style={{color:'var(--sub)',fontSize:12,textAlign:'center',padding:32}}>Could not load stats</div>
          ) : (
            <>
              {/* Summary strip */}
              <div style={{display:'grid',gridTemplateColumns:'repeat(4,1fr)',borderBottom:'1px solid var(--b1)'}}>
                {[
                  { label:'Bumps',            value: fmt(stats.total_bumps)                               },
                  { label:'Contracts',        value: fmt(stats.total_contracts)                           },
                  { label:'Per bump',         value: contractsPerBump != null ? `${contractsPerBump}` : '—' },
                  { label:'Bytes spent',      value: `~${fmt(stats.bytes_spent)}`                         },
                ].map(s => (
                  <div key={s.label} style={{padding:'10px 12px',borderRight:'1px solid var(--b1)'}}>
                    <div style={{fontSize:9,color:'var(--dim)',textTransform:'uppercase',letterSpacing:'.08em',fontFamily:'var(--mono)',marginBottom:3}}>{s.label}</div>
                    <div style={{fontSize:16,fontWeight:700,fontFamily:'var(--mono)',color:'var(--text)'}}>{s.value}</div>
                  </div>
                ))}
              </div>

              {/* Column headers */}
              <div style={{display:'grid',gridTemplateColumns:'70px 55px 1fr auto',gap:8,padding:'6px 8px',borderBottom:'1px solid var(--b1)'}}>
                <span className="col-lbl">Bumped</span>
                <span className="col-lbl">Active</span>
                <span className="col-lbl">Contracts after</span>
                <span className="col-lbl" style={{textAlign:'right'}}>
                  {hasReplyData ? 'Replies' : 'Replies*'}
                </span>
              </div>

              {/* Bump periods */}
              <div style={{padding:'4px 8px',display:'flex',flexDirection:'column',gap:1}}>
                {periods.length === 0 ? (
                  <div style={{color:'var(--sub)',fontSize:12,padding:'16px 0',textAlign:'center'}}>No bumps yet</div>
                ) : periods.map((p, i) => (
                  <PeriodRow key={p.ts} p={p} bumpNum={stats.total_bumps - i} total={stats.total_bumps}/>
                ))}
              </div>

              {/* Reply data note */}
              {!hasReplyData && (
                <div style={{padding:'8px 12px',borderTop:'1px solid var(--b1)',fontSize:10,color:'var(--dim)',fontFamily:'var(--mono)'}}>
                  * Reply tracking started with this update — future bumps will capture reply counts
                </div>
              )}

              {/* Click-to-expand hint if there are contracts */}
              {stats.total_contracts > 0 && (
                <div style={{padding:'6px 12px',borderTop:'1px solid var(--b1)',fontSize:10,color:'var(--dim)'}}>
                  Click any row with contracts to expand details
                </div>
              )}
            </>
          )}
        </div>
      </div>
    </>,
    document.body
  )
}

// ── Mode Badge ────────────────────────────────────────────────────────────────
function ModeBadge({ mode }) {
  if (mode === 'page1')
    return <span style={{fontSize:9,fontFamily:'var(--mono)',fontWeight:700,padding:'1px 5px',borderRadius:3,letterSpacing:'.06em',textTransform:'uppercase',background:'rgba(75,140,245,.12)',border:'1px solid rgba(75,140,245,.3)',color:'var(--blue)'}}>PG1</span>
  return <span style={{fontSize:9,fontFamily:'var(--mono)',fontWeight:700,padding:'1px 5px',borderRadius:3,letterSpacing:'.06em',textTransform:'uppercase',background:'rgba(0,212,180,.08)',border:'1px solid rgba(0,212,180,.2)',color:'var(--acc)'}}>TIMER</span>
}

// ── Job Card ──────────────────────────────────────────────────────────────────
function JobCard({ job, onToggle, onRemove, onStats }) {
  const mode    = job.mode || 'timer'
  const isPage1 = mode === 'page1'
  const isDue   = (job.seconds_until_bump ?? 1) <= 0
  const wasSkipped = job.last_skip && (!job.last_bumped || job.last_skip > job.last_bumped)

  return (
    <div style={{background:'var(--bg)',border:`1px solid ${isDue?(isPage1?'rgba(75,140,245,.3)':'rgba(0,212,180,.25)'):'var(--b1)'}`,borderRadius:'var(--r)',padding:'12px 14px',opacity:job.enabled?1:0.5,transition:'opacity .2s,border-color .2s'}}>
      <div style={{display:'flex',alignItems:'flex-start',gap:12}}>
        <div style={{flex:1,minWidth:0}}>
          <div style={{display:'flex',alignItems:'center',gap:6,marginBottom:5}}>
            <a href={`https://hackforums.net/showthread.php?tid=${job.tid}`} target="_blank" rel="noreferrer"
              style={{fontSize:13,fontWeight:600,color:'var(--acc)',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',flex:1,minWidth:0}}>
              {job.thread_title||`Thread #${job.tid}`}
            </a>
            <ModeBadge mode={mode}/>
          </div>
          <div style={{display:'flex',gap:10,flexWrap:'wrap',fontSize:10.5,color:'var(--sub)',fontFamily:'var(--mono)'}}>
            <span style={{color:'var(--muted)'}}>TID {job.tid}</span>
            {isPage1
              ? <span>bumps when off page 1 · max every {fmtInterval(job.interval_h)}</span>
              : <span>every {fmtInterval(job.interval_h)}</span>
            }
            {job.bump_until && !job.expired && <span style={{color:'var(--yellow)'}}>until {new Date(job.bump_until*1000).toLocaleDateString()}</span>}
            {job.expired && <span style={{color:'var(--red)'}}>expired</span>}
            <span style={{color:'var(--acc)'}}>{job.bump_count} bump{job.bump_count!==1?'s':''}</span>
            {job.fid && <span>FID {job.fid}</span>}
          </div>
          <div style={{display:'flex',gap:12,flexWrap:'wrap',marginTop:6,fontSize:11,color:'var(--sub)'}}>
            {job.lastpost_ts && (
              <span>Last post <strong style={{color:'var(--text)',fontFamily:'var(--mono)'}}>{ago(job.lastpost_ts)}</strong>
                {job.lastposter && <span style={{color:'var(--dim)'}}> by {job.lastposter}</span>}
              </span>
            )}
            {job.last_bumped && <span>Last bumped <strong style={{color:'var(--text)',fontFamily:'var(--mono)'}}>{ago(job.last_bumped)}</strong></span>}
            {wasSkipped && (
              <span style={{color:isPage1?'var(--acc)':'var(--yellow)'}}>
                {isPage1?`✓ on page 1 as of ${ago(job.last_skip)}`:`⚠ skipped ${ago(job.last_skip)} — thread was active`}
              </span>
            )}
          </div>
        </div>
        <div style={{flexShrink:0,display:'flex',flexDirection:'column',alignItems:'flex-end',gap:8}}>
          <div style={{textAlign:'right'}}>
            <div style={{fontFamily:'var(--mono)',fontSize:16,fontWeight:700,lineHeight:1.1,color:isDue?(isPage1?'var(--blue)':'var(--acc)'):'var(--text)'}}>
              {fmtCd(job.seconds_until_bump)}
            </div>
            <div style={{fontSize:9,color:'var(--dim)',textTransform:'uppercase',letterSpacing:'.06em',fontFamily:'var(--mono)',marginTop:2}}>
              {isPage1?(isDue?'checking soon':'next check'):(isDue?'bumping soon':'next bump')}
            </div>
          </div>
          <div style={{display:'flex',gap:6,alignItems:'center'}}>
            <button className="btn btn-ghost" onClick={onStats} style={{fontSize:11,padding:'3px 8px'}}>📊</button>
            <Tog on={!!job.enabled} onChange={onToggle}/>
            <button className="btn btn-danger" onClick={onRemove}>Remove</button>
          </div>
        </div>
      </div>
    </div>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function BumperPage() {
  const apiPaused = useStore(s => s.apiPaused)
  const settings  = useStore(s => s.settings)
  const user      = useStore(s => s.user)
  const upgraded  = isUpgraded(user?.groups)

  const [jobs,       setJobs]       = useState([])
  const [log,        setLog]        = useState([])
  const [budgetData, setBudgetData] = useState(null)
  const [statsJob,   setStatsJob]   = useState(null)

  const [tid,        setTid]        = useState('')
  const [mode,       setMode]       = useState('timer')
  const [iv,         setIv]         = useState(24)
  const [expiryDays, setExpiryDays] = useState(0)
  const [busy,       setBusy]       = useState(false)
  const [msg,        setMsg]        = useState(null)
  const [tab,        setTab]        = useState('jobs')

  const load       = useCallback(() => api.get('/api/autobump/jobs').then(d => setJobs(d?.jobs||[])).catch(()=>{}), [])
  const loadLog    = useCallback(() => api.get('/api/autobump/log').then(d => setLog(d?.log||[])).catch(()=>{}), [])
  const loadBudget = useCallback(() => api.get('/api/autobump/settings').then(d => setBudgetData(d)).catch(()=>{}), [])

  useEffect(() => { load(); loadLog(); loadBudget() }, [])
  usePolling(load,    apiPaused ? null : settings.bumperInterval * 1000)
  usePolling(loadLog, apiPaused ? null : settings.bumperInterval * 1000)

  const add = async () => {
    if (!tid) return
    setBusy(true); setMsg(null)
    try {
      const bump_until = expiryDays > 0 ? Math.floor(Date.now()/1000) + (expiryDays * 86400) : null
      await api.post('/api/autobump/jobs', { tid, mode, interval_h: Number(iv), bump_until })
      setTid(''); setMsg({ ok:true, t:'Job added' }); load()
    } catch(e) { setMsg({ ok:false, t:e.message }) }
    finally { setBusy(false) }
  }

  const remove = async t => { await api.delete(`/api/autobump/jobs/${t}`); load() }
  const toggle = async (t, en) => { await api.patch(`/api/autobump/jobs/${t}`, { enabled:en }); load() }
  const logActionColor = a => a==='bumped'?'var(--acc)':a==='error'?'var(--red)':'var(--yellow)'

  const budgetOver = budgetData?.weekly_budget > 0 && budgetData?.bytes_this_week >= budgetData?.weekly_budget

  return (
    <div style={{display:'flex',flexDirection:'column',gap:14}}>

      {statsJob && <StatsModal job={statsJob} onClose={() => setStatsJob(null)}/>}

      <div className="card">
        <div className="card-head">
          <span className="card-icon">⬆</span>
          <span className="card-title">Auto Bumper</span>
          {jobs.length > 0 && <span className="badge badge-yel">{jobs.length} JOB{jobs.length>1?'S':''}</span>}
          {budgetOver && <span className="badge badge-red">BUDGET PAUSED</span>}
          <span style={{fontSize:10,color:'var(--dim)',fontFamily:'var(--mono)',marginLeft:'auto'}}>~50 byte Stanley fee</span>
        </div>
        <div className="card-body">
          {upgraded ? (
            <>
              <HowItWorks/>
              <BudgetSettings budgetData={budgetData} onSave={loadBudget}/>

              <div style={{display:'flex',gap:6,alignItems:'center',flexWrap:'wrap'}}>
                <input className="inp" placeholder="Thread ID" value={tid}
                  onChange={e=>setTid(e.target.value)} onKeyDown={e=>e.key==='Enter'&&add()} style={{width:110}}/>

                <select className="inp" value={mode} onChange={e=>setMode(e.target.value)} style={{width:140}}>
                  <option value="timer">⏱ Timer</option>
                  <option value="page1">📄 Page 1 Watch</option>
                </select>

                <div style={{display:'flex',alignItems:'center',gap:4}}>
                  <span style={{fontSize:10,color:'var(--dim)',fontFamily:'var(--mono)',whiteSpace:'nowrap'}}>
                    {mode==='page1' ? 'max every' : 'every'}
                  </span>
                  <select className="inp" value={iv} onChange={e=>setIv(Number(e.target.value))} style={{width:100}}>
                    {INTERVAL_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
                  </select>
                </div>

                <select className="inp" value={expiryDays} onChange={e=>setExpiryDays(Number(e.target.value))} style={{width:110}}>
                  <option value={0}>Forever</option>
                  <option value={7}>1 week</option>
                  <option value={14}>2 weeks</option>
                  <option value={30}>1 month</option>
                  <option value={60}>2 months</option>
                </select>

                <button className="btn btn-acc" onClick={add} disabled={busy||!tid}>
                  {busy?<span className="spin"/>:'+ Add'}
                </button>
                {msg && <span style={{fontSize:11,color:msg.ok?'var(--acc)':'var(--red)'}}>{msg.t}</span>}
              </div>

              {mode==='page1' && (
                <div style={{marginTop:8,padding:'7px 10px',background:'rgba(75,140,245,.06)',border:'1px solid rgba(75,140,245,.18)',borderRadius:'var(--r)',fontSize:11,color:'var(--sub)'}}>
                  Checks every 30 min — bumps the moment your thread leaves page 1.
                  HF limits bumps to once every 6h, so <strong style={{color:'var(--text)'}}>6 hours</strong> is the fastest this can fire.
                </div>
              )}
            </>
          ) : <AccessDenied feature="auto_bumper"/>}
        </div>
      </div>

      <div className="card">
        <div className="card-body" style={{padding:'12px 14px 0'}}>
          <div className="tabs">
            <button className={`tab${tab==='jobs'?' on':''}`} onClick={()=>setTab('jobs')}>Jobs ({jobs.length})</button>
            <button className={`tab${tab==='log'?' on':''}`} onClick={()=>setTab('log')}>Log ({log.length})</button>
          </div>
        </div>
        <div className="card-body">
          {tab==='jobs' && (
            jobs.length===0
              ? <div className="empty" style={{padding:'24px 0'}}><span style={{fontSize:20}}>📋</span><span style={{fontSize:12}}>No bump jobs yet</span></div>
              : <div style={{display:'flex',flexDirection:'column',gap:8}}>
                  {jobs.map(job => (
                    <JobCard key={job.id} job={job}
                      onToggle={() => toggle(job.tid, !job.enabled)}
                      onRemove={() => remove(job.tid)}
                      onStats={()  => setStatsJob(job)}
                    />
                  ))}
                </div>
          )}
          {tab==='log' && (
            log.length===0
              ? <div className="empty" style={{padding:'24px 0'}}><span style={{fontSize:20}}>📋</span><span style={{fontSize:12}}>No bump log yet</span></div>
              : <>
                  <div style={{display:'grid',gridTemplateColumns:'58px 1fr 90px 54px',gap:8,padding:'0 0 6px',borderBottom:'1px solid var(--b1)',marginBottom:2}}>
                    <span className="col-lbl">Action</span><span className="col-lbl">Reason</span>
                    <span className="col-lbl">Thread</span><span className="col-lbl" style={{textAlign:'right'}}>When</span>
                  </div>
                  {log.slice(0,60).map(entry => (
                    <div key={entry.id} style={{display:'grid',gridTemplateColumns:'58px 1fr 90px 54px',gap:8,alignItems:'center',padding:'5px 0',borderBottom:'1px solid rgba(21,30,46,.5)'}}>
                      <span style={{fontSize:10.5,fontFamily:'var(--mono)',fontWeight:600,color:logActionColor(entry.action)}}>{entry.action}</span>
                      <span style={{fontSize:11,color:'var(--text)',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{entry.reason||'--'}</span>
                      <span style={{fontSize:10,color:'var(--sub)',fontFamily:'var(--mono)',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{entry.tid}</span>
                      <span style={{fontSize:10,color:'var(--sub)',textAlign:'right',fontFamily:'var(--mono)'}}>{ago(entry.ts)}</span>
                    </div>
                  ))}
                </>
          )}
        </div>
      </div>

    </div>
  )
}
