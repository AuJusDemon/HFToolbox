import { useState, useEffect, useRef } from 'react'
import { api } from './api.js'
import useStore from '../store.js'

const ago = ts => {
  if (!ts) return 'never'
  const d = Math.max(0, Math.floor(Date.now() / 1000) - Number(ts))
  if (d < 60) return `${d}s ago`
  if (d < 3600) return `${Math.floor(d / 60)}m ago`
  if (d < 86400) return `${Math.floor(d / 3600)}h ago`
  return `${Math.floor(d / 86400)}d ago`
}

const shortDate = ts => {
  if (!ts) return '-'
  return new Date(Number(ts) * 1000).toLocaleString()
}

const MODULE_LABELS = {
  bytes: 'Bytes',
  contracts: 'Contracts',
  autobump: 'Auto Bumper',
  sigmarket: 'Sig Market',
  posting: 'Posting',
  merchant: 'Marketplace',
  wire: 'Wire',
}

const ALERT_LABELS = {
  bytes_received: 'Bytes received',
  bytes_gambling_bundle: 'Gambling winnings bundle',
  contract_new: 'New contract',
  contract_status_change: 'Contract status change',
  contract_dispute: 'Contract dispute',
  contract_b_rating: 'B-rating received',
  reply_tracked_thread: 'Sales thread reply',
  merchant_followup_due: 'Follow-up due',
  merchant_rating_due: 'Rating due',
  pm_unread_increase: 'Unread PM count changed',
  autobump_daily: 'Daily autobump digest',
  autobump_budget: 'Autobump budget warning',
  autobump_paused: 'Autobump paused',
  sigmarket_sale: 'Sig Market sale',
  token_expiring: 'Auth token expiring',
  token_dead: 'Auth token stopped',
}

function SectionLabel({ children }) {
  return (
    <div style={{
      fontSize: 9,
      fontFamily: 'var(--mono)',
      letterSpacing: '.1em',
      textTransform: 'uppercase',
      color: 'var(--sub)',
      marginBottom: 8,
      marginTop: 12,
    }}>
      {children}
    </div>
  )
}

function Row({ label, hint, children, last }) {
  return (
    <div style={{
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
      gap: 24,
      padding: '11px 0',
      borderBottom: last ? 'none' : '1px solid var(--b1)',
    }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text)', marginBottom: 2 }}>
          {label}
        </div>
        {hint && <div style={{ fontSize: 11, color: 'var(--sub)', lineHeight: 1.5 }}>{hint}</div>}
      </div>
      <div style={{ flexShrink: 0, display: 'flex', alignItems: 'center', gap: 8 }}>
        {children}
      </div>
    </div>
  )
}

function Toggle({ value, onChange, disabled = false }) {
  return (
    <button
      className={`tog${value ? '' : ' off'}`}
      onClick={() => !disabled && onChange(!value)}
      disabled={disabled}
      aria-pressed={Boolean(value)}
    />
  )
}

function SelectControl({ value, onChange, options }) {
  return (
    <select
      value={value}
      onChange={e => onChange(Number(e.target.value))}
      className="inp"
      style={{ fontSize: 12, padding: '3px 8px', height: 28, minWidth: 92 }}
    >
      {options.map(o => <option key={o.v} value={o.v}>{o.l}</option>)}
    </select>
  )
}

