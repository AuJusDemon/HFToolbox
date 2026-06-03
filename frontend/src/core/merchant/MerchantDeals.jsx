import { useEffect, useLayoutEffect, useState, useCallback, useRef } from 'react'
import { createPortal } from 'react-dom'
import { api } from '../api.js'
import useStore from '../../store.js'
import {
  contractStageLabel, contractStageColor,
  bucketLabel, contractTerms, relTime,
} from './merchantFormat.js'

// "In Progress" tab groups waiting_on_approval + active backend stages
const IN_PROGRESS_STAGES = new Set(['waiting_on_approval', 'active'])
const STALE_SECS = 90 * 86400

const STAGES = [
  { val: null,                       label: 'All' },
  { val: 'needs_review',             label: 'Needs Review' },
  { val: 'in_progress',              label: 'In Progress' },
  { val: 'waiting_on_counterparty',  label: 'Waiting on Counterparty' },
  { val: 'needs_rating',             label: 'Needs Rating' },
  { val: 'completed',                label: 'Completed' },
  { val: 'problem',                  label: 'Problem' },
]

const TYPE_LABEL = { '1':'Selling','2':'Purchasing','3':'Exchanging','4':'Trading','5':'Vouch Copy' }

function interpolate(text, deal) {
  if (!text) return ''
  const product = deal.iproduct || deal.oproduct || ''
  return text
    .replace(/\{username\}/g, deal.counterparty_username || '')
    .replace(/\{uid\}/g,      deal.counterparty_uid      || '')
    .replace(/\{cid\}/g,      deal.cid                   || '')
    .replace(/\{tid\}/g,      deal.tid                   || '')
    .replace(/\{thread\}/g,   deal.thread_title          || '')
    .replace(/\{product\}/g,  product)
}

// Re-classify a deal stage from a raw HF contract response (used after action write-through)
function reclassifyFromRefreshed(raw, myUid, completedSideAt) {
  const s     = String(raw.status || '')
  const dl    = parseInt(raw.dateline) || 0
  const now   = Math.floor(Date.now() / 1000)
  const init  = String(raw.inituid  || '')
  const other = String(raw.otheruid || '')
  const ist   = String(raw.istatus  || '')
  const ost   = String(raw.ostatus  || '')
  const isInit  = init  === String(myUid)
  const isOther = other === String(myUid)

  if (s === '0' || s === '1') {
    if (dl && (now - dl) > STALE_SECS) return 'problem'
    const myFlag    = isInit ? ist : (isOther ? ost : '')
    const theirFlag = isInit ? ost : (isOther ? ist : '')
    if (myFlag === '0') return 'needs_review'
    if (theirFlag === '0') return 'waiting_on_approval'
    return isOther ? 'needs_review' : 'waiting_on_approval'
  }
  if (s === '5') return completedSideAt ? 'waiting_on_counterparty' : 'active'
  // For status 6, needs_rating depends on local DB brating data — defer to background fetchDeals
  if (s === '6') return 'completed'
  return 'problem'
}

// ── Overlay ───────────────────────────────────────────────────────────────────
function Backdrop({ onClose, children, maxWidth = 560 }) {
  // Lock body scroll before paint so the page never jumps when the modal opens
  useLayoutEffect(() => {
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = prev }
  }, [])

  useEffect(() => {
    const handler = e => { if (e.key === 'Escape') onClose() }
    document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [onClose])

  // Portal to document.body so the fixed overlay escapes .content's transform:translateY(0)
  // (the .up animation uses fill-mode:forwards which permanently makes .content a fixed
  // containing block, clipping any position:fixed child to the content height)
  return createPortal(
    <div
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,.72)',
        zIndex: 9999, overflowY: 'auto',
      }}
      onClick={onClose}
    >
      <div style={{
        minHeight: '100%', padding: '16px 12px', boxSizing: 'border-box',
        display: 'flex', alignItems: 'flex-start', justifyContent: 'center',
      }}>
        <div
          style={{
            background: 'var(--s2)', border: '1px solid var(--b2)',
            width: '100%', maxWidth, padding: '16px 18px',
            marginTop: 8, marginBottom: 16,
          }}
          onClick={e => e.stopPropagation()}
        >
          {children}
        </div>
      </div>
    </div>,
    document.body
  )
}

function ModalHeader({ title, onClose }) {
  return (
    <div style={{ display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom: 12 }}>
      <span style={{ fontFamily:'var(--mono)', fontSize:12, color:'var(--sub)', textTransform:'uppercase', letterSpacing:'.08em' }}>
        {title}
      </span>
      <button className="btn btn-sm" onClick={onClose}>Close</button>
    </div>
  )
}

