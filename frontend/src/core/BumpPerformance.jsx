import React from 'react'
import './BumpPerformance.css'

const n = value => value == null ? 'Unknown' : Number(value).toLocaleString()
const stamp = value => value ? new Date(value * 1000).toLocaleString(undefined, { month:'short', day:'numeric', hour:'numeric', minute:'2-digit' }) : 'Unknown'
const schedulerSummary = row => {
  const events = row.period_skips || []
  const failures = events.filter(event => event.action === 'error')
  if (failures.length) return `${failures.length} failed: ${failures[0].reason || 'No reason recorded'}`
  const skips = events.filter(event => event.action === 'skipped')
  if (skips.length) return `${skips.length} skipped: ${skips[0].reason || 'Not eligible'}`
  return events.length ? `${events.length} scheduler events` : 'No scheduler exceptions'
}

export function BumpRangeControl({ value, onChange }) {
  return <div className="bpr-ranges" aria-label="Performance range">
    {[['7d','7 days'],['30d','30 days'],['all','All time']].map(([key,label]) =>
      <button type="button" key={key} className={value === key ? 'is-active' : ''} onClick={() => onChange(key)}>{label}</button>
    )}
  </div>
}

function Metric({ label, metric, suffix = '' }) {
  const value = metric?.available === false ? 'Unknown' : `${n(metric?.value)}${metric?.value != null ? suffix : ''}`
  return <div className="bpr-metric"><span>{label}</span><strong>{value}</strong><small>{metric?.source || 'unknown'}</small></div>
}

export function BumpPerformanceSummary({ data, variant = 'operations' }) {
  if (!data) return null
  const m = data.metrics || {}
  const current = data.current_period || {}
  const metrics = variant === 'business'
    ? [['Tracked replies',m.tracked_replies],['Contracts opened',m.contracts_opened],['Completed',m.contracts_completed],['Contracts / bump',m.contracts_per_bump],['Average reply gain',m.average_reply_gain],['Bumps with replies',m.reply_period_rate,'%']]
    : [['Successful',m.successful_bumps],['Skipped',m.skips],['Failed',m.failures],['Tracked replies',m.tracked_replies],['Contracts',m.contracts_opened],['Estimated spend',m.estimated_bytes_spent,' Bytes']]
  const latestReplies = current.replies_since_latest_bump
  return <section className="bpr-summary" aria-label="Bump performance">
    <div className="bpr-current">
      <div><span>Current period</span><strong>{current.started_at ? `Since ${stamp(current.started_at)}` : 'No successful bump yet'}</strong></div>
      <div><span>Replies since latest bump</span><strong>{latestReplies?.available ? n(latestReplies.value) : 'Unknown'}</strong><small>{latestReplies?.available ? 'observed thread count' : `last observation ${stamp(data.freshness?.thread_observed_at)}`}</small></div>
      <div><span>Contracts since latest bump</span><strong>{current.contracts_opened?.available === false ? 'Unknown' : n(current.contracts_opened?.value)}</strong><small>{current.contracts_opened?.available === false ? 'no completed bump period' : 'observed'}</small></div>
    </div>
    <div className="bpr-metrics">{metrics.map(([label,metric,suffix]) => <Metric key={label} label={label} metric={metric} suffix={suffix} />)}</div>
  </section>
}

export function BumpActivityTimeline({ data, onPage }) {
  if (!data) return null
  const rows = data.activity || []
  const paging = data.pagination || {}
  return <section className="bpr-timeline">
    <div className="bpr-section-head"><div><span>PERFORMANCE PERIODS</span><strong>Activity, grouped where nothing changed</strong></div><span>Page {paging.page || 1} of {paging.total_pages || 1}</span></div>
    {!rows.length ? <p className="bpr-empty">No bump periods in this range.</p> : rows.map((row,index) => row.kind === 'quiet_group'
      ? <div className="bpr-quiet" key={`quiet-${row.start_ts}-${index}`}><strong>{row.count} successful bump{row.count === 1 ? '' : 's'}</strong><span>{row.summary}</span><small>{stamp(row.start_ts)} to {stamp(row.end_ts)}</small></div>
      : <div className="bpr-event" key={`period-${row.bump_ts}-${index}`}><div><strong>{row.is_open ? 'Current period' : stamp(row.bump_ts)}</strong><small>{row.is_open ? 'In progress' : 'Completed period'}</small></div><span>{row.reply_gain == null ? 'Reply gain unknown' : `${row.reply_gain >= 0 ? '+' : ''}${row.reply_gain} replies`}</span><span>{row.contracts_opened || 0} opened / {row.contracts_completed || 0} completed</span><span>{schedulerSummary(row)}</span></div>
    )}
    {(paging.has_previous || paging.has_next) && <div className="bpr-pages"><button type="button" disabled={!paging.has_previous} onClick={() => onPage(paging.page - 1)}>Previous</button><button type="button" disabled={!paging.has_next} onClick={() => onPage(paging.page + 1)}>Next</button></div>}
  </section>
}

