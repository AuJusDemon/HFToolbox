import { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, throttledInterval } from './api.js'
import useStore from '../store.js'

const ago = ts => {
  if (!ts) return '--'
  const d = Math.floor(Date.now()/1000) - ts
  if (d < 60)    return `${d}s ago`
  if (d < 3600)  return `${Math.floor(d/60)}m ago`
  if (d < 86400) return `${Math.floor(d/3600)}h ago`
  return `${Math.floor(d/86400)}d ago`
}
const fmt = n => Number(n||0).toLocaleString()
const fmtCd = s => {
  if (s === null || s === undefined) return '--'
  if (s <= 0) return 'Due now'
  const h = Math.floor(s/3600), m = Math.floor((s%3600)/60)
  return h > 0 ? `${h}h ${m}m` : `${m}m`
}

function usePolling(fn, ms) {
  const ref = useRef(fn); ref.current = fn
  useEffect(() => {
    const id = setInterval(() => ref.current(), ms)
    return () => clearInterval(id)
  }, [ms])
}

const STATUS_COLORS = {
  'Active Deal':       'var(--acc)',
  'Complete':          'var(--sub)',
  'Awaiting Approval': 'var(--yellow)',
  'Disputed':          'var(--red)',
  'Cancelled':         'var(--dim)',
  'Expired':           'rgba(255,71,87,.5)',
  'Unknown':           'var(--dim)',
}

// Shared card header with title, badge, and "Full view →" button
function CardHeader({ icon, title, badge, badgeColor, to, extra }) {
  const nav = useNavigate()
  return (
    <div className="card-head">
      <span className="card-icon">{icon}</span>
      <span className="card-title">{title}</span>
      {badge != null && (
        <span className="badge" style={{
          background: `${badgeColor}20`,
          color: badgeColor,
          borderColor: `${badgeColor}40`,
        }}>{badge}</span>
      )}
      {extra}
      <button
        className="btn btn-ghost"
        style={{marginLeft:'auto', fontSize:10, padding:'2px 8px'}}
        onClick={e => { e.stopPropagation(); nav(to) }}
      >
        Full view →
      </button>
    </div>
  )
}

