import { useState, useEffect, useCallback } from 'react'
import { api } from '../../core/api.js'

function formatCountdown(seconds) {
  if (seconds === null || seconds === undefined) return '--'
  if (seconds <= 0) return 'Due now'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}

function timeAgo(ts) {
  if (!ts) return 'Never'
  const diff = Math.floor(Date.now() / 1000) - ts
  if (diff < 60) return 'Just now'
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`
  return `${Math.floor(diff / 86400)}d ago`
}

const ACTION_COLORS = {
  bumped:  'var(--green)',
  skipped: 'var(--yellow)',
  error:   'var(--red)',
}

export default function AutoBumper() {
  const [jobs, setJobs]       = useState([])
  const [log, setLog]         = useState([])
  const [loading, setLoading] = useState(true)
  const [tab, setTab]         = useState('jobs')

  const loadJobs = useCallback(async () => {
    const d = await api.get('/modules/autobump/jobs')
    setJobs(d?.jobs || [])
  }, [])

  const loadLog = useCallback(async () => {
    const d = await api.get('/modules/autobump/log')
    setLog(d?.log || [])
  }, [])

  // Initial load
  useEffect(() => {
    Promise.all([loadJobs(), loadLog()]).finally(() => setLoading(false))
  }, [])

  // Reload every 60s
  useEffect(() => {
    const id = setInterval(() => { loadJobs(); loadLog() }, 60000)
    return () => clearInterval(id)
  }, [loadJobs, loadLog])

  if (loading) return <Spinner />

  return (
    <div className="up">
      <div className="ph">
        <div>
          <div className="pt">⬆️ Auto Bumper</div>
          <div className="ps">
            Smart bumping — skips if there is a recent post within your interval.
            10 byte service fee + ~50 byte Stanley fee per bump.
          </div>
        </div>
        <div className="row" style={{ gap: 8 }}>
          {['jobs', 'log'].map(t => (
            <button
              key={t}
              className={`btn btn-sm ${tab === t ? 'btn-primary' : 'btn-ghost'}`}
              onClick={() => setTab(t)}
            >
              {t === 'jobs' ? `Threads (${jobs.length})` : 'Log'}
            </button>
          ))}
        </div>
      </div>

      {tab === 'jobs' && (
        <div className="stack">
          <AddJobForm onAdded={loadJobs} />
          <JobList jobs={jobs} onUpdate={loadJobs} />
        </div>
      )}

      {tab === 'log' && <BumpLog log={log} />}
    </div>
  )
}

function AddJobForm({ onAdded }) {
  const [tid, setTid]         = useState('')
  const [interval, setInterval] = useState(6)
  const [loading, setLoading] = useState(false)
  const [status, setStatus]   = useState(null)

  const add = async () => {
    if (!tid) return
    setLoading(true); setStatus(null)
    try {
      await api.post('/modules/autobump/jobs', { tid, interval_h: Number(interval) })
      setStatus({ ok: true, msg: 'Thread added' })
      setTid('')
    } catch (e) {
      setStatus({ ok: false, msg: e.message })
    } finally { setLoading(false); onAdded() }
  }

  return (
    <div className="card">
      <div className="ct">Add Thread</div>
      <div className="row" style={{ gap: 10, flexWrap: 'wrap' }}>
        <input
          className="input"
          placeholder="Thread ID (TID)"
          value={tid}
          onChange={e => setTid(e.target.value)}
          onKeyDown={e => e.key === 'Enter' && add()}
          style={{ maxWidth: 180 }}
        />
        <select
          className="input"
          value={interval}
          onChange={e => setInterval(Number(e.target.value))}
          style={{ maxWidth: 160 }}
        >
          {[6,8,12,16,24].map(h => (
            <option key={h} value={h}>Every {h} hours</option>
          ))}
        </select>
        <button className="btn btn-primary btn-sm" onClick={add} disabled={loading || !tid}>
          {loading ? <Spinner inline /> : '+ Add'}
        </button>
        {status && (
          <span style={{ fontSize: 12, color: status.ok ? 'var(--green)' : 'var(--red)' }}>
            {status.msg}
          </span>
        )}
      </div>
      <div style={{ fontSize: 11, color: 'var(--text-dim)', marginTop: 10 }}>
        Min 6h interval. First bump fires after the first interval.
        10 byte HF Toolbox fee + ~50 byte Stanley fee charged per bump.
      </div>
    </div>
  )
}

function JobList({ jobs, onUpdate }) {
  if (!jobs.length) return (
    <div className="card">
      <div className="empty" style={{ padding: 32 }}>
        <span style={{ fontSize: 32, opacity: 0.4 }}>⬆️</span>
        <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>
          No threads added yet.
        </span>
      </div>
    </div>
  )

  return (
    <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
      {jobs.map((job, i) => (
        <JobRow
          key={job.id}
          job={job}
          last={i === jobs.length - 1}
          onUpdate={onUpdate}
        />
      ))}
    </div>
  )
}

function JobRow({ job, last, onUpdate }) {
  const [toggling, setToggling] = useState(false)
  const [removing, setRemoving] = useState(false)

  const toggle = async () => {
    setToggling(true)
    try {
      await api.patch(`/modules/autobump/jobs/${job.tid}`, { enabled: !job.enabled })
      onUpdate()
    } finally { setToggling(false) }
  }

  const remove = async () => {
    setRemoving(true)
    try {
      await api.delete(`/modules/autobump/jobs/${job.tid}`)
      onUpdate()
    } finally { setRemoving(false) }
  }

  const countdown = job.seconds_until_bump

  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 16,
      padding: '14px 20px',
      borderBottom: last ? 'none' : '1px solid var(--border)',
      opacity: job.enabled ? 1 : 0.5,
      transition: 'opacity var(--t)',
    }}>
      {/* Title + TID */}
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ fontWeight: 500, fontSize: 13, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          <a
            href={`https://hackforums.net/showthread.php?tid=${job.tid}`}
            target="_blank" rel="noreferrer"
            className="blue"
          >
            {job.thread_title}
          </a>
        </div>
        <div style={{ fontSize: 11, color: 'var(--dim)', marginTop: 2 }}>
          TID {job.tid} · Every {job.interval_h}h · {job.bump_count} bumps
        </div>
        {job.lastpost_ts && (
          <div style={{ fontSize: 11, color: 'var(--text)', marginTop: 2 }}>
            Last post {timeAgo(job.lastpost_ts)}{job.lastposter ? ` by ${job.lastposter}` : ''}
          </div>
        )}
      </div>

      {/* Countdown */}
      <div style={{ textAlign: 'center', minWidth: 80 }}>
        <div className="mono" style={{
          fontSize: 14, fontWeight: 700,
          color: countdown === 0 ? 'var(--green)' : 'var(--text)',
        }}>
          {formatCountdown(countdown)}
        </div>
        <div style={{ fontSize: 10, color: 'var(--text-dim)' }}>next bump</div>
      </div>

      {/* Last bumped */}
      <div style={{ textAlign: 'right', minWidth: 80 }}>
        <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          {timeAgo(job.last_bumped)}
        </div>
        <div style={{ fontSize: 10, color: 'var(--text-dim)' }}>last bump</div>
      </div>

      {/* Toggle */}
      <Toggle checked={job.enabled} onChange={toggle} disabled={toggling} />

      {/* Remove */}
      <button
        className="btn btn-danger btn-sm"
        onClick={remove}
        disabled={removing}
        style={{ flexShrink: 0 }}
      >
        {removing ? <Spinner inline /> : 'Remove'}
      </button>
    </div>
  )
}