function AccountSection() {
  const user = useStore(s => s.user)
  const logout = useStore(s => s.logout)
  const [tokenInfo, setTokenInfo] = useState(null)

  useEffect(() => {
    api.get('/api/crawl/status')
      .then(d => setTokenInfo({
        hasRefresh: d.has_refresh_token,
        lastActive: d.last_active,
        tokenExpiry: d.token_expiry || 0,
      }))
      .catch(() => {})
  }, [])

  const exp = Number(tokenInfo?.tokenExpiry || 0)
  const secondsLeft = exp ? exp - Math.floor(Date.now() / 1000) : null
  const authLabel = !tokenInfo ? 'checking'
    : !exp ? 'unknown'
    : secondsLeft <= 0 ? 'expired'
    : secondsLeft < 3600 ? `${Math.floor(secondsLeft / 60)}m left`
    : secondsLeft < 86400 ? `${Math.floor(secondsLeft / 3600)}h left`
    : `${Math.floor(secondsLeft / 86400)}d left`

  return (
    <div className="card" style={{ marginBottom: 12 }}>
      <div className="card-head">
        <span className="card-icon">USR</span>
        <span className="card-title">Account</span>
      </div>
      <div className="card-body">
        {user && (
          <Row label="Logged in as" hint={`UID ${user.uid}`}>
            <span style={{ fontSize: 13, fontFamily: 'var(--mono)', color: 'var(--text)' }}>{user.username}</span>
          </Row>
        )}
        <Row
          label="Hack Forums auth"
          hint={tokenInfo?.hasRefresh ? 'Refresh token stored for normal re-auth.' : 'Manual login is needed when this token expires.'}
        >
          <span style={{ fontSize: 12, fontFamily: 'var(--mono)', color: secondsLeft !== null && secondsLeft < 86400 ? 'var(--yellow)' : 'var(--sub)' }}>
            {authLabel}
          </span>
          <a href="/auth/login" className="btn btn-ghost" style={{ fontSize: 11, textDecoration: 'none' }}>Re-auth</a>
        </Row>
        <Row label="Log out" hint="End this browser session." last>
          <button className="btn btn-ghost" onClick={logout}>Log out</button>
        </Row>
      </div>
    </div>
  )
}

function ApiRefreshSection({ settings, save }) {
  const apiPaused = useStore(s => s.apiPaused)
  const [rate, setRate] = useState(null)
  const [refreshing, setRefreshing] = useState(false)
  const [message, setMessage] = useState('')

  const loadRate = () => {
    api.get('/api/rate-limit').then(setRate).catch(() => {})
  }

  useEffect(() => {
    loadRate()
    const t = setInterval(loadRate, 30000)
    return () => clearInterval(t)
  }, [])

  const refreshNow = async () => {
    setRefreshing(true)
    setMessage('')
    try {
      const d = await api.post('/api/refresh-now')
      setMessage(d?.ok ? 'Refresh queued.' : 'Refresh request sent.')
    } catch (err) {
      if (err?.retry_after) setMessage(`Try again in ${err.retry_after}s.`)
      else setMessage(err?.message || 'Refresh could not be queued.')
    } finally {
      setRefreshing(false)
      loadRate()
    }
  }

  const floorOpts = [
    { v: 10, l: '10' }, { v: 20, l: '20' }, { v: 30, l: '30' },
    { v: 40, l: '40' }, { v: 50, l: '50' }, { v: 75, l: '75' },
    { v: 100, l: '100' },
  ]
  return (
    <div className="card" style={{ marginBottom: 12 }}>
      <div className="card-head">
        <span className="card-icon">API</span>
        <span className="card-title">API & Refresh</span>
        {apiPaused && <span style={{ fontSize: 10, color: 'var(--red)', fontFamily: 'var(--mono)', marginLeft: 'auto' }}>polling paused</span>}
      </div>
      <div className="card-body">
        <div style={{ fontSize: 12, color: 'var(--sub)', marginBottom: 12, lineHeight: 1.6 }}>
          Control browser polling and the API floor. These settings do not change scheduled server jobs.
        </div>
        <Row label="Remaining HF calls" hint="Read-only status from the current token.">
          <span style={{ fontSize: 12, fontFamily: 'var(--mono)', color: 'var(--text)' }}>
            {rate?.remaining ?? 'unknown'}
          </span>
        </Row>
        <Row label="Throttle state" hint={rate?.polling_paused ? 'Polling is paused by your API floor.' : 'Browser polling is allowed.'}>
          <span style={{ fontSize: 12, fontFamily: 'var(--mono)', color: rate?.polling_paused ? 'var(--yellow)' : 'var(--acc)' }}>
            {rate?.throttle || 'unknown'}
          </span>
        </Row>
        <Row label="Enable API floor" hint="Pause browser polling when remaining calls drop below your floor.">
          <Toggle value={settings.apiFloorEnabled} onChange={v => save({ apiFloorEnabled: v })} />
        </Row>
        <Row label="Pause threshold" hint="Browser polling pauses below this remaining-call count.">
          <SelectControl value={settings.apiFloor} onChange={v => save({ apiFloor: v })} options={floorOpts} />
        </Row>
        <Row label="Refresh my data" hint={message || 'Queues the normal refresh worker. Cooldown prevents accidental repeat refreshes.'} last>
          <button className="btn btn-ghost" onClick={refreshNow} disabled={refreshing}>
            {refreshing ? 'Queueing...' : 'Refresh'}
          </button>
        </Row>
      </div>
    </div>
  )
}

