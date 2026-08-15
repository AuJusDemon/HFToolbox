import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { absDate } from './merchantFormat.js'

export default function MerchantReports() {
  const [report, setReport] = useState(null)
  const [loading, setLoading] = useState(true)
  const [week, setWeek] = useState(0)

  useEffect(() => {
    setLoading(true)
    api.get(`/api/merchant/reports/weekly?week=${week}`)
      .then(setReport).catch(() => setReport(null)).finally(() => setLoading(false))
  }, [week])

  return <div className="mhq-shell">
    <div className="mhq-filterbar">
      <button className="btn" onClick={() => setWeek(value => value + 1)}>Previous week</button>
      <span style={{flex:1,textAlign:'center',color:'var(--dim)'}}>{report ? `${absDate(report.week_start)} to ${absDate(report.week_end)}` : 'Loading period'}</span>
      <button className="btn" disabled={week===0} onClick={() => setWeek(value => Math.max(0,value-1))}>Next week</button>
    </div>
    {loading ? <div className="empty"><div className="spin"/></div> : !report ? <div className="mhq-empty" style={{color:'var(--red)'}}>The report could not be loaded.</div> : <>
      <div className="mhq-summary">
        <button type="button"><span className="mhq-summary-label">Completed</span><strong className="mhq-summary-value" style={{color:'var(--green)'}}>{report.completed_deals}</strong><span className="mhq-summary-note">completed during period</span></button>
        <button type="button"><span className="mhq-summary-label">New Contracts</span><strong className="mhq-summary-value">{report.new_contracts}</strong><span className="mhq-summary-note">created during period</span></button>
        <button type="button"><span className="mhq-summary-label">New Replies</span><strong className="mhq-summary-value">{report.new_leads}</strong></button>
        <button type="button"><span className="mhq-summary-label">Repeat Buyers</span><strong className="mhq-summary-value">{report.repeat_customers}</strong></button>
        <button type="button"><span className="mhq-summary-label">Thread Updates</span><strong className="mhq-summary-value">{report.thread_updates?.posted || 0}</strong><span className="mhq-summary-note">posted from HFToolbox</span></button>
      </div>
      <div className="mhq-table-wrap"><table className="mhq-table"><thead><tr><th>Business Check</th><th>Count</th><th>Meaning</th></tr></thead><tbody>
        <tr><td className="mhq-table-primary">Active contracts</td><td>{report.active_pipeline}</td><td>Still moving through fulfillment</td></tr>
        <tr><td className="mhq-table-primary">Late replies</td><td className={report.sla_breaches>0?'r':''}>{report.sla_breaches}</td><td>Past your reply SLA</td></tr>
        <tr><td className="mhq-table-primary">Threads needing replies</td><td>{report.needs_attention}</td><td>Unread marketplace conversations</td></tr>
      </tbody></table></div>
      <div className="mhq-grid">
        <section><div className="mhq-section-head"><div><h3>Top Sales Thread</h3><p>Highest completed-contract count for this period.</p></div></div>{report.best_offer ? <div className="mhq-table-wrap"><table className="mhq-table"><tbody><tr><td><span className="mhq-table-primary">{report.best_offer.title || `TID ${report.best_offer.tid}`}</span></td><td>{report.best_offer.completed} completed</td></tr></tbody></table></div> : <div className="mhq-empty">No completed thread activity.</div>}</section>
        <section><div className="mhq-section-head"><div><h3>Highest Bump Activity</h3><p>Thread with the most recorded bumps.</p></div></div>{report.worst_spend_offer?.bumps > 0 ? <div className="mhq-table-wrap"><table className="mhq-table"><tbody><tr><td><span className="mhq-table-primary">{report.worst_spend_offer.title || `TID ${report.worst_spend_offer.tid}`}</span></td><td>{report.worst_spend_offer.bumps} bumps</td></tr></tbody></table></div> : <div className="mhq-empty">No bump activity recorded.</div>}</section>
      </div>
      <section className="mhq-section">
        <div className="mhq-section-head">
          <div>
            <h3>Thread Update Results</h3>
            <p>HF observed views and posts gained after updates posted from HFToolbox.</p>
          </div>
          <span>{report.thread_updates?.failed || 0} failed</span>
        </div>
        {(report.thread_updates?.rows || []).length === 0
          ? <div className="mhq-empty">No thread updates were posted during this period.</div>
          : <div className="mhq-table-wrap"><table className="mhq-table"><thead><tr><th>Sales Thread</th><th>Status</th><th>Posted</th><th>Views Gained</th><th>Posts Gained</th><th>Contracts Gained</th></tr></thead><tbody>
            {(report.thread_updates?.rows || []).map(row => <tr key={row.id}>
              <td><span className="mhq-table-primary">{row.title || `TID ${row.tid}`}</span><span className="mhq-table-meta">TID {row.tid}</span></td>
              <td><span className={`mhq-status ${row.status === 'posted' ? 'good' : row.status === 'failed' ? 'warn' : ''}`}>{row.status}</span></td>
              <td>{absDate(row.posted_at || row.created_at)}</td>
              <td>{row.views_gained > 0 ? `+${row.views_gained}` : row.views_gained}</td>
              <td>{row.posts_gained > 0 ? `+${row.posts_gained}` : row.posts_gained}</td>
              <td>{row.contracts_gained > 0 ? `+${row.contracts_gained}` : row.contracts_gained}</td>
            </tr>)}
          </tbody></table></div>}
      </section>
    </>}
  </div>
}
