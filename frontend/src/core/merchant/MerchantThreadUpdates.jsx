import { useEffect, useMemo, useState } from 'react'
import { api } from '../api.js'
import { BBEditor, BBPreview } from '../PostingPage.jsx'
import useStore from '../../store.js'
import { relTime } from './merchantFormat.js'

function fmt(n) {
  const value = Number(n || 0)
  return Number.isFinite(value) ? value.toLocaleString() : '0'
}

function gain(n) {
  const value = Number(n || 0)
  if (!value) return '0'
  return value > 0 ? `+${fmt(value)}` : fmt(value)
}

function selectedThread(threads, tid) {
  return threads.find(thread => String(thread.tid) === String(tid)) || threads[0] || null
}

export default function MerchantThreadUpdates({ initialTid = null } = {}) {
  const userGroups = useStore(state => state.user?.groups || [])
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [selectedTid, setSelectedTid] = useState(initialTid || '')
  const [mode, setMode] = useState('')
  const [message, setMessage] = useState('')
  const [draft, setDraft] = useState(null)
  const [posting, setPosting] = useState(false)
  const [drafting, setDrafting] = useState(false)
  const [savingDraft, setSavingDraft] = useState(false)
  const [notice, setNotice] = useState('')
  const [error, setError] = useState('')

  const load = () => {
    setLoading(true)
    api.get('/api/merchant/thread-updates')
      .then(next => {
        setData(next)
        setError('')
        if (!selectedTid && next?.threads?.length) setSelectedTid(String(next.threads[0].tid))
      })
      .catch(err => setError(err.message || 'Thread update workspace could not load'))
      .finally(() => setLoading(false))
  }

  useEffect(() => { load() }, [])

  const threads = data?.threads || []
  const current = useMemo(() => selectedThread(threads, selectedTid), [threads, selectedTid])
  const updates = data?.updates || []
  const canPost = current && message.trim().length >= 5 && !posting

  const postUpdate = async () => {
    if (!canPost) return
    setPosting(true)
    setNotice('')
    setError('')
    try {
      await api.post(`/api/merchant/thread-updates/${current.tid}/post`, { message: message.trim() })
      setMessage('')
      setMode('')
      setNotice('Posted to the sales thread and logged here.')
      load()
    } catch (err) {
      setError(err.message || 'HF did not accept the update')
    } finally {
      setPosting(false)
    }
  }

  const importOpDraft = async () => {
    if (!current || drafting) return
    setDrafting(true)
    setNotice('')
    setError('')
    try {
      const result = await api.post(`/api/merchant/thread-updates/${current.tid}/op-draft`, {})
      const loaded = await api.get(`/api/posting/drafts/${result.draft_id}`)
      setDraft(loaded?.draft || { id: result.draft_id })
      setMode('op')
      setNotice('Opening post imported as an editable draft here. This does not edit HF.')
    } catch (err) {
      setError(err.message || 'Opening post could not be imported')
    } finally {
      setDrafting(false)
    }
  }

  const saveDraft = async () => {
    if (!draft || savingDraft) return
    setSavingDraft(true)
    setNotice('')
    setError('')
    try {
      const result = await api.put(`/api/posting/drafts/${draft.id}`, {
        fid: draft.fid || '',
        forum_name: draft.forum_name || '',
        subject: draft.subject || current?.title || `TID ${current?.tid || ''}`,
        message: draft.message || '',
        reply1: draft.reply1 || '',
        reply2: draft.reply2 || '',
        base_version: draft.version || 1,
      })
      setDraft(result?.draft || draft)
      setNotice('Draft saved. Use this copy as your OP rewrite source.')
    } catch (err) {
      setError(err.message || 'Draft could not be saved')
    } finally {
      setSavingDraft(false)
    }
  }

  if (loading && !data) return <div className="empty"><div className="spin" /></div>

  return (
    <div className="mhq-shell">
      <section className="mhq-section">
        <div className="mhq-section-head">
          <div>
            <h3>Post A Sales Thread Update</h3>
            <p>Pick one owned sales thread, write a fresh reply, preview it, then post it with your HF token.</p>
          </div>
          <span>{threads.length} active threads</span>
        </div>

        {error && <div className="mhq-note warn">{error}</div>}
        {notice && <div className="mhq-note">{notice}</div>}

        {threads.length === 0 ? (
          <div className="mhq-empty">No active sales threads are ready for updates. Archived threads stay out of this workspace.</div>
        ) : (
          <>
            <div className="mhq-thread-picker">
              <label className="mhq-field">
                <span>Sales thread</span>
                <select className="inp" value={String(current?.tid || '')} onChange={event => { setSelectedTid(event.target.value); setMode(''); setMessage(''); setDraft(null) }}>
                  {threads.map(thread => (
                    <option key={thread.tid} value={thread.tid}>{thread.title || `TID ${thread.tid}`}</option>
                  ))}
                </select>
              </label>
              {current && <a className="btn" href={`https://hackforums.net/showthread.php?tid=${current.tid}`} target="_blank" rel="noreferrer">View thread</a>}
            </div>

            {current && (
              <div className="mhq-mini-stats">
                <span><b>{fmt(current.views)}</b> views</span>
                <span><b>{fmt(current.replies)}</b> replies</span>
                <span><b>{fmt(current.posts)}</b> posts</span>
                <span><b>{fmt(current.contracts_total)}</b> contracts</span>
              </div>
            )}

            {!mode && (
              <div className="mhq-start-panel">
                <div>
                  <h4>Choose what you want to work on</h4>
                  <p>Post a new reply to the sales thread, or import the opening post into a local rewrite draft. The OP draft stays inside HFToolbox and does not edit Hack Forums.</p>
                </div>
                <div className="mhq-actions">
                  <button className="btn btn-acc" onClick={() => setMode('reply')}>Write thread reply</button>
                  <button className="btn" disabled={!current || drafting} onClick={importOpDraft}>
                    {drafting ? 'Importing...' : 'Import OP draft'}
                  </button>
                </div>
              </div>
            )}

            {mode === 'reply' && (
              <div className="mhq-composer-layout">
                <section className="mhq-editor-panel">
                  <div className="mhq-composer-head">
                    <div>
                      <h4>Post a sales thread reply</h4>
                      <p>This posts a new reply to the selected sales thread. It does not create a new thread or edit the OP.</p>
                    </div>
                    <button className="btn btn-sm" onClick={() => setMode('')}>Close composer</button>
                  </div>
                  <BBEditor value={message} onChange={setMessage} userGroups={userGroups} />
                  <div className="mhq-actions">
                    <button className="btn btn-acc" disabled={!canPost} onClick={postUpdate}>
                      {posting ? 'Posting...' : 'Post reply'}
                    </button>
                  </div>
                </section>
                <section className="mhq-preview-panel">
                  <div className="mhq-preview-label">Safe preview</div>
                  {message.trim() ? <BBPreview message={message} userGroups={userGroups} compact /> : <div className="mhq-empty">Your BBCode preview will appear here before posting.</div>}
                </section>
              </div>
            )}

            {mode === 'op' && draft && (
              <div className="mhq-composer-layout">
                <section className="mhq-editor-panel">
                  <div className="mhq-composer-head">
                    <div>
                      <h4>Opening post rewrite draft</h4>
                      <p>This is a local draft for rewriting your OP. HF API cannot edit the opening post, so save it here and copy it back manually.</p>
                    </div>
                    <button className="btn btn-sm" onClick={() => setMode('')}>Close draft</button>
                  </div>
                  <label className="mhq-field">
                    <span>Draft title</span>
                    <input className="inp" value={draft.subject || ''} onChange={event => setDraft(next => ({ ...next, subject: event.target.value }))} />
                  </label>
                  <BBEditor value={draft.message || ''} onChange={value => setDraft(next => ({ ...next, message: value }))} userGroups={userGroups} />
                  <div className="mhq-actions">
                    <button className="btn btn-acc" disabled={savingDraft || !(draft.message || '').trim()} onClick={saveDraft}>
                      {savingDraft ? 'Saving...' : 'Save draft'}
                    </button>
                    <a className="btn" href="/dashboard/posting?tab=drafts" target="_blank" rel="noreferrer">Open Drafts</a>
                  </div>
                </section>
                <section className="mhq-preview-panel">
                  <div className="mhq-preview-label">Safe preview</div>
                  {(draft.message || '').trim() ? <BBPreview message={draft.message || ''} title={draft.subject || current?.title || ''} userGroups={userGroups} compact /> : <div className="mhq-empty">Draft preview will appear here.</div>}
                </section>
              </div>
            )}
          </>
        )}
      </section>

      <section className="mhq-section">
        <div className="mhq-section-head">
          <div>
            <h3>Recent Thread Updates</h3>
            <p>Logged HFToolbox actions and the movement observed after each post.</p>
          </div>
        </div>
        {updates.length === 0 ? (
          <div className="mhq-empty">No thread updates posted through HFToolbox yet.</div>
        ) : (
          <div className="mhq-table-wrap">
            <table className="mhq-table">
              <thead><tr><th>Thread</th><th>Status</th><th>Posted</th><th>Views</th><th>Replies</th><th>Posts</th><th>Contracts</th></tr></thead>
              <tbody>
                {updates.map(item => (
                  <tr key={item.id}>
                    <td><span className="mhq-table-primary">{item.title || `TID ${item.tid}`}</span><span className="mhq-table-meta">TID {item.tid}</span></td>
                    <td><span className={`mhq-status ${item.status === 'posted' ? 'good' : item.status === 'failed' ? 'warn' : ''}`}>{item.status}</span></td>
                    <td>{item.posted_at ? relTime(item.posted_at) : 'Not posted'}</td>
                    <td>{gain((item.observed_views || 0) - (item.baseline_views || 0))}</td>
                    <td>{gain((item.observed_replies || 0) - (item.baseline_replies || 0))}</td>
                    <td>{gain((item.observed_posts || 0) - (item.baseline_posts || 0))}</td>
                    <td>{gain((item.observed_contracts || 0) - (item.baseline_contracts || 0))}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  )
}
