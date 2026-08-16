import { useState, useEffect, useCallback, useRef } from 'react'
import { api } from './api.js'
import { parseHfId } from './utils.js'
import useStore from '../store.js'

const ago = ts => {
  if (!ts) return '--'
  const d = Math.floor(Date.now()/1000) - ts
  if (d < 60)    return `${d}s ago`
  if (d < 3600)  return `${Math.floor(d/60)}m ago`
  if (d < 86400) return `${Math.floor(d/3600)}h ago`
  return `${Math.floor(d/86400)}d ago`
}
const fmt  = n => Number(n||0).toLocaleString()
const fmtR = n => Math.round(Number(n||0)).toLocaleString()

function usePolling(fn, ms) {
  const ref = useRef(fn); ref.current = fn
  useEffect(() => {
    if (ms == null) return  // null = paused
    const id = setInterval(() => ref.current(), ms)
    return () => clearInterval(id)
  }, [ms])
}

function inferCategory(reason) {
  const r = (reason || '').toLowerCase()
  if (r.includes('sportsbook wager') || r.includes('bytes sportsbook wager')) return 'sbw'
  if (r.includes('wager winner') || r.includes('sports wager winner')) return 'sbs'
  if (r.includes('sportsbook cancel')) return 'sbc'
  if (r.includes('slot')) return 'slo'
  if (r.includes('blackjack')) return 'bla'
  if (r.includes('flip winner') || r.includes('coin flip winner')) return 'cfw'
  if (r.includes('coin flip') || r.includes('flip')) return 'cfl'
  if (r.includes('convo rain')) return 'cvr'
  if (r.includes('quick love')) return 'qlp'
  if (r.includes('thread bump') || r.startsWith('bump') || r.startsWith('autobump fee') || r.includes('hftoolbox | bump fee')) return 'bum'
  if (r.includes('contract')) return 'don'
  if (r.includes('scratch')) return 'scp'
  if (r.includes('lotto') || r.includes('lottery')) return 'ltb'
  if (r.includes('bonus') || r.includes('award')) return 'bon'
  if (r.includes('upgrade')) return 'ugb'
  if (r.includes('crypto game')) return 'cgp'
  return ''
}

const TYPE_LABELS = {
  att:'Send', don:'Transfer/Contract', qlp:'Quick Love', qlc:'Quick Love',
  cvr:'Convo Rain', sbs:'Sportsbook Win', sbw:'Sportsbook Wager', sbc:'Sportsbook Refund',
  slo:'Slots', bla:'Blackjack', cfl:'Coin Flip', cfw:'Coin Flip Win',
  bum:'Thread Bump', bon:'Bonus', ugb:'Upgrade Bonus', ltb:'Lottery',
  cgp:'Crypto Game', cgs:'Crypto Game', gce:'Game Cash', scp:'Scratch Card',
}

const CAT_CODES = {
  sportsbook: ['sbs','sbw','sbc'],
  slots:      ['slo'],
  blackjack:  ['bla'],
  coinflips:  ['cfl','cfw'],
  quicklove:  ['qlp','qlc'],
  rain:       ['cvr'],
  bumps:      ['bum'],
  transfers:  ['att','don'],
  bonuses:    ['bon','ugb'],
  gambling:   ['slo','bla','cfl','cfw','cgp','cgs','scp','ltb'],
}

