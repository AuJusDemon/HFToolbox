import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { severityColor, relTime } from './merchantFormat.js'

function ActionItem({ item }) {
  return (
    <div className="mhq-action-item" style={{
      display:'flex', alignItems:'center', gap:10,
      padding:'8px 12px', borderLeft:`3px solid ${severityColor(item.severity)}`,
      background:'var(--s1)', marginBottom:4,
    }}>
      <span style={{
        fontSize:10, fontFamily:'var(--mono)', letterSpacing:'.05em',
        color: severityColor(item.severity), minWidth:24, textAlign:'center',
      }}>{item.count}</span>
      <span style={{fontSize:12, color:'var(--text)'}}>{item.label}</span>
    </div>
  )
}

function StatChip({ label, value, color }) {
  return (
    <div style={{
      background:'var(--s1)', padding:'8px 12px', flex:1, minWidth:0,
    }}>
      <div style={{fontSize:10, color:'var(--dim)', fontFamily:'var(--mono)', marginBottom:2}}>{label}</div>
      <div style={{fontSize:20, fontWeight:700, color: color || 'var(--acc)', fontFamily:'var(--mono)'}}>{value}</div>
    </div>
  )
}

function ProblemItem({ p }) {
  const label = p.type === 'bump_no_leads'
    ? `${p.bumps} bumps, no replies or completed deals`
    : `${p.unread} unanswered leads`
  return (
    <div style={{padding:'7px 12px', borderLeft:'2px solid var(--b2)', marginBottom:4}}>
      <div style={{fontSize:11, color:'var(--yellow)', fontFamily:'var(--mono)', marginBottom:1}}>
        {p.type === 'bump_no_leads' ? 'PROMOTION WASTE' : 'UNANSWERED LEADS'}
      </div>
      <div style={{fontSize:12, color:'var(--text)'}}>{p.title || `TID ${p.tid}`}</div>
      <div style={{fontSize:11, color:'var(--dim)'}}>{label}</div>
    </div>
  )
}

export default function MerchantOverview({ setTab }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    api.get('/api/merchant/overview')
      .then(d => { setData(d); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  if (loading) return <div className="empty"><div className="spin" /></div>
  if (!data)   return <div className="empty" style={{color:'var(--red)'}}>Failed to load overview</div>

  const { action_queue = [], today = {}, week = {}, top_problems = [], totals = {} } = data

  return (
    <div className="mhq-overview">

      {/* Action Queue */}
      <div className="card" style={{marginBottom:12}}>
        <div className="card-head">
          <span>Action Queue</span>
          {action_queue.length === 0 && (
            <span style={{fontSize:10, color:'var(--green)', fontFamily:'var(--mono)'}}>all clear</span>
          )}
        </div>
        <div className="card-body" style={{padding:'8px 10px'}}>
          {action_queue.length === 0
            ? <div style={{color:'var(--dim)',fontSize:12,padding:4}}>Nothing urgent right now.</div>
            : action_queue.map((item, i) => <ActionItem key={i} item={item} />)
          }
        </div>
      </div>

      {/* Today / This Week */}
      <div className="card" style={{marginBottom:12}}>
        <div className="card-head">Today / This Week</div>
        <div className="card-body" style={{padding:'8px 10px'}}>
          <div style={{display:'flex', gap:6, flexWrap:'wrap'}}>
            <StatChip label="COMPLETED TODAY"    value={today.completed_deals   ?? 0} color="var(--green)" />
            <StatChip label="NEW LEADS TODAY"    value={today.new_leads         ?? 0} />
            <StatChip label="ACTIVE CONTRACTS"   value={today.active_contracts  ?? 0} color="var(--yellow)" />
            <StatChip label="COMPLETED THIS WEEK" value={week.completed_deals   ?? 0} color="var(--green)" />
          </div>
        </div>
      </div>

      {/* Totals */}
      <div className="card" style={{marginBottom:12}}>
        <div className="card-head">All-Time</div>
        <div className="card-body" style={{padding:'8px 10px'}}>
          <div style={{display:'flex', gap:6, flexWrap:'wrap'}}>
            <StatChip label="TRACKED OFFERS"       value={totals.tracked_offers        ?? 0} />
            <StatChip label="TOTAL CONTRACTS"      value={totals.total_contracts       ?? 0} />
            <StatChip label="COMPLETED CONTRACTS"  value={totals.completed_contracts   ?? 0} color="var(--green)" />
          </div>
        </div>
      </div>

      {/* Problems */}
      {top_problems.length > 0 && (
        <div className="card" style={{marginBottom:12}}>
          <div className="card-head">
            <span>Top Problems</span>
          </div>
          <div className="card-body" style={{padding:'8px 10px'}}>
            {top_problems.map((p, i) => <ProblemItem key={i} p={p} />)}
          </div>
        </div>
      )}

      {/* Quick nav */}
      <div style={{display:'flex', gap:6, flexWrap:'wrap'}}>
        {[
          { tab:'pipeline',  label:'Pipeline',  count: today.new_leads },
          { tab:'deals',     label:'Deals',     count: today.active_contracts },
          { tab:'offers',    label:'Offers',    count: totals.tracked_offers },
          { tab:'customers', label:'Customers', count: null },
        ].map(({tab, label, count}) => (
          <button key={tab}
            className="btn"
            style={{flex:'1 1 120px', minWidth:0}}
            onClick={() => setTab(tab)}
          >
            {label}{count != null ? ` (${count})` : ''}
          </button>
        ))}
      </div>

    </div>
  )
}
