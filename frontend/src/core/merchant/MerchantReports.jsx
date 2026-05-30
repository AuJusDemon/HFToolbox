import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { absDate } from './merchantFormat.js'

function StatRow({ label, value, color, note }) {
  return (
    <div style={{
      display:'flex', justifyContent:'space-between', alignItems:'baseline',
      padding:'7px 0', borderBottom:'1px solid var(--b2)',
    }}>
      <div>
        <span style={{fontSize:12, color:'var(--sub)'}}>{label}</span>
        {note && <span style={{fontSize:10, color:'var(--dim)', marginLeft:8}}>{note}</span>}
      </div>
      <span style={{
        fontSize:16, fontFamily:'var(--mono)', fontWeight:700,
        color: color || 'var(--acc)',
      }}>{value}</span>
    </div>
  )
}

export default function MerchantReports() {
  const [report, setReport]   = useState(null)
  const [loading, setLoading] = useState(true)
  const [week, setWeek]       = useState(0)

  const load = (w) => {
    setLoading(true)
    api.get(`/api/merchant/reports/weekly?week=${w}`)
      .then(d => { setReport(d); setLoading(false) })
      .catch(() => setLoading(false))
  }
  useEffect(() => { load(week) }, [week])

  return (
    <div>
      <div style={{display:'flex', gap:8, alignItems:'center', marginBottom:14}}>
        <button className="btn" style={{fontSize:11}} onClick={() => setWeek(w => w + 1)}>← Prev</button>
        <span style={{fontFamily:'var(--mono)', fontSize:11, color:'var(--dim)', flex:1, textAlign:'center'}}>
          {report
            ? `${absDate(report.week_start)} — ${absDate(report.week_end)}`
            : 'Loading…'
          }
        </span>
        <button className="btn" style={{fontSize:11}} disabled={week === 0} onClick={() => setWeek(w => Math.max(0, w - 1))}>→ Next</button>
      </div>

      {loading
        ? <div className="empty"><div className="spin" /></div>
        : !report
          ? <div className="empty" style={{color:'var(--red)'}}>Failed to load report</div>
          : (
            <div className="card">
              <div className="card-head">Seller Recap</div>
              <div className="card-body">
                <StatRow label="Completed Contracts"  value={report.completed_deals}   color="var(--green)" />
                <StatRow label="New Contracts"        value={report.new_contracts} />
                <StatRow label="Active Contracts"     value={report.active_pipeline}    color="var(--yellow)" />
                <StatRow label="New Replies"          value={report.new_leads} />
                <StatRow label="Repeat Buyers"        value={report.repeat_customers}   color="var(--acc)" />
                <StatRow label="Late Replies"         value={report.sla_breaches}       color={report.sla_breaches > 0 ? 'var(--red)' : 'var(--green)'} />
                <StatRow label="Needs Reply"          value={report.needs_attention}    color={report.needs_attention > 0 ? 'var(--yellow)' : 'var(--green)'} />

                {report.best_offer && (
                  <div style={{marginTop:12}}>
                    <div style={{fontSize:10, color:'var(--dim)', fontFamily:'var(--mono)', marginBottom:4}}>TOP SALES THREAD</div>
                    <div style={{fontSize:12, color:'var(--green)'}}>
                      {report.best_offer.title || `TID ${report.best_offer.tid}`}
                    </div>
                    <div style={{fontSize:11, color:'var(--dim)'}}>
                      {report.best_offer.completed} completed contracts
                    </div>
                  </div>
                )}

                {report.worst_spend_offer && report.worst_spend_offer.bumps > 0 && (
                  <div style={{marginTop:12}}>
                    <div style={{fontSize:10, color:'var(--dim)', fontFamily:'var(--mono)', marginBottom:4}}>HIGHEST BUMP ACTIVITY</div>
                    <div style={{fontSize:12, color:'var(--yellow)'}}>
                      {report.worst_spend_offer.title || `TID ${report.worst_spend_offer.tid}`}
                    </div>
                    <div style={{fontSize:11, color:'var(--dim)'}}>
                      {report.worst_spend_offer.bumps} bumps
                    </div>
                  </div>
                )}
              </div>
            </div>
          )
      }
    </div>
  )
}
