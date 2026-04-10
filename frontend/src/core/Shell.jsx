import { useState, useEffect, useRef } from 'react'
import { Outlet, useNavigate, useLocation } from 'react-router-dom'
import useStore from '../store.js'
import { api } from './api.js'
import extraNavLinks from '../navlinks.jsx'

// ── Theme system ────────────────────────────────────────────────────────────
export const THEMES = [
  { id: 'terminal', label: 'Terminal', swatch: '#39ff14', bg: '#080808', desc: 'Phosphor green CRT' },
  { id: 'classic',  label: 'Classic',  swatch: '#00d4b4', bg: '#050709', desc: 'Original dashboard' },
]

function applyTheme(id) {
  document.documentElement.dataset.theme = id === 'terminal' ? '' : id
  localStorage.setItem('hftb_theme', id)
}

export function useTheme() {
  const [theme, setThemeState] = useState(() => localStorage.getItem('hftb_theme') || 'terminal')
  const setTheme = (id) => { setThemeState(id); applyTheme(id) }
  useEffect(() => { applyTheme(theme) }, [])
  return [theme, setTheme]
}

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

/* Block-character ASCII progress bar */
function AsciiBar({ pct, width = 16, colorClass = '' }) {
  const filled = Math.round(pct * width)
  const empty  = width - filled
  return (
    <span>
      <span className={`rl-fill ${colorClass}`}>{'█'.repeat(filled)}</span>
      <span style={{ color:'var(--b3)' }}>{'░'.repeat(empty)}</span>
    </span>
  )
}