// ── Progress steps ────────────────────────────────────────────────────────────
function ProgressBar({ stage, status_n }) {
  const s = String(status_n || '')
  const steps = [
    { key: 'review',    label: 'Review',       done: !['0','1'].includes(s) },
    { key: 'active',    label: 'Active',        done: ['5','6'].includes(s) },
    { key: 'my_side',   label: 'My Side',       done: stage === 'waiting_on_counterparty' || s === '6' },
    { key: 'complete',  label: 'Complete',      done: s === '6' },
    { key: 'rated',     label: 'Rated',         done: stage === 'completed' },
  ]
  const currentIdx = steps.findLastIndex(st => st.done)

  return (
    <div style={{ display:'flex', alignItems:'center', gap:0, marginBottom: 14 }}>
      {steps.map((st, i) => {
        const isCurrent = i === currentIdx + 1
        const isDone    = st.done
        return (
          <div key={st.key} style={{ display:'flex', alignItems:'center', flex: i < steps.length - 1 ? 1 : 0 }}>
            <div style={{
              display:'flex', flexDirection:'column', alignItems:'center', gap: 3,
            }}>
              <div style={{
                width: 18, height: 18, borderRadius: '50%', flexShrink: 0,
                border: `2px solid ${isDone ? 'var(--acc)' : isCurrent ? 'var(--yellow)' : 'var(--b2)'}`,
                background: isDone ? 'var(--acc)' : 'transparent',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                {isDone && (
                  <span style={{ fontSize: 9, color: 'var(--bg)', fontWeight: 700 }}>✓</span>
                )}
              </div>
              <span style={{
                fontSize: 8.5, fontFamily: 'var(--mono)', color: isDone ? 'var(--acc)' : isCurrent ? 'var(--yellow)' : 'var(--dim)',
                textTransform: 'uppercase', letterSpacing: '.05em', whiteSpace: 'nowrap',
              }}>
                {st.label}
              </span>
            </div>
            {i < steps.length - 1 && (
              <div style={{
                flex: 1, height: 2, background: isDone ? 'var(--acc)' : 'var(--b2)',
                margin: '0 4px', marginBottom: 15,
              }}/>
            )}
          </div>
        )
      })}
    </div>
  )
}

// ── Payment info section ──────────────────────────────────────────────────────
function PaymentInfo({ iaddr, oaddr, isPending }) {
  const [copied, setCopied] = useState('')
  const copy = (text, key) => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(key); setTimeout(() => setCopied(''), 2000)
    }).catch(() => {})
  }

  if (isPending) {
    return (
      <div style={{ fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)', fontStyle: 'italic' }}>
        Payment info hidden until both parties approve.
      </div>
    )
  }

  if (!iaddr && !oaddr) {
    return (
      <div style={{ fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)' }}>
        No payment info returned by HF.{' '}
        <a
          href={`https://hackforums.net/contracts.php?action=view&cid=${deal.cid}`}
          target="_blank" rel="noopener noreferrer"
          style={{ color: 'var(--acc)' }}
        >
          View on HF
        </a>
      </div>
    )
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
      {iaddr && (
        <div>
          <div style={{ fontSize: 9, color: 'var(--dim)', fontFamily: 'var(--mono)', textTransform: 'uppercase', letterSpacing: '.07em', marginBottom: 3 }}>
            Initiator payment info
          </div>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <input
              className="inp" readOnly
              style={{ flex: 1, fontSize: 11, fontFamily: 'var(--mono)' }}
              value={iaddr}
            />
            <button className="btn btn-sm" style={{ flexShrink: 0 }} onClick={() => copy(iaddr, 'iaddr')}>
              {copied === 'iaddr' ? 'Copied!' : 'Copy'}
            </button>
          </div>
        </div>
      )}
      {oaddr && (
        <div>
          <div style={{ fontSize: 9, color: 'var(--dim)', fontFamily: 'var(--mono)', textTransform: 'uppercase', letterSpacing: '.07em', marginBottom: 3 }}>
            Counterparty payment info
          </div>
          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
            <input
              className="inp" readOnly
              style={{ flex: 1, fontSize: 11, fontFamily: 'var(--mono)' }}
              value={oaddr}
            />
            <button className="btn btn-sm" style={{ flexShrink: 0 }} onClick={() => copy(oaddr, 'oaddr')}>
              {copied === 'oaddr' ? 'Copied!' : 'Copy'}
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Contract Modal ────────────────────────────────────────────────────────────
function ContractModal({ deal, myUid, templates, onClose, onActionSuccess, onOpenTemplates }) {
  // liveDetail holds data from a manual "Sync from HF" — null until user requests it
  const [liveDetail,   setLiveDetail]   = useState(null)
  const [syncing,      setSyncing]      = useState(false)
  const [confirmAction, setConfirmAction] = useState(null)
  const [acting,        setActing]        = useState(null)
  const [actionResult,  setActionResult]  = useState(null)
  const [address,       setAddress]       = useState('')
  const [followUpOpen,  setFollowUpOpen]  = useState(false)
  const [fuTid,         setFuTid]         = useState('')
  const [fuCopied,      setFuCopied]      = useState('')

  // Manual sync — spends 1 HF read, only on explicit user request
  const doSync = () => {
    setSyncing(true)
    api.get(`/api/contracts/${deal.cid}?force=true`)
      .then(d => { setLiveDetail(d); setSyncing(false) })
      .catch(() => setSyncing(false))
  }

  const hfUrl    = `https://hackforums.net/contracts.php?action=view&cid=${deal.cid}`
  const pmUrl    = deal.counterparty_uid
    ? `https://hackforums.net/private.php?action=send&uid=${deal.counterparty_uid}`
    : null
  const convoUrl = deal.counterparty_uid
    ? `https://hackforums.net/convo.php?id=${deal.counterparty_uid}`
    : null

  // Prefer liveDetail (after manual sync) over local deal data
  const live     = liveDetail?.contract
  const sc       = contractStageColor(deal.stage)
  const product  = deal.iproduct || deal.oproduct || '—'
  const type     = TYPE_LABEL[live?.type || deal.type_n] || '—'
  const terms    = live?.terms    || deal.terms    || ''
  const idispute = live?.idispute || deal.idispute || null
  const odispute = live?.odispute || deal.odispute || null
  const cpName   = deal.counterparty_username || `UID ${deal.counterparty_uid}` || '?'
  const terms_val = contractTerms(deal)

  const doAction = async (action) => {
    setActing(action)
    setActionResult(null)
    try {
      const res = await api.post(`/api/contracts/${deal.cid}/action`, { action, address })
      if (!res) {
        setActionResult({ ok: false, message: 'No response - action may not have completed.' })
      } else {
        setActionResult({ ok: true, message: `${action} completed.` })
        if (action === 'complete') {
          await api.post(`/api/merchant/contracts/${deal.cid}/complete-side`, {})
        }
        // Immediately update using the write-through refreshed data
        if (res.refreshed) {
          const newStage = reclassifyFromRefreshed(
            res.refreshed, myUid,
            action === 'complete' ? Date.now() / 1000 : deal.completed_side_at
          )
          onActionSuccess(deal.cid, res.refreshed, newStage)
        }
        setTimeout(() => setActionResult(null), 3000)
      }
    } catch (e) {
      setActionResult({ ok: false, message: e.message || 'Unknown error.' })
    }
    setActing(null)
    setConfirmAction(null)
    setAddress('')
  }

  // Follow-up section (inline in modal, not a separate overlay)
  const fuTemplate   = templates.find(t => t.template_id === fuTid) || null
  const fuSubject    = fuTemplate ? interpolate(fuTemplate.subject, deal) : ''
  const fuBody       = fuTemplate ? interpolate(fuTemplate.body,    deal) : ''
  const fuPmUrl      = pmUrl && fuTemplate
    ? `${pmUrl}&subject=${encodeURIComponent(fuSubject)}`
    : pmUrl

  const copyFu = (text, key) => {
    navigator.clipboard.writeText(text).then(() => {
      setFuCopied(key); setTimeout(() => setFuCopied(''), 2000)
    }).catch(() => {})
  }

  const canAct = {
    approve: deal.stage === 'needs_review',
    deny:    deal.stage === 'needs_review',
    complete: deal.stage === 'active',
  }

  const renderActions = () => (
    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
      {canAct.approve && (
        <button className="btn btn-sm btn-acc" disabled={!!acting}
          onClick={() => setConfirmAction('approve')}>
          Approve
        </button>
      )}
      {canAct.deny && (
        <button className="btn btn-sm btn-danger" disabled={!!acting}
          onClick={() => setConfirmAction('deny')}>
          Deny
        </button>
      )}
      {canAct.complete && (
        <button className="btn btn-sm btn-acc" disabled={!!acting}
          onClick={() => setConfirmAction('complete')}>
          Mark My Side Complete
        </button>
      )}
      {(deal.stage === 'active' || deal.stage === 'waiting_on_counterparty' || deal.stage === 'waiting_on_approval') && (
        <button className="btn btn-sm" onClick={() => setFollowUpOpen(o => !o)}>
          {followUpOpen ? 'Hide Follow Up' : 'Follow Up'}
        </button>
      )}
      <a href={hfUrl} target="_blank" rel="noopener noreferrer" className="btn btn-sm">
        View on HF
      </a>
      {pmUrl    && <a href={pmUrl}    target="_blank" rel="noopener noreferrer" className="btn btn-sm">PM</a>}
      {convoUrl && <a href={convoUrl} target="_blank" rel="noopener noreferrer" className="btn btn-sm">Convo</a>}
      {deal.stage === 'needs_rating' && (
        <a href={hfUrl} target="_blank" rel="noopener noreferrer" className="btn btn-sm" style={{ color: 'var(--blue, #4b8cf5)' }}>
          Leave Rating on HF
        </a>
      )}
      <button
        className="btn btn-sm btn-ghost"
        style={{ marginLeft: 'auto', fontSize: 10, opacity: .65 }}
        disabled={syncing}
        onClick={doSync}
      >
        {syncing ? '…' : 'Sync from HF'}
      </button>
    </div>
  )

  return (
    <Backdrop onClose={onClose} maxWidth={580}>
      <ModalHeader title={`Contract #${deal.cid}`} onClose={onClose} />

      {/* Status / counterparty header */}
      <div style={{
        display: 'flex', gap: 10, alignItems: 'flex-start', marginBottom: 12,
        padding: '10px 12px', background: 'var(--s1)', borderLeft: `3px solid ${sc}`,
      }}>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ display: 'flex', gap: 8, alignItems: 'baseline', flexWrap: 'wrap', marginBottom: 2 }}>
            <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--text)' }}>{cpName}</span>
            {deal.counterparty_username && deal.counterparty_uid && (
              <span style={{ fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)' }}>
                UID {deal.counterparty_uid}
              </span>
            )}
          </div>
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
            <span style={{ fontSize: 10, fontFamily: 'var(--mono)', color: sc }}>
              {contractStageLabel(deal.stage)}
            </span>
            {type !== '—' && (
              <span style={{ fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)' }}>{type}</span>
            )}
            {terms_val !== 'terms not recorded' && (
              <span style={{ fontSize: 10, color: 'var(--sub)', fontFamily: 'var(--mono)' }}>{terms_val}</span>
            )}
            <span style={{ fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)', marginLeft: 'auto' }}>
              {relTime(deal.dateline)}
            </span>
          </div>
        </div>
      </div>

      {/* Progress bar */}
      <ProgressBar stage={deal.stage} status_n={deal.status_n} />

      {/* Product / obligations */}
      {(deal.iproduct || deal.oproduct || deal.iprice || deal.oprice) && (
        <div style={{
          display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8, marginBottom: 12,
        }}>
          {[
            { label: 'Initiator provides', prod: deal.iproduct, price: deal.iprice, cur: deal.icurrency },
            { label: 'Counterparty provides', prod: deal.oproduct, price: deal.oprice, cur: deal.ocurrency },
          ].map(({ label, prod, price, cur }) => {
            const val = (price && price !== '0' && cur && cur.toLowerCase() !== 'other')
              ? `${price} ${cur}`
              : (prod && prod !== 'other' && prod !== 'n/a') ? prod : null
            if (!val) return null
            return (
              <div key={label} style={{ background: 'var(--s1)', padding: '8px 10px' }}>
                <div style={{ fontSize: 9, color: 'var(--dim)', fontFamily: 'var(--mono)', textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 4 }}>
                  {label}
                </div>
                <div style={{ fontSize: 11, color: 'var(--text)', fontFamily: 'var(--mono)', wordBreak: 'break-word' }}>
                  {val.length > 80 ? val.slice(0, 77) + '…' : val}
                </div>
              </div>
            )
          })}
        </div>
      )}

      {/* Payment info */}
      {(deal.stage === 'active' || deal.stage === 'waiting_on_counterparty' ||
        deal.stage === 'needs_rating' || deal.stage === 'completed') && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 9, color: 'var(--dim)', fontFamily: 'var(--mono)', textTransform: 'uppercase', letterSpacing: '.07em', marginBottom: 6 }}>
            Payment Info
          </div>
          <PaymentInfo
            iaddr={live?.iaddress || deal.iaddress || ''}
            oaddr={live?.oaddress || deal.oaddress || ''}
            isPending={false}
          />
        </div>
      )}

      {/* Dispute info */}
      {(idispute || odispute) && (
        <div style={{ padding: '10px 12px', marginBottom: 12, borderLeft: '3px solid var(--red)', background: 'rgba(255,71,87,.03)' }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: 'var(--red)', marginBottom: 6 }}>Dispute Active</div>
          {idispute?.claimantnotes && (
            <div style={{ fontSize: 11, color: 'var(--sub)', lineHeight: 1.5 }}>
              <span style={{ color: 'var(--dim)' }}>Claimant: </span>{idispute.claimantnotes}
            </div>
          )}
          {idispute?.defendantnotes && (
            <div style={{ fontSize: 11, color: 'var(--sub)', lineHeight: 1.5, marginTop: 4 }}>
              <span style={{ color: 'var(--dim)' }}>Defendant: </span>{idispute.defendantnotes}
            </div>
          )}
        </div>
      )}

      {/* Terms */}
      {terms && (
        <div style={{ marginBottom: 12 }}>
          <div style={{ fontSize: 9, color: 'var(--dim)', fontFamily: 'var(--mono)', textTransform: 'uppercase', letterSpacing: '.07em', marginBottom: 5 }}>
            Terms
          </div>
          <div style={{
            fontSize: 11, color: 'var(--sub)', lineHeight: 1.6,
            whiteSpace: 'pre-wrap', wordBreak: 'break-word',
            maxHeight: 120, overflowY: 'auto',
            padding: '8px 10px', background: 'var(--s1)',
          }}>
            {terms}
          </div>
        </div>
      )}

      {/* Thread link */}
      {deal.tid && deal.tid !== '0' && (
        <div style={{ fontSize: 10, color: 'var(--dim)', marginBottom: 10 }}>
          Thread:{' '}
          {deal.thread_title
            ? <a href={`https://hackforums.net/showthread.php?tid=${deal.tid}`}
                target="_blank" rel="noopener noreferrer" style={{ color: 'var(--acc)' }}>
                {deal.thread_title.slice(0, 50)}
              </a>
            : <a href={`https://hackforums.net/showthread.php?tid=${deal.tid}`}
                target="_blank" rel="noopener noreferrer" style={{ color: 'var(--acc)' }}>
                #{deal.tid}
              </a>
          }
        </div>
      )}

      {/* Received rating */}
      {deal.has_received_rating && (
        <div style={{
          fontSize: 11, fontFamily: 'var(--mono)', color: 'var(--acc)',
          padding: '6px 10px', background: 'rgba(0,212,180,.05)',
          border: '1px solid rgba(0,212,180,.18)', marginBottom: 10,
        }}>
          Rating received: {deal.received_rating_amount > 0 ? '+' : ''}{deal.received_rating_amount}
          {deal.received_rating_from_username
            ? ` from ${deal.received_rating_from_username}`
            : deal.received_rating_from_uid
              ? ` from UID ${deal.received_rating_from_uid}`
              : ''
          }
          {deal.received_rating_message
            ? <span style={{ color: 'var(--sub)' }}> — {deal.received_rating_message}</span>
            : null
          }
        </div>
      )}

      {/* Action result */}
      {actionResult && (
        <div style={{
          padding: '7px 10px', fontSize: 11, marginBottom: 10, fontFamily: 'var(--mono)',
          background: actionResult.ok ? 'rgba(0,212,180,.06)' : 'rgba(255,71,87,.06)',
          border: `1px solid ${actionResult.ok ? 'rgba(0,212,180,.2)' : 'rgba(255,71,87,.2)'}`,
          color: actionResult.ok ? 'var(--acc)' : 'var(--red)',
        }}>
          {actionResult.message}
        </div>
      )}

      {/* Confirm bar */}
      {confirmAction ? (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 10 }}>
          <div style={{ fontSize: 12, color: 'var(--yellow)', fontFamily: 'var(--mono)' }}>
            Confirm <strong>{confirmAction}</strong> on contract #{deal.cid}?
          </div>
          {(confirmAction === 'approve' || confirmAction === 'complete') && (
            <input
              className="inp"
              placeholder="Address / TX ID (optional)"
              value={address}
              onChange={e => setAddress(e.target.value)}
              style={{ fontSize: 12 }}
            />
          )}
          <div style={{ display: 'flex', gap: 6 }}>
            <button className="btn btn-sm btn-acc" disabled={!!acting} onClick={() => doAction(confirmAction)}>
              {acting ? '…' : `Confirm ${confirmAction}`}
            </button>
            <button className="btn btn-sm" onClick={() => { setConfirmAction(null); setAddress('') }}>
              Cancel
            </button>
          </div>
        </div>
      ) : (
        renderActions()
      )}

      {/* Follow-up inline panel */}
      {followUpOpen && !confirmAction && (
        <div style={{ marginTop: 12, padding: '10px 12px', background: 'var(--s1)', borderTop: '1px solid var(--b2)' }}>
          <div style={{ fontSize: 9, color: 'var(--dim)', fontFamily: 'var(--mono)', textTransform: 'uppercase', letterSpacing: '.07em', marginBottom: 8 }}>
            Follow Up
          </div>
          {templates.length === 0 ? (
            <div style={{ fontSize: 11, color: 'var(--dim)', fontFamily: 'var(--mono)' }}>
              No templates.{' '}
              <button className="btn btn-sm" style={{ padding: '2px 7px' }} onClick={onOpenTemplates}>
                Create
              </button>
            </div>
          ) : (
            <>
              <select
                className="inp"
                style={{ width: '100%', boxSizing: 'border-box', fontSize: 12, marginBottom: 8 }}
                value={fuTid}
                onChange={e => setFuTid(e.target.value)}
              >
                <option value="">— select template —</option>
                {templates.map(t => (
                  <option key={t.template_id} value={t.template_id}>{t.name}</option>
                ))}
              </select>
              {fuTemplate && (
                <>
                  <textarea
                    className="inp" readOnly
                    style={{ width: '100%', boxSizing: 'border-box', fontSize: 11, minHeight: 80, resize: 'vertical', marginBottom: 8 }}
                    value={fuBody}
                  />
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                    {fuPmUrl && (
                      <a href={fuPmUrl} target="_blank" rel="noopener noreferrer" className="btn btn-sm btn-acc">
                        Open PM
                      </a>
                    )}
                    {convoUrl && (
                      <a href={convoUrl} target="_blank" rel="noopener noreferrer" className="btn btn-sm">
                        Open Convo
                      </a>
                    )}
                    <button className="btn btn-sm" onClick={() => copyFu(fuBody, 'body')}>
                      {fuCopied === 'body' ? 'Copied!' : 'Copy Body'}
                    </button>
                  </div>
                </>
              )}
            </>
          )}
        </div>
      )}
    </Backdrop>
  )
}

