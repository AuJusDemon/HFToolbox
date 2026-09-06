import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, throttledInterval } from './api.js'
import useStore from '../store.js'
import { PROGRAMS, prefetchProgram } from '../system/programRegistry.js'

const nowSeconds = () => Math.floor(Date.now() / 1000)
const number = value => Number(value || 0).toLocaleString()
const ago = value => {
  const ts = Number(value || 0)
  if (!ts) return '--'
  const elapsed = Math.max(0, nowSeconds() - ts)
  if (elapsed < 60) return `${elapsed}s ago`
  if (elapsed < 3600) return `${Math.floor(elapsed / 60)}m ago`
  if (elapsed < 86400) return `${Math.floor(elapsed / 3600)}h ago`
  return `${Math.floor(elapsed / 86400)}d ago`
}
const until = seconds => {
  if (seconds == null) return '--'
  if (seconds <= 0) return 'Due now'
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  return hours ? `${hours}h ${minutes}m` : `${minutes}m`
}

function Pane({ title, label, action, children, className = '' }) {
  return <section className={`overview-pane ${className}`}><header><div><span>{label}</span><h2>{title}</h2></div>{action}</header>{children}</section>
}

function OpenButton({ program, children }) {
  const navigate = useNavigate()
  return <button type="button" className="overview-open" onPointerEnter={() => prefetchProgram(program)} onFocus={() => prefetchProgram(program)} onClick={() => navigate(program.route)}>{children || `Open ${program.label}`}</button>
}

function StatusStrip({ snapshot, merchant, jobs, loading }) {
  const navigate = useNavigate()
  const counts = snapshot?.contracts?.counts || {}
  const contractAttention = Number(counts.disputed || 0) + Number(counts.awaiting || 0) + Number(merchant?.contract_stage_counts?.needs_review || 0)
  const bumpAttention = jobs.filter(job => job.expired || (job.enabled && !job.next_bump)).length
  const items = [
    { label:'HF API allowance', value: snapshot?.rate_remaining >= 0 ? `${snapshot.rate_remaining} / 240` : 'Unknown', state: snapshot?.rate_remaining >= 0 && snapshot.rate_remaining < 30 ? 'warning' : 'normal', route:'/dashboard/settings' },
    { label:'Contracts needing action', value: contractAttention, state: contractAttention ? 'warning' : 'normal', route:'/dashboard/contracts' },
    { label:'Open sales replies', value: Number(merchant?.pipeline?.total ?? snapshot?.reply_count ?? 0), state: merchant?.pipeline?.sla_breaches ? 'error' : Number(snapshot?.reply_count) ? 'warning' : 'normal', route:'/dashboard/merchant' },
    { label:'Bump jobs requiring action', value: bumpAttention, state: bumpAttention ? 'error' : 'normal', route:'/dashboard/bumper' },
    { label:'Bytes balance', value: number(snapshot?.bytes?.balance ?? snapshot?.profile?.myps), state:'normal', route:'/dashboard/bytes' },
  ]
  return <section className="overview-status" aria-label="Account status">{items.map(item => <button key={item.label} type="button" onClick={() => navigate(item.route)}><span>{item.label}</span><b className={item.state}>{loading ? '--' : item.value}</b></button>)}</section>
}

function buildWorkItems(merchant, jobs, posting) {
  const routeFor = type => type === 'unread_replies' || type === 'sla_breach' || type === 'followup_due' || type === 'bump_waste' ? '/dashboard/merchant' : '/dashboard/contracts'
  const items = (merchant?.action_queue || []).map((item, index) => ({
    id:`merchant-${item.type}-${index}`, source:item.type.includes('contract') || item.type === 'awaiting_approval' ? 'Contracts' : 'My Business',
    title:item.label, detail:item.type === 'sla_breach' ? 'Reply target has been missed.' : 'Review the current sales workflow.',
    severity:item.severity === 'high' ? 'error' : item.severity === 'medium' ? 'warning' : 'normal', route:routeFor(item.type), order:item.severity === 'high' ? 0 : item.severity === 'medium' ? 1 : 2,
  }))
  for (const job of jobs) {
    if (job.expired || (job.enabled && !job.next_bump)) items.push({ id:`bump-${job.id}`, source:'Bump Service', title:job.thread_title || `Thread ${job.tid}`, detail:job.expired ? 'Job end time has passed.' : 'Enabled job has no next attempt.', severity:'error', route:'/dashboard/bumper', order:0 })
  }
  for (const row of posting?.queue || []) {
    if (row.status === 'failed') items.push({ id:`post-${row.id}`, source:'Posting', title:row.subject || 'Scheduled post failed', detail:row.error || 'Open Posting to review the failed job.', severity:'error', route:'/dashboard/posting', order:0 })
    else if (row.status === 'pending') items.push({ id:`post-${row.id}`, source:'Posting', title:row.subject || 'Scheduled post', detail:`Scheduled ${ago(row.created_at || row.fire_at)}`, severity:'normal', route:'/dashboard/posting', order:3 })
  }
  return items.sort((a, b) => a.order - b.order).slice(0, 10)
}

