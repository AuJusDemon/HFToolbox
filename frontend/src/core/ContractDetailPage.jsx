import { useState, useEffect } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { api } from './api.js'

const ago = ts => {
  if (!ts) return '--'
  const d = Math.floor(Date.now()/1000) - Number(ts)
  if (d < 60)    return `${d}s ago`
  if (d < 3600)  return `${Math.floor(d/60)}m ago`
  if (d < 86400) return `${Math.floor(d/3600)}h ago`
  return `${Math.floor(d/86400)}d ago`
}

const STATUS = { '1':'Awaiting Approval','2':'Cancelled','3':'In Escrow','4':'In Escrow',
                 '5':'Active Deal','6':'Complete','7':'Disputed','8':'Expired' }
const STATUS_COLOR = {
  'Active Deal':'var(--acc)', 'Complete':'var(--sub)', 'Awaiting Approval':'var(--yellow)',
  'Disputed':'var(--red)', 'Expired':'rgba(255,71,87,.6)', 'Cancelled':'var(--dim)',
}
const TYPE = { '1':'Selling','2':'Purchasing','3':'Exchanging','4':'Trading','5':'Vouch Copy' }

function contractValue(c) {
  const ip = c.iprice, ic = c.icurrency, op = c.oprice, oc = c.ocurrency
  const iprod = c.iproduct, oprod = c.oproduct
  if (ip && ip !== '0' && ic && ic.toLowerCase() !== 'other') return `${ip} ${ic}`
  if (op && op !== '0' && oc && oc.toLowerCase() !== 'other') return `${op} ${oc}`
  if (iprod && iprod !== 'other' && iprod !== 'n/a' && iprod !== '') return iprod
  if (oprod && oprod !== 'other' && oprod !== 'n/a' && oprod !== '') return oprod
  return '--'
}

// Which actions are available based on status + party
function availableActions(c, myUid) {
  const status = c.status
  const isInit  = String(c.inituid)  === String(myUid)
  const isOther = String(c.otheruid) === String(myUid)
  const actions = []

  if (status === '1') {
    if (isInit)  actions.push({ action:'undo',     label:'Undo',    cls:'btn-ghost',   confirm:false })
    if (isOther) actions.push({ action:'approve',  label:'Approve', cls:'btn-acc',     confirm:true  })
    if (isOther) actions.push({ action:'deny',     label:'Deny',    cls:'btn-danger',  confirm:true  })
  }
  if (status === '5') {
    actions.push({ action:'complete', label:'Mark Complete', cls:'btn-acc',    confirm:true  })
    actions.push({ action:'cancel',   label:'Request Cancel', cls:'btn-ghost', confirm:true  })
  }
  return actions
}

