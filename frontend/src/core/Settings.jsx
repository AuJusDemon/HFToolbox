import { useState, useEffect } from 'react'
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

// Uses the existing .tog / .tog.off CSS classes from index.css
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
        <span className="card-icon">🛡</span>
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

// ── Section: Dashboard Sections ────────────────────────────────────────────────

function VisibilitySection() {
  const { isEnabled, setEnabled } = useStore()
  const modules = [
    { id: 'bytes',     icon: '💰', label: 'Bytes',       hint: 'Balance, history, stats, send & vault' },
    { id: 'contracts', icon: '📜', label: 'Contracts',   hint: 'Contract list and analytics' },
    { id: 'autobump',  icon: '⬆',  label: 'Auto Bumper', hint: 'Thread bump scheduler' },
    { id: 'sigmarket', icon: '✍',  label: 'Sig Market',  hint: 'Your listing and active orders' },
  ]
  return (
    <div className="card" style={{ marginBottom: 12 }}>
      <div className="card-head">
        <span className="card-icon">👁</span>
        <span className="card-title">Dashboard Sections</span>
      </div>
      <div className="card-body">
        <div style={{ fontSize: 12, color: 'var(--sub)', marginBottom: 12, lineHeight: 1.6 }}>
          Toggle which sections appear on the dashboard. Disabled sections stop polling
          entirely — useful if you don't use a feature.
        </div>
        {modules.map((m, i) => (
          <Row
            key={m.id}
            label={<><span style={{ marginRight: 6 }}>{m.icon}</span>{m.label}</>}
            hint={m.hint}
            last={i === modules.length - 1}
          >
            <Toggle value={isEnabled(m.id)} onChange={v => setEnabled(m.id, v)} />
          </Row>
        ))}
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
        <span className="card-icon">🔄</span>
        <span className="card-title">Crawler Status</span>
        <span style={{ fontSize: 10, color: 'var(--sub)', fontFamily: 'var(--mono)', marginLeft: 'auto' }}>read-only</span>
      </div>
      <div className="card-body">
        <div style={{ fontSize: 12, color: 'var(--sub)', marginBottom: 12, lineHeight: 1.6 }}>
          Background crawlers build your local transaction and contract history over time.
          Full history is fetched once; after that only new entries are checked each cycle.
        </div>

        {loading && <div className="spin" style={{ width: 16, height: 16, margin: '8px 0' }} />}

        {!loading && status && (() => {
          const b = status.bytes
          const c = status.contracts
          const bDone = b.recv_done && b.sent_done
          return (
            <>
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

// ── Section: Account ───────────────────────────────────────────────────────────

function AccountSection() {
  const logout = useStore(s => s.logout)
  const [phase, setPhase] = useState('idle')

  const handleDelete = async () => {
    setPhase('deleting')
    try {
      await api.delete('/api/account')
      setPhase('done')
      setTimeout(() => { window.location.href = '/' }, 1500)
    } catch {
      setPhase('confirm')
    }
  }

  return (
    <div className="card" style={{ marginBottom: 12 }}>
      <div className="card-head">
        <span className="card-icon">👤</span>
        <span className="card-title">Account</span>
      </div>
      <div className="card-body">
        <Row label="Log out" hint="End your current session">
          <button className="btn btn-ghost" onClick={logout}>Log out</button>
        </Row>
        <Row
          label="Delete account data"
          hint="Permanently removes all stored data: bytes history, contracts, bump jobs, drafts, settings. Your HF account is unaffected."
          last
        >
          {phase === 'idle' && (
            <button className="btn btn-danger" onClick={() => setPhase('confirm')}>Delete</button>
          )}
          {phase === 'confirm' && (
            <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
              <span style={{ fontSize: 11, color: 'var(--red)', marginRight: 2 }}>Sure?</span>
              <button className="btn btn-danger" onClick={handleDelete}>Yes, delete</button>
              <button className="btn btn-ghost" onClick={() => setPhase('idle')}>Cancel</button>
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
          API protection, section visibility, crawler status, and account management.
        </div>
      </div>

      <ApiProtectionSection settings={settings} save={saveSettings} />
      <VisibilitySection />
      <CrawlerSection />
      <AccountSection />
    </>
  )
}
