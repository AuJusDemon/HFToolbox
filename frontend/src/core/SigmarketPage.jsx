import { useState, useEffect, useCallback, useRef } from 'react'
import { api, throttledInterval } from './api.js'
import useStore from '../store.js'

// ── Helpers ───────────────────────────────────────────────────────────────────
const fmtDate = ts => ts ? new Date(ts * 1000).toLocaleDateString(undefined, {
  month: 'short', day: 'numeric', year: 'numeric'
}) : '--'

const fmtCountdown = secs => {
  if (secs <= 0) return 'Expired'
  const d = Math.floor(secs / 86400)
  const h = Math.floor((secs % 86400) / 3600)
  if (d > 0) return `${d}d ${h}h`
  return `${h}h ${Math.floor((secs % 3600) / 60)}m`
}

const ago = ts => {
  if (!ts) return '--'
  const d = Math.floor(Date.now() / 1000) - ts
  if (d < 60)    return `${Math.floor(d)}s ago`
  if (d < 3600)  return `${Math.floor(d / 60)}m ago`
  if (d < 86400) return `${Math.floor(d / 3600)}h ago`
  return `${Math.floor(d / 86400)}d ago`
}

function usePolling(fn, ms) {
  const ref = useRef(fn); ref.current = fn
  useEffect(() => {
    if (!ms) return
    const id = setInterval(() => ref.current(), ms)
    return () => clearInterval(id)
  }, [ms])
}

// ── Forum metadata for analytics ──────────────────────────────────────────────
const FID_META = {
  '25':  { name: 'The Lounge'   },
  '89':  { name: 'News & Happenings'   },
  '12':  { name: 'Bragging Rights'   },
  '65':  { name: 'Gaming'   },
  '37':  { name: 'Music'   },
  '32':  { name: 'Movies & TV'   },
  '167': { name: 'Sports'   },
  '180': { name: 'Innuendo'   },
  '370': { name: 'Gambling'   },
  '318': { name: 'Vices'   },
  '112': { name: 'Anime & Manga'   },
  '260': { name: 'Education & Careers'   },
  '262': { name: 'Health'    },
  '385': { name: 'Cars & Motors'    },
  '354': { name: 'Food & Cooking'    },
  '261': { name: 'Pets & Animals'    },
  '163': { name: 'Marketplace Discussion' },
  '402': { name: 'Promotional Ads' },
  '186': { name: 'Free Services' },
  '205': { name: 'Appraisals' },
  '217': { name: 'Jobs & Partnerships' },
  '107': { name: 'Premium Sellers' },
  '374': { name: 'Premium Tools' },
  '106': { name: 'Service Offerings' },
  '263': { name: 'Social Media Services' },
  '219': { name: 'Graphics Market' },
  '171': { name: 'VPN & Proxy Services' },
  '145': { name: 'Hosting Services' },
  '44':  { name: 'Buyers Bay' },
  '176': { name: 'Member Sales' },
  '291': { name: 'Online Accounts' },
  '380': { name: 'Crypto Currency' },
  '281': { name: 'Finance & Investing' },
  '155': { name: 'Member Contests' },
  '218': { name: 'Virtual Game Items' },
  '339': { name: 'Hash Bounties' },
  '255': { name: 'Rewards & Favors' },
  '111': { name: 'Deal Disputes' },
  '5':   { name: 'Coders Lounge'    },
  '8':   { name: 'Computing Lounge'    },
  '4':   { name: 'Beginner Hacking'    },
  '47':  { name: 'Hacking Tutorials'    },
  '50':  { name: 'Website Construction'    },
  '172': { name: 'Website Showcase'    },
  '183': { name: 'Web Development'    },
  '375': { name: 'HF API'    },
  '87':  { name: 'Computer Hardware'    },
  '79':  { name: 'Mobile Smartphones'    },
  '6':   { name: 'Graphics'    },
  '142': { name: 'SEO & Marketing'    },
  '139': { name: 'Social Networking'    },
  '127': { name: 'Referrals'    },
  '121': { name: 'Shopping Deals'    },
  '431': { name: 'AI Discussion'    },
  '462': { name: 'AI Programming'    },
  '117': { name: 'Mobile Development'    },
  '118': { name: 'Software Development'    },
  '10':  { name: 'Hacking Tools'    },
  '114': { name: 'Remote Admin Tools'    },
  '92':  { name: 'Botnets'    },
  '113': { name: 'Keyloggers'    },
  '126': { name: 'Cryptography'    },
  '287': { name: 'Malware & Viruses'    },
  '43':  { name: 'Website Hacking'    },
  '103': { name: 'SQL Injection'    },
  '91':  { name: 'VPN & Proxies (disc)'    },
  '46':  { name: 'Social Media Hacks'    },
  '104': { name: 'WiFi Hacking'    },
  '322': { name: 'OpSec & OSINT'    },
  '231': { name: 'Pentesting'    },
  '400': { name: 'White Hat Hacking'    },
  '229': { name: 'Reverse Engineering'    },
  '433': { name: 'Hacktivism'    },
}

const getFidName  = fid => FID_META[String(fid)]?.name ?? 'Private Forum'
const isKnownFid  = fid => fid in FID_META

function computeSigScore(data, hfPpd) {
  if (!data) return 0
  const { posts_per_day, last_post_ts, post_fid_dist, thread_views } = data

  // Activity: dominant factor — 2/day = full 55pts
  const ppd = posts_per_day || (hfPpd ? parseFloat(hfPpd) : 0)
  const actScore = Math.min(55, (ppd / 2) * 55)

  // Public visibility: % of posts in known public FIDs — no traffic assumptions,
  // just "can people actually see this sig or is it buried in private group forums"
  const dist  = post_fid_dist || {}
  const total = Object.values(dist).reduce((s, c) => s + c, 0)
  const knownCount = Object.entries(dist)
    .filter(([fid]) => isKnownFid(fid))
    .reduce((s, [, c]) => s + c, 0)
  const publicScore = total > 0 ? (knownCount / total) * 20 : 0

  // Recency: steep falloff, 0 pts after 14 days
  const daysSince = last_post_ts ? (Date.now() / 1000 - last_post_ts) / 86400 : 999
  const recencyScore = daysSince <= 1  ? 15
                     : daysSince <= 3  ? 12
                     : daysSince <= 7  ? 8
                     : daysSince <= 14 ? 3
                     : 0

  // Thread views bonus → up to 10pts
  const viewScore = Math.min(10, ((thread_views?.avg || 0) / 400) * 10)

  return Math.round(Math.min(100, actScore + publicScore + recencyScore + viewScore))
}