function BumpLog({ log: entries }) {
  if (!entries.length) return (
    <div className="card">
      <div className="empty" style={{ padding: 32 }}>
        <span style={{ color: 'var(--text-muted)', fontSize: 13 }}>No bump activity yet.</span>
      </div>
    </div>
  )

  return (
    <div className="card" style={{ padding: 0, overflow: 'hidden' }}>
      <div className="tw">
        <table>
          <thead>
            <tr>
              <th>Thread</th>
              <th>Action</th>
              <th>When</th>
            </tr>
          </thead>
          <tbody>
            {entries.map(e => (
              <tr key={e.id}>
                <td>
                  <a
                    href={`https://hackforums.net/showthread.php?tid=${e.tid}`}
                    target="_blank" rel="noreferrer" className="blue"
                    style={{ fontSize: 12 }}
                  >
                    {e.thread_title || `TID ${e.tid}`}
                  </a>
                </td>
                <td>
                  <span style={{
                    fontSize: 11, fontWeight: 700, fontFamily: 'var(--font-mono)',
                    color: ACTION_COLORS[e.action] || 'var(--text-muted)',
                  }}>
                    {e.action.toUpperCase()}
                  </span>
                </td>
                <td style={{ fontSize: 12, color: 'var(--sub)' }}>
                  {timeAgo(e.ts)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

function Toggle({ checked, onChange, disabled }) {
  return (
    <button
      onClick={onChange}
      disabled={disabled}
      title={checked ? 'Enabled — click to disable' : 'Disabled — click to enable'}
      style={{
        width: 36, height: 20, borderRadius: 10,
        border: `1px solid ${checked ? 'rgba(77,142,240,.4)' : 'var(--border2)'}`,
        background: checked ? 'var(--blue)' : 'var(--hover)',
        position: 'relative', transition: 'background 150ms, border-color 150ms',
        cursor: disabled ? 'not-allowed' : 'pointer',
        opacity: disabled ? 0.5 : 1,
        flexShrink: 0,
      }}
    >
      <div style={{
        position: 'absolute', top: 2,
        left: checked ? 17 : 2,
        width: 14, height: 14,
        borderRadius: '50%',
        background: checked ? '#fff' : 'var(--sub)',
        transition: 'left 150ms, background 150ms',
        boxShadow: '0 1px 3px rgba(0,0,0,.3)',
      }} />
    </button>
  )
}

function Spinner({ inline }) {
  if (inline) return <span className="spin" style={{ width: 12, height: 12 }} />
  return <div className="empty"><div className="spin" /></div>
}
