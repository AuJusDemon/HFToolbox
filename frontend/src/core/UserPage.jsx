import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { api } from './api.js'

const GROUPS = {
  "2":"Registered","9":"L33t","28":"Ub3r","46":"H4CK3R$",
  "48":"Quantum","52":"PinkLSZ","50":"Legends","77":"Academy","71":"Warriors",
  "78":"VIBE","70":"Gamblers","68":"Brotherhood",
  "67":"Vendor","7":"Exiled","38":"Banned",
}
const GROUP_PRIORITY = ["9","28","46","48","52","50","77","71","67","78","70","68","7","38","2"]

function groupClass(gid) {
  if (["9","28","46","48","52","50","77","71"].includes(gid)) return "sp sp-rank"
  if (gid === "67") return "sp sp-vendor"
  if (["7","38"].includes(gid)) return "sp sp-dim"
  return "sp sp-comm"
}
function sortGroups(ids) {
  return [...ids].sort((a,b) => {
    const ai=GROUP_PRIORITY.indexOf(a), bi=GROUP_PRIORITY.indexOf(b)
    if(ai===-1&&bi===-1)return 0; if(ai===-1)return 1; if(bi===-1)return-1; return ai-bi
  })
}

const ago = ts => {
  if (!ts) return '--'
  const d = Math.floor(Date.now()/1000) - Number(ts)
  if (d < 60)       return `${d}s ago`
  if (d < 3600)     return `${Math.floor(d/60)}m ago`
  if (d < 86400)    return `${Math.floor(d/3600)}h ago`
  if (d < 86400*30) return `${Math.floor(d/86400)}d ago`
  return new Date(Number(ts)*1000).toLocaleDateString(undefined,{month:'short',day:'numeric',year:'numeric'})
}
const fmtDate = ts => {
  if (!ts) return '--'
  return new Date(Number(ts)*1000).toLocaleDateString(undefined,{month:'short',day:'numeric',year:'numeric'})
}
const fmt = n => Number(n||0).toLocaleString()
const stripBB = s => (s||'').replace(/\[.*?\]/g,'').replace(/\s+/g,' ').trim()

function Spinner() {
  return <div style={{display:'flex',justifyContent:'center',padding:32}}><div className="spin"/></div>
}
function Pager({ page, hasMore, onChange }) {
  return (
    <div style={{display:'flex',gap:8,justifyContent:'flex-end',marginTop:10,alignItems:'center'}}>
      <button className="pg-btn" disabled={page<=1} onClick={()=>onChange(page-1)}>←</button>
      <span style={{fontSize:11,color:'var(--sub)',fontFamily:'var(--mono)'}}>page {page}</span>
      <button className="pg-btn" disabled={!hasMore} onClick={()=>onChange(page+1)}>→</button>
    </div>
  )
}