function DashboardDisplaySection() {
  const { modules, isEnabled, setEnabled } = useStore()
  const visible = modules.filter(m => m.id !== 'wire')
  return (
    <div className="card" style={{ marginBottom: 12 }}>
      <div className="card-head">
        <span className="card-icon">DSP</span>
        <span className="card-title">Dashboard Display</span>
      </div>
      <div className="card-body">
        <div style={{ fontSize: 12, color: 'var(--sub)', marginBottom: 12, lineHeight: 1.6 }}>
          Choose which dashboard cards appear. This does not disable background jobs or alerts.
        </div>
        {visible.map((m, i) => (
          <Row
            key={m.id}
            label={MODULE_LABELS[m.id] || m.name}
            hint={m.description}
            last={i === visible.length - 1}
          >
            <Toggle value={isEnabled(m.id)} onChange={v => setEnabled(m.id, v)} />
          </Row>
        ))}
        {!modules.length && (
          <div style={{ fontSize: 12, color: 'var(--sub)', fontStyle: 'italic' }}>Loading dashboard modules...</div>
        )}
      </div>
    </div>
  )
}

function TelegramSection() {
  const [status, setStatus] = useState(null)
  const [delivery, setDelivery] = useState(null)
  const [loading, setLoading] = useState(true)
  const [linkData, setLinkData] = useState(null)
  const [generating, setGenerating] = useState(false)
  const [copied, setCopied] = useState(false)
  const [unlinking, setUnlinking] = useState(false)
  const pollRef = useRef(null)

  const loadStatus = () => {
    setLoading(true)
    Promise.all([
      api.get('/api/telegram/status').catch(() => null),
      api.get('/api/telegram/delivery-status').catch(() => null),
    ]).then(([s, d]) => {
      setStatus(s)
      setDelivery(d)
      setLoading(false)
    })
  }

  useEffect(() => { loadStatus() }, [])

  useEffect(() => {
    if (!linkData) return
    pollRef.current = setInterval(async () => {
      try {
        const d = await api.get('/api/telegram/status')
        if (d?.linked) {
          clearInterval(pollRef.current)
          pollRef.current = null
          setLinkData(null)
          loadStatus()
        }
      } catch {}
    }, 3000)
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current)
        pollRef.current = null
      }
    }
  }, [linkData])

  const generate = async () => {
    setGenerating(true)
    try {
      const d = await api.post('/api/telegram/link-code')
      setLinkData(d)
    } finally {
      setGenerating(false)
    }
  }

  const copy = () => {
    if (!linkData?.link) return
    navigator.clipboard.writeText(linkData.link).catch(() => {})
    setCopied(true)
    setTimeout(() => setCopied(false), 1800)
  }

  const unlink = async () => {
    setUnlinking(true)
    try {
      await api.post('/api/telegram/unlink')
      setLinkData(null)
      loadStatus()
    } finally {
      setUnlinking(false)
    }
  }

  return (
    <div className="card" style={{ marginBottom: 12 }}>
      <div className="card-head">
        <span className="card-icon">TG</span>
        <span className="card-title">Telegram</span>
        {status?.linked && <span style={{ fontSize: 10, color: 'var(--acc)', fontFamily: 'var(--mono)', marginLeft: 'auto' }}>linked</span>}
      </div>
      <div className="card-body">
        <div style={{ fontSize: 12, color: 'var(--sub)', marginBottom: 12, lineHeight: 1.6 }}>
          Connect the bot once. New links mark existing alerts as seen so old rows do not send.
        </div>
        {loading && <div className="spin" style={{ width: 16, height: 16, margin: '8px 0' }} />}
        {!loading && status?.linked && (
          <>
            <Row label="Status" hint={`Chat ID: ${status.chat_id} - linked ${ago(status.linked_at)}`}>
              <span style={{ fontSize: 12, fontFamily: 'var(--mono)', color: 'var(--acc)' }}>connected</span>
            </Row>
            <Row label="Last alert sent" hint={delivery?.last_sent?.title || 'No sent Telegram alerts recorded.'}>
              <span style={{ fontSize: 12, fontFamily: 'var(--mono)', color: 'var(--sub)' }}>
                {shortDate(delivery?.last_sent?.telegram_delivered_at)}
              </span>
            </Row>
            <Row label="Last delivery failure" hint={delivery?.last_failed?.telegram_error || 'No recent delivery failures.'}>
              <span style={{ fontSize: 12, fontFamily: 'var(--mono)', color: delivery?.last_failed ? 'var(--yellow)' : 'var(--sub)' }}>
                {delivery?.last_failed ? ago(delivery.last_failed.created_at) : '-'}
              </span>
            </Row>
            <Row label="Pending after baseline" hint={`Disabled alert types: ${delivery?.disabled_count ?? 0}`}>
              <span style={{ fontSize: 12, fontFamily: 'var(--mono)', color: 'var(--text)' }}>
                {delivery?.pending_after_baseline ?? 0}
              </span>
            </Row>
            <Row label="Disconnect" hint="Removes Telegram delivery for this account." last>
              <button className="btn btn-ghost" onClick={unlink} disabled={unlinking}>
                {unlinking ? 'Disconnecting...' : 'Disconnect'}
              </button>
            </Row>
          </>
        )}
        {!loading && !status?.linked && !linkData && (
          <Row label="Connect Telegram" hint="Generate a one-time link and open it in Telegram." last>
            <button className="btn btn-ghost" onClick={generate} disabled={generating}>
              {generating ? 'Generating...' : 'Generate link'}
            </button>
          </Row>
        )}
        {!loading && linkData && (
          <>
            <div style={{ fontSize: 12, color: 'var(--sub)', marginBottom: 8, lineHeight: 1.6 }}>
              Open this link in Telegram. It expires in {Math.floor(linkData.expires / 60)} minutes.
            </div>
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: 8,
              background: 'var(--b1)',
              borderRadius: 4,
              padding: '8px 10px',
              marginBottom: 10,
            }}>
              <span style={{
                fontSize: 12,
                fontFamily: 'var(--mono)',
                color: 'var(--sub)',
                flex: 1,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}>
                {linkData.link}
              </span>
              <button className="btn btn-ghost" onClick={copy} style={{ fontSize: 10, padding: '2px 8px' }}>
                {copied ? 'Copied' : 'Copy'}
              </button>
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              <a href={linkData.link} target="_blank" rel="noopener noreferrer" className="btn btn-ghost" style={{ fontSize: 11 }}>
                Open in Telegram
              </a>
              <button className="btn btn-ghost" onClick={() => setLinkData(null)} style={{ fontSize: 11 }}>
                Cancel
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  )
}

