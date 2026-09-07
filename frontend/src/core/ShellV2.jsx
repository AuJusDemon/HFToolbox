import { useEffect, useRef, useState } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import useStore from '../store.js'
import { api } from './api.js'
import { getProgramByRoute, prefetchProgram, PROGRAMS } from '../system/programRegistry.js'
import { CommandLauncher, MobileProgramDrawer, ProgramNavigation, visiblePrograms } from '../system/AppNavigation.jsx'
import { useApiQuery } from './useApiQuery.js'

export const ROUTE_PREFETCHERS = Object.fromEntries(PROGRAMS.filter(p => p.route && p.prefetch).map(p => [p.route, p.prefetch]))

const GROUPS = { '2':'Registered','9':'L33t','28':'Ub3r','46':'H4CK3R$','48':'Quantum','52':'PinkLSZ','50':'Legends','77':'Academy','71':'Warriors','78':'VIBE','70':'Gamblers','68':'Brotherhood','67':'Vendor','7':'Exiled','38':'Banned' }
const GROUP_PRIORITY = ['9','28','67','46','48','50','52','68','70','71','77','78','7','38','2']

function primaryGroup(profile, user) {
  const groups = (profile?.groups || user?.groups || []).map(String).filter(group => GROUPS[group])
  const display = String(profile?.displaygroup || '')
  if (display !== '0' && GROUPS[display]) return GROUPS[display]
  groups.sort((a, b) => GROUP_PRIORITY.indexOf(a) - GROUP_PRIORITY.indexOf(b))
  return GROUPS[groups[0]] || 'HF account'
}

function TokenBanner() {
  const expiry = useStore(state => state.tokenExpiry)
  if (!expiry) return null
  const seconds = expiry - Math.floor(Date.now() / 1000)
  if (seconds > 48 * 3600) return null
  const expired = seconds <= 0
  return <div className={`app-system-banner ${expired ? 'error' : 'warning'}`}><span>{expired ? 'HF authorization expired. Background account work is paused.' : `HF authorization expires in ${Math.floor(seconds / 3600)} hours.`}</span><a href="/auth/login">Re-authenticate</a></div>
}

function ApiBanner() {
  const paused = useStore(state => state.apiPaused)
  const floor = useStore(state => state.settings.apiFloor)
  if (!paused) return null
  return <div className="app-system-banner error"><span>HF API polling is paused at the configured allowance floor ({floor}).</span><a href="/dashboard/settings">Review settings</a></div>
}

function RateLimit() {
  const settings = useStore(state => state.settings)
  const setApiPaused = useStore(state => state.setApiPaused)
  const setThrottle = useStore(state => state.setThrottle)
  const rate = useApiQuery('/api/rate-limit', { refetchInterval: 10000 })
  const data = rate.data
  useEffect(() => {
    if (data?.throttle) setThrottle(data.throttle)
    const remaining = Number(data?.remaining)
    if (settings.apiFloorEnabled && Number.isFinite(remaining) && remaining < 9999) setApiPaused(remaining < (settings.apiFloor ?? 30))
  }, [data, settings.apiFloor, settings.apiFloorEnabled, setApiPaused, setThrottle])
  const remaining = Number(data?.remaining)
  const known = !data?.stale && Number.isFinite(remaining) && remaining < 9999
  const unavailable = data?.hf_api?.available === false
  return <div className="sb-api"><div><span>HF API</span><b className={unavailable ? 'warning' : ''}>{unavailable ? 'Waiting' : known ? `${remaining} / 240` : 'Unknown'}</b></div><div className="sb-api-track" aria-hidden="true"><i style={{ width: known ? `${Math.max(0, Math.min(100, remaining / 2.4))}%` : '0%' }} /></div></div>
}

function NotificationPanel({ notifications, unseen, onClose, onRead }) {
  const navigate = useNavigate()
  return <section className="app-notifications" aria-label="Notifications"><header><b>Notifications</b>{unseen > 0 && <button type="button" onClick={onRead}>Mark read</button>}</header>{notifications.length === 0 ? <p>No notifications.</p> : notifications.map(item => <button key={item.id} type="button" className={item.seen ? '' : 'unseen'} onClick={() => { onClose(); if (item.link?.startsWith('http')) window.open(item.link, '_blank'); else if (item.link) navigate(item.link) }}><b>{item.title}</b>{item.body && <span>{item.body}</span>}</button>)}</section>
}

