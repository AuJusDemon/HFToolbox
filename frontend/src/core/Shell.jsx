import { useState, useEffect, useRef } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import useStore from '../store.js'
import { api } from './api.js'

const GROUPS = {
  "2":"Registered","9":"L33t","28":"Ub3r","46":"H4CK3R$",
  "48":"Quantum","52":"PinkLSZ","50":"Legends","77":"Academy","71":"Warriors",
  "78":"VIBE","70":"Gamblers","68":"Brotherhood",
  "67":"Vendor","7":"Exiled","38":"Banned",
}
const GROUP_PRIORITY = ["9","28","46","48","52","50","77","71","67","78","70","68","7","38","2"]

function groupClass(gid) {
  if (["9","28","46","48","52","50","77","71"].includes(gid)) return "sp sp-rank"
  if (gid === "67") return "sp sp-vendor"
  if (["7","38"].includes(gid)) return "sp sp-dim"
  return "sp sp-comm"
}
function sortGroups(ids) {
  return [...ids].sort((a,b) => {
    const ai=GROUP_PRIORITY.indexOf(a), bi=GROUP_PRIORITY.indexOf(b)
    if(ai===-1&&bi===-1)return 0; if(ai===-1)return 1; if(bi===-1)return-1; return ai-bi
  })
}

function RateLimit() {
  const [val, setVal] = useState(null)
  const settings     = useStore(s => s.settings)
  const setApiPaused = useStore(s => s.setApiPaused)
  const prevPaused   = useRef(false)

  useEffect(() => {
    const go = () => api.get('/api/rate-limit').then(d => {
      const r = d?.remaining ?? null
      setVal(r)
      if (settings.apiFloorEnabled && r !== null && r < 9999) {
        const shouldPause = r < (settings.apiFloor ?? 30)
        if (shouldPause !== prevPaused.current) {
          prevPaused.current = shouldPause
          setApiPaused(shouldPause)
        }
      }
    }).catch(() => {})
    go()
    const id = setInterval(go, 10000)
    return () => clearInterval(id)
  }, [settings.apiFloor, settings.apiFloorEnabled])

  const known  = val !== null && val < 9999
  const floor  = settings.apiFloorEnabled ? (settings.apiFloor ?? 30) : 0
  const paused = known && settings.apiFloorEnabled && val < floor
  const pct    = known ? Math.min(val/240, 1) : 1
  const fc     = !known ? '' : paused ? 'crit' : pct > 0.5 ? '' : pct > 0.2 ? 'warn' : 'crit'
  const numCol = fc === 'crit' ? 'var(--red)' : fc === 'warn' ? 'var(--yellow)' : 'var(--acc)'
  return (
    <>
      <div className="rl-row">
        <span className="rl-lbl">API calls{paused ? ' — paused' : ''}</span>
        <span className="rl-n" style={{color:numCol}}>{known ? `${val}/240` : '—'}</span>
      </div>
      <div className="rl-track">
        <div className={`rl-fill ${fc}`} style={{width:`${pct*100}%`}}/>
      </div>
    </>
  )
}

function NavLink({ to, icon, label, badge, badgeRed, onClick }) {
  const loc = useLocation()
  const nav = useNavigate()
  const on  = loc.pathname === to || (to !== '/dashboard' && loc.pathname.startsWith(to))
  return (
    <button className={`sb-link${on?' on':''}`} onClick={() => { nav(to); onClick?.() }}>
      <span className="sb-link-icon">{icon}</span>
      {label}
      {badge != null && badge > 0 && (
        <span className={`sb-link-badge${badgeRed?' red':''}`}>{badge}</span>
      )}
    </button>
  )
}

