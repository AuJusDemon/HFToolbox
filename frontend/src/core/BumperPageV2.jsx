import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { api } from './api.js'
import { parseHfId } from './utils.js'
import useStore from '../store.js'
import './BumperPageV2.css'
import { BumpActivityTimeline, BumpAttempts, BumpPerformanceSummary, BumpRangeControl, JobScheduleEditor } from './BumpPerformance.jsx'

const ACCESS_GROUPS = new Set(['9', '28', '67'])
const INTERVALS = [[6, '6 hours'], [8, '8 hours'], [12, '12 hours'], [16, '16 hours'], [24, '1 day'], [48, '2 days'], [72, '3 days'], [120, '5 days'], [168, '1 week']]
const EXPIRIES = [[0, 'No end date'], [7, '1 week'], [14, '2 weeks'], [30, '1 month'], [60, '2 months']]

export const isUpgraded = groups => (groups || []).some(group => ACCESS_GROUPS.has(String(group)))
const number = value => Number(value || 0).toLocaleString()
const date = value => value ? new Date(value * 1000).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) : 'No end date'
const time = value => value ? new Date(value * 1000).toLocaleString(undefined, { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }) : '--'
const ago = value => {
  if (!value) return '--'
  const seconds = Math.max(0, Math.floor(Date.now() / 1000) - Number(value))
  if (seconds < 60) return `${seconds}s ago`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`
  return `${Math.floor(seconds / 86400)}d ago`
}
const countdown = seconds => {
  if (seconds == null) return '--'
  if (seconds <= 0) return 'Due now'
  const days = Math.floor(seconds / 86400)
  const hours = Math.floor((seconds % 86400) / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  return days ? `${days}d ${hours}h` : hours ? `${hours}h ${minutes}m` : `${minutes}m`
}

const latestForJob = (job, log) => (log || []).find(entry => String(entry.tid) === String(job.tid)) || (job.latest_action ? { action:job.latest_action, reason:job.latest_reason, ts:job.latest_result_at, tid:job.tid } : null)

export function classifyJob(job, log = [], budgetExceeded = false) {
  if (job.expired) return { key: 'expired', label: 'Expired', rank: 5 }
  if (!job.enabled) return { key: 'paused', label: 'Paused', rank: 4 }
  const latest = latestForJob(job, log)
  const latestIsCurrent = latest && Number(latest.ts || 0) >= Number(job.last_bumped || 0)
  if (budgetExceeded) return { key: 'blocked', label: 'Budget blocked', rank: 1 }
  if (latestIsCurrent && latest.action === 'error') return { key: 'failed', label: 'Needs attention', rank: 0 }
  if (Number(job.seconds_until_bump) <= 0) {
    return job.mode === 'page1'
      ? { key: 'checking', label: 'Checking', rank: 2 }
      : { key: 'due', label: 'Due now', rank: 2 }
  }
  if (latestIsCurrent && latest.action === 'skipped') return { key: 'skipped', label: 'Rescheduled', rank: 3 }
  return { key: 'scheduled', label: 'Scheduled', rank: 3 }
}

export function orderJobs(jobs = [], log = [], budgetExceeded = false) {
  return [...jobs].sort((a, b) => {
    const stateDiff = classifyJob(a, log, budgetExceeded).rank - classifyJob(b, log, budgetExceeded).rank
    if (stateDiff) return stateDiff
    return Number(a.next_bump || Number.MAX_SAFE_INTEGER) - Number(b.next_bump || Number.MAX_SAFE_INTEGER)
  })
}

export function budgetState(settings) {
  const limit = Number(settings?.weekly_budget || 0)
  const spent = Number(settings?.bytes_this_week || 0)
  const cost = Number(settings?.total_cost || 0)
  const remaining = limit ? Math.max(0, limit - spent) : null
  return {
    limit, spent, cost, remaining,
    unlimited: limit === 0,
    exceeded: limit > 0 && remaining < cost,
    percent: limit ? Math.min(100, Math.round((spent / limit) * 100)) : 0,
    remainingBumps: limit && cost ? Math.floor(remaining / cost) : null,
  }
}

function Status({ state }) {
  return <span className={`bp-status bp-status-${state.key}`}>{state.label}</span>
}

function Metric({ label, value, detail }) {
  return <div className="bp-metric"><span>{label}</span><strong>{value}</strong>{detail && <small>{detail}</small>}</div>
}

function ErrorLine({ children }) {
  return children ? <div className="bp-error" role="alert">{children}</div> : null
}

function BudgetPane({ data, error, onReload }) {
  const state = budgetState(data)
  const [value, setValue] = useState('0')
  const [message, setMessage] = useState('')
  const [saving, setSaving] = useState(false)
  useEffect(() => setValue(String(data?.weekly_budget || 0)), [data?.weekly_budget])

  const save = async () => {
    setSaving(true); setMessage('')
    try {
      await api.put('/api/autobump/settings', { weekly_budget: Math.max(0, Number(value) || 0) })
      await onReload()
      setMessage('Weekly limit saved.')
    } catch (err) { setMessage(err.message || 'Could not save weekly limit.') }
    finally { setSaving(false) }
  }

  return <section className="bp-pane bp-budget" aria-labelledby="budget-title">
    <div className="bp-pane-head">
      <div><span className="bp-kicker">SPENDING CEILING</span><h2 id="budget-title">Weekly Budget</h2></div>
      <span className={state.exceeded ? 'bp-value-danger' : 'bp-value'}>{state.unlimited ? 'Unlimited' : `${number(state.remaining)} Bytes left`}</span>
    </div>
    {error ? <ErrorLine>Budget data unavailable. <button onClick={onReload}>Retry</button></ErrorLine> : <>
      <div className="bp-budget-grid">
        <div><span>Spent this week</span><strong>{number(state.spent)} Bytes</strong></div>
        <div><span>Weekly limit</span><strong>{state.unlimited ? 'No limit' : `${number(state.limit)} Bytes`}</strong></div>
        <div><span>Cost per success</span><strong>{number(state.cost)} Bytes</strong></div>
        <div><span>Estimated remaining</span><strong>{state.unlimited ? 'Unlimited' : `${number(state.remainingBumps)} bumps`}</strong></div>
      </div>
      <div className="bp-meter" aria-label={`${state.percent}% of weekly budget used`}><i style={{ width: `${state.percent}%` }} /></div>
      {state.exceeded && <div className="bp-warning">The next successful bump would exceed this limit. Enabled jobs will wait.</div>}
      <div className="bp-budget-control">
        <label htmlFor="weekly-budget">Weekly limit in Bytes <small>0 means unlimited</small></label>
        <div><input id="weekly-budget" type="number" min="0" step="10" value={value} onChange={event => setValue(event.target.value)} /><button onClick={save} disabled={saving}>{saving ? 'Saving...' : 'Save limit'}</button></div>
        {message && <span role="status">{message}</span>}
      </div>
    </>}
  </section>
}

function AddJob({ fee, onAdded }) {
  const [tid, setTid] = useState('')
  const [mode, setMode] = useState('timer')
  const [interval, setIntervalValue] = useState(24)
  const [expiry, setExpiry] = useState(0)
  const [confirming, setConfirming] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const submit = async () => {
    if (!confirming) { setConfirming(true); return }
    setBusy(true); setError('')
    try {
      const bumpUntil = expiry ? Math.floor(Date.now() / 1000) + expiry * 86400 : null
      await api.post('/api/autobump/jobs', { tid, mode, interval_h: Number(interval), bump_until: bumpUntil })
      setTid(''); setConfirming(false); await onAdded()
    } catch (err) { setError(err.message || 'Could not add job.') }
    finally { setBusy(false) }
  }
  return <section className="bp-pane bp-add" aria-labelledby="add-job-title">
    <div className="bp-pane-head"><div><span className="bp-kicker">SCHEDULER INPUT</span><h2 id="add-job-title">Add Job</h2></div></div>
    <div className="bp-add-grid">
      <label>Thread ID or URL<input value={tid} onChange={event => { setTid(parseHfId(event.target.value, 'tid')); setConfirming(false) }} placeholder="6319077" /></label>
      <label>Mode<select value={mode} onChange={event => setMode(event.target.value)}><option value="timer">Timer</option><option value="page1">Page 1 watch</option></select></label>
      <label>{mode === 'page1' ? 'Maximum interval' : 'Interval'}<select value={interval} onChange={event => setIntervalValue(event.target.value)}>{INTERVALS.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
      <label>End<select value={expiry} onChange={event => setExpiry(Number(event.target.value))}>{EXPIRIES.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></label>
      <button className="bp-primary" disabled={!tid || busy} onClick={submit}>{busy ? 'Adding...' : confirming ? 'Confirm and add' : 'Add job'}</button>
    </div>
    {confirming && <div className="bp-confirm" role="status">A successful bump is expected to cost {number(fee?.hf_fee)} HF fee + {number(fee?.service_fee)} service fee = {number(fee?.total_cost)} Bytes. <button onClick={() => setConfirming(false)}>Cancel</button></div>}
    <ErrorLine>{error}</ErrorLine>
  </section>
}

function Periods({ periods = [] }) {
  const [open, setOpen] = useState(null)
  if (!periods.length) return <p className="bp-empty-line">No successful bump periods recorded yet.</p>
  return <div className="bp-periods">
    {periods.slice(0, 8).map(period => <div className="bp-period" key={period.ts}>
      <button onClick={() => setOpen(open === period.ts ? null : period.ts)} aria-expanded={open === period.ts}>
        <span>{period.is_current ? 'Current period' : time(period.ts)}</span>
        <span>{period.reply_gain == null ? 'Replies --' : `Replies ${period.reply_gain >= 0 ? '+' : ''}${period.reply_gain}`}</span>
        <span>{period.contracts?.length || 0} contracts</span>
        <span>{open === period.ts ? 'Close' : 'Details'}</span>
      </button>
      {open === period.ts && <div className="bp-period-detail">{period.contracts?.length ? period.contracts.map(contract => <span key={contract.cid}>CID {contract.cid} / status {contract.status_n}</span>) : <span>No contracts entered during this period.</span>}</div>}
    </div>)}
  </div>
}

function ActiveJob({ job, state, performance, statsLoading, statsError, fee, busyTid, onToggle, onRemove, range, onRange, onPage, onSaved }) {
  const [confirmRemove, setConfirmRemove] = useState(false)
  const [editing, setEditing] = useState(false)
  const [editError, setEditError] = useState('')
  const [saving, setSaving] = useState(false)
  useEffect(() => setConfirmRemove(false), [job?.tid])
  useEffect(() => { setEditing(false); setEditError('') }, [job?.tid])
  if (!job) return <section className="bp-pane bp-empty"><h2>No bump jobs yet</h2><p>Add a thread above to start tracking its scheduler state here.</p></section>
  const cost = performance?.fees || fee
  const saveSchedule = async draft => {
    setSaving(true); setEditError('')
    try {
      await api.put(`/api/autobump/jobs/${job.tid}/schedule`, draft)
      setEditing(false)
      await onSaved()
    } catch (err) { setEditError(err.message || 'Could not save schedule.') }
    finally { setSaving(false) }
  }
  return <section className="bp-pane bp-workspace" aria-labelledby="active-job-title">
    <div className="bp-job-head">
      <div><span className="bp-kicker">ACTIVE WORKSPACE</span><h2 id="active-job-title">{job.thread_title || `Thread ${job.tid}`}</h2><p>TID {job.tid} {job.fid ? `/ FID ${job.fid}` : ''} / {job.mode === 'page1' ? 'Page 1 watch' : 'Timer mode'}</p></div>
      <Status state={state} />
    </div>
    <div className="bp-work-grid">
      <div className="bp-schedule">
        <span className="bp-kicker">NEXT ATTEMPT</span><strong className="bp-countdown">{job.enabled && !job.expired ? countdown(job.seconds_until_bump) : state.label}</strong><span>{job.next_bump ? time(job.next_bump) : 'No attempt scheduled'}</span>
        <dl><div><dt>Last successful bump</dt><dd>{ago(job.last_bumped)}</dd></div><div><dt>Last post</dt><dd>{ago(job.lastpost_ts)}{job.lastposter ? ` by ${job.lastposter}` : ''}</dd></div><div><dt>Interval</dt><dd>{job.interval_h} hours</dd></div><div><dt>End date</dt><dd>{date(job.bump_until)}</dd></div></dl>
      </div>
      <div className="bp-cost">
        <span className="bp-kicker">SUCCESSFUL BUMP COST</span>
        <dl><div><dt>HF group fee</dt><dd>{number(cost?.hf_fee)} Bytes</dd></div><div><dt>Toolbox service fee</dt><dd>{number(cost?.service_fee)} Bytes</dd></div><div className="bp-total"><dt>Total expected cost</dt><dd>{number(cost?.total_cost)} Bytes</dd></div></dl>
        <small>HF and service fees apply only after a confirmed successful bump.</small>
      </div>
    </div>
    <div className="bp-performance-head"><div><span className="bp-kicker">THREAD PERFORMANCE</span><p>Operational totals and measured business movement for this job.</p></div><BumpRangeControl value={range} onChange={onRange} /></div>
    {statsLoading ? <div className="bp-stat-loading" role="status">Loading statistics for TID {job.tid}...</div> : statsError ? <ErrorLine>Statistics could not be loaded. Scheduler controls remain available.</ErrorLine> : <><BumpPerformanceSummary data={performance} /><BumpActivityTimeline data={performance} onPage={onPage} /><BumpAttempts attempts={performance?.attempts} fees={performance?.fees} /></>}
    {editing && <JobScheduleEditor job={job} onSave={saveSchedule} onCancel={() => setEditing(false)} saving={saving} error={editError} />}
    <div className="bp-actions">
      <button onClick={() => setEditing(value => !value)}>{editing ? 'Close editor' : 'Edit schedule'}</button>
      <button onClick={() => onToggle(job)} disabled={busyTid === job.tid}>{job.enabled ? 'Pause job' : 'Resume job'}</button>
      <a href={`https://hackforums.net/showthread.php?tid=${job.tid}`} target="_blank" rel="noreferrer">Inspect HF thread</a>
      <Link to={`/dashboard/merchant?tab=bumps&tid=${job.tid}`}>View business analysis</Link>
      {!confirmRemove ? <button className="bp-danger" onClick={() => setConfirmRemove(true)}>Remove job</button> : <div className="bp-remove-confirm"><span>Remove this job?</span><button className="bp-danger" onClick={() => onRemove(job)}>Confirm remove</button><button onClick={() => setConfirmRemove(false)}>Cancel</button></div>}
    </div>
  </section>
}

