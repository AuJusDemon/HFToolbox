import { useState, useEffect, useRef } from 'react'
import { api } from './api.js'
import useStore from '../store.js'

// ── helpers ────────────────────────────────────────────────────────────────────

const ago = ts => {
  if (!ts) return 'never'
  const d = Math.floor(Date.now() / 1000) - ts
  if (d < 60)    return `${d}s ago`
  if (d < 3600)  return `${Math.floor(d/60)}m ago`
  if (d < 86400) return `${Math.floor(d/3600)}h ago`
  return `${Math.floor(d/86400)}d ago`
}

const MODULE_ICONS = {
  bytes: '💰', contracts: '📜', autobump: '⬆',
  sigmarket: '✍', posting: '✏', wire: '📡',
}

function SectionLabel({ children }) {
  return (
    <div style={{
      fontSize: 9, fontFamily: 'var(--mono)', letterSpacing: '.1em',
      textTransform: 'uppercase', color: 'var(--sub)',
      marginBottom: 8, marginTop: 12,
    }}>
      {children}
    </div>
  )
}

function Row({ label, hint, children, last }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      gap: 24, padding: '11px 0',
      borderBottom: last ? 'none' : '1px solid var(--b1)',
    }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--text)', marginBottom: 2 }}>{label}</div>
        {hint && <div style={{ fontSize: 11, color: 'var(--sub)', lineHeight: 1.5 }}>{hint}</div>}
      </div>
      <div style={{ flexShrink: 0, display: 'flex', alignItems: 'center' }}>
        {children}
      </div>
    </div>
  )
}

function Toggle({ value, onChange }) {
  return (
    <button
      className={`tog${value ? '' : ' off'}`}
      onClick={() => onChange(!value)}
    />
  )
}

// ── Section: API Protection ────────────────────────────────────────────────────

function ApiProtectionSection({ settings, save }) {
  const apiPaused = useStore(s => s.apiPaused)
  const floorOpts = [
    {v:10,l:'10'},{v:20,l:'20'},{v:30,l:'30'},{v:40,l:'40'},
    {v:50,l:'50'},{v:75,l:'75'},{v:100,l:'100'},
  ]
  return (
    <div className="card" style={{ marginBottom: 12 }}>
      <div className="card-head">
        <span className="card-icon">API</span>
        <span className="card-title">API Protection</span>
        {apiPaused && (
          <span style={{ fontSize: 10, color: 'var(--red)', fontFamily: 'var(--mono)', marginLeft: 'auto' }}>
            ● paused
          </span>
        )}
      </div>
      <div className="card-body">
        <div style={{ fontSize: 12, color: 'var(--sub)', marginBottom: 12, lineHeight: 1.6 }}>
          When your hourly API call budget drops below the floor, all live polling pauses
          and a warning banner appears. Pages still load — they just won't auto-refresh
          until your budget recovers.
        </div>
        <Row label="Enable API floor" hint="Pause polling automatically when budget runs low">
          <Toggle value={settings.apiFloorEnabled} onChange={v => save({ apiFloorEnabled: v })} />
        </Row>
        <Row label="Pause threshold" hint="Pause when remaining calls drop below this number (out of 240/hr)" last>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <select
              value={settings.apiFloor}
              onChange={e => save({ apiFloor: Number(e.target.value) })}
              className="inp"
              style={{ fontSize: 12, padding: '3px 8px', height: 28, minWidth: 70 }}
            >
              {floorOpts.map(o => <option key={o.v} value={o.v}>{o.l}</option>)}
            </select>
            <span style={{ fontSize: 11, color: 'var(--sub)' }}>remaining</span>
          </div>
        </Row>
      </div>
    </div>
  )
}

// ── Section: Module Visibility ─────────────────────────────────────────────────