function AlertPreferencesSection() {
  const [prefs, setPrefs] = useState(null)
  const [delivery, setDelivery] = useState(null)
  const [saving, setSaving] = useState(null)
  const [message, setMessage] = useState('')

  const load = () => {
    api.get('/api/telegram/alert-preferences')
      .then(d => setPrefs(d?.preferences || {}))
      .catch(() => {})
    api.get('/api/telegram/delivery-status')
      .then(setDelivery)
      .catch(() => {})
  }

  useEffect(() => { load() }, [])

  const toggle = async (type, val) => {
    setSaving(type)
    setMessage('')
    try {
      const d = await api.patch('/api/telegram/alert-preferences', { [type]: val })
      setPrefs(d?.preferences || {})
      setDelivery(d?.delivery || null)
      setMessage(val ? 'Old rows for this type were marked seen.' : 'This type will not retry to Telegram.')
    } finally {
      setSaving(null)
    }
  }

  const markSeen = async () => {
    setSaving('seen')
    setMessage('')
    try {
      const d = await api.post('/api/telegram/mark-seen')
      setDelivery(d?.status || null)
      setMessage(`Marked ${d?.result?.skipped ?? 0} existing alerts as seen.`)
    } catch (err) {
      setMessage(err?.message || 'Could not mark alerts as seen.')
    } finally {
      setSaving(null)
    }
  }

  const types = Object.keys(ALERT_LABELS)

  return (
    <div className="card" style={{ marginBottom: 12 }}>
      <div className="card-head">
        <span className="card-icon">ALT</span>
        <span className="card-title">Alert Preferences</span>
      </div>
      <div className="card-body">
        <div style={{ fontSize: 12, color: 'var(--sub)', marginBottom: 12, lineHeight: 1.6 }}>
          Control Telegram delivery. Disabling a type skips pending rows for that type. Turning it back on starts from now.
        </div>
        <Row
          label="Notification safety"
          hint={message || `Global baseline: ${shortDate(delivery?.baseline_at)}`}
        >
          <button className="btn btn-ghost" onClick={markSeen} disabled={saving === 'seen'}>
            {saving === 'seen' ? 'Marking...' : 'Mark existing alerts as seen'}
          </button>
        </Row>
        {prefs === null && <div className="spin" style={{ width: 14, height: 14, margin: '8px 0' }} />}
        {prefs !== null && types.map((type, i) => {
          const enabled = prefs[type] !== false
          return (
            <Row key={type} label={ALERT_LABELS[type]} last={i === types.length - 1}>
              <Toggle value={enabled} onChange={v => toggle(type, v)} />
              {saving === type && <div className="spin" style={{ width: 10, height: 10 }} />}
            </Row>
          )
        })}
      </div>
    </div>
  )
}