export default function ShellV2() {
  const user = useStore(state => state.user)
  const logout = useStore(state => state.logout)
  const tokenExpiry = useStore(state => state.tokenExpiry)
  const setTokenExpiry = useStore(state => state.setTokenExpiry)
  const navigate = useNavigate()
  const location = useLocation()
  const [profile, setProfile] = useState(null)
  const [replyCount, setReplyCount] = useState(0)
  const [notifications, setNotifications] = useState([])
  const [unseen, setUnseen] = useState(0)
  const [notificationsOpen, setNotificationsOpen] = useState(false)
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem('hftb_nav_collapsed') === '1')
  const [drawerOpen, setDrawerOpen] = useState(false)
  const [launcherOpen, setLauncherOpen] = useState(false)
  const notificationRef = useRef(null)
  const shellData = useApiQuery('/api/shell-data', { refetchInterval: 60000 })

  useEffect(() => {
    const data = shellData.data
    if (data?.profile) setProfile(data.profile)
    if (data?.reply_count != null) setReplyCount(Number(data.reply_count))
    if (data?.notifications) setNotifications(data.notifications)
    if (data?.unseen != null) setUnseen(Number(data.unseen))
    if (data?.token_expiry != null) setTokenExpiry(Number(data.token_expiry))
  }, [shellData.data, setTokenExpiry])

  useEffect(() => { localStorage.setItem('hftb_nav_collapsed', collapsed ? '1' : '0') }, [collapsed])
  useEffect(() => {
    const close = event => { if (notificationRef.current && !notificationRef.current.contains(event.target)) setNotificationsOpen(false) }
    document.addEventListener('mousedown', close); return () => document.removeEventListener('mousedown', close)
  }, [])
  useEffect(() => {
    const connection = navigator.connection || navigator.mozConnection || navigator.webkitConnection
    if (connection?.saveData || /(^|-)2g$/.test(connection?.effectiveType || '')) return undefined
    const warm = () => visiblePrograms(user)
      .filter(program => program.availability === 'available')
      .forEach(program => prefetchProgram(program, { data: ['home', 'merchant', 'bumper', 'contracts', 'bytes'].includes(program.id) }))
    const id = 'requestIdleCallback' in window
      ? window.requestIdleCallback(warm, { timeout: 2500 })
      : window.setTimeout(warm, 1200)
    return () => 'cancelIdleCallback' in window ? window.cancelIdleCallback(id) : window.clearTimeout(id)
  }, [user])
  useEffect(() => {
    const shortcut = event => {
      const target = event.target
      const typing = target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || target?.isContentEditable
      if ((event.ctrlKey && event.key.toLowerCase() === 'k') || (event.key === '/' && !typing)) { event.preventDefault(); setLauncherOpen(true) }
    }
    document.addEventListener('keydown', shortcut); return () => document.removeEventListener('keydown', shortcut)
  }, [])

  const activeProgram = getProgramByRoute(location.pathname)
  const title = activeProgram.id === 'home' ? 'Overview' : activeProgram.label
  const nested = activeProgram.route ? location.pathname.slice(activeProgram.route.length).split('/').filter(Boolean) : []
  const rawAvatar = user?.avatar || ''
  const avatar = rawAvatar ? (rawAvatar.startsWith('http') ? rawAvatar : `https://hackforums.net/${rawAvatar.replace(/^\.\//, '')}`) : ''
  const initials = (user?.username || 'HF').slice(0, 2).toUpperCase()
  const accountState = tokenExpiry && tokenExpiry <= Math.floor(Date.now() / 1000) ? 'Re-authentication required' : 'Connected'
  const counters = { posting: replyCount }
  const markRead = () => { api.post('/api/notifications/seen').catch(() => {}); setUnseen(0); setNotifications(items => items.map(item => ({ ...item, seen: 1 }))) }

  return <div className="shell-wrap"><div className={`shell${collapsed ? ' nav-collapsed' : ''}`}>
    <aside className="sidebar" aria-label="Primary navigation"><div className="sb-inner">
      <button className="sb-logo" type="button" onClick={() => navigate('/dashboard')} title={collapsed ? 'HF.Toolbox Overview' : undefined}><span className="sb-logo-full">HF<span>.</span>TOOLBOX</span><span className="sb-logo-short">HF</span></button>
      <div className="sb-profile" title={collapsed ? `${user?.username || 'HF user'} - UID ${user?.uid || '--'}` : undefined}><div className="sb-av">{avatar ? <img src={avatar} alt="" onError={event => { event.currentTarget.style.display = 'none' }} /> : initials}</div><div className="sb-account-copy"><b>{user?.username || '---'}</b><span>UID {user?.uid || '--'}</span><span>{primaryGroup(profile, user)}</span><em className={accountState === 'Connected' ? 'connected' : 'warning'}>{accountState}</em></div></div>
      <ProgramNavigation user={user} collapsed={collapsed} counters={counters} />
    </div><div className="sb-bottom"><RateLimit /><button className="sb-collapse" type="button" onClick={() => setCollapsed(value => !value)} aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}>{collapsed ? '>' : '< Collapse'}</button><button className="sb-logout" type="button" onClick={logout}>{collapsed ? 'OUT' : 'Log out'}</button></div></aside>
    <main className="main"><TokenBanner /><ApiBanner /><header className="topbar">
      <button type="button" className="app-menu-button" onClick={() => setDrawerOpen(true)} aria-label="Open navigation">Menu</button>
      <div className="app-route-title"><b>{title}</b>{nested.length > 0 && <span>/ {nested.join(' / ')}</span>}</div>
      <div className="tb-r"><span className={`tb-account-state ${accountState === 'Connected' ? 'connected' : 'warning'}`}>{accountState}</span><button type="button" className="command-trigger" onClick={() => setLauncherOpen(true)}>Open <kbd>Ctrl K</kbd></button><div className="app-notification-wrap" ref={notificationRef}><button type="button" className="app-header-button" onClick={() => { setNotificationsOpen(value => !value); if (!notificationsOpen && unseen) markRead() }} aria-label="Notifications">NT{unseen > 0 && <span>{unseen}</span>}</button>{notificationsOpen && <NotificationPanel notifications={notifications} unseen={unseen} onClose={() => setNotificationsOpen(false)} onRead={markRead} />}</div><button type="button" className="tb-account-button" onClick={() => navigate('/dashboard/settings')} aria-label="Open account settings">{initials}</button></div>
    </header><div className="route-transfer" aria-hidden="true"><span>{activeProgram.shortLabel}</span></div><div className="content app-route-content"><Outlet /></div></main>
  </div><MobileProgramDrawer open={drawerOpen} onClose={() => setDrawerOpen(false)} user={user} counters={counters} account={user?.username || 'HF account'} /><CommandLauncher open={launcherOpen} onClose={() => setLauncherOpen(false)} user={user} /></div>
}