function VisibilitySection() {
  const { modules, isEnabled, setEnabled } = useStore()
  const visible = modules.filter(m => m.id !== 'wire') // wire has no dashboard card
  return (
    <div className="card" style={{ marginBottom: 12 }}>
      <div className="card-head">
        <span className="card-icon">VIS</span>
        <span className="card-title">Module Visibility</span>
      </div>
      <div className="card-body">
        <div style={{ fontSize: 12, color: 'var(--sub)', marginBottom: 12, lineHeight: 1.6 }}>
          Toggle which modules are active. Disabled modules stop polling entirely.
        </div>
        {visible.map((m, i) => (
          <Row
            key={m.id}
            label={<><span style={{ marginRight: 6 }}>{MODULE_ICONS[m.id] || m.icon}</span>{m.name}</>}
            hint={m.description}
            last={i === visible.length - 1}
          >
            <Toggle value={isEnabled(m.id)} onChange={v => setEnabled(m.id, v)} />
          </Row>
        ))}
        {!modules.length && (
          <div style={{ fontSize: 12, color: 'var(--sub)', fontStyle: 'italic' }}>Loading modules…</div>
        )}
      </div>
    </div>
  )
}

// ── Section: Crawler Status ────────────────────────────────────────────────────

function CrawlerSection() {
  const [status, setStatus] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get('/api/crawl/status')
      .then(d => { setStatus(d); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  const StatRow = ({ label, value, color, last }) => (
    <div style={{
      display: 'grid', gridTemplateColumns: '1fr auto', gap: 8,
      padding: '6px 0', borderBottom: last ? 'none' : '1px solid var(--b1)',
    }}>
      <span style={{ fontSize: 12, color: 'var(--sub)' }}>{label}</span>
      <span style={{ fontSize: 12, fontFamily: 'var(--mono)', color: color || 'var(--text)', textAlign: 'right' }}>{value}</span>
    </div>
  )

  return (
    <div className="card" style={{ marginBottom: 12 }}>
      <div className="card-head">
        <span className="card-icon">SYN</span>
        <span className="card-title">Crawler Status</span>
        <span style={{ fontSize: 10, color: 'var(--sub)', fontFamily: 'var(--mono)', marginLeft: 'auto' }}>read-only</span>
      </div>
      <div className="card-body">

        {loading && <div className="spin" style={{ width: 16, height: 16, margin: '8px 0' }} />}

        {!loading && status?.crawl_disabled && (
          <div style={{
            fontSize: 12, color: 'var(--yellow)', fontFamily: 'var(--mono)',
            padding: '8px 10px', background: 'var(--b1)', borderRadius: 4, marginBottom: 12,
          }}>
            ⚠ Background crawl disabled (DEV_DISABLE_CRAWL=1) — data reflects last prod sync
          </div>
        )}

        {!loading && status && (() => {
          const b = status.bytes
          const c = status.contracts
          const bDone = b.recv_done && b.sent_done
          return (
            <>
              <div style={{ fontSize: 12, color: 'var(--sub)', marginBottom: 12, lineHeight: 1.6 }}>
                Background crawlers build your local transaction and contract history over time.
                Full history is fetched once; after that only new entries are checked each cycle.
              </div>

              <SectionLabel>Bytes history</SectionLabel>
              <StatRow label="Transactions stored" value={b.total_stored.toLocaleString()} />
              <StatRow label="Received" value={b.recv_done ? 'complete ✓' : `fetching page ${b.recv_page}`} color={b.recv_done ? 'var(--acc)' : undefined} />
              <StatRow label="Sent" value={b.sent_done ? 'complete ✓' : `fetching page ${b.sent_page}`} color={b.sent_done ? 'var(--acc)' : undefined} />
              <StatRow label="Last crawl" value={ago(b.last_crawl)} />
              <StatRow label="Status" value={bDone ? 'Full history' : 'Building…'} color={bDone ? 'var(--acc)' : 'var(--yellow)'} last />

              <SectionLabel>Contracts history</SectionLabel>
              <StatRow label="Contracts stored" value={c.total_stored.toLocaleString()} />
              <StatRow label="Crawl position" value={c.done ? 'complete ✓' : `fetching page ${c.page}`} color={c.done ? 'var(--acc)' : undefined} />
              <StatRow label="Last crawl" value={ago(c.last_crawl)} />
              <StatRow label="Status" value={c.done ? 'Full history' : 'Building…'} color={c.done ? 'var(--acc)' : 'var(--yellow)'} last />
            </>
          )
        })()}

        {!loading && !status && (
          <div style={{ fontSize: 12, color: 'var(--sub)', fontStyle: 'italic' }}>Could not load crawl status</div>
        )}
      </div>
    </div>
  )
}

// ── Section: Telegram Alerts ──────────────────────────────────────────────────

function TelegramSection() {
  const [status,     setStatus]     = useState(null)
  const [loading,    setLoading]    = useState(true)
  const [linkData,   setLinkData]   = useState(null)
  const [generating, setGenerating] = useState(false)
  const [copied,     setCopied]     = useState(false)
  const [unlinking,  setUnlinking]  = useState(false)
  const pollRef = useRef(null)

  const loadStatus = () => {
    setLoading(true)
    api.get('/api/telegram/status')
      .then(d => { setStatus(d); setLoading(false) })
      .catch(() => setLoading(false))
  }

  useEffect(() => { loadStatus() }, [])

  // Poll for link completion while a code is pending
  useEffect(() => {
    if (!linkData) return
    pollRef.current = setInterval(async () => {
      try {
        const d = await api.get('/api/telegram/status')
        if (d?.linked) {
          clearInterval(pollRef.current)
          pollRef.current = null
          setLinkData(null)
          setStatus(d)
          setLoading(false)
        }
      } catch {}
    }, 3000)
    return () => {
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null }
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

  const mono = { fontSize: 12, fontFamily: 'var(--mono)', color: 'var(--sub)' }

  return (
    <div className="card" style={{ marginBottom: 12 }}>
      <div className="card-head">
        <span className="card-icon">TG</span>
        <span className="card-title">Telegram Alerts</span>
        {status?.linked && (
          <span style={{ fontSize: 10, color: 'var(--acc)', fontFamily: 'var(--mono)', marginLeft: 'auto' }}>
            ● linked
          </span>
        )}
      </div>
      <div className="card-body">
        <div style={{ fontSize: 12, color: 'var(--sub)', marginBottom: 12, lineHeight: 1.6 }}>
          Get instant Telegram alerts for contracts, PMs, and thread replies.
        </div>

        {loading && <div className="spin" style={{ width: 16, height: 16, margin: '8px 0' }} />}

        {!loading && status?.linked && (
          <>
            <Row label="Status" hint={`Chat ID: ${status.chat_id} · linked ${ago(status.linked_at)}`}>
              <span style={{ ...mono, color: 'var(--acc)' }}>connected</span>
            </Row>
            <Row label="Disconnect" hint="Removes the Telegram link — alerts will stop" last>
              <button
                className="btn btn-ghost"
                onClick={unlink}
                disabled={unlinking}
                style={{ fontSize: 11 }}
              >
                {unlinking ? 'Disconnecting…' : 'Disconnect'}
              </button>
            </Row>
          </>
        )}

        {!loading && !status?.linked && !linkData && (
          <Row label="Connect Telegram" hint="Generates a one-time link — open it in Telegram to link your account" last>
            <button
              className="btn btn-ghost"
              onClick={generate}
              disabled={generating}
              style={{ fontSize: 11 }}
            >
              {generating ? 'Generating…' : 'Generate link'}
            </button>
          </Row>
        )}

        {!loading && linkData && (
          <>
            <div style={{ fontSize: 12, color: 'var(--sub)', marginBottom: 8, lineHeight: 1.6 }}>
              Open this link in Telegram. It expires in {Math.floor(linkData.expires / 60)} minutes.
              Waiting for you to open it…
            </div>
            <div style={{
              display: 'flex', alignItems: 'center', gap: 8,
              background: 'var(--b1)', borderRadius: 4, padding: '8px 10px', marginBottom: 10,
            }}>
              <span style={{
                ...mono, flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
              }}>
                {linkData.link}
              </span>
              <button
                className="btn btn-ghost"
                onClick={copy}
                style={{ fontSize: 10, padding: '2px 8px', flexShrink: 0 }}
              >
                {copied ? '✓ copied' : 'copy'}
              </button>
            </div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              <a
                href={linkData.link}
                target="_blank"
                rel="noopener noreferrer"
                className="btn btn-ghost"
                style={{ fontSize: 11 }}
              >
                Open in Telegram ↗
              </a>
              <button
                className="btn btn-ghost"
                onClick={() => setLinkData(null)}
                style={{ fontSize: 11 }}
              >
                Cancel
              </button>
              <div className="spin" style={{ width: 12, height: 12 }} />
            </div>
          </>
        )}
      </div>
    </div>
  )
}


// ── Section: Alert Preferences ────────────────────────────────────────────────

const ALERT_LABELS = {
  bytes_received:          'Bytes received',
  bytes_gambling_bundle:   'Gambling winnings bundle',
  contract_new:            'New contract',
  contract_status_change:  'Contract status change',
  contract_dispute:        'Contract dispute',
  contract_b_rating:       'B-rating received',
  reply_tracked_thread:    'Reply in tracked thread',
  pm_unread_increase:      'Unread PMs increased',
  autobump_daily:          'Daily autobump digest',
  token_expiring:          'Auth token expiring',
}

function AlertPreferencesSection() {
  const [prefs,    setPrefs]    = useState(null)
  const [saving,   setSaving]   = useState(null)

  useEffect(() => {
    api.get('/api/telegram/alert-preferences')
      .then(d => setPrefs(d?.preferences || {}))
      .catch(() => {})
  }, [])

  const toggle = async (type, val) => {
    setSaving(type)
    try {
      const d = await api.patch('/api/telegram/alert-preferences', { [type]: val })
      setPrefs(d?.preferences || {})
    } catch {}
    setSaving(null)
  }

  const types = Object.keys(ALERT_LABELS)

  return (
    <div className="card" style={{ marginBottom: 12 }}>
      <div className="card-head">
        <span className="card-icon">ALT</span>
        <span className="card-title">Alert Preferences</span>
        <span style={{ fontSize: 10, color: 'var(--sub)', fontFamily: 'var(--mono)', marginLeft: 'auto' }}>Telegram</span>
      </div>
      <div className="card-body">
        <div style={{ fontSize: 12, color: 'var(--sub)', marginBottom: 12, lineHeight: 1.6 }}>
          Control which events trigger Telegram alerts. All are enabled by default.
        </div>
        {prefs === null && <div className="spin" style={{ width: 14, height: 14, margin: '8px 0' }} />}
        {prefs !== null && types.map((type, i) => {
          const enabled = prefs[type] !== false
          return (
            <Row key={type} label={ALERT_LABELS[type]} last={i === types.length - 1}>
              <Toggle
                value={enabled}
                onChange={v => toggle(type, v)}
              />
              {saving === type && <div className="spin" style={{ width: 10, height: 10, marginLeft: 6 }} />}
            </Row>
          )
        })}
      </div>
    </div>
  )
}


// ── Section: Account ───────────────────────────────────────────────────────────

function AccountSection() {
  const user   = useStore(s => s.user)
  const logout = useStore(s => s.logout)
  const [phase, setPhase]           = useState('idle')
  const [deleteError, setDeleteError] = useState('')
  const [inventory, setInventory]   = useState(null)
  const [tokenInfo, setTokenInfo]   = useState(null)

  useEffect(() => {
    api.get('/api/crawl/status')
      .then(d => setTokenInfo({
        hasRefresh:  d.has_refresh_token,
        lastActive:  d.last_active,
        tokenExpiry: d.token_expiry || 0,
      }))
      .catch(() => {})
  }, [])

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
        <span className="card-icon">USR</span>
        <span className="card-title">Account</span>
      </div>
      <div className="card-body">
        {user && (
          <Row label="Logged in as" hint={`UID ${user.uid}`}>
            <span style={{ fontSize: 13, fontFamily: 'var(--mono)', color: 'var(--text)' }}>{user.username}</span>
          </Row>
        )}
        {tokenInfo && (() => {
          const exp   = tokenInfo.tokenExpiry
          const now   = Math.floor(Date.now() / 1000)
          const secs  = exp ? exp - now : null
          const expired  = secs !== null && secs <= 0
          const expLabel = !exp ? 'unknown'
            : expired    ? 'expired'
            : secs < 3600  ? `${Math.floor(secs / 60)}m`
            : secs < 86400 ? `${Math.floor(secs / 3600)}h`
            : `${Math.floor(secs / 86400)}d`
          const expColor = !exp ? 'var(--sub)'
            : expired       ? 'var(--red)'
            : secs < 86400  ? 'var(--red)'
            : secs < 604800 ? 'var(--yellow)'
            : 'var(--acc)'
          return (
            <>
              <Row
                label="Auth token"
                hint={tokenInfo.hasRefresh ? 'Refresh token stored — auto-renews on expiry' : 'No refresh token — manual re-auth required when expired'}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span style={{ fontSize: 12, fontFamily: 'var(--mono)', color: expColor }}>
                    {expired ? 'expired' : `expires ${expLabel}`}
                  </span>
                  <a
                    href="/auth/login"
                    style={{
                      fontSize: 11, padding: '3px 8px',
                      border: '1px solid var(--b3)', color: 'var(--sub)',
                      textDecoration: 'none', fontFamily: 'var(--mono)',
                      cursor: 'pointer', whiteSpace: 'nowrap',
                    }}
                  >
                    re-auth
                  </a>
                </div>
              </Row>
            </>
          )
        })()}
        <Row label="Log out" hint="End your current session">
          <button className="btn btn-ghost" onClick={logout}>Log out</button>
        </Row>
        <Row
          label="Delete account data"
          hint="Permanently removes all stored data: bytes history, contracts, bump jobs, drafts, settings. Your HF account is unaffected."
          last
        >
          {phase === 'idle' && (
            <button className="btn btn-danger" onClick={enterConfirm}>Delete</button>
          )}
          {phase === 'confirm' && (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 8 }}>
              {inventory && inventory.total_rows > 0 && (
                <span style={{ fontSize: 10, color: 'var(--sub)', fontFamily: 'var(--mono)' }}>
                  {inventory.total_rows.toLocaleString()} rows across {Object.keys(inventory.inventory).length} tables
                </span>
              )}
              <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                <span style={{ fontSize: 11, color: 'var(--red)', marginRight: 2 }}>Sure?</span>
                <button className="btn btn-danger" onClick={handleDelete}>Yes, delete</button>
                <button className="btn btn-ghost" onClick={() => setPhase('idle')}>Cancel</button>
              </div>
            </div>
          )}
          {phase === 'deleting' && (
            <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
              <div className="spin" style={{ width: 14, height: 14 }} />
              <span style={{ fontSize: 11, color: 'var(--sub)' }}>Deleting…</span>
            </div>
          )}
          {phase === 'done' && (
            <span style={{ fontSize: 11, color: 'var(--acc)' }}>Deleted — redirecting…</span>
          )}
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

// ── Root ───────────────────────────────────────────────────────────────────────

export default function Settings() {
  const { settings, saveSettings } = useStore()

  return (
    <>
      <div style={{ marginBottom: 20 }}>
        <div style={{ fontSize: 16, fontWeight: 700, letterSpacing: '-.02em', marginBottom: 4 }}>Settings</div>
        <div style={{ fontSize: 12, color: 'var(--sub)' }}>
          API protection, module visibility, crawler status, and account management.
        </div>
      </div>

      <ApiProtectionSection settings={settings} save={saveSettings} />
      <VisibilitySection />
      <CrawlerSection />
      <TelegramSection />
      <AlertPreferencesSection />
      <AccountSection />
    </>
  )
}