function scoreLabel(s) {
  if (s >= 76) return 'PREMIUM'
  if (s >= 56) return 'GOOD'
  if (s >= 31) return 'FAIR'
  return 'POOR'
}
function scoreColor(s) {
  if (s >= 76) return 'var(--acc)'
  if (s >= 56) return '#24c98c'
  if (s >= 31) return 'var(--yellow)'
  return 'var(--red)'
}
function scoreDesc(label) {
  if (label === 'PREMIUM') return 'Highly active in high-traffic sections.'
  if (label === 'GOOD')    return 'Regularly active in visible forums.'
  if (label === 'FAIR')    return 'Moderate activity or mixed forum visibility.'
  return 'Low activity or posting in low-traffic areas.'
}

// ── Analytics panel ───────────────────────────────────────────────────────────
function AnalyticsPanel({ targetUid, hfPpd, price, duration }) {
  const [data,    setData]    = useState(null)
  const [loading, setLoading] = useState(true)
  const [err,     setErr]     = useState(null)

  const load = useCallback((force = false) => {
    setLoading(true); setErr(null)
    api.get(`/api/sigmarket/analytics/${targetUid}${force ? '?force=true' : ''}`)
      .then(d => { setData(d); setLoading(false) })
      .catch(e => { setErr(e?.message || 'Failed to load'); setLoading(false) })
  }, [targetUid])

  useEffect(() => { load(false) }, [load])

  if (loading) return (
    <div style={{ padding: '32px 0', display: 'flex', justifyContent: 'center' }}>
      <div className="spin" />
    </div>
  )
  if (err) return (
    <div style={{ padding: '14px 18px', fontSize: 12, color: 'var(--red)', fontFamily: 'var(--mono)', display: 'flex', alignItems: 'center', gap: 8 }}>
      ✕ {err}
      <button className="btn btn-ghost" style={{ fontSize: 11 }} onClick={() => load(true)}>Retry</button>
    </div>
  )
  if (!data) return null

  const { posts_per_day, last_post_ts, post_fid_dist, thread_views,
          unique_tids, posts_sample, threads_sample, last_thread_ts } = data

  const sortedFids = Object.entries(post_fid_dist || {}).sort((a, b) => b[1] - a[1])
  const totalPosts = sortedFids.reduce((s, [, c]) => s + c, 0)
  const top5       = sortedFids.slice(0, 5)
  const otherCount = sortedFids.slice(5).reduce((s, [, c]) => s + c, 0)

  const score = computeSigScore(data, hfPpd)
  const lbl   = scoreLabel(score)
  const col   = scoreColor(score)

  const daysSinceLast = last_post_ts
    ? Math.floor((Date.now() / 1000 - last_post_ts) / 86400)
    : null
  const recencyStr = daysSinceLast === null ? '--'
    : daysSinceLast === 0 ? 'today'
    : `${daysSinceLast}d ago`

  const daysSinceThread = last_thread_ts
    ? Math.floor((Date.now() / 1000 - last_thread_ts) / 86400)
    : null

  const StatBox = ({ val, lbl: l }) => (
    <div style={{ background: 'var(--bg)', padding: '8px 10px' }}>
      <div style={{ fontSize: 13, fontWeight: 600, fontFamily: 'var(--mono)', color: 'var(--text)' }}>{val}</div>
      <div style={{ fontSize: 9, color: 'var(--dim)', textTransform: 'uppercase', letterSpacing: '.06em', marginTop: 2 }}>{l}</div>
    </div>
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 16, padding: '14px 18px' }}>

      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ fontSize: 9, color: 'var(--dim)', fontFamily: 'var(--mono)',
          textTransform: 'uppercase', letterSpacing: '.07em' }}>Cached · 1hr</span>
        <button className="btn btn-ghost" style={{ fontSize: 11, padding: '2px 8px' }}
          onClick={() => load(true)}>↻ Refresh</button>
      </div>

      {/* Activity */}
      <div>
        <div style={{ fontSize: 9, color: 'var(--dim)', fontFamily: 'var(--mono)',
          textTransform: 'uppercase', letterSpacing: '.07em', marginBottom: 8 }}>Activity</div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 1,
          background: 'var(--b1)', borderRadius: 6, overflow: 'hidden' }}>
          <StatBox val={hfPpd ? `${parseFloat(hfPpd).toFixed(2)}/d` : (posts_per_day ? `${posts_per_day}/d` : '--')} lbl="Posts/day (HF avg)" />
          <StatBox val={recencyStr} lbl="Last public post" />
          <StatBox val={`${unique_tids}/${posts_sample || 0}`} lbl="Thread diversity" />
        </div>
        {daysSinceLast !== null && daysSinceLast > 30 && (
          <div style={{ marginTop: 6, fontSize: 11, color: 'var(--yellow)', fontFamily: 'var(--mono)' }}>
            ⚠ Last post {daysSinceLast}d ago — sig reach may be low
          </div>
        )}
      </div>

      {/* Forum distribution */}
      {top5.length > 0 && (
        <div>
          <div style={{ fontSize: 9, color: 'var(--dim)', fontFamily: 'var(--mono)',
            textTransform: 'uppercase', letterSpacing: '.07em', marginBottom: 8 }}>
            Where They Post
            <span style={{ fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>
              {' '}· last {posts_sample}
            </span>
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 7 }}>
            {top5.map(([fid, count]) => {
              const pct    = totalPosts > 0 ? Math.round(count / totalPosts * 100) : 0
              const name   = getFidName(fid)
              const known  = isKnownFid(fid)
              const barC   = known ? 'var(--acc)' : 'var(--dim)'
              return (
                <div key={fid}>
                  <div style={{ display: 'flex', justifyContent: 'space-between',
                    alignItems: 'center', marginBottom: 3 }}>
                    <span style={{ fontSize: 11, color: known ? 'var(--text)' : 'var(--dim)',
                      overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', maxWidth: '70%' }}>
                      {name}
                    </span>
                    <span style={{ fontSize: 10, color: 'var(--sub)', fontFamily: 'var(--mono)', flexShrink: 0 }}>
                      {pct}%
                    </span>
                  </div>
                  <div style={{ height: 3, background: 'var(--b2)', borderRadius: 2 }}>
                    <div style={{ height: '100%', width: `${pct}%`, background: barC,
                      borderRadius: 2, transition: 'width .4s ease' }} />
                  </div>
                </div>
              )
            })}
            {otherCount > 0 && (
              <div style={{ fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)' }}>
                +{otherCount} post{otherCount !== 1 ? 's' : ''} in other forums
              </div>
            )}
          </div>
        </div>
      )}

      {/* Thread traction */}
      {thread_views && thread_views.count > 0 && (
        <div>
          <div style={{ fontSize: 9, color: 'var(--dim)', fontFamily: 'var(--mono)',
            textTransform: 'uppercase', letterSpacing: '.07em', marginBottom: 8 }}>
            Their Threads
            <span style={{ fontWeight: 400, textTransform: 'none', letterSpacing: 0 }}>
              {' '}· {threads_sample} sampled
            </span>
          </div>
          <div style={{ display: 'flex', gap: 20 }}>
            <div>
              <div style={{ fontSize: 15, fontWeight: 700, fontFamily: 'var(--mono)', color: 'var(--text)' }}>
                {thread_views.avg.toLocaleString()}
              </div>
              <div style={{ fontSize: 9, color: 'var(--dim)', textTransform: 'uppercase', letterSpacing: '.06em' }}>avg views</div>
            </div>
            <div>
              <div style={{ fontSize: 15, fontWeight: 700, fontFamily: 'var(--mono)', color: 'var(--text)' }}>
                {thread_views.max.toLocaleString()}
              </div>
              <div style={{ fontSize: 9, color: 'var(--dim)', textTransform: 'uppercase', letterSpacing: '.06em' }}>best thread</div>
            </div>
            {daysSinceThread !== null && (
              <div>
                <div style={{ fontSize: 15, fontWeight: 700, fontFamily: 'var(--mono)', color: 'var(--text)' }}>
                  {daysSinceThread === 0 ? 'today' : `${daysSinceThread}d`}
                </div>
                <div style={{ fontSize: 9, color: 'var(--dim)', textTransform: 'uppercase', letterSpacing: '.06em' }}>since last</div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* Price analysis */}
      {price && duration && (() => {
        const priceInt   = parseInt(price)
        const durInt     = parseInt(duration)
        const perDay     = Math.round(priceInt / durInt)
        const score      = computeSigScore(data, hfPpd)
        const valueIdx   = score > 0 ? (score * 10 / perDay) : 0
        const valueLabel = valueIdx >= 5 ? 'Great value' : valueIdx >= 2 ? 'Fair price' : valueIdx >= 1 ? 'Pricey' : 'Overpriced'
        const valueColor = valueIdx >= 5 ? '#24c98c' : valueIdx >= 2 ? 'var(--blue)' : valueIdx >= 1 ? 'var(--yellow)' : 'var(--red)'
        return (
          <div>
            <div style={{ fontSize: 9, color: 'var(--dim)', fontFamily: 'var(--mono)',
              textTransform: 'uppercase', letterSpacing: '.07em', marginBottom: 8 }}>Cost breakdown</div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 1,
              background: 'var(--b1)', borderRadius: 6, overflow: 'hidden', marginBottom: 8 }}>
              <StatBox val={`${parseInt(price).toLocaleString()}b`} lbl="Total price" />
              <StatBox val={`${duration}d`} lbl="Duration" />
              <StatBox val={`${perDay.toLocaleString()}b/d`} lbl="Daily cost" />
            </div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ fontSize: 11, color: 'var(--dim)' }}>
                Score vs price
              </span>
              <span style={{ fontSize: 13, fontWeight: 700, fontFamily: 'var(--mono)', color: valueColor }}>
                {valueLabel}
              </span>
            </div>
          </div>
        )
      })()}

      {/* Score */}
      <div>
        <div style={{ fontSize: 9, color: 'var(--dim)', fontFamily: 'var(--mono)',
          textTransform: 'uppercase', letterSpacing: '.07em', marginBottom: 8 }}>
          Sig Value Estimate
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginBottom: 6 }}>
          <div style={{ flex: 1, height: 5, background: 'var(--b2)', borderRadius: 3 }}>
            <div style={{ height: '100%', width: `${score}%`, background: col,
              borderRadius: 3, transition: 'width .5s ease' }} />
          </div>
          <span style={{ fontSize: 13, fontWeight: 700, color: col,
            fontFamily: 'var(--mono)', minWidth: 60, textAlign: 'right' }}>
            {lbl}
          </span>
          <span style={{ fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)' }}>
            {score}/100
          </span>
        </div>
        <div style={{ fontSize: 11, color: 'var(--dim)' }}>{scoreDesc(lbl)}</div>
      </div>
    </div>
  )
}

