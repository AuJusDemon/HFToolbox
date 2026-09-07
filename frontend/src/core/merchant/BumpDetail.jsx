import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../api.js'
import { BumpActivityTimeline, BumpPerformanceSummary, BumpRangeControl } from '../BumpPerformance.jsx'

export const REC_LABEL = { keep_bumping:'Keep Bumping', watch:'Watch', review:'Review', pause_candidate:'Pause Candidate', paused:'Paused', closed_thread:'Closed Thread' }
export const REC_COLOR = { keep_bumping:'var(--green)', watch:'var(--dim)', review:'var(--yellow)', pause_candidate:'var(--red)', paused:'var(--acc)', closed_thread:'var(--red)' }

export function periodSummary(period) {
  const parts = []
  if ((period.period_replies || 0) > 0) parts.push(`${period.period_replies} ${period.period_replies === 1 ? 'reply' : 'replies'}`)
  if ((period.contracts_opened || 0) > 0) parts.push(`${period.contracts_opened} contract${period.contracts_opened > 1 ? 's' : ''}`)
  if ((period.contracts_completed || 0) > 0) parts.push(`${period.contracts_completed} complete`)
  return parts.length ? parts.join(' / ') : 'No activity'
}

export default function BumpDetail({ tid, onBack, backLabel = 'Back to Bumps' }) {
  const [data,setData] = useState(null)
  const [loading,setLoading] = useState(true)
  const [error,setError] = useState('')
  const [range,setRange] = useState('30d')
  const [page,setPage] = useState(1)

  useEffect(() => {
    let active = true
    setLoading(true); setError('')
    api.get(`/api/autobump/jobs/${tid}/performance?range=${range}&page=${page}&page_size=5`)
      .then(result => { if (active) setData(result) })
      .catch(err => { if (active) setError(err.message || 'Failed to load bump performance.') })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [tid, range, page])

  if (loading && !data) return <div className="empty"><div className="spin" /></div>
  if (!data) return <div className="empty" style={{color:'var(--red)'}}>{error || 'Failed to load bump performance.'}</div>

  return <div className="mhq-shell">
    <div className="mhq-section-head">
      <div><span className="bp-kicker">BUSINESS IMPACT</span><h3>{data.title || `TID ${data.tid}`}</h3><p>TID {data.tid} / replies, contracts, and completed work attributed to bump periods.</p></div>
      <div style={{display:'flex',gap:6,flexWrap:'wrap'}}>{onBack && <button className="btn" onClick={onBack}>{backLabel}</button>}<Link className="btn btn-acc" to={`/dashboard/bumper?tid=${data.tid}`}>Manage bump schedule</Link></div>
    </div>
    <div className="mhq-filterbar"><BumpRangeControl value={range} onChange={value => { setRange(value); setPage(1) }} /></div>
    {error && <div className="mhq-note warn">{error}</div>}
    <BumpPerformanceSummary data={data} variant="business" />
    <BumpActivityTimeline data={data} onPage={setPage} />
  </div>
}