function DataPrivacySection() {
  const [phase, setPhase] = useState('idle')
  const [deleteError, setDeleteError] = useState('')
  const [inventory, setInventory] = useState(null)

  const enterConfirm = () => {
    setPhase('confirm')
    if (!inventory) {
      api.get('/api/account/inventory')
        .then(d => setInventory(d))
        .catch(() => {})
    }
  }

  const handleDelete = async () => {
    setPhase('deleting')
    setDeleteError('')
    try {
      await api.delete('/api/account')
      setPhase('done')
      setTimeout(() => { window.location.href = '/' }, 1500)
    } catch (err) {
      setDeleteError(err.message || 'Deletion failed')
      setPhase('error')
    }
  }

  return (
    <div className="card" style={{ marginBottom: 12 }}>
      <div className="card-head">
        <span className="card-icon">DAT</span>
        <span className="card-title">Data & Privacy</span>
      </div>
      <div className="card-body">
        <div style={{ fontSize: 12, color: 'var(--sub)', marginBottom: 12, lineHeight: 1.6 }}>
          Account deletion removes HFToolbox records for this UID. It does not change your Hack Forums account.
        </div>
        <Row
          label="Delete account data"
          hint="Removes stored bytes history, contracts, bump jobs, drafts, settings, alerts, and local account records."
          last
        >
          {phase === 'idle' && <button className="btn btn-danger" onClick={enterConfirm}>Delete</button>}
          {phase === 'confirm' && (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 8 }}>
              {inventory && inventory.total_rows > 0 && (
                <span style={{ fontSize: 10, color: 'var(--sub)', fontFamily: 'var(--mono)' }}>
                  {inventory.total_rows.toLocaleString()} rows across {Object.keys(inventory.inventory).length} tables
                </span>
              )}
              <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <span style={{ fontSize: 11, color: 'var(--red)', marginRight: 2 }}>Confirm delete</span>
                <button className="btn btn-danger" onClick={handleDelete}>Yes, delete</button>
                <button className="btn btn-ghost" onClick={() => setPhase('idle')}>Cancel</button>
              </div>
            </div>
          )}
          {phase === 'deleting' && <span style={{ fontSize: 11, color: 'var(--sub)' }}>Deleting...</span>}
          {phase === 'done' && <span style={{ fontSize: 11, color: 'var(--acc)' }}>Deleted. Redirecting...</span>}
          {phase === 'error' && (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 6 }}>
              <span style={{ fontSize: 11, color: 'var(--red)' }}>{deleteError}</span>
              <div style={{ display: 'flex', gap: 6 }}>
                <button className="btn btn-danger" onClick={() => setPhase('confirm')}>Try again</button>
                <button className="btn btn-ghost" onClick={() => setPhase('idle')}>Cancel</button>
              </div>
            </div>
          )}
        </Row>
      </div>
    </div>
  )
}