function RateLimit() {
  const [val, setVal]     = useState(null)
  const settings          = useStore(s => s.settings)
  const setApiPaused      = useStore(s => s.setApiPaused)
  const setThrottle       = useStore(s => s.setThrottle)
  const prevPaused        = useRef(false)

  useEffect(() => {
    const go = () => api.get('/api/rate-limit').then(d => {
      const r = d?.remaining ?? null
      setVal(r)
      if (d?.throttle) setThrottle(d.throttle)
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
  const pct    = known ? Math.min(val / 240, 1) : 1
  const fc     = !known ? '' : paused ? 'crit' : pct > 0.5 ? '' : pct > 0.2 ? 'warn' : 'crit'
  const numCol = fc === 'crit' ? 'var(--red)' : fc === 'warn' ? 'var(--yellow)' : 'var(--acc)'

  return (
    <>
      <div className="rl-row">
        <span className="rl-lbl">API{paused ? ' [PAUSED]' : ''}</span>
        <span className="rl-n" style={{ color: numCol }}>
          {known ? `${val}/240` : '---'}
        </span>
      </div>
      <div className="rl-track">
        {known
          ? <AsciiBar pct={pct} width={16} colorClass={fc} />
          : <span style={{ color:'var(--dim)' }}>{'░'.repeat(16)}</span>
        }
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
      {label}
      {badge != null && badge > 0 && (
        <span className={`sb-link-badge${badgeRed?' red':''}`}>{badge}</span>
      )}
    </button>
  )
}

function ApiPausedBanner() {
  const apiPaused = useStore(s => s.apiPaused)
  const settings  = useStore(s => s.settings)
  const nav       = useNavigate()
  if (!apiPaused) return null
  return (
    <div style={{
      background:'rgba(255,51,51,.06)',borderBottom:'1px solid rgba(255,51,51,.2)',
      padding:'7px 16px',display:'flex',alignItems:'center',gap:10,
      fontSize:11,color:'var(--red)',fontFamily:'var(--mono)',
    }}>
      <span>! API calls low — polling paused (floor: {settings.apiFloor})</span>
      <button
        onClick={() => nav('/dashboard/settings')}
        style={{fontSize:10,color:'var(--red)',opacity:.6,background:'none',border:'none',cursor:'pointer',textDecoration:'underline',padding:0,fontFamily:'var(--mono)',marginLeft:'auto'}}
      >
        [adjust]
      </button>
    </div>
  )
}

/* Notification dropdown */
function NotifPanel({ notifs, unseenCount, setNotifOpen, setUnseenCount, setNotifs }) {
  const nav = useNavigate()
  return (
    <div style={{
      position:'absolute',top:'calc(100% + 8px)',right:0,
      width:'min(320px, calc(100vw - 16px))',
      background:'var(--s2)',border:'1px solid var(--b3)',
      maxHeight:'70vh',overflowY:'auto',zIndex:500,
      boxShadow:'0 4px 24px rgba(0,0,0,.7)',
    }}>
      {/* header */}
      <div style={{padding:'7px 12px',borderBottom:'1px solid var(--b2)',fontSize:10,color:'var(--dim)',display:'flex',justifyContent:'space-between',alignItems:'center',fontFamily:'var(--mono)',textTransform:'uppercase',letterSpacing:'.08em'}}>
        <span>// notifications</span>
        {unseenCount > 0 && (
          <button onClick={() => { api.post('/api/notifications/seen'); setUnseenCount(0); setNotifs(n => n.map(x=>({...x,seen:1}))) }}
            style={{background:'none',border:'none',color:'var(--dim)',fontSize:10,cursor:'pointer',fontFamily:'var(--mono)'}}>
            [mark read]
          </button>
        )}
      </div>
      {notifs.length === 0
        ? <div style={{padding:'14px 12px',fontSize:11,color:'var(--dim)',fontFamily:'var(--mono)'}}>
            {'> no entries'}
          </div>
        : [...notifs].reverse().map(n => {
            const ICONS = { pm:'PM', contract_new:'CTR', contract_status:'UPD', reply:'RPL' }
            const tag   = ICONS[n.type] || '---'
            const ts    = n.created_at ? Math.floor(Date.now()/1000) - n.created_at : 0
            const timeStr = ts < 60 ? 'now' : ts < 3600 ? `${Math.floor(ts/60)}m` : ts < 86400 ? `${Math.floor(ts/3600)}h` : `${Math.floor(ts/86400)}d`
            return (
              <div key={n.id}
                onClick={() => { setNotifOpen(false); if(n.link) { if(n.link.startsWith('http')) window.open(n.link,'_blank'); else nav(n.link) }}}
                style={{
                  padding:'8px 12px',cursor:n.link?'pointer':'default',
                  borderBottom:'1px solid var(--b1)',
                  background:n.seen?'transparent':'rgba(57,255,20,.03)',
                  borderLeft:n.seen?'2px solid transparent':'2px solid rgba(57,255,20,.3)',
                  transition:'background 120ms',fontFamily:'var(--mono)',
                }}
                onMouseOver={e => {if(n.link) e.currentTarget.style.background='rgba(57,255,20,.04)'}}
                onMouseOut={e => e.currentTarget.style.background = n.seen?'transparent':'rgba(57,255,20,.03)'}
              >
                <div style={{display:'flex',gap:8,alignItems:'flex-start'}}>
                  <span style={{fontSize:9,color:'var(--dim)',border:'1px solid var(--b3)',padding:'1px 3px',flexShrink:0,marginTop:1}}>{tag}</span>
                  <div style={{flex:1,minWidth:0}}>
                    <div style={{fontSize:11,color:n.seen?'var(--sub)':'var(--text)',lineHeight:1.4,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{n.title}</div>
                    {n.body && <div style={{fontSize:10,color:'var(--dim)',marginTop:2}}>{n.body}</div>}
                  </div>
                  <span style={{fontSize:9,color:'var(--dim)',flexShrink:0,marginTop:2}}>{timeStr}</span>
                </div>
              </div>
            )
          })
      }
    </div>
  )
}

const TITLE_MAP = {
  '/dashboard':           'Overview',
  '/dashboard/bytes':     'Bytes',
  '/dashboard/contracts': 'Contracts',
  '/dashboard/bumper':    'Auto Bumper',
  '/dashboard/posting':   'Posting',
  '/dashboard/sigmarket':  'Sig Market',
  '/dashboard/groups':    'Group Features',
  '/dashboard/settings':  'Settings',
}

function ThemePicker({ theme, setTheme }) {
  return (
    <div style={{ marginBottom: 8 }}>
      <div style={{ fontSize: 9, color: 'var(--dim)', textTransform: 'uppercase', letterSpacing: '.1em', fontFamily: 'var(--mono)', marginBottom: 6 }}>
        Theme
      </div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
        {THEMES.map(t => (
          <button
            key={t.id}
            onClick={() => setTheme(t.id)}
            style={{
              display: 'flex', alignItems: 'center', gap: 8,
              padding: '4px 6px',
              background: theme === t.id ? 'var(--acc2)' : 'transparent',
              border: '1px solid',
              borderColor: theme === t.id ? 'var(--acc3)' : 'transparent',
              borderLeft: theme === t.id ? '2px solid var(--acc)' : '2px solid transparent',
              cursor: 'pointer',
              transition: 'all 120ms ease',
              textAlign: 'left',
              width: '100%',
            }}
          >
            <span style={{
              width: 10, height: 10, flexShrink: 0,
              background: t.swatch,
              boxShadow: theme === t.id ? `0 0 6px ${t.swatch}88` : 'none',
              transition: 'box-shadow 120ms',
            }}/>
            <span style={{ fontSize: 11, fontFamily: 'var(--mono)', color: theme === t.id ? 'var(--acc)' : 'var(--sub)', flex: 1 }}>
              {t.label}
            </span>
            {theme === t.id && (
              <span style={{ fontSize: 9, color: 'var(--acc)', fontFamily: 'var(--mono)' }}>ON</span>
            )}
          </button>
        ))}
      </div>
    </div>
  )
}


export default function Shell() {
  const user   = useStore(s => s.user)
  const logout = useStore(s => s.logout)
  const nav    = useNavigate()
  const loc    = useLocation()
  const [theme, setTheme] = useTheme()

  const [profile,     setProfile]     = useState(null)
  const [replyCount,  setReplyCount]  = useState(0)
  const [notifs,      setNotifs]      = useState([])
  const [unseenCount, setUnseenCount] = useState(0)
  const [notifOpen,   setNotifOpen]   = useState(false)
  const notifRef = useRef(null)

  useEffect(() => {
    const load = () => api.get('/api/profile').then(d => setProfile(d)).catch(()=>{})
    load(); const id = setInterval(load, 60000); return () => clearInterval(id)
  }, [])

  useEffect(() => {
    const poll = () => api.get('/api/posting/replies/count').then(d => setReplyCount(d.count||0)).catch(()=>{})
    poll(); const id = setInterval(poll, 60000); return () => clearInterval(id)
  }, [])

  useEffect(() => {
    const poll = () => api.get('/api/notifications').then(d => { if(d){setNotifs(d.notifications||[]); setUnseenCount(d.unseen||0)} }).catch(()=>{})
    poll(); const id = setInterval(poll, 60000); return () => clearInterval(id)
  }, [])

  useEffect(() => {
    const h = e => { if(notifRef.current && !notifRef.current.contains(e.target)) setNotifOpen(false) }
    document.addEventListener('mousedown', h); return () => document.removeEventListener('mousedown', h)
  }, [])

  const openNotifs = () => {
    setNotifOpen(o => !o)
    if (!notifOpen && unseenCount > 0) api.post('/api/notifications/seen').then(() => setUnseenCount(0)).catch(()=>{})
  }

  const rawGroups  = profile?.groups || user?.groups || []
  const sortedGids = sortGroups(rawGroups.filter(g => GROUPS[g]))
  const rawAvatar  = user?.avatar || ''
  const avatar     = rawAvatar ? (rawAvatar.startsWith('http') ? rawAvatar : 'https://hackforums.net/' + rawAvatar.replace(/^\.\//, '')) : ''
  const initials   = (user?.username || 'HF').slice(0, 2).toUpperCase()

  const stats = profile ? [
    { l:'Posts',   v: Number(profile.postnum   ||0).toLocaleString() },
    { l:'Threads', v: Number(profile.threadnum ||0).toLocaleString() },
    { l:'Bytes',   v: Number(profile.myps      ||0).toLocaleString() },
    { l:'Rep',     v: Number(profile.reputation||0).toLocaleString() },
  ] : []

  const cachedStr = profile?.profile_ts
    ? new Date(profile.profile_ts*1000).toLocaleString(undefined,{month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'})
    : null

  // Current path for topbar
  const title = TITLE_MAP[loc.pathname] || ''
  const pathDisplay = loc.pathname.replace('/dashboard', '') || '/'

  return (
    <div className="shell-wrap">
      <div className="shell">

        {/* ── SIDEBAR ── */}
        <aside className="sidebar">
          <div className="sb-inner">

            {/* Logo */}
            <button className="sb-logo" onClick={() => nav('/dashboard')}>
              HF<span>.</span>TOOLBOX
            </button>

            {/* Profile */}
            <div className="sb-profile">
              <div style={{display:'flex',alignItems:'center',gap:9,marginBottom:7}}>
                <div className="sb-av">
                  {avatar
                    ? <img src={avatar} alt="" onError={e => e.currentTarget.style.display='none'}/>
                    : initials}
                </div>
                <div style={{minWidth:0}}>
                  <div className="sb-name">{user?.username || '---'}</div>
                  <div className="sb-pills">
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
                    {[0,1,2,3].map(i => <div key={i} className="sb-stat" style={{height:32,background:'var(--s3)',opacity:.3}}/>)}
                  </div>
              }
              {cachedStr && (
                <div style={{fontSize:9,color:'var(--dim)',fontFamily:'var(--mono)',marginTop:5,letterSpacing:'.03em'}}>
                  cached {cachedStr}
                </div>
              )}
            </div>

            {/* Nav */}
            <div className="sb-nav-lbl">navigation</div>
            <NavLink to="/dashboard" label="Overview" />

            <div className="sb-nav-lbl" style={{marginTop:4}}>modules</div>
            <NavLink to="/dashboard/bytes"     label="Bytes" />
            <NavLink to="/dashboard/contracts" label="Contracts" />
            <NavLink to="/dashboard/bumper"    label="Auto Bumper" />
            <NavLink to="/dashboard/posting"   label="Posting" badge={replyCount} />
            <NavLink to="/dashboard/sigmarket"  label="Sig Market" />

            <div className="sb-nav-lbl" style={{marginTop:4}}>system</div>
            <NavLink to="/dashboard/settings"  label="Settings" />
            {extraNavLinks}

          </div>

          {/* Bottom: rate limit + logout */}
          <div className="sb-bottom">
            <RateLimit />
            <div style={{height:8}}/>
            <ThemePicker theme={theme} setTheme={setTheme} />
            <button className="sb-logout" onClick={logout}>LOGOUT</button>
          </div>
        </aside>

        {/* ── MAIN ── */}
        <div className="main">
          <ApiPausedBanner />

          {/* Topbar */}
          <div className="topbar">
            <span style={{color:'var(--dim)',fontFamily:'var(--mono)',fontSize:10}}>
              hftoolbox<span style={{color:'var(--b3)'}}>:</span>
              <span style={{color:'var(--sub)'}}>~</span>
              <span style={{color:'var(--b3)'}}>$</span>
              {' '}
            </span>
            <span className="tb-title" style={{color:'var(--text)'}}>{pathDisplay}</span>

            <div className="tb-r">
              {/* Notifications */}
              <div ref={notifRef} style={{position:'relative'}}>
                <button
                  onClick={openNotifs}
                  style={{
                    position:'relative',background:'none',border:'1px solid var(--b2)',
                    cursor:'pointer',padding:'2px 7px',lineHeight:1.4,
                    fontSize:10,color:unseenCount>0?'var(--yellow)':'var(--dim)',
                    fontFamily:'var(--mono)',transition:'all 120ms',letterSpacing:'.04em',
                  }}
                  title="Notifications"
                >
                  NOTIF
                  {unseenCount > 0 && (
                    <span style={{
                      position:'absolute',top:-4,right:-4,
                      background:'var(--red)',color:'var(--bg)',
                      fontSize:8,fontWeight:700,
                      padding:'0px 3px',fontFamily:'var(--mono)',lineHeight:1.6,
                      minWidth:13,textAlign:'center',
                    }}>{unseenCount}</span>
                  )}
                </button>
                {notifOpen && (
                  <NotifPanel
                    notifs={notifs}
                    unseenCount={unseenCount}
                    setNotifOpen={setNotifOpen}
                    setUnseenCount={setUnseenCount}
                    setNotifs={setNotifs}
                  />
                )}
              </div>

              <div className="live-dot"/>
              <span className="tb-tag tb-live">LIVE</span>
            </div>
          </div>

          {/* Page header */}
          <div className="page-header">
            <div className="page-header-title">{title}</div>
          </div>

          {/* Content */}
          <div className="content up" key={loc.key}>
            <Outlet />
          </div>
        </div>

      </div>
      <MobileNav />
    </div>
  )
}

function MobileNav() {
  const nav = useNavigate()
  const loc = useLocation()
  const items = [
    { to:'/dashboard',           label:'HOME'      },
    { to:'/dashboard/bytes',     label:'BYTES'     },
    { to:'/dashboard/contracts', label:'CONTRACTS' },
    { to:'/dashboard/bumper',    label:'BUMPER'    },
    { to:'/dashboard/posting',   label:'POST'      },
  ]
  return (
    <nav className="mob-nav">
      {items.map(({to,label}) => {
        const on = loc.pathname===to||(to!=='/dashboard'&&loc.pathname.startsWith(to))
        return (
          <button key={to} className={`mob-nav-btn${on?' on':''}`} onClick={()=>nav(to)}>
            <span className="mob-nav-btn-icon">{on?'▶':'·'}</span>
            {label}
          </button>
        )
      })}
    </nav>
  )
}
