import { useEffect, useState } from 'react'
import { api } from './api.js'

const fmt = n => {
  if (n === null || n === undefined || n === '') return '--'
  if (typeof n === 'string') return n
  return Number(n || 0).toLocaleString()
}

const ago = seconds => {
  if (seconds === null || seconds === undefined) return '--'
  const s = Number(seconds || 0)
  if (s < 60) return `${s}s ago`
  if (s < 3600) return `${Math.floor(s / 60)}m ago`
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`
  return `${Math.floor(s / 86400)}d ago`
}

const stamp = ts => {
  if (!ts) return '--'
  return new Date(ts * 1000).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function Metric({ label, value, tone = 'info' }) {
  return (
    <div className={`cp-metric ${tone}`}>
      <span className="cp-label">{label}</span>
      <strong>{fmt(value)}</strong>
    </div>
  )
}

function Pill({ value, tone = 'info' }) {
  return <span className={`cp-pill ${tone}`}>{value}</span>
}

function Section({ title, children }) {
  return (
    <section className="cp-section">
      <div className="cp-section-head">
        <h3>{title}</h3>
      </div>
      {children}
    </section>
  )
}

function Rows({ rows }) {
  return (
    <div className="cp-list compact">
      {rows.map(row => (
        <div className="cp-list-row" key={row.label}>
          <span>{row.label}</span>
          <strong>{row.value}</strong>
        </div>
      ))}
    </div>
  )
}

export default function OperatorPage() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let alive = true
    api.get('/api/operator/summary')
      .then(d => { if (alive) setData(d) })
      .catch(err => { if (alive) setError(err?.message || 'Operator summary could not be loaded') })
    const id = setInterval(() => {
      api.get('/api/operator/summary')
        .then(d => { if (alive) { setData(d); setError('') } })
        .catch(err => { if (alive) setError(err?.message || 'Operator summary could not be loaded') })
    }, 60000)
    return () => { alive = false; clearInterval(id) }
  }, [])

  if (error) {
    return (
      <div className="cp-page">
        <div className="card">
          <div className="card-head"><span className="card-title">Operator</span></div>
          <div className="card-body" style={{ color: 'var(--red)' }}>{error}</div>
        </div>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="empty" style={{ minHeight: 260 }}>
        <div className="spin" />
      </div>
    )
  }

  const users = data.users || {}
  const bump = data.bump_service || {}
  const market = data.marketplace || {}
  const alerts = data.alerts || {}
  const runtime = data.runtime || {}
  const run = market.last_run || {}
  const attention = data.attention || []

  return (
    <div className="cp-page">
      <div className="cp-header">
        <div>
          <div className="market-kicker">owner operations</div>
          <h2>Operator</h2>
          <p>Private aggregate health for Toolbox services. No user content, tokens, or message bodies are shown here.</p>
        </div>
        <div className="cp-static-tabs">
          <span>Read only</span>
          <span>UID {data.operator_uid}</span>
          <span>{stamp(data.generated_at)}</span>
        </div>
      </div>

      <div className="cp-status-strip">
        <div>
          <span>Environment</span>
          <strong>{data.environment || 'development'}</strong>
        </div>
        <div>
          <span>Background crawl</span>
          <strong>{runtime.background_crawl || '--'}</strong>
        </div>
        <div>
          <span>Telegram delivery</span>
          <strong>{runtime.telegram_delivery || '--'}</strong>
        </div>
        <div>
          <span>HF controller</span>
          <strong>{runtime.controller || '--'}</strong>
        </div>
      </div>

      <div className="cp-metrics">
        <Metric label="Authed users" value={users.total} />
        <Metric label="Active 24h" value={users.active_24h} tone={users.active_24h ? 'good' : 'info'} />
        <Metric label="Ready tokens" value={users.token_ready} tone="good" />
        <Metric label="Dead tokens" value={users.token_dead} tone={users.token_dead ? 'warn' : 'good'} />
        <Metric label="Active bump jobs" value={bump.jobs_active} tone={bump.jobs_active ? 'good' : 'info'} />
        <Metric label="Telegram failed 24h" value={alerts.telegram_failed_24h} tone={alerts.telegram_failed_24h ? 'bad' : 'good'} />
      </div>

      <div className="cp-grid cp-grid-two">
        <Section title="Attention">
          {attention.length ? (
            <div className="cp-table-wrap">
              <table className="cp-table">
                <tbody>
                  {attention.map(item => (
                    <tr key={item.label}>
                      <td>{item.label}</td>
                      <td><Pill value={item.level} tone={item.level === 'bad' ? 'bad' : 'info'} /></td>
                      <td>{fmt(item.value)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="cp-empty">No aggregate warnings right now.</div>
          )}
        </Section>

        <Section title="Users And Auth">
          <Rows rows={[
            { label: 'Total users', value: fmt(users.total) },
            { label: 'Active in 7 days', value: fmt(users.active_7d) },
            { label: 'Telegram linked', value: fmt(users.telegram_linked) },
            { label: 'Tokens expiring in 24h', value: fmt(users.token_expiring_24h) },
          ]} />
        </Section>
      </div>

      <div className="cp-grid">
        <Section title="Auto Bumper">
          <Rows rows={[
            { label: 'Total jobs', value: fmt(bump.jobs_total) },
            { label: 'Due now', value: fmt(bump.jobs_due) },
            { label: 'Expired jobs', value: fmt(bump.jobs_expired) },
            { label: 'Blocked by dead token', value: fmt(bump.blocked_dead_token) },
            { label: 'Bumps in 24h', value: fmt(bump.bumps_24h) },
            { label: 'Non-success in 24h', value: fmt(bump.non_success_24h) },
          ]} />
        </Section>

        <Section title="Marketplace">
          <Rows rows={[
            { label: 'Indexed threads', value: fmt(market.threads) },
            { label: 'Indexed contracts', value: fmt(market.contracts) },
            { label: 'Enabled watches', value: fmt(market.watches_enabled) },
            { label: 'Watch matches 24h', value: fmt(market.watch_matches_24h) },
            { label: 'Thread queue', value: fmt(market.refresh_queue) },
            { label: 'Contract queue', value: fmt(market.contract_queue) },
          ]} />
        </Section>

        <Section title="Freshness">
          <Rows rows={[
            { label: 'Last thread seen', value: ago(market.last_thread_seen_age) },
            { label: 'Last contract seen', value: ago(market.last_contract_seen_age) },
            { label: 'Last forum scan', value: ago(market.last_forum_scan_age) },
            { label: 'Last market run', value: stamp(run.started_at) },
            { label: 'Run status', value: run.status || '--' },
            { label: 'Remaining after run', value: fmt(run.remaining) },
          ]} />
        </Section>

        <Section title="Telegram Alerts">
          <Rows rows={[
            { label: 'Events in 24h', value: fmt(alerts.events_24h) },
            { label: 'Sent in 24h', value: fmt(alerts.telegram_sent_24h) },
            { label: 'Failed in 24h', value: fmt(alerts.telegram_failed_24h) },
            { label: 'Pending older than 1h', value: fmt(alerts.pending_older_1h) },
          ]} />
        </Section>

        <Section title="Last Market Run">
          <Rows rows={[
            { label: 'Source', value: run.source || '--' },
            { label: 'Calls used', value: fmt(run.calls_used) },
            { label: 'Threads seen', value: fmt(run.threads_seen) },
            { label: 'New threads', value: fmt(run.new_threads) },
            { label: 'Contracts seen', value: fmt(run.contracts_seen) },
            { label: 'Finished', value: stamp(run.finished_at) },
          ]} />
        </Section>
      </div>
    </div>
  )
}
