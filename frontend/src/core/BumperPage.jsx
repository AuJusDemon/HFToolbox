import { useState, useEffect, useCallback, useRef } from 'react'
import { api } from './api.js'
import useStore from '../store.js'

const ago = ts => {
  if (!ts) return null
  const d = Math.floor(Date.now()/1000) - ts
  if (d < 60)    return `${d}s ago`
  if (d < 3600)  return `${Math.floor(d/60)}m ago`
  if (d < 86400) return `${Math.floor(d/3600)}h ago`
  return `${Math.floor(d/86400)}d ago`
}
const fmtCd = s => {
  if (s === null || s === undefined) return '--'
  if (s <= 0) return 'Due now'
  const h = Math.floor(s/3600), m = Math.floor((s%3600)/60)
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}

function usePolling(fn, ms) {
  const ref = useRef(fn); ref.current = fn
  useEffect(() => {
    if (ms == null) return  // null = paused
    const id = setInterval(() => ref.current(), ms)
    return () => clearInterval(id)
  }, [ms])
}

function Tog({ on, onChange }) {
  return <button className={`tog${on?'':' off'}`} onClick={onChange}/>
}

// How the bumper works — shown inline
function HowItWorks() {
  const [open, setOpen] = useState(false)
  return (
    <div style={{marginBottom:12}}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{background:'none',border:'none',color:'var(--sub)',fontSize:11,fontFamily:'var(--sans)',cursor:'pointer',display:'flex',alignItems:'center',gap:5,padding:0}}
      >
        <span style={{fontFamily:'var(--mono)',fontSize:10}}>{open?'▾':'▸'}</span>
        How bump scheduling works
      </button>
      {open && (
        <div style={{marginTop:8,padding:'10px 12px',background:'var(--bg)',border:'1px solid var(--b1)',borderRadius:'var(--r)',fontSize:11.5,color:'var(--sub)',lineHeight:1.7}}>
          <p style={{marginBottom:6}}>
            The bumper runs every <strong style={{color:'var(--text)'}}>30 minutes</strong> and checks if each job is due.
            When a job is due, it first checks the thread's last post timestamp.
          </p>
          <p style={{marginBottom:6}}>
            If someone posted within your interval window — for example, within the last 24h on a 24h job —
            it <strong style={{color:'var(--yellow)'}}>skips</strong> the bump and reschedules to{' '}
            <code style={{fontFamily:'var(--mono)',fontSize:10,background:'var(--s3)',padding:'1px 4px',borderRadius:2}}>last post time + interval</code>.
            This prevents double-bumping when your thread is already active.
          </p>
          <p style={{marginBottom:0}}>
            When the thread is quiet and the window has passed, it charges the{' '}
            <strong style={{color:'var(--text)'}}>10 byte fee</strong> to your account and posts
            a bump (which costs ~50 bytes to Stanley, HF's system bot).
          </p>
        </div>
      )}
    </div>
  )
}