function SystemStatusSection() {
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get('/api/crawl/status')
      .then(d => { setStatus(d); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  const StatRow = ({ label, value, color, last }) => (
    <div style={{
      display: 'grid',
      gridTemplateColumns: '1fr auto',
      gap: 8,
      padding: '6px 0',
      borderBottom: last ? 'none' : '1px solid var(--b1)',
    }}>
      <span style={{ fontSize: 12, color: 'var(--sub)' }}>{label}</span>
      <span style={{ fontSize: 12, fontFamily: 'var(--mono)', color: color || 'var(--text)', textAlign: 'right' }}>{value}</span>
    </div>
  )

  return (
    <div className="card" style={{ marginBottom: 12 }}>
      <div className="card-head">
        <span className="card-icon">SYS</span>
        <span className="card-title">System Status</span>
        <span style={{ fontSize: 10, color: 'var(--sub)', fontFamily: 'var(--mono)', marginLeft: 'auto' }}>read-only</span>
      </div>
      <div className="card-body">
        {loading && <div className="spin" style={{ width: 16, height: 16, margin: '8px 0' }} />}
        {!loading && status?.crawl_disabled && (
          <div style={{
            fontSize: 12,
            color: 'var(--yellow)',
            fontFamily: 'var(--mono)',
            padding: '8px 10px',
            background: 'var(--b1)',
            borderRadius: 4,
            marginBottom: 12,
          }}>
            Background crawl disabled in this runtime.
          </div>
        )}
        {!loading && status && (() => {
          const b = status.bytes || {}
          const c = status.contracts || {}
          return (
            <>
              <div style={{ fontSize: 12, color: 'var(--sub)', marginBottom: 12, lineHeight: 1.6 }}>
                Read-only crawl and token status. Change alert and polling behavior above.
              </div>
              <SectionLabel>Bytes history</SectionLabel>
              <StatRow label="Transactions stored" value={Number(b.total_stored || 0).toLocaleString()} />
              <StatRow label="Received crawl" value={b.recv_done ? 'complete' : `page ${b.recv_page || '-'}`} />
              <StatRow label="Sent crawl" value={b.sent_done ? 'complete' : `page ${b.sent_page || '-'}`} />
              <StatRow label="Last crawl" value={ago(b.last_crawl)} last />
              <SectionLabel>Contracts history</SectionLabel>
              <StatRow label="Contracts stored" value={Number(c.total_stored || 0).toLocaleString()} />
              <StatRow label="Crawl position" value={c.done ? 'complete' : `page ${c.page || '-'}`} />
              <StatRow label="Last crawl" value={ago(c.last_crawl)} last />
            </>
          )
        })()}
        {!loading && !status && (
          <div style={{ fontSize: 12, color: 'var(--sub)', fontStyle: 'italic' }}>Could not load system status.</div>
        )}
      </div>
    </div>
  )
}

export default function Settings() {
  const { settings, saveSettings } = useStore()

  return (
    <>
      <div style={{ marginBottom: 20 }}>
        <div style={{ fontSize: 16, fontWeight: 700, letterSpacing: '-.02em', marginBottom: 4 }}>Settings</div>
        <div style={{ fontSize: 12, color: 'var(--sub)' }}>
          Account controls, dashboard cards, Telegram delivery, alerts, and stored data.
        </div>
      </div>

      <AccountSection />
      <ApiRefreshSection settings={settings} save={saveSettings} />
      <DashboardDisplaySection />
      <TelegramSection />
      <AlertPreferencesSection />
      <DataPrivacySection />
      <SystemStatusSection />
    </>
  )
}