function ApiPausedBanner() {
  const apiPaused  = useStore(s => s.apiPaused)
  const settings   = useStore(s => s.settings)
  const nav        = useNavigate()
  if (!apiPaused) return null
  return (
    <div style={{
      background:'rgba(232,84,84,.1)', borderBottom:'1px solid rgba(232,84,84,.25)',
      padding:'9px 20px', display:'flex', alignItems:'center', gap:10,
      fontSize:12, color:'var(--red)',
    }}>
      <span style={{fontSize:14}}>⚠</span>
      <span style={{flex:1}}>
        API calls running low — live polling paused to protect your budget (floor: {settings.apiFloor} remaining).
        Data shown may be slightly stale.
      </span>
      <button
        onClick={() => nav('/dashboard/settings')}
        style={{fontSize:11,color:'var(--red)',opacity:.7,background:'none',border:'none',cursor:'pointer',textDecoration:'underline',padding:0}}
      >
        adjust floor
      </button>
    </div>
  )
}

export default function Shell() {
  const user   = useStore(s => s.user)
  const logout = useStore(s => s.logout)
  const nav    = useNavigate()
  const loc    = useLocation()
  const [profile,       setProfile]       = useState(null)
  const [replyCount,    setReplyCount]    = useState(0)
  const [notifs,        setNotifs]        = useState([])
  const [unseenCount,   setUnseenCount]   = useState(0)
  const [notifOpen,     setNotifOpen]     = useState(false)
  const notifRef = useRef(null)

  useEffect(() => {
    const load = () => api.get('/api/profile').then(d => setProfile(d)).catch(() => {})
    load()
    const id = setInterval(load, 60000)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    const poll = () => api.get('/api/posting/replies/count')
      .then(d => setReplyCount(d.count || 0))
      .catch(() => {})
    poll()
    const id = setInterval(poll, 60000)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    const poll = () => api.get('/api/notifications')
      .then(d => { if(d) { setNotifs(d.notifications || []); setUnseenCount(d.unseen || 0) }})
      .catch(() => {})
    poll()
    const id = setInterval(poll, 60000)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    const handler = e => { if (notifRef.current && !notifRef.current.contains(e.target)) setNotifOpen(false) }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const openNotifs = () => {
    setNotifOpen(o => !o)
    if (!notifOpen && unseenCount > 0) {
      api.post('/api/notifications/seen').then(() => setUnseenCount(0)).catch(() => {})
    }
  }

  const rawGroups  = profile?.groups || user?.groups || []
  const sortedGids = sortGroups(rawGroups.filter(g => GROUPS[g]))
  const rawAvatar  = user?.avatar || ''
  const avatar     = rawAvatar ? (rawAvatar.startsWith('http') ? rawAvatar : 'https://hackforums.net/' + rawAvatar.replace(/^\.\//, '')) : ''
  const initials   = (user?.username || 'HF').slice(0, 2).toUpperCase()

  const stats = profile ? [
    { l:'Posts',   v: Number(profile.postnum    ||0).toLocaleString() },
    { l:'Threads', v: Number(profile.threadnum  ||0).toLocaleString() },
    { l:'Bytes',   v: Number(profile.myps       ||0).toLocaleString() },
    { l:'Rep',     v: Number(profile.reputation ||0).toLocaleString() },
  ] : []

  const cachedStr = profile?.profile_ts
    ? new Date(profile.profile_ts*1000).toLocaleString(undefined,
        {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'})
    : null

  const titleMap = {
    '/dashboard':          'Dashboard',
    '/dashboard/bytes':    'Bytes',
    '/dashboard/contracts':'Contracts',
    '/dashboard/bumper':   'Auto Bumper',
    '/dashboard/settings':   'Settings',
    '/dashboard/groups':     'Group Features',
  }
  const title = titleMap[loc.pathname] || (loc.pathname.startsWith('/dashboard/user/') ? 'User Profile' : 'Dashboard')

  return (
    <div className="shell-wrap">
      <div className="shell">

        {/* ── SIDEBAR ── */}
        <div className="sidebar">
          <div className="sb-inner">

            <button className="sb-logo" onClick={() => nav('/dashboard')}>
              HF<span>.</span>Toolbox
            </button>

            {/* Profile card */}
            <div className="sb-profile">
              {/* Avatar + name row */}
              <div style={{display:'flex',alignItems:'center',gap:9,marginBottom:8}}>
                <div className="sb-av">
                  {avatar
                    ? <img src={avatar} alt="" onError={e => e.currentTarget.style.display='none'}/>
                    : initials}
                </div>
                <div style={{minWidth:0}}>
                  <div className="sb-name" style={{marginBottom:0}}>{user?.username}</div>
                  <div className="sb-pills" style={{marginBottom:0,marginTop:4}}>
                    {sortedGids.map(g => (
                      <span key={g} className={groupClass(g)}>{GROUPS[g]}</span>
                    ))}
                  </div>
                </div>
              </div>

              {stats.length > 0
                ? <div className="sb-stats">
                    {stats.map(s => (
                      <div key={s.l} className="sb-stat">
                        <div className="sb-stat-v">{s.v}</div>
                        <div className="sb-stat-l">{s.l}</div>
                      </div>
                    ))}
                  </div>
                : <div className="sb-stats">
                    {[0,1,2,3].map(i => (
                      <div key={i} className="sb-stat" style={{height:32,background:'var(--s3)',opacity:.4}}/>
                    ))}
                  </div>
              }
              {cachedStr && (
                <div style={{fontSize:9,color:'var(--dim)',fontFamily:'var(--mono)',marginTop:6}}>
                  cached {cachedStr}
                </div>
              )}
            </div>

            {/* Nav */}
            <div className="sb-nav-lbl">Navigation</div>
            <NavLink to="/dashboard"          icon="⬡" label="Overview" />

            <div className="sb-nav-lbl" style={{marginTop:6}}>Modules</div>
            <NavLink to="/dashboard/bytes"     icon="💰" label="Bytes" />
            <NavLink to="/dashboard/contracts" icon="📜" label="Contracts" />
            <NavLink to="/dashboard/bumper"    icon="⬆" label="Auto Bumper" />
            <NavLink to="/dashboard/posting"   icon="💬" label="Posting" badge={replyCount} />
            <NavLink to="/dashboard/sigmarket"  icon="✍" label="Sig Market" />
            <NavLink to="/dashboard/settings"  icon="⚙" label="Settings" />

          </div>

          <div className="sb-bottom">
            <RateLimit />
            <button className="sb-logout" onClick={logout}>Logout</button>
          </div>
        </div>

        {/* ── MAIN ── */}
        <div className="main">
          <ApiPausedBanner />
          <div className="topbar">
            <span className="tb-title">{title}</span>
            <div className="tb-r" style={{ display:'flex', alignItems:'center', gap:8 }}>
              {/* Notification bell in topbar */}
              <div ref={notifRef} style={{ position:'relative' }}>
                <button
                  onClick={openNotifs}
                  style={{
                    position:'relative', background:'none', border:'none',
                    cursor:'pointer', padding:'2px 4px', lineHeight:1,
                    fontSize:15, color: unseenCount > 0 ? 'var(--yellow)' : 'var(--dim)',
                    transition:'color 130ms',
                  }}
                  title="Notifications"
                >
                  🔔
                  {unseenCount > 0 && (
                    <span style={{
                      position:'absolute', top:-3, right:-3,
                      background:'var(--red)', color:'#fff',
                      fontSize:8, fontWeight:700, borderRadius:8,
                      padding:'1px 4px', fontFamily:'var(--mono)', lineHeight:1.4,
                      minWidth:14, textAlign:'center',
                    }}>{unseenCount}</span>
                  )}
                </button>
                {notifOpen && (
                  <div style={{
                    position:'absolute', top:'calc(100% + 8px)', right:0,
                    width:'min(300px, calc(100vw - 16px))', background:'var(--s2)', border:'1px solid var(--b2)',
                    borderRadius:6, maxHeight:'70vh', overflowY:'auto', zIndex:500,
                    boxShadow:'0 4px 20px rgba(0,0,0,.5)',
                  }}>
                    <div style={{ padding:'8px 12px', borderBottom:'1px solid var(--b1)', fontSize:11, fontWeight:600, color:'var(--sub)', display:'flex', justifyContent:'space-between', alignItems:'center' }}>
                      <span>Notifications</span>
                      {unseenCount > 0 && (
                        <button onClick={() => { api.post('/api/notifications/seen'); setUnseenCount(0); setNotifs(n => n.map(x => ({...x,seen:1}))) }}
                          style={{ background:'none', border:'none', color:'var(--dim)', fontSize:10, cursor:'pointer' }}>
                          Mark all read
                        </button>
                      )}
                    </div>
                    {notifs.length === 0
                      ? <div style={{ padding:'14px 12px', fontSize:12, color:'var(--dim)', fontStyle:'italic' }}>No notifications</div>
                      : notifs.map(n => {
                          const ICONS = { pm:'✉', contract_new:'📜', contract_status:'🔄', reply:'💬' }
                          const icon = ICONS[n.type] || '•'
                          const ts = n.created_at ? Math.floor(Date.now()/1000) - n.created_at : 0
                          const timeStr = ts < 60 ? 'just now' : ts < 3600 ? `${Math.floor(ts/60)}m ago` : ts < 86400 ? `${Math.floor(ts/3600)}h ago` : `${Math.floor(ts/86400)}d ago`
                          return (
                            <div key={n.id}
                              onClick={() => { setNotifOpen(false); if(n.link) { if(n.link.startsWith('http')) window.open(n.link,'_blank'); else nav(n.link) }}}
                              style={{
                                padding:'9px 12px', cursor: n.link ? 'pointer' : 'default',
                                borderBottom:'1px solid var(--b1)',
                                background: n.seen ? 'transparent' : 'rgba(77,142,240,.05)',
                                transition:'background 130ms',
                              }}
                              onMouseOver={e => { if(n.link) e.currentTarget.style.background='var(--hover)' }}
                              onMouseOut={e => e.currentTarget.style.background = n.seen ? 'transparent' : 'rgba(77,142,240,.05)'}
                            >
                              <div style={{ display:'flex', gap:8, alignItems:'flex-start' }}>
                                <span style={{ fontSize:13, flexShrink:0 }}>{icon}</span>
                                <div style={{ flex:1, minWidth:0 }}>
                                  <div style={{ fontSize:12, color: n.seen ? 'var(--sub)' : 'var(--text)', fontWeight: n.seen ? 400 : 500, lineHeight:1.4, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{n.title}</div>
                                  {n.body && <div style={{ fontSize:10.5, color:'var(--dim)', marginTop:2 }}>{n.body}</div>}
                                </div>
                                <span style={{ fontSize:9, color:'var(--dim)', fontFamily:'var(--mono)', flexShrink:0, marginTop:2 }}>{timeStr}</span>
                              </div>
                            </div>
                          )
                        })
                    }
                  </div>
                )}
              </div>
              <div className="live-dot"/>
              <span className="tb-tag tb-live">LIVE</span>
            </div>
          </div>
          <div className="page-header">
            <div className="page-header-title">{title}</div>
          </div>
          <div className="content up">
            <Outlet />
          </div>
        </div>

      </div>

      <MobileNav />
    </div>
  )
}

function MobileNav() {
  const nav  = useNavigate()
  const loc  = useLocation()
  const user = useStore(s => s.user)
  // Core 5 items — always visible. Posting badge comes from parent shell poll.
  const items = [
    { to:'/dashboard',           icon:'⬡', label:'Home'     },
    { to:'/dashboard/bytes',     icon:'💰', label:'Bytes'    },
    { to:'/dashboard/contracts', icon:'📜', label:'Contracts'},
    { to:'/dashboard/bumper',    icon:'⬆', label:'Bumper'   },
    { to:'/dashboard/posting',   icon:'💬', label:'Post'     },
  ]
  return (
    <nav className="mob-nav">
      {items.map(({to,icon,label}) => {
        const on = loc.pathname===to||(to!=='/dashboard'&&loc.pathname.startsWith(to))
        return (
          <button key={to} className={`mob-nav-btn${on?' on':''}`} onClick={()=>nav(to)}>
            <span className="mob-nav-btn-icon">{icon}</span>
            {label}
          </button>
        )
      })}
    </nav>
  )
}