export default function ContractDetailPage() {
  const { cid } = useParams()
  const nav     = useNavigate()
  const [data,      setData]      = useState(null)
  const [loading,   setLoading]   = useState(true)
  const [error,     setError]     = useState(null)
  const [acting,    setActing]    = useState(null)   // action in progress
  const [actionResult, setActionResult] = useState(null)
  const [confirmAction, setConfirmAction] = useState(null)
  const [address, setAddress] = useState('')

  useEffect(() => {
    setLoading(true)
    api.get(`/api/contracts/${cid}`)
      .then(d => { setData(d); setLoading(false) })
      .catch(e => { setError(e.message); setLoading(false) })
  }, [cid])

  const doAction = async (action) => {
    setActing(action)
    setActionResult(null)
    try {
      const res = await api.post(`/api/contracts/${cid}/action`, { action, address })
      setActionResult({ ok: true, message: `${action} successful` })
      // Refresh contract data after action
      setTimeout(() => {
        api.get(`/api/contracts/${cid}`).then(d => setData(d)).catch(() => {})
        setActionResult(null)
      }, 2000)
    } catch (e) {
      setActionResult({ ok: false, message: e.message })
    }
    setActing(null)
    setConfirmAction(null)
    setAddress('')
  }

  if (loading) return (
    <div style={{ display:'flex', justifyContent:'center', padding:60 }}>
      <div className="spin"/>
    </div>
  )
  if (error) return (
    <div className="card" style={{ padding:20 }}>
      <div style={{ color:'var(--red)', fontSize:13 }}>Error: {error}</div>
      <button className="btn btn-ghost" style={{ marginTop:12, fontSize:11 }} onClick={() => nav(-1)}>← Back</button>
    </div>
  )
  if (!data) return null

  const { contract: c, counterparty_username, my_uid } = data
  const status      = STATUS[c.status]  || `Status ${c.status}`
  const type        = TYPE[c.type]      || `Type ${c.type}`
  const statusColor = STATUS_COLOR[status] || 'var(--dim)'
  const value       = contractValue(c)
  const isInit      = String(c.inituid) === String(my_uid)
  const cpUid       = isInit ? c.otheruid : c.inituid
  const actions     = availableActions(c, my_uid)
  const needsAddress = (confirmAction === 'approve' || confirmAction === 'complete')

  return (
    <div style={{ display:'flex', flexDirection:'column', gap:14 }}>

      {/* Header */}
      <div style={{ display:'flex', alignItems:'center', gap:10 }}>
        <button className="btn btn-ghost" style={{ fontSize:11, padding:'4px 10px' }} onClick={() => nav(-1)}>← Back</button>
        <span style={{ fontSize:16, fontWeight:700, color:'var(--text)' }}>Contract #{cid}</span>
        <span style={{
          fontSize:11, fontWeight:600, padding:'2px 8px', borderRadius:3,
          background:`${statusColor}18`, color:statusColor, border:`1px solid ${statusColor}44`,
          fontFamily:'var(--mono)', marginLeft:'auto',
        }}>{status}</span>
        <a href={`https://hackforums.net/contracts.php?action=view&cid=${cid}`}
          target="_blank" rel="noreferrer"
          className="btn btn-ghost" style={{ fontSize:11, padding:'4px 10px' }}>
          View on HF →
        </a>
      </div>

      {/* Main info card */}
      <div className="card" style={{ padding:'16px 20px' }}>
        <div style={{ display:'grid', gridTemplateColumns:'repeat(auto-fit, minmax(min(180px,100%), 1fr))', gap:'12px 24px', fontSize:12 }}>
          {(() => {
            // istatus/ostatus only track deal START approval, not completion marking.
            // For Awaiting (1): show whether you've approved the contract.
            // For Active (5): both parties already approved to start — but "marking complete"
            //   is a separate action the API doesn't expose per-party, so we can't show it.
            // All other statuses: hide the field.
            const myApproval = isInit ? c.istatus : c.ostatus
            const approvalDisplay = c.status === '1'
              ? (myApproval === '1' ? '✓ Approved' : 'Pending')
              : null  // Active/Complete/Cancelled/Disputed/Expired: field not shown
            const fields = [
              ['Type',         type],
              ['Value',        value],
              ['Created',      ago(c.dateline)],
              ['Timeout',      c.timeout_days ? `${c.timeout_days} days` : '--'],
              ['Counterparty', counterparty_username ? `${counterparty_username} (UID ${cpUid})` : `UID ${cpUid || '--'}`],
              ['Public',       c.public === '1' ? 'Yes' : 'No'],
              ['Your role',    isInit ? 'Initiator' : 'Counterparty'],
              ...(approvalDisplay !== null ? [['Your approval', approvalDisplay]] : []),
            ]
            return fields
          })().map(([label, val]) => (
            <div key={label}>
              <div style={{ fontSize:9, color:'var(--dim)', textTransform:'uppercase', letterSpacing:'.07em', fontFamily:'var(--mono)', marginBottom:3 }}>{label}</div>
              <div style={{ color:'var(--text)', fontWeight:500 }}>{val}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Terms */}
      {c.terms && (
        <div className="card" style={{ padding:'14px 18px' }}>
          <div style={{ fontSize:10, color:'var(--dim)', textTransform:'uppercase', letterSpacing:'.07em', fontFamily:'var(--mono)', marginBottom:8 }}>Terms</div>
          <div style={{ fontSize:12.5, color:'var(--sub)', lineHeight:1.7, whiteSpace:'pre-wrap', wordBreak:'break-word' }}>{c.terms}</div>
        </div>
      )}

      {/* Dispute info */}
      {(c.idispute || c.odispute) && (
        <div className="card" style={{ padding:'14px 18px', borderColor:'var(--red)', background:'rgba(255,71,87,.04)' }}>
          <div style={{ fontSize:11, fontWeight:600, color:'var(--red)', marginBottom:8 }}>⚠ Dispute Active</div>
          {c.idispute?.claimantnotes && (
            <div style={{ fontSize:11.5, color:'var(--sub)', lineHeight:1.6 }}>
              <span style={{ color:'var(--dim)' }}>Claimant: </span>{c.idispute.claimantnotes}
            </div>
          )}
          {c.idispute?.defendantnotes && (
            <div style={{ fontSize:11.5, color:'var(--sub)', lineHeight:1.6, marginTop:4 }}>
              <span style={{ color:'var(--dim)' }}>Defendant: </span>{c.idispute.defendantnotes}
            </div>
          )}
        </div>
      )}

      {/* Actions */}
      {actions.length > 0 && (
        <div className="card" style={{ padding:'14px 18px' }}>
          <div style={{ fontSize:10, color:'var(--dim)', textTransform:'uppercase', letterSpacing:'.07em', fontFamily:'var(--mono)', marginBottom:12 }}>Actions</div>

          {actionResult && (
            <div style={{
              padding:'8px 12px', borderRadius:4, fontSize:12, marginBottom:10,
              background: actionResult.ok ? 'rgba(0,212,180,.06)' : 'rgba(255,71,87,.06)',
              border: `1px solid ${actionResult.ok ? 'rgba(0,212,180,.2)' : 'rgba(255,71,87,.2)'}`,
              color: actionResult.ok ? 'var(--acc)' : 'var(--red)',
            }}>
              {actionResult.message}
            </div>
          )}

          {confirmAction ? (
            <div style={{ display:'flex', flexDirection:'column', gap:10 }}>
              <div style={{ fontSize:12, color:'var(--yellow)' }}>
                Confirm <strong>{confirmAction}</strong> on contract #{cid}?
              </div>
              {needsAddress && (
                <div>
                  <div style={{ fontSize:10, color:'var(--dim)', fontFamily:'var(--mono)', marginBottom:4 }}>
                    Address / TX ID (optional)
                  </div>
                  <input className="inp" placeholder="Optional transaction ID or address"
                    value={address} onChange={e => setAddress(e.target.value)}
                    style={{ width:'100%' }}
                  />
                </div>
              )}
              <div style={{ display:'flex', gap:8 }}>
                <button className="btn btn-acc" style={{ fontSize:11 }}
                  disabled={!!acting} onClick={() => doAction(confirmAction)}>
                  {acting ? '…' : `Yes, ${confirmAction}`}
                </button>
                <button className="btn btn-ghost" style={{ fontSize:11 }}
                  onClick={() => { setConfirmAction(null); setAddress('') }}>
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <div style={{ display:'flex', gap:8, flexWrap:'wrap' }}>
              {actions.map(a => (
                <button key={a.action}
                  className={`btn ${a.cls}`}
                  style={{ fontSize:11 }}
                  disabled={!!acting}
                  onClick={() => a.confirm ? setConfirmAction(a.action) : doAction(a.action)}
                >
                  {a.label}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Thread link */}
      {c.tid && c.tid !== '0' && (
        <div style={{ fontSize:11, color:'var(--dim)' }}>
          Related thread:{' '}
          <a href={`https://hackforums.net/showthread.php?tid=${c.tid}`}
            target="_blank" rel="noreferrer" style={{ color:'var(--acc)' }}>
            #{c.tid} →
          </a>
        </div>
      )}
    </div>
  )
}