// ── AUTO BUMPER ───────────────────────────────────────────────────────────────
function BumperOverview() {
  const nav = useNavigate()
  const [jobs, setJobs] = useState([])
  const load = useCallback(() =>
    api.get('/api/autobump/jobs').then(d => setJobs(d?.jobs||[])).catch(() => {})
  , [])
  useEffect(() => { load() }, [])
  const throttle = useStore(s => s.throttle)
  usePolling(load, throttledInterval(60000, throttle))

  const enabled  = jobs.filter(j => j.enabled)
  const dueCount = jobs.filter(j => j.enabled && (j.seconds_until_bump||0) <= 0).length

  // Sort: due first, then soonest next bump, disabled jobs last
  const sorted = [...jobs].sort((a, b) => {
    if (!a.enabled && b.enabled) return 1
    if (a.enabled && !b.enabled) return -1
    const aS = a.seconds_until_bump || 0
    const bS = b.seconds_until_bump || 0
    if (aS <= 0 && bS > 0) return -1
    if (bS <= 0 && aS > 0) return 1
    return aS - bS
  })
  const PREVIEW = 3
  const visible  = sorted.slice(0, PREVIEW)
  const overflow = sorted.length - PREVIEW

  return (
    <div className="card" style={{cursor:'pointer'}} onClick={() => nav('/dashboard/bumper')}>
      <CardHeader
        icon="⬆" title="Auto Bumper" to="/dashboard/bumper"
        badge={
          dueCount > 0
            ? `${dueCount} DUE NOW`
            : jobs.length > 0
              ? `${enabled.length} / ${jobs.length} ACTIVE`
              : null
        }
        badgeColor={dueCount > 0 ? 'var(--acc)' : 'var(--yellow)'}
      />
      <div className="card-body">
        {jobs.length === 0 ? (
          <div style={{fontSize:11,color:'var(--sub)',fontStyle:'italic'}}>No bump jobs — add one on the bumper page</div>
        ) : (
          <>
            <div style={{display:'grid',gridTemplateColumns:'1fr 80px 70px 64px',gap:8,padding:'0 0 5px',borderBottom:'1px solid var(--b1)',marginBottom:2}}>
              <span className="col-lbl">Thread</span>
              <span className="col-lbl">Interval</span>
              <span className="col-lbl">Last post</span>
              <span className="col-lbl" style={{textAlign:'right'}}>Next bump</span>
            </div>
            {visible.map(job => {
              const due   = (job.seconds_until_bump||0) <= 0
              const cdCol = due ? 'var(--acc)' : 'var(--text)'
              return (
                <div key={job.id} style={{
                  display:'grid', gridTemplateColumns:'1fr 80px 70px 64px',
                  gap:8, alignItems:'center',
                  padding:'5px 0', borderBottom:'1px solid rgba(21,30,46,.5)',
                  opacity: job.enabled ? 1 : .4,
                }}>
                  <a
                    href={`https://hackforums.net/showthread.php?tid=${job.tid}`}
                    target="_blank" rel="noreferrer"
                    onClick={e => e.stopPropagation()}
                    style={{fontSize:11.5,fontWeight:500,color:'var(--acc)',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}
                  >
                    {job.thread_title || `TID ${job.tid}`}
                  </a>
                  <span style={{fontSize:10,color:'var(--sub)',fontFamily:'var(--mono)'}}>every {job.interval_h}h</span>
                  <span style={{fontSize:10,color:'var(--dim)',fontFamily:'var(--mono)'}}>
                    {job.lastpost_ts ? ago(job.lastpost_ts) : '--'}
                  </span>
                  <div style={{textAlign:'right'}}>
                    <div style={{fontSize:12,fontWeight:700,fontFamily:'var(--mono)',color:cdCol}}>
                      {due ? '▶ Now' : fmtCd(job.seconds_until_bump)}
                    </div>
                    <div style={{fontSize:9,color:'var(--dim)',fontFamily:'var(--mono)'}}>
                      {job.bump_count} bump{job.bump_count!==1?'s':''}
                    </div>
                  </div>
                </div>
              )
            })}
            {overflow > 0 && (
              <div style={{paddingTop:7,fontSize:11,color:'var(--sub)'}}>
                + {overflow} more thread{overflow!==1?'s':''} — <span style={{color:'var(--acc)'}}>Full view →</span>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

// ── BYTES OVERVIEW ────────────────────────────────────────────────────────────
function BytesOverview() {
  const nav = useNavigate()
  const [data,    setData]    = useState(null)
  const [toUid,   setToUid]   = useState('')
  const [amount,  setAmount]  = useState('')
  const [reason,  setReason]  = useState('')
  const [sendMsg, setSendMsg] = useState(null)
  const [sendLd,  setSendLd]  = useState(false)

  const refresh = () => api.get('/api/dash/bytes').then(d => { if(d) setData(d) }).catch(() => {})

  useEffect(() => {
    refresh()
  }, [])
  const throttle = useStore(s => s.throttle)
  usePolling(refresh, throttledInterval(120000, throttle))

  const txns = (data?.transactions || []).slice(0, 10)

  const doSend = async (e) => {
    e.stopPropagation()
    if (!toUid || !amount) return
    setSendLd(true); setSendMsg(null)
    try {
      await api.post('/api/dash/bytes/send', { to_uid: toUid.trim(), amount: Number(amount), reason: reason.trim() })
      setSendMsg({ ok: true, text: 'Sent!' })
      setToUid(''); setAmount(''); setReason('')
      setSending(false)
      refresh()
    } catch (err) {
      setSendMsg({ ok: false, text: err.message || 'Failed' })
    } finally {
      setSendLd(false)
      setTimeout(() => setSendMsg(null), 3000)
    }
  }

  return (
    <div className="card" style={{cursor:'pointer',height:420,display:'flex',flexDirection:'column'}} onClick={() => nav('/dashboard/bytes')}>
      <CardHeader
        icon="💰" title="Bytes" to="/dashboard/bytes"
        badge={data ? fmt(data.balance) : null}
        badgeColor="var(--blue)"
        extra={
          data && Number(data.vault||0) > 0
            ? <span style={{fontSize:10,color:'var(--dim)',fontFamily:'var(--mono)'}}>+ {fmt(data.vault)} vault</span>
            : null
        }
      />
      <div style={{display:'flex',gap:5,padding:'6px 13px',borderBottom:'1px solid var(--b1)',minWidth:0}}
           onClick={e => e.stopPropagation()}>
        <input className="inp" placeholder="UID" value={toUid}
          onChange={e => setToUid(e.target.value)}
          style={{flex:'1 1 0',minWidth:0,fontSize:11,padding:'3px 7px'}} />
        <input className="inp" placeholder="Amt" value={amount}
          onChange={e => setAmount(e.target.value)}
          type="number" min="1"
          style={{flex:'1 1 0',minWidth:0,fontSize:11,padding:'3px 7px'}} />
        <input className="inp" placeholder="Reason" value={reason}
          onChange={e => setReason(e.target.value)}
          onKeyDown={e => e.key==='Enter' && doSend(e)}
          style={{flex:'2 1 0',minWidth:0,fontSize:11,padding:'3px 7px'}} />
        <button className="btn btn-acc" style={{fontSize:11,padding:'3px 10px',flexShrink:0,whiteSpace:'nowrap'}}
          onClick={doSend} disabled={sendLd||!toUid||!amount}>
          {sendLd ? <span className="spin" style={{width:9,height:9}}/> : 'Send →'}
        </button>
        {sendMsg && <span style={{fontSize:11,alignSelf:'center',flexShrink:0,color:sendMsg.ok?'var(--acc)':'var(--red)'}}>{sendMsg.text}</span>}
      </div>

      <div className="card-body" style={{flex:1,display:'flex',flexDirection:'column',minHeight:0,padding:"8px 14px"}}>

        {/* Transactions */}
        {txns.length === 0 ? (
          <div style={{fontSize:11,color:'var(--sub)',fontStyle:'italic'}}>No transactions yet</div>
        ) : (
          <>
            <div style={{display:'grid',gridTemplateColumns:'20px 72px 1fr 52px',gap:8,padding:'0 0 5px',borderBottom:'1px solid var(--b1)',marginBottom:2,flexShrink:0}}>
              <span/>
              <span className="col-lbl">Amount</span>
              <span className="col-lbl">Reason</span>
              <span className="col-lbl" style={{textAlign:'right'}}>When</span>
            </div>
            <div style={{display:'flex',flexDirection:'column',flex:1}}>
              {txns.map((t,i) => {
                const col = t.sent ? 'var(--red)' : 'var(--acc)'
                const amt = Number(t.amount)
                return (
                  <div key={t.id||i} style={{flex:1,display:'grid',gridTemplateColumns:'20px 72px 1fr 52px',gap:8,alignItems:'center',borderBottom:'1px solid rgba(21,30,46,.4)'}}>
                    <span style={{fontSize:11,color:col,textAlign:'center'}}>{t.sent?'↑':'↓'}</span>
                    <span style={{fontFamily:'var(--mono)',fontSize:11,fontWeight:700,color:col}}>
                      {t.sent?'-':'+'}{Math.abs(amt).toLocaleString()}
                    </span>
                    <span style={{fontSize:11,color:'var(--muted)',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{t.reason||'--'}</span>
                    <span style={{fontSize:10,color:'var(--dim)',textAlign:'right',fontFamily:'var(--mono)'}}>{ago(t.dateline)}</span>
                  </div>
                )
              })}
            </div>
          </>
        )}

      </div>
    </div>
  )
}

// ── CONTRACTS OVERVIEW ────────────────────────────────────────────────────────
function ContractsOverview() {
  const nav = useNavigate()
  const [data, setData] = useState(null)

  useEffect(() => {
    api.get('/api/dash/contracts').then(d => { if(d) setData(d) }).catch(() => {})
  }, [])
  const throttle = useStore(s => s.throttle)
  usePolling(() => api.get('/api/dash/contracts').then(d => { if(d) setData(d) }).catch(() => {}), throttledInterval(300000, throttle))

  const contracts = (data?.contracts || []).slice(0, 10)
  const active    = (data?.contracts||[]).filter(c => c.status_n === '5').length
  const awaiting  = (data?.contracts||[]).filter(c => c.status_n === '1').length
  const disputed  = (data?.contracts||[]).filter(c => c.status_n === '7').length
  const total     = data?.total_count ?? (data?.contracts||[]).length

  return (
    <div className="card" style={{cursor:'pointer',height:420,display:'flex',flexDirection:'column'}} onClick={() => nav('/dashboard/contracts')}>
      <CardHeader
        icon="📜" title="Contracts" to="/dashboard/contracts"
        badge={
          disputed > 0 ? `${disputed} DISPUTED`
          : active > 0  ? `${active} ACTIVE`
          : awaiting > 0 ? `${awaiting} AWAITING`
          : null
        }
        badgeColor={disputed > 0 ? 'var(--red)' : awaiting > 0 ? 'var(--yellow)' : 'var(--acc)'}
      />
      <div className="card-body" style={{flex:1,display:'flex',flexDirection:'column',minHeight:0}}>

        {/* Quick counts */}
        {data && (
          <div style={{display:'flex',gap:14,marginBottom:10,paddingBottom:8,borderBottom:'1px solid var(--b1)',flexWrap:'wrap',flexShrink:0}}>
            {[
              { l:'Total',    v: total,    c: 'var(--text)' },
              { l:'Active',   v: active,   c: active   > 0 ? 'var(--acc)'    : 'var(--dim)' },
              { l:'Awaiting', v: awaiting, c: awaiting > 0 ? 'var(--yellow)' : 'var(--dim)' },
              { l:'Disputed', v: disputed, c: disputed > 0 ? 'var(--red)'    : 'var(--dim)' },
            ].map(s => (
              <div key={s.l}>
                <div style={{fontFamily:'var(--mono)',fontSize:14,fontWeight:700,color:s.c,lineHeight:1.1}}>{s.v}</div>
                <div style={{fontSize:9,color:'var(--sub)',textTransform:'uppercase',letterSpacing:'.06em',marginTop:2}}>{s.l}</div>
              </div>
            ))}
          </div>
        )}

        {/* Column labels */}
        {contracts.length > 0 && (
          <div style={{display:'grid',gridTemplateColumns:'6px 56px 80px 1fr 52px',gap:8,padding:'0 0 5px',borderBottom:'1px solid var(--b1)',marginBottom:2,flexShrink:0}}>
            <span/>
            <span className="col-lbl">CID</span>
            <span className="col-lbl">Status</span>
            <span className="col-lbl">Value</span>
            <span className="col-lbl" style={{textAlign:'right'}}>When</span>
          </div>
        )}

        {!data
          ? <div style={{display:'flex',flexDirection:'column',gap:4}}>{[1,2,3,4,5].map(i=><div key={i} style={{height:18,background:'var(--s3)',borderRadius:2,opacity:.4}}/>)}</div>
          : contracts.length === 0
            ? <div style={{fontSize:11,color:'var(--sub)',fontStyle:'italic'}}>No contracts</div>
            : <div style={{display:'flex',flexDirection:'column',flex:1}}>
                {contracts.map(c => {
                  const val = c.value || (c.type === 'Vouch Copy' ? 'Vouch Copy' : c.type || '--')
                  const dot = STATUS_COLORS[c.status] || 'var(--dim)'
                  return (
                    <div key={c.cid} style={{flex:1,display:'grid',gridTemplateColumns:'6px 56px 80px 1fr 52px',gap:8,alignItems:'center',borderBottom:'1px solid rgba(21,30,46,.4)'}}>
                      <span style={{width:6,height:6,borderRadius:'50%',flexShrink:0,display:'inline-block',background:dot}}/>
                      <a
                        href={`https://hackforums.net/contracts.php?action=view&cid=${c.cid}`}
                        target="_blank" rel="noreferrer"
                        onClick={e => e.stopPropagation()}
                        style={{fontSize:11,color:'var(--acc)',fontFamily:'var(--mono)'}}
                      >#{c.cid}</a>
                      <span style={{fontSize:10,fontFamily:'var(--mono)',fontWeight:600,color:dot}}>{c.status}</span>
                      <span style={{fontSize:11,color:'var(--muted)',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{val}</span>
                      <span style={{fontSize:10,color:'var(--dim)',textAlign:'right',fontFamily:'var(--mono)'}}>{ago(c.dateline)}</span>
                    </div>
                  )
                })}
              </div>
        }
      </div>
    </div>
  )
}

// ── USER LOOKUP ───────────────────────────────────────────────────────────────
function UserLookup() {
  const nav      = useNavigate()
  const [uid,    setUid]  = useState('')
  const [loading,setLd]   = useState(false)
  const [err,    setErr]  = useState(null)

  const lookup = async () => {
    const id = uid.trim()
    if (!id) return
    setLd(true); setErr(null)
    try {
      // Quick validate the UID exists before navigating
      await api.get(`/api/dash/user/${id}`)
      nav(`/dashboard/user/${id}`)
    } catch {
      setErr('Not found')
      setLd(false)
    }
  }

  return (
    <div className="card">
      <div className="card-head">
        <span className="card-icon">🔍</span>
        <span className="card-title">User Lookup</span>
      </div>
      <div className="card-body">
        <div style={{display:'flex',gap:5}}>
          <input
            className="inp" placeholder="UID…" value={uid}
            onChange={e => setUid(e.target.value)}
            onKeyDown={e => e.key==='Enter' && lookup()}
            style={{flex:1}}
          />
          <button className="btn btn-acc" onClick={lookup} disabled={loading||!uid}>
            {loading ? <span className="spin"/> : 'Go'}
          </button>
          {err && <span style={{fontSize:11,color:'var(--red)',alignSelf:'center'}}>{err}</span>}
        </div>
        <div style={{fontSize:11,color:'var(--dim)',marginTop:6}}>
          Enter a UID to view their full profile, recent posts, and threads.
        </div>
      </div>
    </div>
  )
}

// ── SIGMARKET OVERVIEW ────────────────────────────────────────────────────────
function SigmarketOverview() {
  const nav       = useNavigate()
  const isEnabled = useStore(s => s.isEnabled)
  const apiPaused = useStore(s => s.apiPaused)
  const [data, setData] = useState(null)

  const load = useCallback(() => {
    api.get('/api/sigmarket/status').then(d => { if(d) setData(d) }).catch(() => {})
  }, [])

  useEffect(() => { load() }, [load])
  const throttle = useStore(s => s.throttle)
  usePolling(load, apiPaused ? null : throttledInterval(300000, throttle))

  if (!isEnabled('sigmarket')) return null

  const listing      = data?.listing
  const isListed     = listing && parseInt(listing.active || 0)
  const orders       = data?.seller_orders || []
  const activeOrders = orders.filter(o => o.active)

  return (
    <div className="card" style={{cursor:'pointer'}} onClick={() => nav('/dashboard/sigmarket')}>
      <CardHeader
        icon="✍" title="Sig Market" to="/dashboard/sigmarket"
        badge={activeOrders.length > 0 ? `${activeOrders.length} ORDER${activeOrders.length!==1?'S':''}` : null}
        badgeColor="var(--acc)"
      />
      <div className="card-body">
        {!data ? (
          <div style={{fontSize:11,color:'var(--sub)',fontStyle:'italic'}}>Loading…</div>
        ) : (
          <>
            {/* Listing status */}
            <div style={{marginBottom: activeOrders.length ? 10 : 0}}>
              {isListed ? (
                <div style={{display:'flex',gap:12,alignItems:'center'}}>
                  <span style={{fontSize:11,color:'var(--acc)',fontFamily:'var(--mono)',fontWeight:700}}>
                    LISTED
                  </span>
                  <span style={{fontSize:11,color:'var(--sub)',fontFamily:'var(--mono)'}}>
                    {listing.price}b / {listing.duration}d
                  </span>
                  {listing.ppd && (
                    <span style={{fontSize:10,color:'var(--dim)',fontFamily:'var(--mono)'}}>
                      ({listing.ppd}b/day)
                    </span>
                  )}
                </div>
              ) : (
                <div style={{fontSize:11,color:'var(--dim)',fontStyle:'italic'}}>No active listing</div>
              )}
            </div>

            {/* Active orders */}
            {activeOrders.length > 0 && (
              <div>
                <div style={{display:'grid',gridTemplateColumns:'1fr auto auto',gap:8,padding:'0 0 4px',borderBottom:'1px solid var(--b1)',marginBottom:4}}>
                  <span className="col-lbl">Buyer</span>
                  <span className="col-lbl">Expires</span>
                  <span className="col-lbl" style={{textAlign:'right'}}>Price</span>
                </div>
                {activeOrders.slice(0, 4).map((o, i) => {
                  const daysLeft = Math.max(0, Math.floor(o.expires_in / 86400))
                  return (
                    <div key={o.smid||i} style={{
                      display:'grid', gridTemplateColumns:'1fr auto auto', gap:8,
                      alignItems:'center', padding:'4px 0',
                      borderBottom:'1px solid rgba(21,30,46,.4)',
                    }}>
                      <span style={{fontSize:11,color:'var(--text)',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>
                        {o.buyer?.username || `UID ${o.buyer?.uid}` || '--'}
                      </span>
                      <span style={{fontSize:10,fontFamily:'var(--mono)',color: daysLeft<=3?'var(--yellow)':'var(--dim)'}}>
                        {daysLeft}d
                      </span>
                      <span style={{fontSize:10,fontFamily:'var(--mono)',color:'var(--sub)',textAlign:'right'}}>
                        {o.price}b
                      </span>
                    </div>
                  )
                })}
                {activeOrders.length > 4 && (
                  <div style={{fontSize:10,color:'var(--dim)',fontStyle:'italic',paddingTop:4}}>
                    +{activeOrders.length - 4} more
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}


function DashGrid({ children }) {
  // Filter out false/null/undefined children — only count what actually renders
  const real = Array.isArray(children) ? children.filter(Boolean) : [children].filter(Boolean)
  if (!real.length) return null
  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: real.length === 1 ? '1fr' : 'minmax(0,1fr) minmax(0,1fr)',
      gap: 12,
      alignItems: 'start',
    }}>
      {real}
    </div>
  )
}

export default function Dashboard() {
  const isEnabled = useStore(s => s.isEnabled)

  const showBumper    = isEnabled('autobump')
  const showBytes     = isEnabled('bytes')
  const showContracts = isEnabled('contracts')
  const showSigmarket = isEnabled('sigmarket')

  return (
    <>
      {showBumper && <BumperOverview />}
      <DashGrid>
        {showBytes     && <BytesOverview />}
        {showContracts && <ContractsOverview />}
      </DashGrid>
      <DashGrid>
        {showSigmarket && <SigmarketOverview />}
        <UserLookup />
      </DashGrid>
    </>
  )
}
