import { useEffect, useMemo, useState } from 'react'
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

const toneForStatus = status => {
  if (status === 'bad') return 'bad'
  if (status === 'warn') return 'warn'
  if (status === 'good') return 'good'
  return 'info'
}

function Metric({ label, value, tone = 'info', note = '' }) {
  return (
    <div className={`cp-metric ${tone}`}>
      <span className="cp-label">{label}</span>
      <strong>{fmt(value)}</strong>
      {note ? <small>{note}</small> : null}
    </div>
  )
}

function Pill({ value, tone = 'info' }) {
  return <span className={`cp-pill ${tone}`}>{value}</span>
}

function Section({ title, meta = '', children }) {
  return (
    <section className="cp-section">
      <div className="cp-section-head">
        <h3>{title}</h3>
        {meta ? <span>{meta}</span> : null}
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

function StatusStrip({ items }) {
  return (
    <div className="cp-status-strip">
      {items.map(item => (
        <div key={item.label}>
          <span>{item.label}</span>
          <strong>{item.value}</strong>
        </div>
      ))}
    </div>
  )
}

function WorkerTable({ workers }) {
  if (!workers.length) return <div className="cp-empty">No worker rows were returned.</div>
  return (
    <div className="cp-table-wrap">
      <table className="cp-table wide">
        <thead>
          <tr>
            <th>Worker</th>
            <th>State</th>
            <th>Last Seen</th>
            <th>Backlog</th>
            <th>Note</th>
          </tr>
        </thead>
        <tbody>
          {workers.map(worker => (
            <tr key={worker.name}>
              <td>{worker.name}</td>
              <td><Pill value={worker.state || worker.status || 'unknown'} tone={toneForStatus(worker.status)} /></td>
              <td>{ago(worker.last_seen_age)}</td>
              <td>{fmt(worker.backlog)}</td>
              <td>{worker.note || '--'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

function FailureTable({ failures }) {
  if (!failures.length) return <div className="cp-empty">No grouped failures in the last 7 days.</div>
  return (
    <div className="cp-table-wrap">
      <table className="cp-table wide">
        <thead>
          <tr>
            <th>Area</th>
            <th>Failure</th>
            <th>Hits</th>
            <th>Last Seen</th>
          </tr>
        </thead>
        <tbody>
          {failures.map((failure, index) => (
            <tr key={`${failure.area}-${failure.message}-${index}`}>
              <td>{failure.area}</td>
              <td>{failure.message}</td>
              <td>{fmt(failure.count)}</td>
              <td>{stamp(failure.last_seen)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function OperatorPage() {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    let alive = true
    const load = () => {
      api.get('/api/operator/summary')
        .then(d => { if (alive) { setData(d); setError('') } })
        .catch(err => { if (alive) setError(err?.message || 'Operator summary could not be loaded') })
    }
    load()
    const id = setInterval(load, 60000)
    return () => { alive = false; clearInterval(id) }
  }, [])

  const now = Math.floor(Date.now() / 1000)

  const derived = useMemo(() => {
    const users = data?.users || {}
    const bump = data?.bump_service || {}
    const alerts = data?.alerts || {}
    const queues = data?.queues || {}
    const market = data?.marketplace || {}
    const failures = data?.recent_failures || []
    const attention = data?.attention || []
    const badWorkers = (data?.workers || []).filter(worker => worker.status === 'bad').length
    const warnWorkers = (data?.workers || []).filter(worker => worker.status === 'warn').length
    const queueBacklog = Number(queues.posting_due || 0)
      + Number(queues.reply_checks_due || 0)
      + Number(queues.market_thread_refresh_due || 0)
      + Number(queues.market_reply_verify_due || 0)
      + Number(queues.market_contract_lookup_due || 0)
      + Number(queues.telegram_pending_old || 0)
    return { users, bump, alerts, queues, market, failures, attention, badWorkers, warnWorkers, queueBacklog }
  }, [data])

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

  const users = derived.users
  const bump = derived.bump
  const market = derived.market
  const alerts = derived.alerts
  const queues = derived.queues
  const runtime = data.runtime || {}
  const freshness = data.freshness || {}
  const run = market.last_run || {}
  const attention = derived.attention
  const authedUsers = data.authed_users || []
  const operatorUser = data.operator_user || null

  return (
    <div className="cp-page">
      <div className="cp-header">
        <div>
          <div className="market-kicker">owner operations</div>
          <h2>Operator</h2>
          <p>Private read-only view of Toolbox health, queues, workers, auth state, and delivery failures. Raw tokens, customer messages, and secrets are not returned.</p>
        </div>
        <div className="cp-static-tabs">
          <span>Read only</span>
          <span>UID {data.operator_uid}</span>
          <span>Refresh 60s</span>
          <span>{stamp(data.generated_at)}</span>
        </div>
      </div>

      <StatusStrip items={[
        { label: 'Environment', value: data.environment || 'development' },
        { label: 'Data Source', value: runtime.database || '--' },
        { label: 'Background Crawl', value: runtime.background_crawl || '--' },
        { label: 'HF Controller', value: runtime.controller || '--' },
      ]} />
      <StatusStrip items={[
        { label: 'Telegram Delivery', value: runtime.telegram_delivery || '--' },
        { label: 'Summary Type', value: 'dev database snapshot' },
        { label: 'Records Shown', value: `${fmt(authedUsers.length)} latest real users` },
        { label: 'Dev Test Rows Hidden', value: fmt(users.synthetic_hidden) },
      ]} />

      {operatorUser && operatorUser.uid ? (
        <StatusStrip items={[
          { label: 'Current Operator Row', value: operatorUser.username || 'unknown' },
          { label: 'Operator Last Seen', value: stamp(operatorUser.last_seen) },
          { label: 'Stored HF Token', value: Number(operatorUser.has_token || 0) ? 'present' : 'blank' },
          { label: 'Token State', value: Number(operatorUser.token_dead || 0) ? 'dead' : 'not marked dead' },
        ]} />
      ) : null}

      <div className="cp-metrics">
        <Metric label="Attention Items" value={attention.length} tone={attention.length ? 'warn' : 'good'} />
        <Metric label="Bad Workers" value={derived.badWorkers} tone={derived.badWorkers ? 'bad' : 'good'} />
        <Metric label="Warn Workers" value={derived.warnWorkers} tone={derived.warnWorkers ? 'warn' : 'good'} />
        <Metric label="Queue Backlog" value={derived.queueBacklog} tone={derived.queueBacklog ? 'warn' : 'good'} note="due or old" />
        <Metric label="Authed Users" value={users.total} />
        <Metric label="Active 24h" value={users.active_24h} tone={users.active_24h ? 'good' : 'info'} />
      </div>

      <div className="cp-grid cp-grid-two">
        <Section title="Attention" meta={`${attention.length} items`}>
          {attention.length ? (
            <div className="cp-table-wrap">
              <table className="cp-table">
                <tbody>
                  {attention.map(item => (
                    <tr key={`${item.label}-${item.value}`}>
                      <td>{item.label}</td>
                      <td><Pill value={item.level} tone={toneForStatus(item.level)} /></td>
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

        <Section title="Identity And Auth">
          <Rows rows={[
            { label: 'Real users', value: fmt(users.total) },
            { label: 'Active in 7 days', value: fmt(users.active_7d) },
            { label: 'Ready tokens', value: fmt(users.token_ready) },
            { label: 'Dead tokens', value: fmt(users.token_dead) },
            { label: 'Tokens expiring in 24h', value: fmt(users.token_expiring_24h) },
            { label: 'Telegram linked rows', value: fmt(users.telegram_linked) },
          ]} />
        </Section>
      </div>

      <Section title="Workers" meta="read-only">
        <WorkerTable workers={data.workers || []} />
      </Section>

      <div className="cp-grid">
        <Section title="Queues">
          <Rows rows={[
            { label: 'Scheduled posts pending', value: fmt(queues.posting_pending) },
            { label: 'Scheduled posts due', value: fmt(queues.posting_due) },
            { label: 'Scheduled posts failed', value: fmt(queues.posting_failed) },
            { label: 'Reply checks due', value: fmt(queues.reply_checks_due) },
            { label: 'Reply checks stuck', value: fmt(queues.reply_checks_stuck) },
            { label: 'Unread replies', value: fmt(queues.reply_unread) },
          ]} />
        </Section>

        <Section title="Marketplace Queues">
          <Rows rows={[
            { label: 'Thread refresh queued', value: fmt(queues.market_thread_refresh) },
            { label: 'Thread refresh due', value: fmt(queues.market_thread_refresh_due) },
            { label: 'Reply verify queued', value: fmt(queues.market_reply_verify) },
            { label: 'Reply verify due', value: fmt(queues.market_reply_verify_due) },
            { label: 'Contract lookup queued', value: fmt(queues.market_contract_lookup) },
            { label: 'Contract lookup due', value: fmt(queues.market_contract_lookup_due) },
          ]} />
        </Section>

        <Section title="Bump Service">
          <Rows rows={[
            { label: 'Total jobs', value: fmt(bump.jobs_total) },
            { label: 'Active jobs', value: fmt(bump.jobs_active) },
            { label: 'Due now', value: fmt(bump.jobs_due) },
            { label: 'Expired jobs', value: fmt(bump.jobs_expired) },
            { label: 'Blocked by dead token', value: fmt(bump.blocked_dead_token) },
            { label: 'Last success', value: ago(freshness.last_bump_success_age) },
          ]} />
        </Section>

        <Section title="Marketplace Index">
          <Rows rows={[
            { label: 'Indexed threads', value: fmt(market.threads) },
            { label: 'Indexed contracts', value: fmt(market.contracts) },
            { label: 'Enabled watches', value: fmt(market.watches_enabled) },
            { label: 'Watch matches 24h', value: fmt(market.watch_matches_24h) },
            { label: 'Last thread seen', value: ago(market.last_thread_seen_age) },
            { label: 'Last contract seen', value: ago(market.last_contract_seen_age) },
          ]} />
        </Section>

        <Section title="Telegram Alerts">
          <Rows rows={[
            { label: 'Events in 24h', value: fmt(alerts.events_24h) },
            { label: 'Sent in 24h', value: fmt(alerts.telegram_sent_24h) },
            { label: 'Failed in 24h', value: fmt(alerts.telegram_failed_24h) },
            { label: 'Pending total', value: fmt(queues.telegram_pending) },
            { label: 'Pending older than 1h', value: fmt(alerts.pending_older_1h) },
            { label: 'Last sent', value: ago(freshness.last_alert_sent_age) },
          ]} />
        </Section>
      </div>

      <div className="cp-grid cp-grid-two">
        <Section title="Freshness">
          <Rows rows={[
            { label: 'Forum scan', value: ago(market.last_forum_scan_age) },
            { label: 'Bytes crawl', value: ago(freshness.bytes_crawl_age) },
            { label: 'Contracts crawl', value: ago(freshness.contracts_crawl_age) },
            { label: 'Contracts recheck', value: ago(freshness.contracts_recheck_age) },
            { label: 'Scheduled post sent', value: ago(freshness.last_post_sent_age) },
            { label: 'Reply seen', value: ago(freshness.last_reply_seen_age) },
          ]} />
        </Section>

        <Section title="Last Market Run">
          <Rows rows={[
            { label: 'Started', value: stamp(run.started_at) },
            { label: 'Finished', value: stamp(run.finished_at) },
            { label: 'Source', value: run.source || '--' },
            { label: 'Status', value: run.status || '--' },
            { label: 'Calls used', value: fmt(run.calls_used) },
            { label: 'Remaining after run', value: fmt(run.remaining) },
          ]} />
        </Section>
      </div>

      <Section title="Recent Failures" meta="grouped, last 7 days">
        <FailureTable failures={derived.failures} />
      </Section>

      <Section title="Authed Users" meta={`${fmt(authedUsers.length)} shown`}>
        {data.authed_users_error ? (
          <div className="cp-empty" style={{ color: 'var(--red)' }}>{data.authed_users_error}</div>
        ) : authedUsers.length ? (
          <div className="cp-table-wrap">
            <table className="cp-table wide op-users-table">
              <thead>
                <tr>
                  <th>User</th>
                  <th>UID</th>
                  <th>Last Seen</th>
                  <th>Token</th>
                  <th>Token Expiry</th>
                  <th>Telegram</th>
                  <th>Bumps</th>
                  <th>Posts</th>
                  <th>Replies</th>
                  <th>Watches</th>
                  <th>Alerts 7d</th>
                </tr>
              </thead>
              <tbody>
                {authedUsers.map(user => {
                  const tokenDead = Number(user.token_dead || 0) === 1
                  const hasToken = Number(user.has_token || 0) === 1
                  const tokenExpiry = Number(user.token_expiry || 0)
                  const expiringSoon = tokenExpiry > 0 && tokenExpiry < now + 86400
                  const tokenLabel = tokenDead ? 'dead' : (hasToken ? 'ready' : 'blank')
                  const tokenTone = tokenDead ? 'bad' : (hasToken ? 'good' : 'warn')
                  return (
                    <tr key={user.uid}>
                      <td>{user.username || 'unknown'}</td>
                      <td>{user.uid}</td>
                      <td>{stamp(user.last_seen)}</td>
                      <td><Pill value={tokenLabel} tone={tokenTone} /></td>
                      <td>{tokenExpiry ? <span style={{ color: expiringSoon ? 'var(--yellow)' : 'inherit' }}>{stamp(tokenExpiry)}</span> : '--'}</td>
                      <td>{Number(user.telegram_linked || 0) ? 'linked' : '--'}</td>
                      <td>{fmt(user.bump_jobs)}</td>
                      <td>{fmt(user.scheduled_posts)}</td>
                      <td>{fmt(user.open_replies)}</td>
                      <td>{fmt(user.market_watches)}</td>
                      <td>{fmt(user.alerts_7d)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="cp-empty">No authed users found in this environment.</div>
        )}
      </Section>
    </div>
  )
}