function WorkQueue({ merchant, jobs, posting, loading, error }) {
  const navigate = useNavigate()
  const items = useMemo(() => buildWorkItems(merchant, jobs, posting), [merchant, jobs, posting])
  return <Pane title="Work Queue" label="Requires attention" className="overview-work"><div className="overview-work-head"><span>Program</span><span>Item</span><span>State</span></div>{loading ? <div className="overview-loading">Loading current work...</div> : error ? <div className="overview-failure"><b>Dashboard data could not be loaded.</b><span>{error}</span></div> : items.length === 0 ? <div className="overview-empty"><b>Nothing currently needs attention.</b><span>Scheduled and account activity will appear here when action is required.</span></div> : <div className="overview-work-list">{items.map(item => <button key={item.id} type="button" onClick={() => navigate(item.route)}><span className="overview-source">{item.source}</span><span><b>{item.title}</b><small>{item.detail}</small></span><em className={item.severity}>{item.severity === 'error' ? 'Failure' : item.severity === 'warning' ? 'Action' : 'Upcoming'}</em></button>)}</div>}</Pane>
}

function BusinessSummary({ merchant }) {
  const program = PROGRAMS.find(item => item.id === 'merchant')
  const health = merchant?.thread_health || []
  return <Pane title="My Business" label="Sales workspace" action={<OpenButton program={program} />}><div className="overview-service-metrics"><div><span>Active contracts</span><b>{number(merchant?.today?.active_contracts)}</b></div><div><span>Open replies</span><b>{number(merchant?.pipeline?.total)}</b></div><div><span>Threads needing review</span><b className={merchant?.threads_needing_attention ? 'warning' : ''}>{number(merchant?.threads_needing_attention)}</b></div></div><div className="overview-compact-list">{health.slice(0, 4).map(thread => <div key={thread.tid}><span><b>{thread.title || `Thread ${thread.tid}`}</b><small>{thread.unread_replies || 0} unread replies, {thread.contracts_active || 0} open contracts</small></span><em className={thread.health === 'needs_attention' ? 'warning' : ''}>{String(thread.health || 'unknown').replaceAll('_', ' ')}</em></div>)}{health.length === 0 && <p>No tracked sales-thread issues.</p>}</div></Pane>
}

function BumpSummary({ jobs, snapshot }) {
  const program = PROGRAMS.find(item => item.id === 'bumper')
  const active = jobs.filter(job => job.enabled && !job.expired)
  const next = [...active].filter(job => job.seconds_until_bump != null).sort((a,b) => a.seconds_until_bump - b.seconds_until_bump)[0]
  const latest = [...jobs].filter(job => job.last_bumped).sort((a,b) => b.last_bumped - a.last_bumped)[0]
  const totalBumps = jobs.reduce((sum, job) => sum + Number(job.bump_count || 0), 0)
  const recentSpend = (snapshot?.bytes?.transactions || []).filter(row => row.sent && /bump/i.test(row.reason || '') && Number(row.dateline || 0) >= nowSeconds() - 7 * 86400).reduce((sum, row) => sum + Math.abs(Number(row.amount || 0)), 0)
  return <Pane title="Bump Service" label="Scheduler" action={<OpenButton program={program} />}><div className="overview-service-metrics"><div><span>Active jobs</span><b>{active.length}</b></div><div><span>Next bump</span><b>{next ? until(next.seconds_until_bump) : '--'}</b></div><div><span>Spend, 7 days</span><b>{number(recentSpend)}b</b></div></div><div className="overview-compact-list">{jobs.slice(0,4).map(job => <div key={job.id}><span><b>{job.thread_title || `Thread ${job.tid}`}</b><small>{job.last_bumped ? `Last result ${ago(job.last_bumped)} - ${number(totalBumps)} total recorded bumps` : 'No completed bump recorded'}</small></span><em className={job.expired ? 'error' : job.enabled ? 'connected' : ''}>{job.expired ? 'Expired' : job.enabled ? until(job.seconds_until_bump) : 'Paused'}</em></div>)}{jobs.length === 0 && <p>No bump jobs configured.</p>}</div>{latest && <footer className="overview-service-note">Latest successful result: {latest.thread_title || `Thread ${latest.tid}`} {ago(latest.last_bumped)}.</footer>}</Pane>
}