function JobNavigator({ jobs, log, budgetExceeded, selectedTid, onSelect }) {
  if (!jobs.length) return null
  return <aside className="bp-pane bp-job-nav" aria-label="Bump jobs">
    <div className="bp-pane-head"><div><span className="bp-kicker">THREAD QUEUE</span><h2>Jobs</h2></div><strong>{jobs.length}</strong></div>
    <label className="bp-mobile-job-picker">Selected thread
      <select value={selectedTid || ''} onChange={event => onSelect(event.target.value)}>
        {jobs.map(job => <option key={job.id} value={job.tid}>{job.thread_title || `Thread ${job.tid}`}</option>)}
      </select>
    </label>
    <div className="bp-job-list">
      {jobs.map(job => {
        const state = classifyJob(job, log, budgetExceeded)
        const latest = latestForJob(job, log)
        return <button className={String(job.tid) === String(selectedTid) ? 'is-selected' : ''} key={job.id} onClick={() => onSelect(String(job.tid))}>
          <span className="bp-job-row-head"><strong>{job.thread_title || `Thread ${job.tid}`}</strong><Status state={state} /></span>
          <span className="bp-job-row-meta"><small>TID {job.tid} / {job.mode === 'page1' ? 'Page 1' : `${job.interval_h}h timer`}</small><b>{job.enabled && !job.expired ? countdown(job.seconds_until_bump) : state.label}</b></span>
          <span className="bp-job-row-result">{latest ? `Last: ${latest.action}${latest.reason ? ` / ${latest.reason}` : ''}` : 'No attempts recorded'}</span>
        </button>
      })}
    </div>
  </aside>
}

