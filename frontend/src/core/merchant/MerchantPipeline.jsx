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

export default function MerchantPipeline() {
  const [data, setData]       = useState(null)
  const [loading, setLoading] = useState(true)
  const [tab, setTab]         = useState('new')

  const load = () => {
    setLoading(true)
    api.get('/api/merchant/pipeline')
      .then(d => { setData(d); setLoading(false) })
      .catch(() => setLoading(false))
  }
  useEffect(load, [])

  if (loading) return <div className="empty"><div className="spin" /></div>
  if (!data)   return <div className="empty" style={{ color: 'var(--red)' }}>Failed to load replies</div>

  const { leads = [], summary = {}, sla_hours = 24 } = data
  const stages = ['new', 'qualified', 'follow_up', 'contract_opened', 'won', 'lost', 'ignored']
  const visibleLeads = leads.filter(l => l.stage === tab)

  return (
    <div>
      {/* Summary bar */}
      <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 12 }}>
        {[
          { label: 'OPEN REPLIES', val: summary.total ?? 0 },
          { label: 'LATE REPLY',   val: summary.sla_breaches ?? 0, color: 'var(--red)' },
        ].concat(
          Object.entries(summary.by_stage || {}).map(([s, c]) => ({
            label: stageLabel(s).toUpperCase(), val: c, color: stageColor(s),
          }))
        ).map(({ label, val, color }) => (
          <div key={label} style={{
            background: 'var(--s1)', padding: '6px 12px', minWidth: 60, textAlign: 'center',
          }}>
            <div style={{ fontSize: 9, color: 'var(--dim)', fontFamily: 'var(--mono)' }}>{label}</div>
            <div style={{ fontSize: 16, fontWeight: 700, fontFamily: 'var(--mono)', color: color || 'var(--sub)' }}>{val}</div>
          </div>
        ))}
      </div>

      {/* Stage tabs */}
      <div style={{ display: 'flex', gap: 4, marginBottom: 12, overflowX: 'auto', whiteSpace: 'nowrap' }}>
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
        ? <div className="empty" style={{ color: 'var(--dim)' }}>No replies in this stage.</div>
        : visibleLeads.map(lead => (
          <LeadCard
            key={`${lead.from_uid}_${lead.tid}`}
            lead={lead}
            onStageChange={load}
          />
        ))
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