function ActivityLedger({ snapshot, merchant, jobs }) {
  const rows = []
  for (const transaction of snapshot?.bytes?.transactions || []) rows.push({ id:`byte-${transaction.id}`, source:'Bytes', action:transaction.reason || 'Balance transaction', result:`${transaction.sent ? '-' : '+'}${number(Math.abs(Number(transaction.amount || 0)))} Bytes`, ts:Number(transaction.dateline || 0), route:'/dashboard/bytes' })
  for (const contract of merchant?.recent_contracts || []) rows.push({ id:`contract-${contract.cid}`, source:'Contracts', action:contract.product || `Contract ${contract.cid}`, result:String(contract.stage || contract.bucket || 'Updated').replaceAll('_',' '), ts:Number(contract.dateline || 0), route:'/dashboard/contracts' })
  for (const job of jobs) if (job.last_bumped) rows.push({ id:`bump-log-${job.id}`, source:'Bump Service', action:job.thread_title || `Thread ${job.tid}`, result:'Bump recorded', ts:Number(job.last_bumped), route:'/dashboard/bumper' })
  rows.sort((a,b) => b.ts - a.ts)
  const navigate = useNavigate()
  return <Pane title="Activity Ledger" label="Recent account changes"><div className="overview-ledger-head"><span>Source</span><span>Action</span><span>Result</span><span>When</span></div><div className="overview-ledger">{rows.slice(0,10).map(row => <button key={row.id} type="button" onClick={() => navigate(row.route)}><span>{row.source}</span><b>{row.action}</b><span>{row.result}</span><time>{ago(row.ts)}</time></button>)}{rows.length === 0 && <p>No recent account activity.</p>}</div></Pane>
}

export default function OverviewDashboard() {
  const throttle = useStore(state => state.throttle)
  const [data, setData] = useState({ snapshot:null, merchant:null, jobs:[], posting:null })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const load = useCallback(() => Promise.allSettled([
    api.get('/api/dashboard/snapshot'), api.get('/api/merchant/overview'), api.get('/api/autobump/jobs'), api.get('/api/posting/queue'),
  ]).then(results => {
    const [snapshot, merchant, jobs, posting] = results
    if (snapshot.status === 'rejected') throw snapshot.reason
    setData({ snapshot:snapshot.value, merchant:merchant.status === 'fulfilled' ? merchant.value : null, jobs:jobs.status === 'fulfilled' ? jobs.value?.jobs || [] : [], posting:posting.status === 'fulfilled' ? posting.value : null })
    setError('')
  }).catch(reason => setError(reason?.message || 'Snapshot request failed.')).finally(() => setLoading(false)), [])
  useEffect(() => { load(); const timer = setInterval(load, throttledInterval(60000, throttle)); return () => clearInterval(timer) }, [load, throttle])
  return <div className="overview-dashboard"><div className="overview-heading"><div><span>Account operations</span><h1>Overview</h1><p>Current work, service state, and recent account changes.</p></div><button type="button" onClick={load}>Refresh</button></div><StatusStrip {...data} loading={loading} /><WorkQueue merchant={data.merchant} jobs={data.jobs} posting={data.posting} loading={loading} error={error} /><div className="overview-services"><BusinessSummary merchant={data.merchant} /><BumpSummary jobs={data.jobs} snapshot={data.snapshot} /></div><ActivityLedger {...data} /></div>
}