function Attempts({ log, error, fee }) {
  return <section className="bp-pane" aria-labelledby="attempts-title"><div className="bp-pane-head"><div><span className="bp-kicker">AUDIT TRAIL</span><h2 id="attempts-title">Recent Attempts</h2></div></div>
    {error ? <ErrorLine>Attempt history is unavailable.</ErrorLine> : !log.length ? <p className="bp-empty-line">No scheduler attempts recorded yet.</p> : <div className="bp-attempts"><div className="bp-attempt-head"><span>Time</span><span>Thread</span><span>Result</span><span>Reason</span><span>Estimated HF fee</span><span>Service fee</span></div>{log.map(entry => <div className="bp-attempt" key={entry.id}><span data-label="Time">{time(entry.ts)}</span><span data-label="Thread">{entry.thread_title || `TID ${entry.tid}`}</span><span data-label="Result"><Status state={{ key: entry.action === 'bumped' ? 'scheduled' : entry.action === 'error' ? 'failed' : 'skipped', label: entry.action }} /></span><span data-label="Reason">{entry.reason || '--'}</span><span data-label="Estimated HF fee">{entry.action === 'bumped' ? `${number(fee?.hf_fee)} Bytes estimated` : '--'}</span><span data-label="Service fee">{entry.action === 'bumped' ? `${number(fee?.service_fee)} Bytes expected` : '--'}</span></div>)}</div>}
  </section>
}