function BytesHistory({ data }) {
  const [allTxns,  setAllTxns]  = useState([])
  const [loading,  setLoading]  = useState(true)
  const [expanded, setExpanded] = useState(null)
  const [dir,      setDir]      = useState('all')
  const [cat,      setCat]      = useState('')
  const [q,        setQ]        = useState('')
  const [qInput,   setQInput]   = useState('')
  const [page,     setPage]     = useState(1)
  const PERPAGE = 30

  const [total, setTotal] = useState(0)

  useEffect(() => {
    setLoading(true)
    const params = new URLSearchParams({ page: String(page), perpage: String(PERPAGE), direction: dir })
    if (cat && CAT_CODES[cat]) params.set('type_filter', CAT_CODES[cat].join(','))
    if (q) params.set('q', q)
    api.get(`/api/bytes/history?${params.toString()}`)
      .then(d => {
        if (d) {
          setAllTxns(d.transactions || [])
          setTotal(Number(d.total || 0))
        }
        setLoading(false)
      })
      .catch(() => setLoading(false))
  }, [page, dir, cat, q])

  const filtered = allTxns
  const totalPages = Math.max(1, Math.ceil(total / PERPAGE))
  const safePage   = Math.min(page, totalPages)
  const rows       = filtered
  const hasFilters = dir !== 'all' || cat !== '' || q !== ''

  const changeDir = d => { setDir(d); setPage(1) }
  const changeCat = c => { setCat(c === cat ? '' : c); setPage(1) }
  const submitSearch = () => { setQ(qInput); setPage(1) }
  const clearAll = () => { setDir('all'); setCat(''); setQ(''); setQInput(''); setPage(1) }

  const CATS = [
    ['sportsbook','Sportsbook'],['slots','Slots'],['blackjack','Blackjack'],
    ['coinflips','Coin Flips'],['quicklove','Quick Love'],['rain','Rain'],
    ['bumps','Bumps'],['transfers','Transfers'],['bonuses','Bonuses'],['gambling','Gambling'],
  ]

  if (loading) return <div style={{padding:'20px 0',textAlign:'center'}}><span className="spin"/></div>

  return (
    <div>
      <div style={{display:'flex',gap:6,marginBottom:10,flexWrap:'wrap',alignItems:'center'}}>
        <div style={{display:'flex',gap:0,flex:'1 1 180px',minWidth:0}}>
          <input className="inp" placeholder="Search reason..." value={qInput}
            onChange={e=>setQInput(e.target.value)}
            onKeyDown={e=>e.key==='Enter'&&submitSearch()}
            style={{flex:1,borderRadius:'var(--r) 0 0 var(--r)',fontSize:11}}/>
          <button className="btn btn-acc" onClick={submitSearch}
            style={{borderRadius:'0 var(--r) var(--r) 0',fontSize:11,padding:'0 10px',flexShrink:0}}>
            Search
          </button>
        </div>
        {[['all','All'],['received','In'],['sent','Out']].map(([v,l])=>(
          <button key={v} onClick={()=>changeDir(v)}
            className={dir===v?'btn btn-acc':'btn btn-ghost'}
            style={{fontSize:10,padding:'3px 9px'}}>{l}</button>
        ))}
        {hasFilters && (
          <button className="btn btn-ghost"
            style={{fontSize:10,padding:'3px 8px',color:'var(--dim)'}} onClick={clearAll}>
            Clear
          </button>
        )}
      </div>

      <div style={{display:'flex',gap:4,marginBottom:10,flexWrap:'wrap',alignItems:'center'}}>
        {CATS.map(([v,l])=>(
          <button key={v} onClick={()=>changeCat(v)} style={{
            fontSize:9.5,padding:'2px 8px',borderRadius:3,cursor:'pointer',border:'none',
            fontFamily:'var(--mono)',fontWeight:600,
            background:cat===v?'var(--acc3)':'var(--s3)',
            color:cat===v?'var(--acc)':'var(--dim)',
            outline:cat===v?'1px solid var(--acc)':'none',
          }}>{l}</button>
        ))}
        {hasFilters && (
          <span style={{fontSize:10,color:'var(--dim)',marginLeft:4}}>
            {total.toLocaleString()} result{total!==1?'s':''}
          </span>
        )}
      </div>

      <div className="bh-tbl-hdr" style={{display:'grid',gridTemplateColumns:'80px 110px 1fr 52px',gap:8,
        padding:'0 0 5px',borderBottom:'1px solid var(--b1)',marginBottom:2}}>
        <span className="col-lbl">Amount</span>
        <span className="col-lbl">Category</span>
        <span className="col-lbl">Reason</span>
        <span className="col-lbl" style={{textAlign:'right'}}>When</span>
      </div>

      {rows.length===0 ? (
        <div style={{fontSize:12,color:'var(--sub)',fontStyle:'italic',padding:'10px 0'}}>
          {hasFilters?'No transactions match':'No transactions yet'}
        </div>
      ) : rows.map((t,i)=>{
          const type   = t.type || inferCategory(t.reason)
          const col    = t.sent?'var(--red)':'var(--acc)'
          const amt    = Number(t.amount)
          const label  = TYPE_LABELS[type] || '---'
          const isOpen = expanded===(t.id||i)
          const isBump = type==='bum'
          const isQL   = type==='qlp'||type==='qlc'

          // Parse "HFToolbox | Bump Fee | TID: 6309426" format
          // Also handles old formats gracefully
          const bumpTidMatch = isBump
            ? ((t.reason||'').match(/TID[:\s]+(\d+)/i) || (t.reason||'').match(/\[tid:(\d+)\]/i) || [])
            : []
          const bumpTid   = bumpTidMatch[1] || ''
          const isHFTBump = (t.reason||'').toLowerCase().includes('hftoolbox')
          const threadLink = (isQL && t.post_tid)
            ? 'https://hackforums.net/showthread.php?tid=' + t.post_tid
            : (isBump && bumpTid)
              ? 'https://hackforums.net/showthread.php?tid=' + bumpTid
              : ''
          // Clean display label for the reason column
          const bumpDisplay = isHFTBump && bumpTid
            ? `Bump Fee — TID: ${bumpTid}`
            : (t.reason || '---')

          return (
            <div key={t.id||i}>
              <div onClick={()=>setExpanded(isOpen?null:(t.id||i))} className="bh-tbl-row" style={{
                display:'grid',gridTemplateColumns:'80px 110px 1fr 52px',gap:8,
                alignItems:'center',padding:'4.5px 0',
                borderBottom:'1px solid rgba(21,30,46,.5)',cursor:'pointer',
                background:isOpen?'rgba(0,212,180,.03)':'transparent',
              }}
                onMouseOver={e=>{if(!isOpen)e.currentTarget.style.background='var(--s2)'}}
                onMouseOut={e=>{if(!isOpen)e.currentTarget.style.background='transparent'}}
              >
                <span style={{fontFamily:'var(--mono)',fontSize:12,fontWeight:700,color:col}}>
                  {t.sent?'-':'+'}{Math.abs(amt).toLocaleString()}
                </span>
                <span style={{fontSize:10,color:'var(--dim)',fontFamily:'var(--mono)',
                  overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>{label}</span>
                <span style={{fontSize:11.5,color:'var(--text)',
                  overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>
                  {isBump ? bumpDisplay : (t.reason||'---')}
                </span>
                <span style={{fontSize:10,color:'var(--sub)',textAlign:'right',
                  fontFamily:'var(--mono)'}}>{ago(t.dateline)}</span>
              </div>

              {isOpen && (
                <div style={{background:'var(--s2)',border:'1px solid var(--b1)',
                  borderRadius:'0 0 4px 4px',padding:'10px 14px',marginBottom:4,
                  display:'flex',flexDirection:'column',gap:8}}>
                  <div style={{display:'flex',gap:24,flexWrap:'wrap'}}>
                    <div>
                      <div className="col-lbl" style={{marginBottom:3}}>Category</div>
                      <div style={{fontSize:11.5,color:'var(--text)'}}>{label}</div>
                    </div>
                    <div>
                      <div className="col-lbl" style={{marginBottom:3}}>Direction</div>
                      <div style={{fontSize:11.5,color:col}}>{t.sent?'Sent':'Received'}</div>
                    </div>
                    <div>
                      <div className="col-lbl" style={{marginBottom:3}}>Amount</div>
                      <div style={{fontSize:11.5,color:col,fontFamily:'var(--mono)',fontWeight:700}}>
                        {t.sent?'-':'+'}{Math.abs(amt).toLocaleString()} bytes
                      </div>
                    </div>
                    <div>
                      <div className="col-lbl" style={{marginBottom:3}}>Date</div>
                      <div style={{fontSize:11,color:'var(--sub)'}}>
                        {t.dateline ? new Date(t.dateline*1000).toLocaleString() : '---'}
                      </div>
                    </div>
                    <div>
                      <div className="col-lbl" style={{marginBottom:3}}>Transaction ID</div>
                      <div style={{fontSize:10,color:'var(--dim)',fontFamily:'var(--mono)'}}>{t.id}</div>
                    </div>
                  </div>
                  {t.reason && (
                    <div>
                      <div className="col-lbl" style={{marginBottom:3}}>Full Reason</div>
                      <div style={{fontSize:11.5,color:'var(--text)',wordBreak:'break-all'}}>{t.reason}</div>
                    </div>
                  )}
                  {isBump && bumpTid && (
                    <div>
                      <div className="col-lbl" style={{marginBottom:3}}>Bumped Thread</div>
                      <div style={{display:'flex',alignItems:'center',gap:8,flexWrap:'wrap'}}>
                        <span style={{fontSize:11,fontFamily:'var(--mono)',color:'var(--text)',fontWeight:600}}>
                          TID: {bumpTid}
                        </span>
                        {threadLink && (
                          <a href={threadLink} target="_blank" rel="noreferrer"
                            onClick={e=>e.stopPropagation()}
                            style={{fontSize:11,color:'var(--acc)'}}>
                            View on HF →
                          </a>
                        )}
                      </div>
                    </div>
                  )}
                  {isQL && threadLink && (
                    <div>
                      <div className="col-lbl" style={{marginBottom:3}}>Thread Quick-Loved</div>
                      <a href={threadLink} target="_blank" rel="noreferrer"
                        onClick={e=>e.stopPropagation()}
                        style={{fontSize:11.5,color:'var(--acc)'}}>
                        View thread on HF
                      </a>
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        })
      }

      {total > PERPAGE && (
        <div className="pg">
          <button className="pg-btn" disabled={safePage<=1} onClick={()=>setPage(safePage-1)}>&lt;</button>
          <span className="pg-info">{safePage} / {totalPages}
            <span style={{color:'var(--dim)'}}> ({total.toLocaleString()} txns)</span>
          </span>
          <button className="pg-btn" disabled={safePage>=totalPages} onClick={()=>setPage(safePage+1)}>&gt;</button>
        </div>
      )}
    </div>
  )
}

function SendBytes({ onDone }) {
  const [sf,setSf]=useState({to_uid:'',amount:'',reason:''})
  const [sd,setSd]=useState(false),[msg,setMsg]=useState(null)
  const send=async()=>{
    if(!sf.to_uid||!sf.amount)return
    setSd(true);setMsg(null)
    try{await api.post('/api/dash/bytes/send',sf);setMsg({ok:true,t:`Sent ${sf.amount} bytes to UID ${sf.to_uid}`});setSf({to_uid:'',amount:'',reason:''});onDone?.()}
    catch(e){setMsg({ok:false,t:e.message||'Send failed - check UID and balance'})}finally{setSd(false)}
  }
  return (
    <div>
      {msg&&<div style={{fontSize:12,color:msg.ok?'var(--acc)':'var(--red)',marginBottom:14,padding:'7px 10px',background:msg.ok?'var(--acc2)':'var(--red2)',border:`1px solid ${msg.ok?'rgba(0,212,180,.2)':'rgba(255,71,87,.2)'}`,borderRadius:'var(--r)'}}>{msg.t}</div>}
      <div style={{display:'flex',flexDirection:'column',gap:6,maxWidth:360}}>
        <input className="inp" placeholder="Recipient UID or URL" value={sf.to_uid} onChange={e=>setSf(f=>({...f,to_uid:parseHfId(e.target.value,'uid')}))}/>
        <input className="inp" placeholder="Amount" type="number" min="1" value={sf.amount} onChange={e=>setSf(f=>({...f,amount:e.target.value}))}/>
        <input className="inp" placeholder="Reason (optional)" value={sf.reason} onChange={e=>setSf(f=>({...f,reason:e.target.value}))} onKeyDown={e=>e.key==='Enter'&&send()}/>
        <button className="btn btn-acc" onClick={send} disabled={sd||!sf.to_uid||!sf.amount}>{sd?<span className="spin"/>:'Send'}</button>
      </div>
    </div>
  )
}
function Section({ title, children }) {
  return (
    <div className="card">
      <div className="card-head"><span className="card-title">{title}</span></div>
      <div className="card-body">{children}</div>
    </div>
  )
}

export default function BytesPage() {
  const apiPaused = useStore(s => s.apiPaused)
  const settings  = useStore(s => s.settings)
  const [data,setData]=useState(null)
  const loadBalance=useCallback(()=>api.get('/api/dash/bytes').then(d=>{if(d)setData(d)}).catch(()=>{}),[])

  useEffect(()=>{loadBalance()},[])
  usePolling(loadBalance, apiPaused ? null : settings.bytesInterval * 1000)

  return (
    <div style={{display:'flex',flexDirection:'column',gap:14}}>

      {/* Balance */}
      <div className="card">
        <div className="card-head" style={{padding:'14px 18px'}}>
          <div>
            <div style={{fontSize:9.5,color:'var(--sub)',textTransform:'uppercase',letterSpacing:'.1em',fontFamily:'var(--mono)',marginBottom:5}}>Balance</div>
            <div style={{fontFamily:'var(--mono)',fontSize:28,fontWeight:700,color:'var(--acc)',letterSpacing:'-.02em',lineHeight:1}}>
              {data?fmt(data.balance):<span className="spin"/>}
            </div>
          </div>
        </div>
      </div>

      {/* Send bytes */}
      <Section title="Send Bytes">
        <SendBytes onDone={loadBalance}/>
      </Section>

      <Section title="History"><BytesHistory data={data}/></Section>

    </div>
  )
}