// ── PM Templates Modal ────────────────────────────────────────────────────────
function PMTemplatesModal({ templates, onClose, onRefresh }) {
  const [selected, setSelected]           = useState(null)
  const [name, setName]                   = useState('')
  const [subject, setSubject]             = useState('')
  const [body, setBody]                   = useState('')
  const [saving, setSaving]               = useState(false)
  const [deleting, setDeleting]           = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [error, setError]                 = useState('')

  const isNew = selected === '__new__'

  const selectTemplate = (tid) => {
    setSelected(tid)
    setConfirmDelete(false)
    setError('')
    if (tid === '__new__') {
      setName(''); setSubject(''); setBody('')
    } else {
      const t = templates.find(t => t.template_id === tid)
      if (t) { setName(t.name || ''); setSubject(t.subject || ''); setBody(t.body || '') }
    }
  }

  const save = () => {
    if (!name.trim()) { setError('Name is required'); return }
    setSaving(true); setError('')
    const payload = { name: name.trim(), subject: subject.trim(), body: body.trim() }
    const req = isNew
      ? api.post('/api/merchant/pm-templates', payload)
      : api.patch(`/api/merchant/pm-templates/${selected}`, payload)
    req
      .then(res => {
        setSaving(false)
        if (isNew && res?.template_id) setSelected(res.template_id)
        onRefresh()
      })
      .catch(err => { setSaving(false); setError(err?.message || 'Save failed') })
  }

  const doDelete = () => {
    if (!selected || isNew) return
    setDeleting(true)
    api.delete(`/api/merchant/pm-templates/${selected}`)
      .then(() => {
        setDeleting(false); setSelected(null)
        setName(''); setSubject(''); setBody('')
        setConfirmDelete(false); onRefresh()
      })
      .catch(() => { setDeleting(false); setError('Delete failed') })
  }

  return (
    <Backdrop onClose={onClose}>
      <div style={{ maxWidth: 520, margin: '0 auto' }}>
        <ModalHeader title="PM Templates" onClose={onClose} />
        <div style={{ display: 'flex', gap: 6, marginBottom: 10, flexWrap: 'wrap' }}>
          {templates.map(t => (
            <button
              key={t.template_id}
              className={`btn btn-sm${selected === t.template_id ? ' btn-acc' : ''}`}
              onClick={() => selectTemplate(t.template_id)}
            >
              {t.name}
            </button>
          ))}
          <button
            className="btn btn-sm"
            style={selected === '__new__' ? { borderColor: 'var(--acc)', color: 'var(--acc)' } : {}}
            onClick={() => selectTemplate('__new__')}
          >
            + New Template
          </button>
        </div>
        {selected && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {error && <div style={{ fontSize: 11, color: 'var(--red)', fontFamily: 'var(--mono)' }}>{error}</div>}
            <input className="inp" style={{ width: '100%', boxSizing: 'border-box', fontSize: 12 }}
              placeholder="Template name…" value={name} onChange={e => setName(e.target.value)} />
            <input className="inp" style={{ width: '100%', boxSizing: 'border-box', fontSize: 12 }}
              placeholder="Subject… (e.g. Follow up on contract #{cid})"
              value={subject} onChange={e => setSubject(e.target.value)} />
            <textarea className="inp"
              style={{ width: '100%', boxSizing: 'border-box', fontSize: 12, minHeight: 140, resize: 'vertical' }}
              placeholder={'Body… Placeholders: {username} {uid} {cid} {tid} {thread} {product}'}
              value={body} onChange={e => setBody(e.target.value)} />
            <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
              <button className="btn btn-sm" disabled={saving} onClick={save}>
                {saving ? 'Saving…' : 'Save'}
              </button>
              {!isNew && (
                confirmDelete ? (
                  <>
                    <span style={{ fontSize: 11, color: 'var(--red)', fontFamily: 'var(--mono)' }}>
                      Delete this template?
                    </span>
                    <button className="btn btn-sm btn-danger" disabled={deleting} onClick={doDelete}>
                      {deleting ? '…' : 'Confirm'}
                    </button>
                    <button className="btn btn-sm" onClick={() => setConfirmDelete(false)}>Cancel</button>
                  </>
                ) : (
                  <button className="btn btn-sm btn-danger" onClick={() => setConfirmDelete(true)}>Delete</button>
                )
              )}
            </div>
          </div>
        )}
        {!selected && templates.length === 0 && (
          <div style={{ fontSize: 11, color: 'var(--dim)', fontFamily: 'var(--mono)' }}>
            No templates yet. Click <strong>+ New Template</strong> to create one.
          </div>
        )}
      </div>
    </Backdrop>
  )
}