export default function UserPage() {
  const { uid } = useParams()
  const nav     = useNavigate()

  const [actData,    setActData]    = useState(null)
  const [actLoading, setActLoading] = useState(true)
  const [actErr,     setActErr]     = useState(null)
  const [pPage,      setPPage]      = useState(1)
  const [tPage,      setTPage]      = useState(1)

  const [trustData,    setTrustData]    = useState(null)
  const [trustLoading, setTrustLoading] = useState(false)
  const [trustErr,     setTrustErr]     = useState(null)
  const [rPage,        setRPage]        = useState(1)
  const [trustLoaded,  setTrustLoaded]  = useState(false)

  const [tab, setTab] = useState('posts')

  // Activity is fetched once and cached server-side for 5 min.
  // All pagination is client-side — no API call on page nav.
  const PAGE_SIZE = 20
  const loadActivity = useCallback(() => {
    setActLoading(true); setActErr(null)
    api.get(`/api/user/${uid}/activity`)
      .then(d => { setActData(d); setActLoading(false) })
      .catch(e => { setActErr(e.message||'Failed to load'); setActLoading(false) })
  }, [uid])

  useEffect(() => { loadActivity() }, [loadActivity])

  const loadTrust = useCallback((rp) => {
    setTrustLoading(true); setTrustErr(null)
    api.get(`/api/user/${uid}/trust?ratings_page=${rp}`)
      .then(d => { setTrustData(d); setTrustLoading(false); setTrustLoaded(true) })
      .catch(e => { setTrustErr(e.message||'Failed to load'); setTrustLoading(false) })
  }, [uid])

  const switchTab = (t) => {
    setTab(t)
    if ((t === 'ratings' || t === 'contracts') && !trustLoaded) loadTrust(1)
  }

  const user       = actData?.user
  const allPosts   = [...(actData?.posts   || [])].sort((a,b) => Number(b.dateline||0) - Number(a.dateline||0))
  const allThreads = [...(actData?.threads || [])].sort((a,b) => Number(b.lastpost||0)  - Number(a.lastpost||0))
  const posts      = allPosts.slice((pPage-1)*PAGE_SIZE, pPage*PAGE_SIZE)
  const threads    = allThreads.slice((tPage-1)*PAGE_SIZE, tPage*PAGE_SIZE)
  const ratings = trustData?.ratings || []
  const cstats  = trustData?.contract_stats || {}

  const rawGroups  = user ? [
    user.usergroup, user.displaygroup,
    ...(user.additionalgroups||'').split(',').filter(Boolean)
  ].filter((v,i,a) => v && a.indexOf(v)===i) : []
  const sortedGids = sortGroups(rawGroups.filter(g => GROUPS[g]))
  const avatar     = user?.avatar ? (user.avatar.startsWith('http') ? user.avatar : 'https://hackforums.net/' + (user.avatar||'').replace(/^\.\//, '')) : null

  return (
    <>
      <div style={{marginBottom:14}}>
        <button className="btn btn-ghost" style={{fontSize:11,padding:'3px 10px'}} onClick={() => nav(-1)}>
          ← Back
        </button>
      </div>

      {actErr && <div style={{fontSize:13,color:'var(--red)',marginBottom:12}}>{actErr}</div>}
      {!user && actLoading && <Spinner />}

      {user && (
        <div className="card" style={{marginBottom:12}}>
          <div className="card-body">
            <div style={{display:'flex',gap:14,alignItems:'flex-start'}}>
              <div style={{
                width:56,height:56,borderRadius:6,flexShrink:0,
                background:'var(--s3)',border:'1px solid var(--b2)',overflow:'hidden',
                display:'flex',alignItems:'center',justifyContent:'center',
                fontFamily:'var(--mono)',fontSize:18,fontWeight:700,color:'var(--acc)',
              }}>
                {avatar
                  ? <img src={avatar} alt="" style={{width:'100%',height:'100%',objectFit:'cover'}}
                      onError={e=>e.currentTarget.style.display='none'}/>
                  : (user.username||'?').slice(0,2).toUpperCase()
                }
              </div>
              <div style={{flex:1,minWidth:0}}>
                <div style={{display:'flex',alignItems:'center',gap:10,marginBottom:4,flexWrap:'wrap'}}>
                  <span style={{fontSize:17,fontWeight:700,letterSpacing:'-.02em'}}>{user.username}</span>
                  <span style={{fontSize:10,color:'var(--dim)',fontFamily:'var(--mono)'}}>UID {user.uid}</span>
                  <div style={{display:'flex',gap:4,flexWrap:'wrap'}}>
                    {sortedGids.map(g => <span key={g} className={groupClass(g)}>{GROUPS[g]}</span>)}
                  </div>
                  <a href={`https://hackforums.net/member.php?action=profile&uid=${user.uid}`}
                    target="_blank" rel="noreferrer"
                    style={{fontSize:11,color:'var(--acc)',marginLeft:'auto'}}>
                    HF Profile →
                  </a>
                </div>
                {user.usertitle && (
                  <div style={{fontSize:11,color:'var(--sub)',fontStyle:'italic',marginBottom:8}}>{user.usertitle}</div>
                )}
                <div style={{display:'flex',gap:16,flexWrap:'wrap'}}>
                  {[
                    ['Posts',     fmt(user.postnum)],
                    ['Threads',   fmt(user.threadnum)],
                    ['Bytes',     fmt(user.myps)],
                    ['Rep',       fmt(user.reputation)],
                    ['Referrals', fmt(user.referrals)],
                    ['Time Online', (() => {
                      const s = Number(user.timeonline||0)
                      if (s < 3600)  return `${Math.floor(s/60)}m`
                      if (s < 86400) return `${Math.floor(s/3600)}h`
                      return `${Math.floor(s/86400)}d`
                    })()],
                  ].map(([l,v]) => (
                    <div key={l}>
                      <div style={{fontFamily:'var(--mono)',fontSize:13,fontWeight:700,lineHeight:1.1}}>{v}</div>
                      <div style={{fontSize:9,color:'var(--sub)',textTransform:'uppercase',letterSpacing:'.06em',marginTop:1}}>{l}</div>
                    </div>
                  ))}
                </div>
                {user.website && (
                  <div style={{marginTop:8,fontSize:11}}>
                    <a href={user.website} target="_blank" rel="noreferrer" style={{color:'var(--acc)'}}>{user.website}</a>
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {user && (
        <div className="card">
          <div style={{display:'flex',padding:'0 13px',borderBottom:'1px solid var(--b1)'}}>
            {[['posts','Recent Posts'],['threads','Recent Threads'],['ratings','B-Ratings'],['contracts','Trade Stats']].map(([key,label]) => (
              <button key={key} className={`tab${tab===key?' on':''}`} onClick={() => switchTab(key)}>{label}</button>
            ))}
          </div>

          <div className="card-body">

            {/* ── Posts ── */}
            {tab === 'posts' && (
              actLoading ? <Spinner /> : posts.length === 0
                ? <div style={{fontSize:12,color:'var(--sub)',fontStyle:'italic'}}>No posts found</div>
                : <>
                    <div style={{display:'grid',gridTemplateColumns:'1fr 120px',gap:8,padding:'0 0 5px',borderBottom:'1px solid var(--b1)',marginBottom:4}}>
                      <span className="col-lbl">Post</span>
                      <span className="col-lbl" style={{textAlign:'right'}}>When</span>
                    </div>
                    {posts.map(p => {
                      const preview   = stripBB(p.message).slice(0,120)
                      const threadUrl = `https://hackforums.net/showthread.php?pid=${p.pid}#pid${p.pid}`
                      return (
                        <div key={p.pid} style={{padding:'8px 0',borderBottom:'1px solid rgba(21,30,46,.5)'}}>
                          <div style={{display:'flex',justifyContent:'space-between',gap:8,alignItems:'flex-start',marginBottom:3}}>
                            <a href={threadUrl} target="_blank" rel="noreferrer"
                              style={{fontSize:12,fontWeight:600,color:'var(--acc)',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',flex:1}}>
                              {p.subject || `Post #${p.pid}`}
                            </a>
                            <span style={{fontSize:10,color:'var(--dim)',fontFamily:'var(--mono)',flexShrink:0}}>{ago(p.dateline)}</span>
                          </div>
                          {preview && (
                            <div style={{fontSize:11,color:'var(--sub)',lineHeight:1.5,overflow:'hidden',display:'-webkit-box',WebkitLineClamp:2,WebkitBoxOrient:'vertical'}}>
                              {preview}{preview.length>=120?'…':''}
                            </div>
                          )}
                        </div>
                      )
                    })}
                    <Pager page={pPage} hasMore={pPage * PAGE_SIZE < allPosts.length}
                      onChange={p => setPPage(p)} />
                  </>
            )}

            {/* ── Threads ── */}
            {tab === 'threads' && (
              actLoading ? <Spinner /> : threads.length === 0
                ? <div style={{fontSize:12,color:'var(--sub)',fontStyle:'italic'}}>No threads found</div>
                : <>
                    <div style={{display:'grid',gridTemplateColumns:'1fr 60px 100px',gap:8,padding:'0 0 5px',borderBottom:'1px solid var(--b1)',marginBottom:4}}>
                      <span className="col-lbl">Thread</span>
                      <span className="col-lbl" style={{textAlign:'right'}}>Views</span>
                      <span className="col-lbl" style={{textAlign:'right'}}>Last Post</span>
                    </div>
                    {threads.map(t => (
                      <div key={t.tid} style={{display:'grid',gridTemplateColumns:'1fr 60px 100px',gap:8,alignItems:'center',padding:'6px 0',borderBottom:'1px solid rgba(21,30,46,.5)'}}>
                        <a href={`https://hackforums.net/showthread.php?tid=${t.tid}`} target="_blank" rel="noreferrer"
                          style={{fontSize:12,fontWeight:500,color:'var(--acc)',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>
                          {t.subject}
                        </a>
                        <span style={{fontSize:11,fontFamily:'var(--mono)',color:'var(--dim)',textAlign:'right'}}>{fmt(t.views)}</span>
                        <span style={{fontSize:10,fontFamily:'var(--mono)',color:'var(--dim)',textAlign:'right'}}>{ago(t.lastpost)}</span>
                      </div>
                    ))}
                    <Pager page={tPage} hasMore={tPage * PAGE_SIZE < allThreads.length}
                      onChange={p => setTPage(p)} />
                  </>
            )}

            {/* ── B-Ratings ── */}
            {tab === 'ratings' && (
              trustLoading || !trustLoaded ? <Spinner />
              : trustErr ? <div style={{fontSize:12,color:'var(--red)'}}>{trustErr}</div>
              : ratings.length === 0
              ? <div style={{fontSize:12,color:'var(--sub)',fontStyle:'italic'}}>No b-ratings found</div>
              : <>
                  {/* Summary bar */}
                  <div style={{display:'flex',gap:20,flexWrap:'wrap',padding:'8px 12px',marginBottom:14,background:'var(--s2)',borderRadius:6,border:'1px solid var(--b1)'}}>
                    <div>
                      <div style={{fontFamily:'var(--mono)',fontSize:15,fontWeight:700}}>{ratings.length}{trustData?.ratings_has_more?'+':''}</div>
                      <div style={{fontSize:9,color:'var(--sub)',textTransform:'uppercase',letterSpacing:'.06em'}}>Ratings shown</div>
                    </div>
                    {cstats.total > 0 && <>
                      <div>
                        <div style={{fontFamily:'var(--mono)',fontSize:15,fontWeight:700,color:'var(--green)'}}>{cstats.completion_rate}%</div>
                        <div style={{fontSize:9,color:'var(--sub)',textTransform:'uppercase',letterSpacing:'.06em'}}>Completion</div>
                      </div>
                      <div>
                        <div style={{fontFamily:'var(--mono)',fontSize:15,fontWeight:700,color:cstats.dispute_rate>10?'var(--red)':'var(--dim)'}}>{cstats.dispute_rate}%</div>
                        <div style={{fontSize:9,color:'var(--sub)',textTransform:'uppercase',letterSpacing:'.06em'}}>Dispute Rate</div>
                      </div>
                    </>}
                  </div>

                  <div style={{display:'grid',gridTemplateColumns:'130px 1fr 80px',gap:8,padding:'0 0 5px',borderBottom:'1px solid var(--b1)',marginBottom:4}}>
                    <span className="col-lbl">From</span>
                    <span className="col-lbl">Message</span>
                    <span className="col-lbl" style={{textAlign:'right'}}>Date</span>
                  </div>
                  {ratings.map(r => (
                    <div key={r.crid} style={{display:'grid',gridTemplateColumns:'130px 1fr 80px',gap:8,alignItems:'start',padding:'7px 0',borderBottom:'1px solid rgba(21,30,46,.5)'}}>
                      <div>
                        <a href={`https://hackforums.net/member.php?action=profile&uid=${r.from_uid}`}
                          target="_blank" rel="noreferrer"
                          style={{fontSize:11,fontWeight:600,color:'var(--acc)'}}>
                          {r.from_username || `UID ${r.from_uid}`}
                        </a>
                        {r.contractid && (
                          <div>
                            <a href={`https://hackforums.net/contracts.php?action=view&cid=${r.contractid}`}
                              target="_blank" rel="noreferrer"
                              style={{fontSize:9,color:'var(--dim)'}}>
                              contract #{r.contractid}
                            </a>
                          </div>
                        )}
                        {r.amount !== 0 && (
                          <div style={{fontSize:9,fontFamily:'var(--mono)',color:'var(--sub)',marginTop:2}}>{fmt(r.amount)} bytes</div>
                        )}
                      </div>
                      <div style={{fontSize:12,color:'var(--text)',lineHeight:1.5,wordBreak:'break-word'}}>
                        {r.message || <span style={{color:'var(--dim)',fontStyle:'italic'}}>No message</span>}
                      </div>
                      <div style={{fontSize:10,fontFamily:'var(--mono)',color:'var(--dim)',textAlign:'right'}}>{fmtDate(r.dateline)}</div>
                    </div>
                  ))}
                  <Pager page={rPage} hasMore={trustData?.ratings_has_more} onChange={p => { setRPage(p); loadTrust(p) }} />
                </>
            )}

            {/* ── Trade Stats ── */}
            {tab === 'contracts' && (
              trustLoading || !trustLoaded ? <Spinner />
              : trustErr ? <div style={{fontSize:12,color:'var(--red)'}}>{trustErr}</div>
              : cstats.total === 0
              ? <div style={{fontSize:12,color:'var(--sub)',fontStyle:'italic'}}>No contracts found (last 30)</div>
              : <>
                  <div style={{fontSize:10,color:'var(--dim)',marginBottom:14}}>Based on most recent 30 contracts</div>

                  <div style={{display:'flex',gap:20,flexWrap:'wrap',marginBottom:22}}>
                    {[
                      ['Total',     cstats.total,     'var(--text)'],
                      ['Complete',  cstats.complete,  'var(--green)'],
                      ['Active',    cstats.active,    'var(--blue)'],
                      ['Disputed',  cstats.disputed,  cstats.disputed>0?'var(--red)':'var(--dim)'],
                      ['Cancelled', cstats.cancelled, 'var(--dim)'],
                      ['Expired',   cstats.expired,   'var(--dim)'],
                      ['Awaiting',  cstats.awaiting,  'var(--yellow)'],
                    ].map(([l,v,col]) => (
                      <div key={l}>
                        <div style={{fontFamily:'var(--mono)',fontSize:18,fontWeight:700,color:col,lineHeight:1.1}}>{v}</div>
                        <div style={{fontSize:9,color:'var(--sub)',textTransform:'uppercase',letterSpacing:'.06em',marginTop:2}}>{l}</div>
                      </div>
                    ))}
                  </div>

                  <div style={{display:'flex',flexDirection:'column',gap:12,maxWidth:360}}>
                    {[
                      ['Completion Rate', cstats.completion_rate, false],
                      ['Dispute Rate',    cstats.dispute_rate,    true],
                    ].map(([label, val, invert]) => {
                      const color = invert
                        ? (val===0?'var(--green)':val<=5?'var(--yellow)':'var(--red)')
                        : (val>=80?'var(--green)':val>=50?'var(--yellow)':'var(--red)')
                      return (
                        <div key={label}>
                          <div style={{display:'flex',justifyContent:'space-between',marginBottom:5}}>
                            <span style={{fontSize:11,color:'var(--sub)'}}>{label}</span>
                            <span style={{fontSize:11,fontFamily:'var(--mono)',fontWeight:700,color}}>{val}%</span>
                          </div>
                          <div style={{height:5,borderRadius:3,background:'var(--b2)',overflow:'hidden'}}>
                            <div style={{height:'100%',borderRadius:3,width:`${Math.min(val,100)}%`,background:color,transition:'width .4s ease'}}/>
                          </div>
                        </div>
                      )
                    })}
                  </div>

                  <div style={{marginTop:16,fontSize:10,color:'var(--dim)'}}>Completion rate excludes cancelled contracts.</div>
                </>
            )}

          </div>
        </div>
      )}
    </>
  )
}
