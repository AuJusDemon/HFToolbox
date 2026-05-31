import { useEffect, useState } from 'react'
import { api } from '../api.js'
import { bucketLabel, bucketColor, contractTerms, relTime } from './merchantFormat.js'

const BUCKETS = [
  { val: null,                 label: 'All' },
  { val: 'awaiting_approval',  label: 'Awaiting Approval' },
  { val: 'active_fulfillment', label: 'Active' },
  { val: 'completed',          label: 'Completed' },
  { val: 'cancelled',          label: 'Cancelled' },
  { val: 'disputed',           label: 'Disputed' },
  { val: 'expired',            label: 'Expired' },
]

function interpolate(text, contract) {
  if (!text) return ''
  const product = contract.iproduct || contract.oproduct || ''
  return text
    .replace(/\{username\}/g, contract.counterparty_username || '')
    .replace(/\{uid\}/g,      contract.counterparty_uid      || '')
    .replace(/\{cid\}/g,      contract.cid                   || '')
    .replace(/\{tid\}/g,      contract.tid                   || '')
    .replace(/\{thread\}/g,   contract.thread_title          || '')
    .replace(/\{product\}/g,  product)
}

// ── Overlay backdrop ──────────────────────────────────────────────────────────
function Backdrop({ onClose, children }) {
  return (
    <div
      style={{
        position: 'fixed', inset: 0, background: 'rgba(0,0,0,.65)',
        zIndex: 9999, display: 'flex', alignItems: 'center',
        justifyContent: 'center', padding: 16,
      }}
      onClick={onClose}
    >
      <div
        style={{
          background: 'var(--s2)', border: '1px solid var(--b2)',
          width: '100%', padding: '16px 18px',
        }}
        onClick={e => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  )
}

function ModalHeader({ title, onClose }) {
  return (
    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
      <span style={{
        fontFamily: 'var(--mono)', fontSize: 12, color: 'var(--sub)',
        textTransform: 'uppercase', letterSpacing: '.08em',
      }}>
        {title}
      </span>
      <button className="btn btn-sm" onClick={onClose}>Close</button>
    </div>
  )
}

// ── PM Templates Modal ────────────────────────────────────────────────────────
function PMTemplatesModal({ templates, onClose, onRefresh }) {
  const [selected, setSelected]       = useState(null)
  const [name, setName]               = useState('')
  const [subject, setSubject]         = useState('')
  const [body, setBody]               = useState('')
  const [saving, setSaving]           = useState(false)
  const [deleting, setDeleting]       = useState(false)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const [error, setError]             = useState('')

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
    setSaving(true)
    setError('')
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
        setDeleting(false)
        setSelected(null)
        setName(''); setSubject(''); setBody('')
        setConfirmDelete(false)
        onRefresh()
      })
      .catch(() => { setDeleting(false); setError('Delete failed') })
  }

  return (
    <Backdrop onClose={onClose}>
      <div style={{ maxWidth: 520, margin: '0 auto' }}>
        <ModalHeader title="PM Templates" onClose={onClose} />

        {/* Template pill list */}
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

        {/* Edit form */}
        {selected && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {error && (
              <div style={{ fontSize: 11, color: 'var(--red)', fontFamily: 'var(--mono)' }}>{error}</div>
            )}
            <input
              className="inp" style={{ width: '100%', boxSizing: 'border-box', fontSize: 12 }}
              placeholder="Template name…"
              value={name} onChange={e => setName(e.target.value)}
            />
            <input
              className="inp" style={{ width: '100%', boxSizing: 'border-box', fontSize: 12 }}
              placeholder="Subject… (e.g. Follow up on contract #{cid})"
              value={subject} onChange={e => setSubject(e.target.value)}
            />
            <textarea
              className="inp"
              style={{ width: '100%', boxSizing: 'border-box', fontSize: 12, minHeight: 140, resize: 'vertical' }}
              placeholder={'Body… Placeholders: {username} {uid} {cid} {tid} {thread} {product}'}
              value={body} onChange={e => setBody(e.target.value)}
            />
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

// ── Follow-Up Modal ───────────────────────────────────────────────────────────
function FollowUpModal({ contract, templates, onClose, onOpenTemplates }) {
  const [selectedTid, setSelectedTid] = useState('')
  const [copied, setCopied]           = useState('')

  const template        = templates.find(t => t.template_id === selectedTid) || null
  const renderedSubject = template ? interpolate(template.subject, contract) : ''
  const renderedBody    = template ? interpolate(template.body,    contract) : ''

  const pmUrl = contract.counterparty_uid
    ? `https://hackforums.net/private.php?action=send&uid=${
        contract.counterparty_uid
      }&subject=${encodeURIComponent(renderedSubject)}`
    : null

  const copyText = (text, key) => {
    navigator.clipboard.writeText(text)
      .then(() => { setCopied(key); setTimeout(() => setCopied(''), 2000) })
      .catch(() => {})
  }

  const bc      = bucketColor(contract.bucket)
  const product = contract.iproduct || contract.oproduct || '—'

  return (
    <Backdrop onClose={onClose}>
      <div style={{ maxWidth: 480, margin: '0 auto' }}>
        <ModalHeader title="Follow Up" onClose={onClose} />

        {/* Contract context */}
        <div style={{
          background: 'var(--s1)', padding: '8px 10px', marginBottom: 12,
          borderLeft: `3px solid ${bc}`, fontSize: 11, fontFamily: 'var(--mono)',
        }}>
          <div style={{ display: 'flex', gap: 8, marginBottom: 3, flexWrap: 'wrap' }}>
            <span style={{ color: 'var(--acc)' }}>#{contract.cid}</span>
            <span style={{ color: 'var(--text)' }}>
              {contract.counterparty_username || contract.counterparty_uid || '?'}
            </span>
            {contract.counterparty_uid && (
              <span style={{ color: 'var(--dim)' }}>UID {contract.counterparty_uid}</span>
            )}
            <span style={{ color: bc, marginLeft: 'auto' }}>{bucketLabel(contract.bucket)}</span>
          </div>
          {product !== '—' && (
            <div style={{
              color: 'var(--sub)', overflow: 'hidden',
              textOverflow: 'ellipsis', whiteSpace: 'nowrap',
            }}>
              {product.length > 70 ? product.slice(0, 67) + '…' : product}
            </div>
          )}
          {contract.thread_title && (
            <div style={{
              color: 'var(--dim)', overflow: 'hidden',
              textOverflow: 'ellipsis', whiteSpace: 'nowrap', marginTop: 2,
            }}>
              {contract.thread_title.slice(0, 70)}
            </div>
          )}
        </div>

        {/* Template selector */}
        {templates.length === 0 ? (
          <div style={{ fontSize: 11, color: 'var(--dim)', fontFamily: 'var(--mono)', marginBottom: 12 }}>
            No PM templates saved.{' '}
            <button
              className="btn btn-sm"
              style={{ display: 'inline', padding: '2px 6px' }}
              onClick={onOpenTemplates}
            >
              Create a template
            </button>
          </div>
        ) : (
          <div style={{ marginBottom: 10 }}>
            <select
              className="inp"
              style={{ width: '100%', boxSizing: 'border-box', fontSize: 12 }}
              value={selectedTid}
              onChange={e => setSelectedTid(e.target.value)}
            >
              <option value="">— select a template —</option>
              {templates.map(t => (
                <option key={t.template_id} value={t.template_id}>{t.name}</option>
              ))}
            </select>
          </div>
        )}

        {/* Rendered fields (shown only after template is selected) */}
        {template && (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 12 }}>
            <div>
              <div style={{
                fontSize: 9, color: 'var(--dim)', fontFamily: 'var(--mono)',
                textTransform: 'uppercase', letterSpacing: '.08em', marginBottom: 3,
              }}>
                Subject
              </div>
              <input
                className="inp" readOnly
                style={{ width: '100%', boxSizing: 'border-box', fontSize: 12 }}
                value={renderedSubject}
              />
            </div>
            <div>
              <div style={{
                fontSize: 9, color: 'var(--dim)', fontFamily: 'var(--mono)',
                textTransform: 'uppercase', letterSpacing: '.08em', marginBottom: 3,
              }}>
                Body
              </div>
              <textarea
                className="inp" readOnly
                style={{ width: '100%', boxSizing: 'border-box', fontSize: 12, minHeight: 120, resize: 'vertical' }}
                value={renderedBody}
              />
            </div>
          </div>
        )}

        {/* Action buttons */}
        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', alignItems: 'center' }}>
          {pmUrl && template ? (
            <a
              href={pmUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="btn btn-sm btn-acc"
            >
              Open PM
            </a>
          ) : (
            <button className="btn btn-sm" disabled>Open PM</button>
          )}
          {template && (
            <>
              <button className="btn btn-sm" onClick={() => copyText(renderedBody, 'body')}>
                {copied === 'body' ? 'Copied!' : 'Copy Body'}
              </button>
              <button className="btn btn-sm" onClick={() => copyText(renderedSubject, 'subject')}>
                {copied === 'subject' ? 'Copied!' : 'Copy Subject'}
              </button>
            </>
          )}
        </div>
        {!contract.counterparty_uid && (
          <div style={{ fontSize: 10, color: 'var(--red)', fontFamily: 'var(--mono)', marginTop: 6 }}>
            Counterparty UID missing — cannot open PM.
          </div>
        )}
      </div>
    </Backdrop>
  )
}

// ── Contract card ─────────────────────────────────────────────────────────────
function DealCard({ deal, onFollowUp }) {
  const bc    = bucketColor(deal.bucket)
  const terms = contractTerms(deal)
  const product = deal.iproduct || deal.oproduct || '—'
  return (
    <div style={{
      background: 'var(--s1)', padding: '11px 14px', marginBottom: 4,
      display: 'flex', alignItems: 'center', gap: 12,
      borderLeft: `3px solid ${bc}`,
    }}>
      <div style={{ flex: 1, minWidth: 0 }}>
        <div style={{ display: 'flex', gap: 8, alignItems: 'baseline', marginBottom: 3 }}>
          <a
            href={`/dashboard/contracts/${deal.cid}`}
            style={{ fontSize: 11, fontFamily: 'var(--mono)', color: 'var(--acc)' }}
          >
            #{deal.cid}
          </a>
          <span style={{ fontSize: 12, color: 'var(--text)' }}>
            {deal.counterparty_username || deal.counterparty_uid || '?'}
          </span>
          <span style={{
            fontSize: 9, fontFamily: 'var(--mono)', color: bc,
            marginLeft: 'auto', flexShrink: 0,
          }}>
            {bucketLabel(deal.bucket)}
          </span>
        </div>

        <div style={{
          fontSize: 11, color: 'var(--sub)',
          overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
        }}>
          {product.length > 60 ? product.slice(0, 57) + '…' : product}
        </div>

        <div style={{ display: 'flex', gap: 10, marginTop: 4 }}>
          {terms !== 'terms not recorded' && (
            <span style={{ fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)' }}>{terms}</span>
          )}
          {deal.thread_title && (
            <span style={{
              fontSize: 10, color: 'var(--dim)',
              overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', flex: 1,
            }}>
              {deal.thread_title.slice(0, 50)}
            </span>
          )}
          <span style={{ fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)', flexShrink: 0 }}>
            {relTime(deal.dateline)}
          </span>
        </div>
      </div>

      {(deal.bucket === 'active_fulfillment' || deal.bucket === 'awaiting_approval') && (
        <button
          className="btn btn-sm"
          style={{ flexShrink: 0 }}
          onClick={() => onFollowUp(deal)}
        >
          Follow Up
        </button>
      )}
    </div>
  )
}

// ── Main component ────────────────────────────────────────────────────────────
export default function MerchantDeals() {
  const [allDeals, setAllDeals]             = useState([])
  const [loading, setLoading]               = useState(true)
  const [bucket, setBucket]                 = useState(null)
  const [templates, setTemplates]           = useState([])
  const [showTemplatesModal, setShowTemplatesModal] = useState(false)
  const [followUpContract, setFollowUpContract]     = useState(null)

  const fetchTemplates = () => {
    api.get('/api/merchant/pm-templates')
      .then(d => setTemplates(Array.isArray(d) ? d : []))
      .catch(() => {})
  }

  useEffect(() => {
    setLoading(true)
    api.get('/api/merchant/deals')
      .then(d => { setAllDeals(Array.isArray(d) ? d : []); setLoading(false) })
      .catch(() => setLoading(false))
    fetchTemplates()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const counts = allDeals.reduce((acc, d) => {
    acc[d.bucket] = (acc[d.bucket] || 0) + 1
    return acc
  }, {})

  const visible = bucket ? allDeals.filter(d => d.bucket === bucket) : allDeals

  return (
    <div>
      {/* Controls row: bucket filter tabs + PM Templates button */}
      <div style={{
        display: 'flex', gap: 4, marginBottom: 12,
        flexWrap: 'wrap', alignItems: 'center',
      }}>
        <div style={{ display: 'flex', gap: 4, overflowX: 'auto', whiteSpace: 'nowrap', flex: 1 }}>
          {BUCKETS.map(b => {
            const cnt = b.val ? counts[b.val] ?? 0 : allDeals.length
            return (
              <button
                key={b.val || 'all'}
                className={`tab${bucket === b.val ? ' on' : ''}`}
                onClick={() => setBucket(b.val)}
              >
                {b.label}{!loading && cnt > 0 ? ` (${cnt})` : ''}
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

      {/* Contract list */}
      {loading
        ? <div className="empty"><div className="spin" /></div>
        : visible.length === 0
          ? <div className="empty" style={{ color: 'var(--dim)' }}>No contracts found.</div>
          : visible.map(d => (
              <DealCard key={d.cid} deal={d} onFollowUp={setFollowUpContract} />
            ))
      }

      {/* PM Templates modal */}
      {showTemplatesModal && (
        <PMTemplatesModal
          templates={templates}
          onClose={() => setShowTemplatesModal(false)}
          onRefresh={fetchTemplates}
        />
      )}

      {/* Follow-up modal */}
      {followUpContract && (
        <FollowUpModal
          contract={followUpContract}
          templates={templates}
          onClose={() => setFollowUpContract(null)}
          onOpenTemplates={() => { setFollowUpContract(null); setShowTemplatesModal(true) }}
        />
      )}
    </div>
  )
}