function JobCard({ job, onToggle, onRemove }) {
  const isDue      = (job.seconds_until_bump ?? 1) <= 0
  const wasSkipped = job.last_skip && (!job.last_bumped || job.last_skip > job.last_bumped)

  return (
    <div style={{
      background:'var(--bg)',
      border:`1px solid ${isDue ? 'rgba(0,212,180,.25)' : 'var(--b1)'}`,
      borderRadius:'var(--r)',
      padding:'12px 14px',
      opacity: job.enabled ? 1 : 0.5,
      transition: 'opacity .2s, border-color .2s',
    }}>
      <div style={{display:'flex',alignItems:'flex-start',gap:12}}>

        {/* Left — thread info */}
        <div style={{flex:1,minWidth:0}}>
          <a
            href={`https://hackforums.net/showthread.php?tid=${job.tid}`}
            target="_blank" rel="noreferrer"
            style={{fontSize:13,fontWeight:600,color:'var(--acc)',display:'block',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',marginBottom:5}}
          >
            {job.thread_title || `Thread #${job.tid}`}
          </a>

          {/* Meta row */}
          <div style={{display:'flex',gap:10,flexWrap:'wrap',fontSize:10.5,color:'var(--sub)',fontFamily:'var(--mono)'}}>
            <span style={{color:'var(--muted)'}}>TID {job.tid}</span>
            <span>every {job.interval_h}h</span>
            <span style={{color:'var(--acc)'}}>{job.bump_count} bump{job.bump_count!==1?'s':''}</span>
            {job.fid && <span>FID {job.fid}</span>}
          </div>

          {/* Status row */}
          <div style={{display:'flex',gap:12,flexWrap:'wrap',marginTop:6,fontSize:11,color:'var(--sub)'}}>
            {job.lastpost_ts && (
              <span>
                Last post <strong style={{color:'var(--text)',fontFamily:'var(--mono)'}}>{ago(job.lastpost_ts)}</strong>
                {job.lastposter && <span style={{color:'var(--dim)'}}> by {job.lastposter}</span>}
              </span>
            )}
            {job.last_bumped && (
              <span>
                Last bumped <strong style={{color:'var(--text)',fontFamily:'var(--mono)'}}>{ago(job.last_bumped)}</strong>
              </span>
            )}
            {wasSkipped && (
              <span style={{color:'var(--yellow)'}}>
                ⚠ skipped {ago(job.last_skip)} — thread was active
              </span>
            )}
          </div>
        </div>

        {/* Right — countdown + controls */}
        <div style={{flexShrink:0,display:'flex',flexDirection:'column',alignItems:'flex-end',gap:8}}>
          <div style={{textAlign:'right'}}>
            <div style={{
              fontFamily:'var(--mono)',
              fontSize:16,
              fontWeight:700,
              color: isDue ? 'var(--acc)' : 'var(--text)',
              lineHeight:1.1,
            }}>
              {fmtCd(job.seconds_until_bump)}
            </div>
            <div style={{fontSize:9,color:'var(--dim)',textTransform:'uppercase',letterSpacing:'.06em',fontFamily:'var(--mono)',marginTop:2}}>
              {isDue ? 'bumping soon' : 'next bump'}
            </div>
          </div>
          <div style={{display:'flex',gap:8,alignItems:'center'}}>
            <Tog on={!!job.enabled} onChange={onToggle}/>
            <button className="btn btn-danger" onClick={onRemove}>Remove</button>
          </div>
        </div>

      </div>
    </div>
  )
}

export default function BumperPage() {
  const apiPaused = useStore(s => s.apiPaused)
  const settings  = useStore(s => s.settings)
  const [jobs, setJobs] = useState([])
  const [log,  setLog]  = useState([])
  const [tid,  setTid]  = useState('')
  const [iv,   setIv]   = useState(6)
  const [busy, setBusy] = useState(false)
  const [msg,  setMsg]  = useState(null)
  const [tab,  setTab]  = useState('jobs')

  const load    = useCallback(() => api.get('/api/autobump/jobs').then(d => setJobs(d?.jobs||[])).catch(()=>{}),[])
  const loadLog = useCallback(() => api.get('/api/autobump/log').then(d => setLog(d?.log||[])).catch(()=>{}), [])

  useEffect(() => { load(); loadLog() }, [])
  usePolling(load,    apiPaused ? null : settings.bumperInterval * 1000)
  usePolling(loadLog, apiPaused ? null : settings.bumperInterval * 1000)

  const add = async () => {
    if (!tid) return
    setBusy(true); setMsg(null)
    try {
      await api.post('/api/autobump/jobs', { tid, interval_h: Number(iv) })
      setTid(''); setMsg({ ok:true, t:'Job added' }); load()
    } catch(e) { setMsg({ ok:false, t:e.message }) }
    finally { setBusy(false) }
  }
  const remove = async t => { await api.delete(`/api/autobump/jobs/${t}`); load() }
  const toggle = async (t, en) => { await api.patch(`/api/autobump/jobs/${t}`, { enabled:en }); load() }

  const logActionColor = a => a==='bumped'?'var(--acc)':a==='error'?'var(--red)':'var(--yellow)'

  return (
    <div style={{display:'flex',flexDirection:'column',gap:14}}>

      {/* Add job card */}
      <div className="card">
        <div className="card-head">
          <span className="card-icon">⬆</span>
          <span className="card-title">Auto Bumper</span>
          {jobs.length > 0 && <span className="badge badge-yel">{jobs.length} JOB{jobs.length>1?'S':''}</span>}
          <span style={{fontSize:10,color:'var(--dim)',fontFamily:'var(--mono)',marginLeft:'auto'}}>10 bytes + ~50 Stanley fee</span>
        </div>
        <div className="card-body">
          <HowItWorks/>
          <div style={{display:'flex',gap:6,alignItems:'center',flexWrap:'wrap'}}>
            <input
              className="inp" placeholder="Thread ID"
              value={tid} onChange={e=>setTid(e.target.value)}
              onKeyDown={e=>e.key==='Enter'&&add()}
              style={{width:110}}
            />
            <select className="inp" value={iv} onChange={e=>setIv(Number(e.target.value))} style={{width:110}}>
              {[6,8,12,16,24].map(h=><option key={h} value={h}>Every {h}h</option>)}
            </select>
            <button className="btn btn-acc" onClick={add} disabled={busy||!tid}>
              {busy?<span className="spin"/>:'+ Add'}
            </button>
            {msg&&<span style={{fontSize:11,color:msg.ok?'var(--acc)':'var(--red)'}}>{msg.t}</span>}
          </div>
        </div>
      </div>

      {/* Jobs / Log */}
      <div className="card">
        <div className="card-body" style={{padding:'12px 14px 0'}}>
          <div className="tabs">
            <button className={`tab${tab==='jobs'?' on':''}`} onClick={()=>setTab('jobs')}>
              Jobs ({jobs.length})
            </button>
            <button className={`tab${tab==='log'?' on':''}`} onClick={()=>setTab('log')}>
              Log ({log.length})
            </button>
          </div>
        </div>

        <div className="card-body">

          {tab === 'jobs' && (
            jobs.length === 0
              ? <div className="empty" style={{padding:'24px 0'}}>
                  <span style={{fontSize:20}}>📋</span>
                  <span style={{fontSize:12}}>No bump jobs yet — add a thread ID above</span>
                </div>
              : <div style={{display:'flex',flexDirection:'column',gap:8}}>
                  {jobs.map(job => (
                    <JobCard
                      key={job.id}
                      job={job}
                      onToggle={() => toggle(job.tid, !job.enabled)}
                      onRemove={() => remove(job.tid)}
                    />
                  ))}
                </div>
          )}

          {tab === 'log' && (
            log.length === 0
              ? <div className="empty" style={{padding:'24px 0'}}>
                  <span style={{fontSize:20}}>📋</span>
                  <span style={{fontSize:12}}>No bump log yet</span>
                </div>
              : <>
                  <div style={{display:'grid',gridTemplateColumns:'58px 1fr 90px 54px',gap:8,padding:'0 0 6px',borderBottom:'1px solid var(--b1)',marginBottom:2}}>
                    <span className="col-lbl">Action</span>
                    <span className="col-lbl">Reason</span>
                    <span className="col-lbl">Thread</span>
                    <span className="col-lbl" style={{textAlign:'right'}}>When</span>
                  </div>
                  {log.slice(0,60).map(entry => (
                    <div key={entry.id} style={{display:'grid',gridTemplateColumns:'58px 1fr 90px 54px',gap:8,alignItems:'center',padding:'5px 0',borderBottom:'1px solid rgba(21,30,46,.5)'}}>
                      <span style={{fontSize:10.5,fontFamily:'var(--mono)',fontWeight:600,color:logActionColor(entry.action)}}>
                        {entry.action}
                      </span>
                      <span style={{fontSize:11,color:'var(--text)',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>
                        {entry.reason || '--'}
                      </span>
                      <span style={{fontSize:10,color:'var(--sub)',fontFamily:'var(--mono)',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>
                        {entry.tid}
                      </span>
                      <span style={{fontSize:10,color:'var(--sub)',textAlign:'right',fontFamily:'var(--mono)'}}>
                        {ago(entry.ts)}
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