export default function BumperPageV2() {
  const [searchParams, setSearchParams] = useSearchParams()
  const user = useStore(state => state.user)
  const appSettings = useStore(state => state.settings)
  const apiPaused = useStore(state => state.apiPaused)
  const [jobs, setJobs] = useState([])
  const [logs, setLogs] = useState([])
  const [fee, setFee] = useState(null)
  const [errors, setErrors] = useState({})
  const [loading, setLoading] = useState(true)
  const [selectedTid, setSelectedTid] = useState(null)
  const [stats, setStats] = useState(null)
  const [statsLoading, setStatsLoading] = useState(false)
  const [statsError, setStatsError] = useState('')
  const [range, setRange] = useState('30d')
  const [page, setPage] = useState(1)
  const [busyTid, setBusyTid] = useState(null)
  const pollRef = useRef(null)

  const load = useCallback(async () => {
    const [jobResult, logResult, feeResult] = await Promise.allSettled([api.get('/api/autobump/jobs'), api.get('/api/autobump/log'), api.get('/api/autobump/settings')])
    const nextErrors = {}
    if (jobResult.status === 'fulfilled') setJobs(jobResult.value?.jobs || []); else nextErrors.jobs = jobResult.reason?.message || 'Jobs unavailable'
    if (logResult.status === 'fulfilled') setLogs(logResult.value?.log || []); else nextErrors.logs = logResult.reason?.message || 'Attempts unavailable'
    if (feeResult.status === 'fulfilled') setFee(feeResult.value); else nextErrors.fee = feeResult.reason?.message || 'Budget unavailable'
    setErrors(nextErrors); setLoading(false)
  }, [])

  useEffect(() => { load() }, [load])
  useEffect(() => {
    if (apiPaused) return undefined
    pollRef.current = setInterval(load, Math.max(15000, Number(appSettings?.bumperInterval || 30) * 1000))
    return () => clearInterval(pollRef.current)
  }, [apiPaused, appSettings?.bumperInterval, load])

  const budget = budgetState(fee)
  const ordered = useMemo(() => orderJobs(jobs, logs, budget.exceeded), [jobs, logs, budget.exceeded])
  useEffect(() => {
    if (!ordered.length) setSelectedTid(null)
    else {
      const requested = searchParams.get('tid')
      const next = ordered.some(job => String(job.tid) === String(requested)) ? String(requested) : String(ordered[0].tid)
      if (String(selectedTid) !== next) setSelectedTid(next)
      if (requested !== next) setSearchParams(current => { const params = new URLSearchParams(current); params.set('tid', next); return params }, { replace:true })
    }
  }, [ordered, searchParams, selectedTid, setSearchParams])
  const selectTid = tid => {
    setSelectedTid(String(tid)); setPage(1)
    setSearchParams(current => { const params = new URLSearchParams(current); params.set('tid', String(tid)); return params })
  }
  const selected = ordered.find(job => String(job.tid) === String(selectedTid)) || ordered[0]
  const selectedState = selected ? classifyJob(selected, logs, budget.exceeded) : null

  useEffect(() => {
    if (!selected?.tid) { setStats(null); setStatsLoading(false); return }
    let alive = true; setStats(null); setStatsError(''); setStatsLoading(true)
    api.get(`/api/autobump/jobs/${selected.tid}/performance?range=${range}&page=${page}&page_size=5`)
      .then(data => { if (alive) setStats(data) })
      .catch(err => { if (alive) { setStats(null); setStatsError(err.message) } })
      .finally(() => { if (alive) setStatsLoading(false) })
    return () => { alive = false }
  }, [selected?.tid, range, page, jobs])

  const toggle = async job => {
    const enabled = !job.enabled
    setBusyTid(job.tid); setJobs(current => current.map(item => item.tid === job.tid ? { ...item, enabled } : item))
    try { await api.patch(`/api/autobump/jobs/${job.tid}`, { enabled }) }
    catch (err) { setJobs(current => current.map(item => item.tid === job.tid ? { ...item, enabled: job.enabled } : item)); setErrors(current => ({ ...current, action: err.message })) }
    finally { setBusyTid(null) }
  }
  const remove = async job => {
    setBusyTid(job.tid)
    try { await api.delete(`/api/autobump/jobs/${job.tid}`); await load() }
    catch (err) { setErrors(current => ({ ...current, action: err.message })) }
    finally { setBusyTid(null) }
  }

  if (!isUpgraded(user?.groups)) return <div className="bp-page"><section className="bp-pane bp-denied"><span className="bp-kicker">ACCESS REQUIRED</span><h1>Bump Service</h1><p>This program requires an eligible HF account group.</p><a href="https://hackforums.net/upgrade.php" target="_blank" rel="noreferrer">Review HF upgrades</a></section></div>

  return <main className="bp-page">
    <header className="bp-title"><div><span className="bp-kicker">AUTOMATED THREAD SCHEDULER</span><h1>Bump Service</h1><p>Track timing, costs, results, and contract movement without leaving the scheduler.</p></div><span className={`bp-scheduler-state ${errors.jobs ? 'is-error' : ''}`}>{loading ? 'LOADING' : errors.jobs ? 'DEGRADED' : apiPaused ? 'POLLING PAUSED' : 'SCHEDULER READY'}</span></header>
    <div className="bp-status-strip"><Metric label="Active jobs" value={number(jobs.filter(job => job.enabled && !job.expired).length)} /><Metric label="Next attempt" value={selected ? countdown(selected.seconds_until_bump) : '--'} /><Metric label="Spent this week" value={`${number(fee?.bytes_this_week)} Bytes`} /><Metric label="Weekly limit" value={budget.unlimited ? 'Unlimited' : `${number(budget.limit)} Bytes`} /><Metric label="Remaining" value={budget.unlimited ? 'Unlimited' : `${number(budget.remaining)} Bytes`} /></div>
    <ErrorLine>{errors.jobs}</ErrorLine><ErrorLine>{errors.action}</ErrorLine>
    {errors.logs && <ErrorLine>Attempt history is unavailable. Job controls and thread reports remain available.</ErrorLine>}
    {loading ? <section className="bp-pane bp-loading" aria-label="Loading bump service"><i /><i /><i /></section> : <>
      <BudgetPane data={fee} error={errors.fee} onReload={load} />
      <AddJob fee={fee} onAdded={load} />
      {ordered.length ? <section className="bp-operations">
        <JobNavigator jobs={ordered} log={logs} budgetExceeded={budget.exceeded} selectedTid={selected?.tid} onSelect={selectTid} />
        <div className="bp-operation-detail">
          <ActiveJob job={selected} state={selectedState} performance={stats} statsLoading={statsLoading} statsError={statsError} fee={fee} busyTid={busyTid} onToggle={toggle} onRemove={remove} range={range} onRange={value => { setRange(value); setPage(1) }} onPage={setPage} onSaved={load} />
        </div>
      </section> : <ActiveJob job={null} />}
      <details className="bp-pane bp-details"><summary>Scheduling and fee details</summary><div><h3>Timer mode</h3><p>Attempts on the selected interval. Recent thread activity can move the next attempt forward.</p><h3>Page 1 watch</h3><p>Checks the forum page periodically and bumps after the thread leaves page 1, subject to HF timing limits.</p><h3>Fees</h3><p>A confirmed success uses the HF group fee shown above and the Toolbox service fee. Skips and failed attempts do not show as successful-bump spending.</p></div></details>
    </>}
  </main>
}