// ── Your Listing ──────────────────────────────────────────────────────────────
function ListingSection({ status, onRefresh }) {
  const listing = status?.listing
  const [mode,  setMode]  = useState('view')
  const [price, setPrice] = useState('')
  const [dur,   setDur]   = useState('')
  const [busy,  setBusy]  = useState(false)
  const [err,   setErr]   = useState(null)
  const [ok,    setOk]    = useState(null)

  useEffect(() => {
    setPrice(listing?.price || '')
    setDur(listing?.duration || '')
  }, [listing])

  const act = async (action, body) => {
    setBusy(true); setErr(null); setOk(null)
    try {
      await api.post('/api/sigmarket/listing', { action, ...body })
      setOk('Done'); setMode('view'); onRefresh()
    } catch (e) { setErr(e.message || 'Error') }
    finally { setBusy(false) }
  }

  const isListed = listing && parseInt(listing.active || 0)

  return (
    <div className="card">
      <div className="card-head">
        <span className="card-icon">&#x1F3F7;</span>
        <span className="card-title">Your Listing</span>
        {isListed && (
          <span style={{ marginLeft: 'auto', fontSize: 10, padding: '2px 8px', borderRadius: 3,
            background: 'rgba(0,212,180,.1)', border: '1px solid rgba(0,212,180,.25)',
            color: 'var(--acc)', fontFamily: 'var(--mono)' }}>ACTIVE</span>
        )}
      </div>
      <div className="card-body">
        {!listing || !isListed ? (
          /* ── No listing ── */
          <div>
            <div style={{ fontSize: 12, color: 'var(--dim)', marginBottom: 12 }}>
              You don't have an active sig listing.
            </div>
            {mode !== 'setsale' ? (
              <button className="btn btn-acc" style={{ fontSize: 11 }}
                onClick={() => setMode('setsale')}>List My Sig</button>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 10 }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                  <div>
                    <div style={{ fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)', marginBottom: 4 }}>PRICE (bytes)</div>
                    <input className="inp" type="number" min="1" value={price}
                      onChange={e => setPrice(e.target.value)} placeholder="e.g. 500" />
                  </div>
                  <div>
                    <div style={{ fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)', marginBottom: 4 }}>DURATION (days)</div>
                    <input className="inp" type="number" min="1" value={dur}
                      onChange={e => setDur(e.target.value)} placeholder="e.g. 30" />
                  </div>
                </div>
                {err && <div style={{ fontSize: 11, color: 'var(--red)', fontFamily: 'var(--mono)' }}>&#x2715; {err}</div>}
                <div style={{ display: 'flex', gap: 6 }}>
                  <button className="btn btn-acc" style={{ fontSize: 11 }}
                    disabled={busy || !price || !dur}
                    onClick={() => act('setsale', { price, duration: dur })}>
                    {busy ? '\u2026' : 'List Sig'}
                  </button>
                  <button className="btn btn-ghost" style={{ fontSize: 11 }}
                    onClick={() => setMode('view')}>Cancel</button>
                </div>
              </div>
            )}
          </div>
        ) : (
          /* ── Active listing ── */
          <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3,1fr)', gap: 1,
              background: 'var(--b1)', borderRadius: 6, overflow: 'hidden', border: '1px solid var(--b1)' }}>
              {[
                { lbl: 'Price',    val: `${parseInt(listing.price || 0).toLocaleString()} bytes` },
                { lbl: 'Duration', val: `${listing.duration} days` },
                { lbl: 'PPD',      val: listing.ppd ? `${listing.ppd} bytes/day` : '--' },
              ].map(({ lbl, val }) => (
                <div key={lbl} style={{ background: 'var(--s2)', padding: '8px 12px' }}>
                  <div style={{ fontSize: 13, fontWeight: 600, fontFamily: 'var(--mono)', color: 'var(--text)' }}>{val}</div>
                  <div style={{ fontSize: 9, color: 'var(--sub)', textTransform: 'uppercase', letterSpacing: '.07em' }}>{lbl}</div>
                </div>
              ))}
            </div>

            {listing.sig && (
              <div>
                <div style={{ fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)', marginBottom: 6 }}>CURRENT SIG</div>
                <div style={{ padding: '8px 10px', background: 'var(--bg)', border: '1px solid var(--b2)',
                  borderRadius: 4, fontSize: 11, fontFamily: 'var(--mono)', color: 'var(--sub)',
                  whiteSpace: 'pre-wrap', wordBreak: 'break-all' }}>{listing.sig}</div>
              </div>
            )}

            {/* Change Price form */}
            {mode === 'setsale' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                  <div>
                    <div style={{ fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)', marginBottom: 4 }}>NEW PRICE</div>
                    <input className="inp" type="number" min="1" value={price} onChange={e => setPrice(e.target.value)} />
                  </div>
                  <div>
                    <div style={{ fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)', marginBottom: 4 }}>NEW DURATION</div>
                    <input className="inp" type="number" min="1" value={dur} onChange={e => setDur(e.target.value)} />
                  </div>
                </div>
                {err && <div style={{ fontSize: 11, color: 'var(--red)', fontFamily: 'var(--mono)' }}>&#x2715; {err}</div>}
                <div style={{ display: 'flex', gap: 6 }}>
                  <button className="btn btn-acc" style={{ fontSize: 11 }}
                    disabled={busy || !price || !dur}
                    onClick={() => act('setsale', { price, duration: dur })}>
                    {busy ? '\u2026' : 'Update Listing'}
                  </button>
                  <button className="btn btn-ghost" style={{ fontSize: 11 }}
                    onClick={() => setMode('view')}>Cancel</button>
                </div>
              </div>
            )}

            {err && mode === 'view' && <div style={{ fontSize: 11, color: 'var(--red)', fontFamily: 'var(--mono)' }}>&#x2715; {err}</div>}
            {ok  && <div style={{ fontSize: 11, color: 'var(--acc)', fontFamily: 'var(--mono)' }}>&#x2713; {ok}</div>}

            {mode === 'view' && (
              <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                <button className="btn btn-ghost" style={{ fontSize: 11 }}
                  onClick={() => setMode('setsale')}>Change Price</button>
                <button className="btn btn-danger" style={{ fontSize: 11 }} disabled={busy}
                  onClick={() => setMode('confirm_remove')}>
                  {busy ? '\u2026' : 'Remove Listing'}
                </button>
              </div>
            )}

            {mode === 'confirm_remove' && (
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                <div style={{ fontSize: 12, color: 'var(--text)' }}>Remove your sig listing? This cannot be undone.</div>
                <div style={{ display: 'flex', gap: 6 }}>
                  <button className="btn btn-danger" style={{ fontSize: 11 }} disabled={busy}
                    onClick={() => act('removesale', {})}>
                    {busy ? '\u2026' : 'Remove'}
                  </button>
                  <button className="btn btn-ghost" style={{ fontSize: 11 }}
                    onClick={() => setMode('view')}>Cancel</button>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Orders table ──────────────────────────────────────────────────────────────
function OrdersTable({ orders, partyKey, partyLabel, icon, title, count }) {
  const [now, setNow] = useState(Math.floor(Date.now() / 1000))
  useEffect(() => {
    const id = setInterval(() => setNow(Math.floor(Date.now() / 1000)), 60000)
    return () => clearInterval(id)
  }, [])

  return (
    <div className="card">
      <div className="card-head">
        <span className="card-icon" dangerouslySetInnerHTML={{ __html: icon }} />
        <span className="card-title">{title}</span>
        <span style={{ marginLeft: 'auto', fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)' }}>
          {count ?? 0} active
        </span>
      </div>
      <div className="card-body" style={{ padding: orders.length ? 0 : undefined }}>
        {!orders.length ? (
          <div style={{ fontSize: 12, color: 'var(--dim)', fontStyle: 'italic' }}>No orders yet</div>
        ) : (
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
            <thead>
              <tr style={{ borderBottom: '1px solid var(--b1)' }}>
                {[partyLabel, 'Started', 'Expires', 'Time Left', 'Price'].map(h => (
                  <th key={h} style={{ padding: '7px 14px', textAlign: 'left', fontSize: 9,
                    color: 'var(--dim)', fontFamily: 'var(--mono)', textTransform: 'uppercase',
                    letterSpacing: '.07em', fontWeight: 600 }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {orders.map((o, i) => {
                const rem   = o.enddate - now
                const party = o[partyKey] || {}
                return (
                  <tr key={o.smid || i} style={{ borderBottom: '1px solid var(--b1)', opacity: rem <= 0 ? .5 : 1 }}>
                    <td style={{ padding: '8px 14px', fontWeight: 600 }}>
                      {party.username || `UID ${party.uid}` || '--'}
                    </td>
                    <td style={{ padding: '8px 14px', color: 'var(--sub)' }}>{fmtDate(o.startdate)}</td>
                    <td style={{ padding: '8px 14px', color: 'var(--sub)' }}>{fmtDate(o.enddate)}</td>
                    <td style={{ padding: '8px 14px' }}>
                      <span style={{ fontFamily: 'var(--mono)', fontSize: 11, fontWeight: 600,
                        color: rem <= 0 ? 'var(--red)' : rem < 86400 * 3 ? 'var(--yellow)' : 'var(--acc)' }}>
                        {fmtCountdown(rem)}
                      </span>
                    </td>
                    <td style={{ padding: '8px 14px', color: 'var(--sub)', fontFamily: 'var(--mono)' }}>
                      {o.price ? `${o.price}b` : '--'}
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

// ── My Purchases ──────────────────────────────────────────────────────────────
function MyPurchasesSection({ orders, count, onRefresh }) {
  const [now, setNow] = useState(Math.floor(Date.now() / 1000))
  const [editors, setEditors] = useState({})
  const [bulkOpen,  setBulkOpen]  = useState(false)
  const [bulkValue, setBulkValue] = useState('')
  const [bulkBusy,  setBulkBusy]  = useState(false)
  const [bulkOk,    setBulkOk]    = useState(false)
  const [bulkErr,   setBulkErr]   = useState(null)

  useEffect(() => {
    const id = setInterval(() => setNow(Math.floor(Date.now() / 1000)), 60000)
    return () => clearInterval(id)
  }, [])

  const setEditor  = (smid, patch) =>
    setEditors(prev => ({ ...prev, [smid]: { ...(prev[smid] || {}), ...patch } }))
  const openEditor  = smid => setEditor(smid, { open: true, value: '', ok: null, err: null })
  const closeEditor = smid => setEditor(smid, { open: false })

  const pushSig = async smid => {
    const ed = editors[smid] || {}
    setEditor(smid, { busy: true, ok: null, err: null })
    try {
      await api.post('/api/sigmarket/listing', {
        action: 'changesig', smid: String(smid), sig: ed.value || '',
      })
      setEditor(smid, { busy: false, ok: 'Signature updated!', open: false })
      setTimeout(() => setEditor(smid, { ok: null }), 4000)
      onRefresh()
    } catch (e) {
      setEditor(smid, { busy: false, err: e.message || 'Failed to update' })
    }
  }

  const pushAll = async () => {
    setBulkBusy(true); setBulkErr(null); setBulkOk(false)
    try {
      await api.post('/api/sigmarket/listing', { action: 'changesig', smid: 'all', sig: bulkValue })
      setBulkOk(true); setBulkOpen(false); setBulkValue('')
      setTimeout(() => setBulkOk(false), 4000)
      onRefresh()
    } catch (e) {
      setBulkErr(e.message || 'Failed to update')
    } finally {
      setBulkBusy(false)
    }
  }

  const activeCount = orders.filter(o => (o.enddate - now) > 0).length

  return (
    <div className="card">
      <div className="card-head">
        <span className="card-icon">🛒</span>
        <span className="card-title">My Purchases</span>
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
          {bulkOk && <span style={{ fontSize: 11, color: 'var(--acc)', fontFamily: 'var(--mono)' }}>✓ All updated</span>}
          <span style={{ fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)' }}>{count ?? 0} active</span>
          {activeCount > 1 && (
            <button className="btn btn-ghost" style={{ fontSize: 11, whiteSpace: 'nowrap' }}
              onClick={() => { setBulkOpen(o => !o); setBulkErr(null) }}>
              {bulkOpen ? 'Cancel' : 'Set All Sigs'}
            </button>
          )}
        </div>
      </div>
      {bulkOpen && (
        <div style={{ padding: '12px 14px', borderBottom: '1px solid var(--b1)', background: 'var(--s3)' }}>
          <div style={{ fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)',
            textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 6 }}>
            Push to all {activeCount} active slots (BBCode, max 255 chars)
          </div>
          <textarea value={bulkValue} onChange={e => setBulkValue(e.target.value)}
            placeholder="[align=center][img]https://...[/img][/align]"
            maxLength={255} spellCheck={false}
            style={{ width: '100%', minHeight: 72, padding: '8px 10px', boxSizing: 'border-box',
              background: 'var(--bg)', border: '1px solid var(--b2)', borderRadius: 4,
              color: 'var(--text)', fontFamily: 'var(--mono)', fontSize: 12,
              lineHeight: 1.6, resize: 'vertical', outline: 'none' }}
            onFocus={e => { e.target.style.borderColor = 'var(--acc)' }}
            onBlur={e  => { e.target.style.borderColor = 'var(--b2)'  }} />
          <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 8 }}>
            <button className="btn btn-acc" style={{ fontSize: 11 }}
              disabled={bulkBusy || !bulkValue.trim()} onClick={pushAll}>
              {bulkBusy ? '…' : `Update All ${activeCount} Slots`}
            </button>
            <span style={{ fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)' }}>
              {bulkValue.length}/255
            </span>
            {bulkErr && <span style={{ fontSize: 11, color: 'var(--red)' }}>{bulkErr}</span>}
          </div>
        </div>
      )}
      <div className="card-body" style={{ padding: orders.length ? 0 : undefined }}>
        {!orders.length ? (
          <div style={{ fontSize: 12, color: 'var(--dim)', fontStyle: 'italic' }}>No purchased sig slots yet.</div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column' }}>
            {orders.map((o, i) => {
              const rem    = o.enddate - now
              const seller = o.seller || {}
              const ed     = editors[o.smid] || {}
              const expired = rem <= 0
              const urgent  = !expired && rem < 86400 * 3
              return (
                <div key={o.smid || i} style={{ borderBottom: '1px solid var(--b1)', opacity: expired ? 0.55 : 1 }}>
                  <div style={{ display: 'grid',
                    gridTemplateColumns: 'minmax(0,1.4fr) minmax(0,1fr) minmax(0,1fr) minmax(0,1fr) auto',
                    gap: 8, alignItems: 'center', padding: '10px 14px' }}>
                    <div>
                      <div style={{ fontSize: 12, fontWeight: 600 }}>
                        <a href={`https://hackforums.net/member.php?action=profile&uid=${seller.uid}`}
                          target="_blank" rel="noreferrer"
                          style={{ color: 'var(--acc)', textDecoration: 'none' }}>
                          {seller.username || `UID ${seller.uid}` || '--'}
                        </a>
                      </div>
                      <div style={{ fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)', marginTop: 2 }}>
                        {o.price ? `${o.price}b` : '--'} · {o.duration}d
                      </div>
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--sub)' }}>
                      <div style={{ fontSize: 9, color: 'var(--dim)', fontFamily: 'var(--mono)',
                        textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 2 }}>Started</div>
                      {fmtDate(o.startdate)}
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--sub)' }}>
                      <div style={{ fontSize: 9, color: 'var(--dim)', fontFamily: 'var(--mono)',
                        textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 2 }}>Expires</div>
                      {fmtDate(o.enddate)}
                    </div>
                    <div>
                      <div style={{ fontSize: 9, color: 'var(--dim)', fontFamily: 'var(--mono)',
                        textTransform: 'uppercase', letterSpacing: '.06em', marginBottom: 2 }}>Time Left</div>
                      <span style={{ fontFamily: 'var(--mono)', fontSize: 11, fontWeight: 600,
                        color: expired ? 'var(--red)' : urgent ? 'var(--yellow)' : 'var(--acc)' }}>
                        {fmtCountdown(rem)}
                      </span>
                    </div>
                    <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                      {ed.ok && <span style={{ fontSize: 11, color: 'var(--acc)', fontFamily: 'var(--mono)' }}>✓</span>}
                      {!expired && (
                        <button className="btn btn-ghost" style={{ fontSize: 11, whiteSpace: 'nowrap' }}
                          onClick={() => ed.open ? closeEditor(o.smid) : openEditor(o.smid)}>
                          {ed.open ? 'Cancel' : 'Set Sig'}
                        </button>
                      )}
                    </div>
                  </div>
                  {ed.open && (
                    <div style={{ padding: '0 14px 14px', borderTop: '1px solid var(--b1)' }}>
                      <div style={{ fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)',
                        textTransform: 'uppercase', letterSpacing: '.06em', margin: '10px 0 6px' }}>
                        Sig for {seller.username || seller.uid}'s slot (BBCode, max 255 chars)
                      </div>
                      <textarea value={ed.value || ''} onChange={e => setEditor(o.smid, { value: e.target.value })}
                        placeholder="[align=center][img]https://...[/img][/align]"
                        maxLength={255} spellCheck={false}
                        style={{ width: '100%', minHeight: 72, padding: '8px 10px', boxSizing: 'border-box',
                          background: 'var(--bg)', border: '1px solid var(--b2)', borderRadius: 4,
                          color: 'var(--text)', fontFamily: 'var(--mono)', fontSize: 12,
                          lineHeight: 1.6, resize: 'vertical', outline: 'none' }}
                        onFocus={e => { e.target.style.borderColor = 'var(--acc)' }}
                        onBlur={e  => { e.target.style.borderColor = 'var(--b2)' }} />
                      <div style={{ display: 'flex', gap: 8, alignItems: 'center', marginTop: 8 }}>
                        <button className="btn btn-acc" style={{ fontSize: 11 }}
                          disabled={ed.busy || !(ed.value || '').trim()}
                          onClick={() => pushSig(o.smid)}>
                          {ed.busy ? '…' : 'Update Signature'}
                        </button>
                        <span style={{ fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)' }}>
                          {(ed.value || '').length}/255
                        </span>
                        {ed.err && <span style={{ fontSize: 11, color: 'var(--red)' }}>{ed.err}</span>}
                      </div>
                    </div>
                  )}
                  {ed.ok && !ed.open && (
                    <div style={{ padding: '6px 14px 10px' }}>
                      <span style={{ fontSize: 11, color: 'var(--acc)', fontFamily: 'var(--mono)' }}>✓ {ed.ok}</span>
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
}

// ── Info Modal (Browse Market) ────────────────────────────────────────────────
function InfoModal({ listing, onClose, onBuyDone }) {
  const [tab,  setTab]  = useState('order')
  const [busy, setBusy] = useState(false)
  const [err,  setErr]  = useState(null)
  const [ok,   setOk]   = useState(false)

  const ppd         = listing.ppd ? parseFloat(listing.ppd).toFixed(2) : '--'
  const pricePerDay = listing.price && listing.duration
    ? (parseInt(listing.price) / parseInt(listing.duration)).toFixed(2)
    : '--'

  const buy = async () => {
    setBusy(true); setErr(null)
    try {
      await api.post('/api/sigmarket/buy', { uid: listing.uid, max_price: listing.price })
      setOk(true)
      setTimeout(() => { onBuyDone(); onClose() }, 1200)
    } catch (e) { setErr(e.message || 'Purchase failed'); setBusy(false) }
  }

  const TabBtn = ({ id, label }) => (
    <button onClick={() => setTab(id)}
      style={{ fontSize: 11, padding: '4px 12px', borderRadius: 3, cursor: 'pointer',
        fontFamily: 'var(--mono)', textTransform: 'uppercase', letterSpacing: '.05em',
        border: 'none', background: tab === id ? 'var(--acc)' : 'transparent',
        color: tab === id ? '#000' : 'var(--dim)', transition: 'all var(--ease)' }}>
      {label}
    </button>
  )

  return (
    <div style={{ position: 'fixed', inset: 0, background: 'rgba(0,0,0,.7)', zIndex: 200,
      display: 'flex', alignItems: 'center', justifyContent: 'center' }}
      onClick={e => { if (e.target === e.currentTarget) onClose() }}>
      <div style={{ background: 'var(--s2)', border: '1px solid var(--b2)', borderRadius: 8,
        maxWidth: 440, width: '92%', overflow: 'hidden', display: 'flex', flexDirection: 'column',
        maxHeight: '90vh' }}>

        {/* Header */}
        <div style={{ padding: '12px 18px', borderBottom: '1px solid var(--b1)',
          display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexShrink: 0 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <span style={{ fontSize: 14, fontWeight: 700, color: 'var(--text)' }}>Details</span>
            <div style={{ display: 'flex', gap: 2 }}>
              <TabBtn id="order"     label="Order" />
              <TabBtn id="analytics" label="Analytics" />
            </div>
          </div>
          <button className="btn btn-ghost" style={{ fontSize: 11, padding: '2px 8px' }}
            onClick={onClose}>✕</button>
        </div>

        {/* Scrollable content */}
        <div style={{ overflowY: 'auto', flex: 1 }}>
          {tab === 'order' && (
            <>
              {/* User Stats */}
              <div style={{ padding: '12px 18px', borderBottom: '1px solid var(--b1)' }}>
                <div style={{ fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)',
                  textTransform: 'uppercase', letterSpacing: '.07em', marginBottom: 10 }}>User Stats</div>
                {[
                  ['User',       listing.username],
                  ['UID',        listing.uid],
                  ['Post Count', parseInt(listing.postnum || 0).toLocaleString()],
                  ['Reputation', parseInt(listing.reputation || 0).toLocaleString()],
                  ['Avg PPD',    `${ppd} posts/day`],
                ].map(([label, value]) => (
                  <div key={label} style={{ display: 'flex', justifyContent: 'space-between',
                    padding: '5px 0', borderBottom: '1px solid rgba(255,255,255,.04)' }}>
                    <span style={{ fontSize: 12, color: 'var(--sub)' }}>{label}</span>
                    <span style={{ fontSize: 12, color: 'var(--text)',
                      fontWeight: label === 'User' ? 700 : 400 }}>{value}</span>
                  </div>
                ))}
              </div>

              {/* Order Info */}
              <div style={{ padding: '12px 18px', borderBottom: '1px solid var(--b1)' }}>
                <div style={{ fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)',
                  textTransform: 'uppercase', letterSpacing: '.07em', marginBottom: 10 }}>Order Information</div>
                {[
                  ['Duration', `${listing.duration} days`],
                  ['Price',    `${parseInt(listing.price).toLocaleString()} bytes`],
                  ['Rate',     `${parseInt(pricePerDay).toLocaleString()} bytes/day`],
                ].map(([label, value]) => (
                  <div key={label} style={{ display: 'flex', justifyContent: 'space-between',
                    padding: '5px 0', borderBottom: '1px solid rgba(255,255,255,.04)' }}>
                    <span style={{ fontSize: 12, color: 'var(--sub)' }}>{label}</span>
                    <span style={{ fontSize: 12, fontFamily: 'var(--mono)',
                      color: label === 'Price' ? 'var(--acc)' : 'var(--text)',
                      fontWeight: label === 'Price' ? 700 : 400 }}>{value}</span>
                  </div>
                ))}
                {listing.sig && (
                  <div style={{ marginTop: 10 }}>
                    <div style={{ fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)', marginBottom: 5 }}>Sig Content</div>
                    <div style={{ padding: '7px 10px', background: 'var(--bg)', border: '1px solid var(--b1)',
                      borderRadius: 4, fontSize: 11, fontFamily: 'var(--mono)', color: 'var(--sub)',
                      whiteSpace: 'pre-wrap', wordBreak: 'break-all', maxHeight: 90, overflow: 'auto' }}>
                      {listing.sig}
                    </div>
                  </div>
                )}
              </div>
            </>
          )}

          {tab === 'analytics' && <AnalyticsPanel targetUid={listing.uid} hfPpd={listing.ppd} price={listing.price} duration={listing.duration} />}
        </div>

        {/* Footer — buy action always visible */}
        <div style={{ padding: '12px 18px', borderTop: '1px solid var(--b1)', flexShrink: 0,
          display: 'flex', alignItems: 'center', gap: 12 }}>
          {ok ? (
            <span style={{ fontSize: 12, color: 'var(--acc)', fontFamily: 'var(--mono)' }}>✓ Purchase successful!</span>
          ) : (
            <>
              {err && <span style={{ fontSize: 11, color: 'var(--red)', fontFamily: 'var(--mono)', flex: 1 }}>✕ {err}</span>}
              <button className="btn btn-ghost" style={{ fontSize: 12 }} onClick={onClose} disabled={busy}>Cancel</button>
              <button className="btn btn-acc"   style={{ fontSize: 12 }} onClick={buy}     disabled={busy}>
                {busy ? '…' : `Buy — ${parseInt(listing.price).toLocaleString()}b`}
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}

// ── Browse Market ─────────────────────────────────────────────────────────────
function BrowseSection({ myUid }) {
  const browseData  = useStore(s => s.sigmarketBrowse)
  const fetchBrowse = useStore(s => s.fetchSigmarketBrowse)
  const [loading, setLoading] = useState(!browseData)
  const [info,    setInfo]    = useState(null)
  const [buyOk,   setBuyOk]   = useState(null)
  const [err,     setErr]     = useState(null)

  const load = useCallback(async (force = false) => {
    if (!force && browseData) { setLoading(false); return }
    setLoading(true); setErr(null)
    try { await fetchBrowse(force) }
    catch (e) { setErr(e.message || 'Failed to load') }
    finally { setLoading(false) }
  }, [browseData])

  useEffect(() => { load(false) }, [])

  const listings = browseData?.listings || []
  const visible  = listings.filter(l => String(l.uid) !== String(myUid))
  const hasOwn   = listings.some(l => String(l.uid) === String(myUid))

  const TH = ({ children, right }) => (
    <th style={{ padding: '8px 14px', textAlign: right ? 'right' : 'left', fontSize: 9,
      color: 'var(--dim)', fontFamily: 'var(--mono)', textTransform: 'uppercase',
      letterSpacing: '.07em', fontWeight: 600, borderBottom: '1px solid var(--b1)',
      whiteSpace: 'nowrap' }}>{children}</th>
  )

  return (
    <>
      {info && (
        <InfoModal
          listing={info}
          onClose={() => setInfo(null)}
          onBuyDone={() => { setBuyOk(info.username); setInfo(null); load(true) }}
        />
      )}
      <div className="card">
        <div className="card-head">
          <span className="card-icon">🛍</span>
          <span className="card-title">Browse Market</span>
          {!loading && (
            <span style={{ marginLeft: 8, fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)' }}>
              {visible.length} active
            </span>
          )}
          <button className="btn btn-ghost" style={{ marginLeft: 'auto', fontSize: 11 }}
            onClick={() => load(true)} disabled={loading}>
            {loading ? '…' : '↻'}
          </button>
        </div>
        <div className="card-body" style={{ padding: 0 }}>
          {buyOk && (
            <div style={{ margin: '12px 14px 0', fontSize: 12, color: 'var(--acc)',
              padding: '8px 12px', background: 'rgba(0,212,180,.08)',
              border: '1px solid rgba(0,212,180,.2)', borderRadius: 4, fontFamily: 'var(--mono)' }}>
              ✓ Purchased {buyOk}'s sig slot!
            </div>
          )}
          {err && (
            <div style={{ margin: '12px 14px 0', fontSize: 12, color: 'var(--red)' }}>✕ {err}</div>
          )}
          {hasOwn && (
            <div style={{ margin: '12px 14px 0', fontSize: 11, color: 'var(--dim)', padding: '6px 10px',
              background: 'var(--s3)', border: '1px solid var(--b1)', borderRadius: 4 }}>
              Your own listing is hidden.
            </div>
          )}
          {loading ? (
            <div style={{ display: 'flex', justifyContent: 'center', padding: 32 }}><div className="spin" /></div>
          ) : !visible.length ? (
            <div style={{ padding: '14px', fontSize: 12, color: 'var(--dim)', fontStyle: 'italic' }}>
              No active listings found.
            </div>
          ) : (
            <div style={{ overflowX: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
                <thead>
                  <tr>
                    <TH>Username</TH>
                    <TH right>Posts</TH>
                    <TH right>Rep</TH>
                    <TH right>PPD</TH>
                    <TH right>Duration</TH>
                    <TH right>Price</TH>
                    <TH right>Price/Day</TH>
                    <TH></TH>
                  </tr>
                </thead>
                <tbody>
                  {visible.map((l, i) => {
                    const pricePerDay = l.price && l.duration
                      ? Math.round(parseInt(l.price) / parseInt(l.duration)).toLocaleString()
                      : '--'
                    return (
                      <tr key={l.uid || i}
                        style={{ borderBottom: '1px solid var(--b1)', cursor: 'pointer' }}
                        onMouseEnter={e => e.currentTarget.style.background = 'var(--s3)'}
                        onMouseLeave={e => e.currentTarget.style.background = ''}>
                        <td style={{ padding: '10px 14px' }}>
                          <a href={`https://hackforums.net/member.php?action=profile&uid=${l.uid}`}
                            target="_blank" rel="noreferrer"
                            style={{ fontWeight: 700, color: 'var(--acc)', textDecoration: 'none' }}
                            onMouseEnter={e => e.target.style.textDecoration = 'underline'}
                            onMouseLeave={e => e.target.style.textDecoration = 'none'}>
                            {l.username}
                          </a>
                        </td>
                        <td style={{ padding: '10px 14px', textAlign: 'right', color: 'var(--sub)',
                          fontFamily: 'var(--mono)', fontSize: 11 }}>
                          {parseInt(l.postnum || 0).toLocaleString()}
                        </td>
                        <td style={{ padding: '10px 14px', textAlign: 'right', color: 'var(--sub)',
                          fontFamily: 'var(--mono)', fontSize: 11 }}>
                          {parseInt(l.reputation || 0).toLocaleString()}
                        </td>
                        <td style={{ padding: '10px 14px', textAlign: 'right', color: 'var(--sub)',
                          fontFamily: 'var(--mono)', fontSize: 11 }}>
                          {l.ppd ? `${parseFloat(l.ppd).toFixed(2)} ppd` : '--'}
                        </td>
                        <td style={{ padding: '10px 14px', textAlign: 'right', color: 'var(--sub)',
                          fontFamily: 'var(--mono)', fontSize: 11 }}>
                          {l.duration} days
                        </td>
                        <td style={{ padding: '10px 14px', textAlign: 'right',
                          fontFamily: 'var(--mono)', fontWeight: 700, color: 'var(--acc)' }}>
                          {parseInt(l.price).toLocaleString()}b
                        </td>
                        <td style={{ padding: '10px 14px', textAlign: 'right', color: 'var(--sub)',
                          fontFamily: 'var(--mono)', fontSize: 11 }}>
                          {pricePerDay}b/d
                        </td>
                        <td style={{ padding: '10px 14px', textAlign: 'right' }}>
                          <button className="btn btn-acc" style={{ fontSize: 11, padding: '3px 12px' }}
                            onClick={() => setInfo(l)}>
                            Info
                          </button>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </>
  )
}

// ── Main Page ─────────────────────────────────────────────────────────────────
export default function SigmarketPage() {
  const [tab,        setTab]        = useState('mine')
  const [refreshing, setRefreshing] = useState(false)

  const myUid            = useStore(s => s.user?.uid)
  const throttle         = useStore(s => s.throttle)
  const status           = useStore(s => s.sigmarketStatus)
  const statusAt         = useStore(s => s.sigmarketStatusAt)
  const fetchStatus      = useStore(s => s.fetchSigmarketStatus)
  const invalidateStatus = useStore(s => s.invalidateSigmarketStatus)

  useEffect(() => { fetchStatus(false) }, [])
  usePolling(() => fetchStatus(false), throttledInterval(300000, throttle))

  const refresh = async () => {
    setRefreshing(true)
    invalidateStatus()
    await fetchStatus(true)
    setTimeout(() => setRefreshing(false), 1500)
  }

  const ts = statusAt ? statusAt * 1000 : null

  if (!status) return (
    <div style={{ display: 'flex', justifyContent: 'center', padding: 40 }}>
      <div className="spin" />
    </div>
  )

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
        <div style={{ display: 'flex', gap: 4 }}>
          {[
            { id: 'mine',      label: 'My Listing' },
            { id: 'browse',    label: 'Browse Market' },
            { id: 'purchases', label: 'My Purchases' },
          ].map(t => (
            <button key={t.id} className={`tab${tab === t.id ? ' on' : ''}`}
              style={{ fontSize: 12 }} onClick={() => setTab(t.id)}>
              {t.label}
            </button>
          ))}
        </div>
        <div style={{ marginLeft: 'auto', display: 'flex', alignItems: 'center', gap: 8 }}>
          {ts && (
            <span style={{ fontSize: 10, color: 'var(--dim)', fontFamily: 'var(--mono)' }}>
              {new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
            </span>
          )}
          <button className="btn btn-ghost" style={{ fontSize: 11 }} disabled={refreshing} onClick={refresh}>
            {refreshing ? '\u2026' : '\u21bb Refresh'}
          </button>
        </div>
      </div>

      {tab === 'mine' && (
        <>
          <ListingSection status={status} onRefresh={refresh} />
          <OrdersTable
            orders={status?.seller_orders || []}
            partyKey="buyer" partyLabel="Buyer"
            icon="&#x1F4CB;" title="Active Orders"
            count={status?.active_order_count}
          />
        </>
      )}

      {tab === 'browse' && <BrowseSection myUid={myUid} />}

      {tab === 'purchases' && (
        <MyPurchasesSection
          orders={status?.buyer_orders || []}
          count={status?.active_buys}
          onRefresh={refresh}
        />
      )}
    </div>
  )
}
