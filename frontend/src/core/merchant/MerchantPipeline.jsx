import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { stageLabel, stageColor, relTime, absDate } from './merchantFormat.js'

const STAGES = ['new', 'qualified', 'follow_up', 'contract_opened', 'won', 'lost', 'ignored']

function LeadCard({ lead, onStageChange }) {
  const [patching, setPatching] = useState(false)
  const [note, setNote]         = useState(lead.note || '')
  const [showNote, setShowNote] = useState(false)

  const patch = (fields) => {
    setPatching(true)
    api.patch(`/api/merchant/leads/${lead.from_uid}/${lead.tid}`, fields)
      .then(() => { onStageChange(); setPatching(false) })
      .catch(() => setPatching(false))
  }

  const sc = stageColor(lead.stage)
  const isActive = !['won', 'lost', 'ignored'].includes(lead.stage)

  return (
    <div style={{
      background: 'var(--s1)', padding: '11px 14px', marginBottom: 6,
      borderLeft: `3px solid ${lead.sla_breached ? 'var(--red)' : sc}`,
      opacity: isActive ? 1 : 0.6,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 8, marginBottom: 5 }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{
            fontSize: 12, color: 'var(--text)', fontFamily: 'var(--mono)',
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}>
            {lead.from_username || lead.from_uid || '?'}
          </div>
          <div style={{
            fontSize: 10, color: 'var(--dim)',
            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          }}>
            {lead.thread_title || `TID ${lead.tid}`}
          </div>
        </div>
        <div style={{ textAlign: 'right', flexShrink: 0 }}>
          <div style={{ fontSize: 10, color: sc, fontFamily: 'var(--mono)' }}>{stageLabel(lead.stage)}</div>
          <div style={{ fontSize: 9, color: lead.sla_breached ? 'var(--red)' : 'var(--dim)', fontFamily: 'var(--mono)' }}>
            {relTime(lead.latest_dateline || lead.dateline)}{lead.sla_breached ? ' LATE' : ''}
          </div>
        </div>
      </div>

      {/* Reply count + first contact */}
      <div style={{ display: 'flex', gap: 10, marginBottom: 6, alignItems: 'center' }}>
        {lead.reply_count > 1 && (
          <span style={{ fontSize: 9, fontFamily: 'var(--mono)', color: 'var(--acc)',
                         background: 'var(--b2)', padding: '1px 5px' }}>
            {lead.reply_count} msgs
          </span>
        )}
        {lead.unread_count > 0 && (
          <span style={{ fontSize: 9, fontFamily: 'var(--mono)', color: 'var(--yellow)' }}>
            {lead.unread_count} unread
          </span>
        )}
        <span style={{ fontSize: 9, color: 'var(--dim)', fontFamily: 'var(--mono)' }}>
          first contact {absDate(lead.dateline)}
        </span>
      </div>

      {lead.message_preview && (
        <div style={{
          fontSize: 11, color: 'var(--sub)', marginBottom: 8,
          borderLeft: '2px solid var(--b2)', paddingLeft: 8,
          fontStyle: 'italic', lineHeight: 1.5,
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {lead.message_preview}
        </div>
      )}

      {lead.likely_converted && (
        <div style={{ fontSize: 10, color: 'var(--green)', fontFamily: 'var(--mono)', marginBottom: 6 }}>
          contract found on this thread
        </div>
      )}

      {/* Stage quick-select */}
      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap', marginBottom: showNote ? 8 : 0 }}>
        {STAGES.filter(s => s !== lead.stage).slice(0, 4).map(s => (
          <button key={s}
            className="btn"
            style={{ fontSize: 9, padding: '2px 7px', fontFamily: 'var(--mono)',
                     color: stageColor(s), borderColor: stageColor(s), opacity: patching ? 0.5 : 1 }}
            disabled={patching}
            onClick={() => patch({ stage: s })}
          >
            {stageLabel(s)}
          </button>
        ))}
        <button
          className="btn"
          style={{ fontSize: 9, padding: '2px 7px', fontFamily: 'var(--mono)', marginLeft: 'auto' }}
          onClick={() => setShowNote(n => !n)}
        >
          {showNote ? 'hide note' : 'note'}
        </button>
        {lead.latest_pid && (
          <a
            href={`https://hackforums.net/showthread.php?tid=${lead.tid}&pid=${lead.latest_pid}#pid${lead.latest_pid}`}
            target="_blank" rel="noopener noreferrer"
            style={{ fontSize: 9, fontFamily: 'var(--mono)', color: 'var(--acc)',
                     padding: '2px 7px', border: '1px solid var(--b2)', lineHeight: 2 }}
          >
            HF
          </a>
        )}
      </div>

      {showNote && (
        <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
          <input
            className="inp"
            style={{ flex: 1, fontSize: 11 }}
            placeholder="Add note..."
            value={note}
            onChange={e => setNote(e.target.value)}
          />
          <button
            className="btn"
            style={{ fontSize: 11 }}
            disabled={patching}
            onClick={() => { patch({ note }); setShowNote(false) }}
          >
            Save
          </button>
        </div>
      )}
    </div>
  )
}

function LeadTableRow({ lead, onStageChange }) {
  const [patching, setPatching] = useState(false)
  const [showNote, setShowNote] = useState(false)
  const [note, setNote] = useState(lead.note || '')
  const patch = fields => {
    setPatching(true)
    api.patch(`/api/merchant/leads/${lead.from_uid}/${lead.tid}`, fields)
      .then(onStageChange).finally(() => setPatching(false))
  }
  return <>
    <tr>
      <td><span className="mhq-table-primary">{lead.from_username || `UID ${lead.from_uid}`}</span><span className="mhq-table-meta">{lead.reply_count || 1} messages · {lead.unread_count || 0} unread</span></td>
      <td><span className="mhq-table-primary">{lead.thread_title || `TID ${lead.tid}`}</span><span className="mhq-table-meta">TID {lead.tid}</span></td>
      <td><select className="inp" value={lead.stage} disabled={patching} onChange={e => patch({stage:e.target.value})}>{STAGES.map(stage => <option key={stage} value={stage}>{stageLabel(stage)}</option>)}</select></td>
      <td>{lead.message_preview || 'No reply preview'}</td>
      <td><span className={lead.sla_breached ? 'r' : ''}>{relTime(lead.latest_dateline || lead.dateline)}{lead.sla_breached ? ' · Late' : ''}</span></td>
      <td><div style={{display:'flex',gap:6}}><button className="btn btn-sm" onClick={() => setShowNote(v => !v)}>Notes</button>{lead.latest_pid && <a className="btn btn-sm" href={`https://hackforums.net/showthread.php?tid=${lead.tid}&pid=${lead.latest_pid}#pid${lead.latest_pid}`} target="_blank" rel="noreferrer">Open</a>}</div></td>
    </tr>
    {showNote && <tr><td colSpan="6"><div style={{display:'flex',gap:8}}><input className="inp" style={{flex:1}} value={note} onChange={e=>setNote(e.target.value)} placeholder="Private lead note"/><button className="btn btn-sm" disabled={patching} onClick={()=>{patch({note});setShowNote(false)}}>Save Note</button></div></td></tr>}
  </>
}

export default function MerchantPipeline({marketAccess=null}) {
  const [data, setData]       = useState(null)
  const [opportunities, setOpportunities] = useState([])
  const [loading, setLoading] = useState(true)
  const [tab, setTab]         = useState('new')

  const load = () => {
    setLoading(true)
    api.get('/api/merchant/pipeline')
      .then(d => { setData(d); setLoading(false) })
      .catch(() => setLoading(false))
  }
  useEffect(() => { load() }, [])
  useEffect(() => {
    if (!marketAccess?.paid) { setOpportunities([]); return }
    api.get('/api/market/my-business/opportunities?days=30&limit=50')
      .then(d => setOpportunities(d.opportunities || []))
      .catch(() => setOpportunities([]))
  }, [marketAccess?.paid])

  if (loading) return <div className="empty"><div className="spin" /></div>
  if (!data)   return <div className="empty" style={{ color: 'var(--red)' }}>Failed to load replies</div>

  const { leads = [], summary = {}, sla_hours = 24 } = data
  const stages = ['new', 'qualified', 'follow_up', 'contract_opened', 'won', 'lost', 'ignored']
  const visibleLeads = leads.filter(l => l.stage === tab)

  return (
    <div className="mhq-shell">
      {marketAccess?.paid && <section className="mhq-section"><div className="mhq-section-head"><div><h3>Buyer request matches</h3><p>Requests strongly matched to your detected sales products.</p></div><span>{opportunities.length} matches</span></div>
        {opportunities.length === 0 ? <div className="mhq-empty">No strong product matches in the past 30 days.</div> : <div className="mhq-table-wrap"><table className="mhq-table"><thead><tr><th>Source</th><th>Buyer Request</th><th>Your Product</th><th>Market</th><th>Posted</th><th>Next Action</th></tr></thead><tbody>{opportunities.map(row => <tr key={`${row.product_id}:${row.tid}`}><td><span className="mhq-status info">Buyer Request</span></td><td><span className="mhq-table-primary">{row.subject}</span><span className="mhq-table-meta">UID {row.buyer_uid}</span></td><td>{row.product_name}</td><td>{row.unique_buyers || 0} buyers · {row.matching_supply || 0} seller listings</td><td>{relTime(row.created_at)}</td><td><a className="btn btn-sm" href={`https://hackforums.net/showthread.php?tid=${row.tid}`} target="_blank" rel="noreferrer">Review request</a></td></tr>)}</tbody></table></div>}
      </section>}
      <div className="mhq-summary">
        <button type="button"><span className="mhq-summary-label">Open Replies</span><strong className="mhq-summary-value">{summary.open ?? 0}</strong></button>
        <button type="button"><span className="mhq-summary-label">Late Replies</span><strong className="mhq-summary-value" style={{color:(summary.sla_breaches||0)>0?'var(--red)':'var(--text)'}}>{summary.sla_breaches ?? 0}</strong><span className="mhq-summary-note">SLA: {sla_hours} hours</span></button>
        <button type="button"><span className="mhq-summary-label">Qualified</span><strong className="mhq-summary-value">{summary.by_stage?.qualified || 0}</strong></button>
        <button type="button"><span className="mhq-summary-label">Contracts Opened</span><strong className="mhq-summary-value" style={{color:'var(--green)'}}>{summary.by_stage?.contract_opened || 0}</strong></button>
      </div>

      {/* Stage tabs */}
      <div className="mhq-filterbar" style={{overflowX:'auto',whiteSpace:'nowrap'}}>
        {stages.map(s => {
          const cnt = (summary.by_stage || {})[s] ?? 0
          return (
            <button key={s}
              className={`tab${tab === s ? ' on' : ''}`}
              onClick={() => setTab(s)}
            >
              {stageLabel(s)}{cnt > 0 ? ` (${cnt})` : ''}
            </button>
          )
        })}
      </div>

      {visibleLeads.length === 0
        ? <div className="mhq-empty">No replies in this stage.</div>
        : <div className="mhq-table-wrap"><table className="mhq-table"><thead><tr><th>Buyer</th><th>Sales Thread</th><th>Stage</th><th>Latest Reply</th><th>Updated</th><th>Next Action</th></tr></thead><tbody>{visibleLeads.map(lead => <LeadTableRow key={`${lead.from_uid}_${lead.tid}`} lead={lead} onStageChange={load}/>)}</tbody></table></div>
      }

      {leads.length === 0 && (
        <div className="empty" style={{ color: 'var(--dim)' }}>
          <div>No replies tracked yet.</div>
          <div style={{ fontSize: 11, marginTop: 6 }}>Track marketplace threads in Posting to start seeing replies here.</div>
        </div>
      )}
    </div>
  )
}