export function BumpAttempts({ attempts = [], fees }) {
  return <section className="bpr-attempts"><div className="bpr-section-head"><div><span>RECENT ATTEMPTS</span><strong>Latest five for this thread</strong></div></div>
    {!attempts.length ? <p className="bpr-empty">No attempts in this range.</p> : attempts.map(row => <div className="bpr-attempt" key={row.id}><span>{stamp(row.ts)}</span><strong className={`is-${row.action}`}>{row.action}</strong><span>{row.reason || 'No additional detail'}</span><small>{row.action === 'bumped' ? `${n(fees?.hf_fee)} + ${n(fees?.service_fee)} Bytes estimated` : 'No successful-bump charge'}</small></div>)}
  </section>
}

export function JobScheduleEditor({ job, onSave, onCancel, saving, error }) {
  const toInput = ts => ts ? new Date(ts * 1000).toISOString().slice(0,10) : ''
  const [draft,setDraft] = React.useState({mode:job.mode,interval_h:Number(job.interval_h),bump_until:toInput(job.bump_until),enabled:Boolean(job.enabled)})
  const originalDate = toInput(job.bump_until)
  const endTs = draft.bump_until === originalDate ? (job.bump_until || null) : draft.bump_until ? Math.floor(new Date(`${draft.bump_until}T23:59:59`).getTime()/1000) : null
  const now = Math.floor(Date.now()/1000)
  const nextTs = draft.mode === 'page1' ? now + 1800 : job.lastpost_ts ? Math.max(now,Number(job.lastpost_ts)+Number(draft.interval_h)*3600) : now+Number(draft.interval_h)*3600
  const changes = [
    draft.mode !== job.mode && ['Mode',job.mode === 'page1' ? 'Page 1 Watch' : 'Timer',draft.mode === 'page1' ? 'Page 1 Watch' : 'Timer'],
    Number(draft.interval_h) !== Number(job.interval_h) && ['Interval',`${job.interval_h} hours`,`${draft.interval_h} hours`],
    endTs !== (job.bump_until || null) && ['End date',job.bump_until ? stamp(job.bump_until) : 'No end date',endTs ? stamp(endTs) : 'No end date'],
    draft.enabled !== Boolean(job.enabled) && ['State',job.enabled ? 'Enabled' : 'Paused',draft.enabled ? 'Enabled' : 'Paused'],
  ].filter(Boolean)
  return <section className="bpr-editor" aria-label="Edit schedule">
    <div className="bpr-identity"><span>Thread identity</span><strong>{job.thread_title || `Thread ${job.tid}`}</strong><small>TID {job.tid}{job.fid ? ` / FID ${job.fid}` : ''} / cannot be changed here</small></div>
    <div className="bpr-editor-fields">
      <label>Mode<select value={draft.mode} onChange={e=>setDraft({...draft,mode:e.target.value})}><option value="timer">Timer</option><option value="page1">Page 1 Watch</option></select></label>
      <label>Interval<select value={draft.interval_h} onChange={e=>setDraft({...draft,interval_h:Number(e.target.value)})}>{[6,8,12,16,24,48,72,120,168].map(v=><option key={v} value={v}>{v} hours</option>)}</select></label>
      <label>End date<input type="date" min={new Date().toISOString().slice(0,10)} value={draft.bump_until} onChange={e=>setDraft({...draft,bump_until:e.target.value})} /></label>
      <div className="bpr-state">
        <span>Scheduler state</span>
        <button type="button" role="switch" aria-label="Scheduler enabled" aria-checked={draft.enabled} className="bpr-toggle" onClick={()=>setDraft({...draft,enabled:!draft.enabled})}>
          <i aria-hidden="true" />
          <strong>{draft.enabled ? 'Enabled' : 'Paused'}</strong>
        </button>
      </div>
    </div>
    <div className="bpr-change-list"><span>CHANGE SUMMARY</span>{changes.length ? <>{changes.map(([label,from,to])=><div key={label}><b>{label}</b><span>{from}</span><i>to</i><strong>{to}</strong></div>)}<div><b>Next check</b><span>{stamp(nextTs)}</span><i /><strong>{draft.enabled ? 'scheduled after save' : 'held while paused'}</strong></div></> : <p>No schedule changes.</p>}</div>
    {error && <p className="bpr-error" role="alert">{error}</p>}
    <div className="bpr-editor-actions"><button type="button" onClick={onCancel}>Cancel</button><button type="button" className="is-primary" disabled={saving||!changes.length} onClick={()=>onSave({...draft,bump_until:endTs})}>{saving ? 'Saving...' : 'Save schedule'}</button></div>
  </section>
}