// ── Contract card ─────────────────────────────────────────────────────────────
function DealCard({ deal, onClick }) {
  const sc         = contractStageColor(deal.stage)
  const product    = deal.iproduct || deal.oproduct || ''
  const isDisputed = deal.status_n === '7'

  const badgeLabel = deal.stage === 'problem'
    ? bucketLabel(deal.bucket)
    : contractStageLabel(deal.stage)

  const borderColor = isDisputed ? 'var(--red)' : sc

  return (
    <div
      onClick={onClick}
      style={{
        background:   isDisputed ? 'rgba(255,71,87,.03)' : 'var(--s1)',
        padding:      '10px 13px',
        marginBottom: 3,
        borderLeft:   `3px solid ${borderColor}`,
        cursor:       'pointer',
      }}
      onMouseOver={e => e.currentTarget.style.filter = 'brightness(1.14)'}
      onMouseOut={e  => e.currentTarget.style.filter = 'none'}
    >
      <div style={{ display: 'flex', gap: 8, alignItems: 'baseline', marginBottom: 2, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 11, fontFamily: 'var(--mono)', color: 'var(--acc)', flexShrink: 0 }}>
          #{deal.cid}
        </span>
        <span style={{ fontSize: 12, color: 'var(--text)' }}>
          {deal.counterparty_username || `UID ${deal.counterparty_uid}` || '?'}
        </span>
        {deal.counterparty_username && deal.counterparty_uid && (
          <span style={{ fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)' }}>
            UID {deal.counterparty_uid}
          </span>
        )}
        <span style={{
          fontSize: 9, fontFamily: 'var(--mono)', color: borderColor,
          marginLeft: 'auto', flexShrink: 0,
          ...(isDisputed ? { fontWeight: 700 } : {}),
        }}>
          {badgeLabel}{isDisputed ? ' !' : ''}
        </span>
      </div>

      {product && (
        <div style={{
          fontSize: 11, color: 'var(--sub)',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
          marginBottom: 2,
        }}>
          {product.length > 65 ? product.slice(0, 62) + '…' : product}
        </div>
      )}

      <div style={{ display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
        {deal.thread_title && (
          <span style={{
            fontSize: 10, color: 'var(--dim)', overflow: 'hidden',
            textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1,
          }}>
            {deal.thread_title.slice(0, 50)}
          </span>
        )}
        <span style={{ fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)', flexShrink: 0, marginLeft: 'auto' }}>
          {relTime(deal.dateline)}
        </span>
      </div>
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────
export default function MerchantDeals() {
  const myUid = useStore(s => s.user?.uid)

  const [allDeals, setAllDeals]                     = useState([])
  const [loading, setLoading]                       = useState(true)
  const [stage, setStage]                           = useState(null)
  const [templates, setTemplates]                   = useState([])
  const [showTemplatesModal, setShowTemplatesModal] = useState(false)
  const [modalDeal, setModalDeal]                   = useState(null)
  const [actionBanner, setActionBanner]             = useState(null)

  const fetchDeals = useCallback(() => {
    setLoading(true)
    api.get('/api/merchant/deals')
      .then(d => { setAllDeals(Array.isArray(d) ? d : []); setLoading(false) })
      .catch(() => setLoading(false))
  }, [])

  const fetchTemplates = useCallback(() => {
    api.get('/api/merchant/pm-templates')
      .then(d => setTemplates(Array.isArray(d) ? d : []))
      .catch(() => {})
  }, [])

  useEffect(() => {
    fetchDeals()
    fetchTemplates()
    // Sync received ratings in background; only re-fetch deals if server got fresh data
    // (server caches for 15 min, so this avoids HF calls on every tab open)
    api.post('/api/merchant/ratings/refresh', {})
      .then(d => { if (d && !d.cached) fetchDeals() })
      .catch(() => {})
  }, [fetchDeals, fetchTemplates])

  // Counts: in_progress groups active + waiting_on_approval
  const rawCounts = allDeals.reduce((acc, d) => {
    acc[d.stage] = (acc[d.stage] || 0) + 1
    return acc
  }, {})
  const counts = {
    ...rawCounts,
    in_progress: (rawCounts.active || 0) + (rawCounts.waiting_on_approval || 0),
  }

  const visible = stage === 'in_progress'
    ? allDeals.filter(d => IN_PROGRESS_STAGES.has(d.stage))
    : stage
      ? allDeals.filter(d => d.stage === stage)
      : allDeals

  const handleActionSuccess = useCallback((cid, refreshed, newStage) => {
    setAllDeals(prev => prev.map(d => {
      if (d.cid !== String(cid)) return d
      return {
        ...d,
        status_n:   refreshed.status   || d.status_n,
        istatus:    refreshed.istatus  || d.istatus,
        ostatus:    refreshed.ostatus  || d.ostatus,
        iaddress:   refreshed.iaddress || d.iaddress,
        oaddress:   refreshed.oaddress || d.oaddress,
        brating:    refreshed.brating  || d.brating,
        stage:      newStage,
        bucket:     newStage === 'problem' ? d.bucket : d.bucket,
      }
    }))
    // Also update the open modal's deal data
    setModalDeal(prev => {
      if (!prev || prev.cid !== String(cid)) return prev
      return {
        ...prev,
        status_n:   refreshed.status   || prev.status_n,
        istatus:    refreshed.istatus  || prev.istatus,
        ostatus:    refreshed.ostatus  || prev.ostatus,
        iaddress:   refreshed.iaddress || prev.iaddress,
        oaddress:   refreshed.oaddress || prev.oaddress,
        brating:    refreshed.brating  || prev.brating,
        stage:      newStage,
      }
    })
    // Background sync to keep list consistent
    setTimeout(fetchDeals, 2000)
  }, [fetchDeals])

  return (
    <div>
      {/* Stage filter tabs + PM Templates button */}
      <div style={{ display:'flex', gap:4, marginBottom:12, flexWrap:'wrap', alignItems:'center' }}>
        <div style={{ display:'flex', gap:4, overflowX:'auto', whiteSpace:'nowrap', flex:1 }}>
          {STAGES.map(s => {
            const cnt = s.val ? counts[s.val] ?? 0 : allDeals.length
            return (
              <button
                key={s.val || 'all'}
                className={`tab${stage === s.val ? ' on' : ''}`}
                onClick={() => setStage(s.val)}
              >
                {s.label}{!loading && cnt > 0 ? ` (${cnt})` : ''}
              </button>
            )
          })}
        </div>
        <button
          className="btn btn-sm"
          style={{ flexShrink: 0 }}
          onClick={() => setShowTemplatesModal(true)}
        >
          PM Templates
        </button>
      </div>

      {/* Global action banner (from closed modal) */}
      {actionBanner && (
        <div style={{
          padding:'8px 12px', fontSize:11, marginBottom:8, fontFamily:'var(--mono)',
          background:'rgba(0,212,180,.06)', border:'1px solid rgba(0,212,180,.2)',
          color:'var(--acc)',
        }}>
          {actionBanner}
        </div>
      )}

      {/* Contract queue */}
      {loading
        ? <div className="empty"><div className="spin" /></div>
        : visible.length === 0
          ? <div className="empty" style={{ color:'var(--dim)' }}>No contracts found.</div>
          : visible.map(d => (
              <DealCard
                key={d.cid}
                deal={d}
                onClick={() => setModalDeal(d)}
              />
            ))
      }

      {/* Contract modal */}
      {modalDeal && (
        <ContractModal
          deal={modalDeal}
          myUid={myUid}
          templates={templates}
          onClose={() => setModalDeal(null)}
          onActionSuccess={handleActionSuccess}
          onOpenTemplates={() => { setModalDeal(null); setShowTemplatesModal(true) }}
        />
      )}

      {/* PM Templates modal */}
      {showTemplatesModal && (
        <PMTemplatesModal
          templates={templates}
          onClose={() => setShowTemplatesModal(false)}
          onRefresh={fetchTemplates}
        />
      )}
    </div>
  )
}
