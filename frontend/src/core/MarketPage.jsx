import { useEffect, useMemo, useState } from 'react'
import { api } from './api.js'
import { BBCode } from './WirePage.jsx'
import MerchantPage from './MerchantPage.jsx'

const STATUS = {'0':'Awaiting approval','1':'Awaiting approval','2':'Cancelled','3':'Middleman','4':'Cancelled','5':'Active','6':'Complete','7':'Disputed','8':'Expired'}
const CONTRACT_BUCKETS = [
  ['complete_contracts','complete'],['active_contracts','active'],
  ['awaiting_contracts','awaiting'],['middleman_contracts','middleman'],
  ['cancelled_contracts','cancelled'],['disputed_contracts','disputed'],
  ['expired_contracts','expired'],
]
const CATEGORIES = ['hosting','social','accounts','design','development','security','crypto','gaming','marketing','data','other']
const FORUMS = [
  [107,'Premium Sellers'],[44,'Buyers Bay'],[308,'Service Requests'],[106,'Service Offerings'],
  [145,'Hosting Services'],[263,'Social Media Services'],[171,'VPN and Proxy Services'],
  [291,'Online Accounts'],[225,'Webmaster Marketplace'],[176,'Member Sales Market'],
]

function ago(ts) {
  if (!ts) return 'unknown'
  const s=Math.max(0,Math.floor(Date.now()/1000-Number(ts)))
  if(s<60)return`${s}s ago`;if(s<3600)return`${Math.floor(s/60)}m ago`
  if(s<86400)return`${Math.floor(s/3600)}h ago`;return`${Math.floor(s/86400)}d ago`
}
function Empty({children}) { return <div className="market-empty">{children}</div> }
function parseList(value) { try { return JSON.parse(value||'[]') } catch { return [] } }
function newPurchaseId() {
  if (window.crypto?.randomUUID) return window.crypto.randomUUID()
  const seed = `${Date.now()}-${Math.random()}`
  return Array.from(seed).map(ch=>ch.charCodeAt(0).toString(16)).join('').slice(0,64)
}
function purchaseReference(id) {
  const compact=String(id||'').toUpperCase().replace(/[^0-9A-F]/g,'')
  return `MP-${compact.slice(0,12)}`
}

function AccessStrip({access,onPurchase,purchasing,onPreview}) {
  if(!access)return null
  const expires=access.expires_at&&access.expires_at<4102444800
    ?new Date(Number(access.expires_at)*1000).toLocaleDateString():null
  const passTerm=access.permanent?'one-time access':`${access.duration_days} days`
  return <div className="market-access">
    <div><strong>{access.paid?'Market pass active':'Free market tools'}</strong>
      <span>{access.paid?`${access.watch_limit} alert rules, retained history, comparisons, and Telegram delivery${expires?` - active through ${expires}`:''}`:`Recent listings, demand summaries, disputes, My Business, and ${access.watch_limit} dashboard alerts`}</span></div>
    {access.preview_available&&<div className="market-preview-toggle"><span>Dev preview</span><button className={`btn btn-sm${access.preview_mode==='free'?' btn-acc':''}`} onClick={()=>onPreview('free')}>Free</button><button className={`btn btn-sm${access.preview_mode!=='free'?' btn-acc':''}`} onClick={()=>onPreview('paid')}>Paid</button></div>}
    {!access.paid&&<button className="btn btn-acc" onClick={onPurchase} disabled={purchasing}>
      {purchasing?'Processing...':`Add market pass for ${Number(access.price).toLocaleString()} bytes (${passTerm})`}
    </button>}
  </div>
}

function UpgradeDialog({access,open,onClose,onConfirm,purchasing,purchaseId}) {
  if(!open||!access)return null
  const passTerm=access.permanent?'one-time access':`${access.duration_days} days`
  const reference=purchaseReference(purchaseId)
  return <div className="market-modal-backdrop" onMouseDown={e=>{if(e.target===e.currentTarget&&!purchasing)onClose()}}><section className="market-upgrade-dialog" role="dialog" aria-modal="true" aria-labelledby="market-upgrade-title"><header><div><div className="market-kicker">Market pass</div><h3 id="market-upgrade-title">Confirm Market Intelligence</h3></div><button className="btn btn-sm" onClick={onClose} disabled={purchasing}>Close</button></header><div className="market-upgrade-price"><b>{Number(access.price).toLocaleString()} bytes</b><span>{passTerm}</span></div><dl className="market-confirm-list"><dt>Receiver UID</dt><dd>{access.receiver_uid||'Not configured'}</dd><dt>Reference</dt><dd>{reference}</dd><dt>HF reason</dt><dd>HFToolbox | Market Pass | Ref: {reference}</dd></dl><ul><li>Buyer requests matched to products you sell</li><li>Contract movement on watched threads and sellers</li><li>Bump checks for threads that are not turning into replies</li><li>25 alert rules with Telegram delivery</li></ul><footer><button className="btn" onClick={onClose} disabled={purchasing}>Cancel</button><button className="btn btn-acc" onClick={onConfirm} disabled={purchasing||!access.receiver_uid}>{purchasing?'Processing...':`Send ${Number(access.price).toLocaleString()} bytes`}</button></footer></section></div>
}

function ContractCounts({thread}) {
  const total=Number(thread.observed_contracts||0)
  if(!total)return <span className="market-muted">No contracts observed</span>
  const visible=CONTRACT_BUCKETS.filter(([key])=>Number(thread[key]||0)>0)
  const known=visible.reduce((sum,[key])=>sum+Number(thread[key]||0),0)
  return <span className="market-contracts">
    {visible.map(([key,label])=><span className={`contract-${label}`} key={key}>{thread[key]} {label}</span>)}
    {known<total&&<span>{total-known} other</span>}<strong>{total} total</strong>
  </span>
}

function ThreadRow({thread,onOpen}) {
  return <button className="market-thread-row" onClick={()=>onOpen(thread.tid)}>
    <div className="market-thread-main">
      <div className="market-thread-title">{thread.subject}</div>
      <div className="market-thread-meta">{thread.forum_name}  -  UID {thread.seller_uid}  -  posted {ago(thread.created_at)}</div>
      {thread.excerpt&&<div className="market-thread-excerpt">{thread.excerpt.replace(/\s+/g,' ')}</div>}
    </div>
    <div><span className={thread.market_type==='wtb'?'badge badge-yel':'badge badge-acc'}>{thread.market_type==='wtb'?'BUYING':'SELLING'}</span></div>
    <div className="market-activity"><b>{thread.views}</b> views <b>{thread.replies}</b> replies
      <span>7d change: +{thread.views_7d} views  -  +{thread.replies_7d} replies</span></div>
    <ContractCounts thread={thread}/>
    <div className="market-checked">checked {ago(thread.last_seen_at)}</div>
  </button>
}

function WorkItem({label,title,meta,onClick,empty}) {
  if(empty)return <div className="market-work-empty">{empty}</div>
  return <button className="market-work-item" onClick={onClick}>
    <span>{label}</span>
    <b>{title}</b>
    {meta&&<small>{meta}</small>}
  </button>
}

function MarketFreshness({data}) {
  const times=[
    ...(data?.recent_threads||[]).map(row=>Number(row.last_seen_at||row.created_at||0)),
    ...(data?.recent_buyer_threads||[]).map(row=>Number(row.last_seen_at||row.created_at||0)),
    ...(data?.overview_movers||[]).map(row=>Number(row.last_seen_at||row.created_at||0)),
    ...(data?.overview_matches||[]).map(row=>Number(row.matched_at||0)),
    ...(data?.overview_disputes||[]).map(row=>Number(row.last_seen_at||row.created_at||0)),
  ].filter(Boolean)
  const newest=times.length?Math.max(...times):null
  const retained=data?.retention_days||data?.days||null
  return <div className="market-freshness">
    <div><b>Data freshness</b><span>{newest?`Last indexed item ${ago(newest)}`:'No indexed timestamp available'}</span></div>
    <div><b>Data window</b><span>{retained?`${retained} days of retained rows`:'Showing the current retained dataset'}</span></div>
    <div><b>Scope</b><span>This section shows indexed public marketplace activity. Open My Business for your own threads and contracts.</span></div>
  </div>
}

function Threads({preset={},onPresetUsed,access,onPurchase}) {
  const [data,setData]=useState(null),[selected,setSelected]=useState(preset.tid||null),[detail,setDetail]=useState(null)
  const [filters,setFilters]=useState({q:'',category:'',fid:'',market_type:'',sort:'posted',sort_dir:'desc',days:'0',contract_status:'',topic_id:'',topic_name:'',page:1,...preset})
  const presetKey=JSON.stringify(preset)
  useEffect(()=>{if(Object.keys(preset).length){if(preset.tid)setSelected(preset.tid);setFilters(f=>({...f,...preset,page:1}));onPresetUsed?.()}},[presetKey])
  const query=useMemo(()=>{
    const p=new URLSearchParams({page:String(filters.page),perpage:'25',sort:filters.sort,sort_dir:filters.sort_dir,days:filters.days})
    for(const key of ['q','category','fid','market_type','contract_status','topic_id'])if(filters[key])p.set(key,filters[key])
    return p.toString()
  },[filters])
  useEffect(()=>{if(!access)return;setData(null);api.get(`/api/market/threads?${query}`).then(setData).catch(()=>setData({threads:[],error:true}))},[query,access?.paid])
  useEffect(()=>{if(!access||!selected){setDetail(null);return}api.get(`/api/market/threads/${selected}`).then(setDetail).catch(()=>setDetail(null))},[selected,access?.paid])
  const change=(key,value)=>setFilters(f=>({...f,[key]:value,page:1}))
  const changeSort=value=>{
    const [sort,sort_dir]=value.split(':')
    setFilters(f=>({...f,sort,sort_dir,page:1}))
  }

  if(selected)return <div>
    <button className="btn" onClick={()=>setSelected(null)}>Back to results</button>
    {!detail?<Empty>Loading thread...</Empty>:<div className="market-detail">
      <header><div className="market-kicker">{detail.market_type==='wtb'?'Buyer request':'Seller listing'}  -  {detail.forum_name}</div>
        <h3>{detail.subject}</h3><div className="market-thread-meta">UID {detail.seller_uid}  -  {detail.views} views  -  {detail.replies} replies  -  checked {ago(detail.last_seen_at)}</div></header>
      <div className="market-detail-grid"><section><div className="col-lbl">Opening post</div><div className="market-post">{detail.opening_post?<BBCode raw={detail.opening_post}/>:<span className="market-muted">Opening post unavailable.</span>}</div>
        <a className="btn" href={`https://hackforums.net/showthread.php?tid=${detail.tid}`} target="_blank" rel="noreferrer">Open original thread</a></section>
        <aside><div className="col-lbl">Observed contract activity</div>{(detail.contract_counts||[]).length===0?<p className="market-muted">No contracts linked to this TID have been observed.</p>:detail.contract_counts.map(r=><div className="market-stat-line" key={r.status}><span>{STATUS[r.status]||`Status ${r.status}`}</span><b>{r.count}</b></div>)}
          <p className="market-note">Observed contracts indicate activity linked to this thread. They do not prove payment, delivery, or revenue.</p></aside></div>
    </div>}
  </div>

  return <div>
    <div className="market-filter-head"><div><div className="col-lbl">{filters.topic_name?`Topic: ${filters.topic_name}`:'Find market threads'}</div><p>{filters.topic_name?'Showing threads assigned to this demand topic. The text search is not used for topic matches.':'Search the indexed opening posts or narrow the list by demand, category, activity, and observed contracts.'}</p></div>
      <div className="market-head-actions"><button className="btn" onClick={()=>setFilters({q:'',category:'',fid:'',market_type:'',sort:'posted',sort_dir:'desc',days:access?.paid?'0':'30',contract_status:'',topic_id:'',topic_name:'',page:1})}>Reset filters</button></div></div>
    <div className="market-filters">
      <label>Search<input className="inp" placeholder="Product, service, phrase, or seller" value={filters.q} onChange={e=>change('q',e.target.value)}/></label>
      <label>Listing type<select className="inp" value={filters.market_type} onChange={e=>change('market_type',e.target.value)}><option value="">Selling and buying</option><option value="wts">Selling</option><option value="wtb">Buyer requests</option></select></label>
      <label>Category<select className="inp" value={filters.category} onChange={e=>change('category',e.target.value)}><option value="">All categories</option>{CATEGORIES.map(v=><option key={v}>{v}</option>)}</select></label>
      <label>Forum<select className="inp" value={filters.fid} onChange={e=>change('fid',e.target.value)}><option value="">All forums</option>{FORUMS.map(([id,name])=><option key={id} value={id}>{name}</option>)}</select></label>
      <label>Time range<select className="inp" value={access?.paid?filters.days:(filters.days==='0'?'30':filters.days)} onChange={e=>change('days',e.target.value)}>{access?.paid&&<option value="0">All retained</option>}<option value="1">Past 24 hours</option><option value="7">Past 7 days</option><option value="30">Past 30 days</option></select></label>
      {access?.paid&&<label>Contract signal<select className="inp" value={filters.contract_status} onChange={e=>change('contract_status',e.target.value)}><option value="">Any contract status</option><option value="active">Active</option><option value="complete">Completed</option><option value="awaiting">Awaiting approval</option><option value="middleman">Middleman</option><option value="cancelled">Cancelled</option><option value="disputed">Disputed</option><option value="expired">Expired</option></select></label>}
      <label>Sort results<select className="inp" value={`${filters.sort}:${filters.sort_dir}`} onChange={e=>changeSort(e.target.value)}>
        <option value="posted:desc">Newest threads</option><option value="posted:asc">Oldest threads</option>
        <option value="views:desc">Most viewed</option><option value="views:asc">Fewest viewed</option>
        <option value="replies:desc">Most replies</option><option value="replies:asc">Fewest replies</option>
        {access?.paid&&<><option value="recent_contracts:desc">Most recently contracted</option>
          <option value="total_contracts:desc">Most contracts</option><option value="total_contracts:asc">Fewest contracts</option>
          <option value="complete_contracts:desc">Most completed contracts</option>
          <option value="active_contracts:desc">Most active contracts</option>
          <option value="cancelled_contracts:desc">Most cancelled contracts</option>
          <option value="disputed_contracts:desc">Most disputed contracts</option>
          <option value="expired_contracts:desc">Most expired contracts</option></>}
      </select></label>
    </div>
    <div className="market-results-head"><b>{data?`${data.total} matching threads`:'Loading results...'}</b><span>Click a thread for its opening post and observed contract breakdown.</span></div>
    {!data?<Empty>Loading market threads...</Empty>:(data.threads||[]).length===0?<Empty>No threads match these filters.</Empty>:<div className="market-thread-list">{data.threads.map(t=><ThreadRow key={t.tid} thread={t} onOpen={setSelected}/>)}</div>}
    {data&&data.total>data.perpage&&<div className="pg market-pages"><button className="pg-btn" disabled={filters.page===1} onClick={()=>setFilters(f=>({...f,page:f.page-1}))}>Previous</button><span className="pg-info">Page {filters.page}  -  {data.total} results</span><button className="pg-btn" disabled={filters.page*data.perpage>=data.total} onClick={()=>setFilters(f=>({...f,page:f.page+1}))}>Next</button></div>}
  </div>
}

function Pulse({access,openBrowse,openDemand,openSection,onPurchase}) {
  const [data,setData]=useState(null)
  useEffect(()=>{
    api.get('/api/market/pulse').then(setData).catch(()=>setData({error:true}))
  },[access?.paid])
  if(!access||!data)return <Empty>Loading market overview...</Empty>
  if(data.error)return <Empty>Market overview is unavailable.</Empty>
  const recentBuyerRequests=(data.recent_buyer_threads||[]).slice(0,5)
  const recentListings=(data.recent_threads||[]).filter(row=>row.market_type==='wts').slice(0,5)
  if(access&&!access.paid)return <div className="market-free-overview">
    <section className="market-free-hero"><div><div className="market-kicker">Marketplace</div><h3>See what buyers are asking for before you bump another thread.</h3><p>Free accounts can browse recent listings, demand topics, dispute threads, and My Business. The market pass adds matched buyer requests, movement history, market comparisons, and Telegram alerts.</p></div><div className="market-free-plan"><span>Market pass</span><b>{Number(access.price).toLocaleString()} bytes</b><small>{access.permanent?'one-time access':`${access.duration_days} days`}</small><button className="btn btn-acc" onClick={onPurchase}>View plan</button></div></section>
    <MarketFreshness data={data}/>
    <section className="market-feature-table"><div><b>Free</b><span>Recent listings and buyer requests</span><span>Demand topic summaries</span><span>Deal disputes</span><span>{access.watch_limit} dashboard alerts</span><span>My Business work queue</span></div><div><b>Market pass</b><span>Buyer requests matched to your products</span><span>Contract movement on watched threads</span><span>Bump checks and thread health</span><span>25 alerts with Telegram delivery</span></div></section>
    <section className="market-seller-proof"><div><span>Why this is here</span><b>Use the marketplace when you need buyer demand, competitor movement, or dispute context before changing your sales thread.</b></div><div><span>What to do next</span><b>Start with demand, then open matching listings or My Business when a thread needs a reply, bump, rating, or follow-up.</b></div></section>
    <div className="market-section-head"><div><div className="col-lbl">Current buyer demand</div><p>A topic-level view of what buyers are requesting.</p></div><button className="btn" onClick={()=>openDemand({})}>Open Demand</button></div>
    <div className="market-category-grid">{(data.categories||[]).filter(row=>Number(row.wtb_threads||0)>0).slice(0,6).map(row=><button key={row.category} onClick={()=>openDemand({})}><div><strong>{row.category}</strong></div><div className="market-category-signals"><span>{row.wtb_threads||0} buyer requests</span></div></button>)}</div>
    <div className="market-overview-columns"><section><div className="market-section-head"><div><div className="col-lbl">Recent listings</div><p>Seller threads added during the free window.</p></div><button className="btn btn-sm" onClick={()=>openBrowse({market_type:'wts',days:'30'})}>Browse listings</button></div><div className="market-overview-list">{recentListings.map(row=><button key={row.tid} onClick={()=>openBrowse({tid:String(row.tid)})}><b>{row.subject}</b><span>{row.views} views - {row.replies} replies - {ago(row.created_at)}</span></button>)}</div></section><section><div className="market-section-head"><div><div className="col-lbl">Recent buyer requests</div><p>Requests currently visible in the marketplace.</p></div><button className="btn btn-sm" onClick={()=>openBrowse({market_type:'wtb',days:'30'})}>Browse requests</button></div><div className="market-overview-list">{recentBuyerRequests.map(row=><button key={row.tid} onClick={()=>openBrowse({tid:String(row.tid)})}><b>{row.subject}</b><span>{row.views} views - {row.replies} replies - {ago(row.created_at)}</span></button>)}</div></section></div>
  </div>
  const opportunities=data.overview_opportunities||[]
  const movers=data.overview_movers||[]
  const matches=data.overview_matches||[]
  const disputes=data.overview_disputes||[]
  const workItems=[
    opportunities[0]&&{label:'Buyer match',title:opportunities[0].subject,meta:`${opportunities[0].product_name} - ${opportunities[0].unique_buyers||0} buyers`,onClick:()=>openBrowse({tid:String(opportunities[0].tid)})},
    movers[0]&&{label:'Contract movement',title:movers[0].subject,meta:`${movers[0].complete_contracts||0} complete - ${movers[0].active_contracts||0} active`,onClick:()=>openSection('movers')},
    matches[0]&&{label:'Watch hit',title:matches[0].subject,meta:`${matches[0].watch_name} - ${ago(matches[0].matched_at)}`,onClick:()=>openSection('watches')},
    disputes[0]&&{label:'Dispute watch',title:disputes[0].subject,meta:`${disputes[0].views} views - ${disputes[0].replies} replies`,onClick:()=>openSection('disputes')},
  ].filter(Boolean)
  return <div>
    <div className="market-desk-head"><div><div className="market-kicker">Seller desk</div><h3>Start with the work that can turn into a reply, contract, or saved bump.</h3><p>Marketplace data is grouped by what you can do with it: answer a buyer, watch a thread, compare movement, or stop wasting bumps.</p></div><div className="market-intro-actions"><button className="btn btn-acc" onClick={()=>openSection('business')}>Open My Business</button><button className="btn" onClick={()=>openBrowse({sort:'posted',sort_dir:'desc'})}>Explore</button></div></div>
    <MarketFreshness data={data}/>
    <section className="market-workbench"><div className="market-work-main"><div className="market-section-head"><div><div className="col-lbl">Market signals</div><p>Public marketplace movement from indexed threads: buyer demand, active listings, disputes, and contract activity.</p></div></div>{workItems.length===0?<WorkItem empty="No strong market signals right now. Add products, watches, or owned threads to make this view sharper."/>:workItems.map((item,index)=><WorkItem key={`${item.label}:${index}`} {...item}/>)}</div><aside className="market-work-side"><button onClick={()=>openSection('business')}><span>Buyer matches</span><b>{opportunities.length}</b><small>Matched to your products</small></button><button onClick={()=>openSection('movers')}><span>Moving threads</span><b>{movers.length}</b><small>Recent contract signals</small></button><button onClick={()=>openSection('watches')}><span>Watch hits</span><b>{matches.length}</b><small>Saved rules matched</small></button><button onClick={()=>openSection('disputes')}><span>Disputes</span><b>{disputes.length}</b><small>Recent risk signals</small></button></aside></section>
    <div className="market-overview-columns"><section><div className="market-section-head"><div><div className="col-lbl">Buyer requests for your products</div><p>Requests matched to your detected sales threads.</p></div><button className="btn btn-sm" onClick={()=>openSection('business')}>Open Leads</button></div>{opportunities.length===0?<Empty>No strong product matches in the past 30 days.</Empty>:<div className="market-overview-list">{opportunities.map(row=><button key={`${row.product_id}:${row.tid}`} onClick={()=>openBrowse({tid:String(row.tid)})}><b>{row.subject}</b><span>{row.product_name} - {row.unique_buyers||0} buyers - {row.matching_supply||0} seller listings</span></button>)}</div>}</section><section><div className="market-section-head"><div><div className="col-lbl">Contract movement</div><p>Listings with recently observed contracts.</p></div><button className="btn btn-sm" onClick={()=>openSection('movers')}>View Movers</button></div>{movers.length===0?<Empty>No recent movement.</Empty>:<div className="market-overview-list">{movers.map(row=><button key={row.tid} onClick={()=>openBrowse({tid:String(row.tid)})}><b>{row.subject}</b><span>{row.complete_contracts||0} complete - {row.active_contracts||0} active - {row.observed_contracts||0} observed</span></button>)}</div>}</section></div>
    <div className="market-overview-columns"><section><div className="market-section-head"><div><div className="col-lbl">Latest alert matches</div><p>New or changed threads matching your rules.</p></div><button className="btn btn-sm" onClick={()=>openSection('watches')}>View Alerts</button></div>{matches.length===0?<Empty>No recent alert matches.</Empty>:<div className="market-overview-list">{matches.map(row=><button key={row.id} onClick={()=>openBrowse({tid:String(row.tid)})}><b>{row.subject}</b><span>{row.watch_name} - matched {ago(row.matched_at)}</span></button>)}</div>}</section><section><div className="market-section-head"><div><div className="col-lbl">Recent disputes</div><p>Deal Disputes threads in the index.</p></div><button className="btn btn-sm" onClick={()=>openSection('disputes')}>View Disputes</button></div>{disputes.length===0?<Empty>No recent dispute threads.</Empty>:<div className="market-overview-list">{disputes.map(row=><a key={row.tid} href={`https://hackforums.net/showthread.php?tid=${row.tid}`} target="_blank" rel="noreferrer"><b>{row.subject}</b><span>{row.views} views - {row.replies} replies - {ago(row.created_at)}</span></a>)}</div>}</section></div>
    <div className="market-section-head"><div><div className="col-lbl">Recent market activity</div><p>New buyer requests and seller listings.</p></div><button className="btn btn-sm" onClick={()=>openBrowse({sort:'posted',sort_dir:'desc'})}>View all</button></div>
    <div className="market-thread-list">{(data.recent_threads||[]).slice(0,6).map(t=><ThreadRow key={t.tid} thread={t} onOpen={()=>openBrowse({tid:String(t.tid)})}/>)}</div>
  </div>
}
function Movers({access,onPurchase}) {
  const [data,setData]=useState(null)
  useEffect(()=>{if(access?.paid)api.get('/api/market/movers?days=30').then(setData).catch(()=>setData({error:true}))},[access?.paid])
  if(access&&!access.paid)return <div className="market-locked"><div className="market-kicker">Market pass</div><h3>Find listings with recent contract movement.</h3><p>Compare completed, active, cancelled, disputed, and expired contract signals across indexed listings. The pass also includes 25 market alerts and Telegram delivery.</p><button className="btn btn-acc" onClick={onPurchase}>Add pass for {Number(access.price).toLocaleString()} bytes</button></div>
  if(!data)return <Empty>Loading movers...</Empty>
  if(data.error)return <Empty>Market Intelligence access is required.</Empty>
  return <div><div className="market-section-head"><div><div className="col-lbl">Contract movers</div><p>Threads ranked by observed completed and active contracts during the past 30 days.</p></div></div>
    <div className="market-thread-list">{(data.threads||[]).map(row=><a className="market-mover" key={row.tid} href={`https://hackforums.net/showthread.php?tid=${row.tid}`} target="_blank" rel="noreferrer"><div><b>{row.subject}</b><span>UID {row.seller_uid}  -  {row.views} views  -  {row.replies} replies</span></div><div><b>{row.complete_contracts||0}</b> complete  -  <b>{row.active_contracts||0}</b> active</div></a>)}</div></div>
}

function Demand({access,onPurchase,openBrowse}) {
  const [data,setData]=useState(null),[selected,setSelected]=useState(null),[detail,setDetail]=useState(null),[days,setDays]=useState(90)
  const [query,setQuery]=useState(''),[view,setView]=useState('all'),[sortBy,setSortBy]=useState('buyers'),[page,setPage]=useState(1)
  useEffect(()=>{const range=access?.paid?days:7;setData(null);api.get(`/api/market/topics?days=${range}&limit=50`).then(d=>setData({...d,topics:(d.topics||[]).filter(t=>(t.buyer_threads||0)>0)})).catch(()=>setData({topics:[],error:true}))},[access?.paid,days])
  useEffect(()=>{if(!selected){setDetail(null);return}setDetail(null);api.get(`/api/market/topics/${selected.id}?days=${days}`).then(setDetail).catch(()=>setDetail({error:true}))},[selected?.id,days])
  if(!data)return <Empty>Loading demand topics...</Empty>
  const filtered=(data.topics||[]).filter(topic=>topic.name.toLowerCase().includes(query.toLowerCase())).filter(topic=>view==='unmet'?(topic.seller_threads||0)===0:view==='repeated'?(topic.buyer_threads||0)>1:view==='validated'?(topic.observed_contracts||0)>0:true).sort((a,b)=>sortBy==='requests'?Number(b.buyer_threads||0)-Number(a.buyer_threads||0):sortBy==='supply'?Number(a.seller_threads||0)-Number(b.seller_threads||0):sortBy==='evidence'?Number(b.observed_contracts||0)-Number(a.observed_contracts||0):Number(b.unique_buyers||0)-Number(a.unique_buyers||0))
  const totals=(data.topics||[]).reduce((sum,topic)=>({topics:sum.topics+1,requests:sum.requests+Number(topic.buyer_threads||0),buyers:sum.buyers+Number(topic.unique_buyers||0),unmet:sum.unmet+Number((topic.seller_threads||0)===0)}),{topics:0,requests:0,buyers:0,unmet:0})
  const pageSize=15,totalPages=Math.max(1,Math.ceil(filtered.length/pageSize)),visible=filtered.slice((page-1)*pageSize,page*pageSize)
  const setFilter=(setter,value)=>{setter(value);setPage(1);setSelected(null)}
  return <div>
    <div className="market-demand-intro"><div><div className="market-kicker">Buyer demand</div><h3>Find repeated requests and gaps in existing supply.</h3><p>Each topic groups related buyer-request threads. Open one to compare the requests against matching seller listings.</p></div><div className="market-demand-range"><span>Time range</span>{(access?.paid?[7,30,90]:[7]).map(value=><button key={value} className={`btn btn-sm${(access?.paid?days:7)===value?' btn-acc':''}`} onClick={()=>setDays(value)}>{value} days</button>)}</div></div>
    <div className="market-demand-summary"><div><b>{totals.topics}</b><span>topics</span></div><div><b>{totals.requests}</b><span>requests</span></div><div><b>{totals.buyers}</b><span>unique buyers</span></div><div><b>{totals.unmet}</b><span>without supply</span></div></div>
    <div className="market-demand-tools"><input className="inp" value={query} onChange={e=>setFilter(setQuery,e.target.value)} placeholder="Search topics"/><div>{[['all','All topics'],['unmet','Supply gaps'],['repeated','Multiple requests'],['validated','Sales evidence']].map(([id,label])=><button className={`btn btn-sm${view===id?' btn-acc':''}`} key={id} onClick={()=>setFilter(setView,id)}>{label}</button>)}<select className="inp market-demand-sort" value={sortBy} onChange={e=>setFilter(setSortBy,e.target.value)}><option value="buyers">Most buyers</option><option value="requests">Most requests</option><option value="supply">Least supply</option><option value="evidence">Most sales evidence</option></select></div></div>
    <div className="market-demand-layout"><div><div className="market-demand-table"><div className="market-demand-row market-demand-head"><span>Topic</span><span>Requests</span><span>Buyers</span><span>Supply</span><span>Evidence</span></div>
      {visible.map(topic=><button className={`market-demand-row${selected?.id===topic.id?' selected':''}`} key={topic.id} onClick={()=>access?.paid?setSelected(topic):onPurchase()}><strong>{topic.name}</strong><span>{topic.buyer_threads||0}</span><span>{topic.unique_buyers||0}</span><span>{topic.seller_threads||0}{Number(topic.seller_threads||0)===0&&<small>Supply gap</small>}</span><span>{access?.paid?`${topic.observed_contracts||0} contracts`:'Locked'}</span></button>)}
    </div>{filtered.length===0?<Empty>No demand topics match this view.</Empty>:<div className="market-demand-pages"><span>{filtered.length} topics</span><div><button className="btn btn-sm" disabled={page===1} onClick={()=>setPage(p=>p-1)}>Previous</button><span>{page} / {totalPages}</span><button className="btn btn-sm" disabled={page===totalPages} onClick={()=>setPage(p=>p+1)}>Next</button></div></div>}</div><aside className="market-demand-inspector">{!access?.paid?<><div className="col-lbl">Market Intelligence</div><h3>Review the requests and matching listings behind each topic.</h3><p>The free view shows seven-day topic totals. The paid plan adds the underlying threads, longer history, contract movement, and alerts.</p><button className="btn btn-acc" onClick={onPurchase}>View Market Intelligence</button></>:!selected?<Empty>Select a topic to view its requests and matching supply.</Empty>:!detail?<Empty>Loading topic threads...</Empty>:detail.error?<Empty>Topic detail could not be loaded.</Empty>:<><header><div className="col-lbl">{selected.name}</div><button className="btn" onClick={()=>openBrowse({topic_id:String(selected.id),topic_name:selected.name})}>View all results</button></header><section><b>Buyer requests</b>{(detail.threads||[]).filter(t=>t.market_type==='wtb').length===0?<p>No published buyer matches.</p>:(detail.threads||[]).filter(t=>t.market_type==='wtb').slice(0,8).map(t=><a key={t.tid} href={`https://hackforums.net/showthread.php?tid=${t.tid}`} target="_blank" rel="noreferrer">{t.subject}<span>{t.views} views  -  {t.replies} replies</span></a>)}</section><section><b>Seller listings</b>{(detail.threads||[]).filter(t=>t.market_type==='wts').length===0?<p>No matching seller listings.</p>:(detail.threads||[]).filter(t=>t.market_type==='wts').slice(0,8).map(t=><a key={t.tid} href={`https://hackforums.net/showthread.php?tid=${t.tid}`} target="_blank" rel="noreferrer">{t.subject}<span>{t.views} views  -  {t.replies} replies</span></a>)}</section></>}</aside></div>
    {(data.topics||[]).length===0&&<Empty>Demand topics are still being classified from indexed buyer requests.</Empty>}
  </div>
}

function Disputes({access,onPurchase}) {
  const [data,setData]=useState(null),[page,setPage]=useState(1)
  useEffect(()=>{if(!access)return;setData(null);api.get(`/api/market/disputes?page=${page}&perpage=25`).then(setData).catch(()=>setData({disputes:[],total:0,error:true}))},[page,access?.paid])
  if(!data)return <Empty>Loading recent disputes...</Empty>
  const pages=Math.max(1,Math.ceil(Number(data.total||0)/25))
  return <div>
    <div className="market-section-head"><div><div className="market-kicker">Deal disputes</div><h3>Recent dispute threads</h3><p>Use this view to spot risky patterns before you accept, buy, or copy a thread format.</p></div></div>
    {data.error?<Empty>Disputes could not be loaded.</Empty>:(data.disputes||[]).length===0?<Empty>No indexed dispute threads.</Empty>:<div className="market-dispute-table">
      <div className="market-dispute-row market-dispute-head"><span>Dispute thread</span><span>Posted by</span><span>Activity</span><span>Posted</span><span>Status</span></div>
      {data.disputes.map(row=><a className="market-dispute-row" key={row.tid} href={`https://hackforums.net/showthread.php?tid=${row.tid}`} target="_blank" rel="noreferrer"><strong>{row.subject}</strong><span>UID {row.seller_uid}</span><span>{row.views} views  -  {row.replies} replies</span><span>{ago(row.created_at)}</span><span>{row.closed?'Closed':'Open'}</span></a>)}
    </div>}
    {pages>1&&<div className="market-demand-pages"><span>{data.total} indexed disputes</span><div><button className="btn btn-sm" disabled={page===1} onClick={()=>setPage(value=>value-1)}>Previous</button><span>{page} / {pages}</span><button className="btn btn-sm" disabled={page===pages} onClick={()=>setPage(value=>value+1)}>Next</button></div></div>}
  </div>
}

function MyBusiness({access,onPurchase}) {
  return <div className="market-business"><div className="market-business-head"><div><div className="market-kicker">My Business</div><p>Your sales threads, leads, contracts, buyers, thread updates, reports, and settings. Market pass data adds comparisons and alerts, but the seller workspace stays available.</p></div>{!access?.paid&&<button className="btn" onClick={onPurchase}>Add market comparisons</button>}</div><MerchantPage embedded marketAccess={access}/></div>
}

function Watches({access,onPurchase}) {
  const empty={name:'',watch_kind:'phrase',required_phrase:'',optional:'',excluded:'',fid:'',market_type:'any',seller_uid:'',category:'',thread_tid:'',telegram_enabled:false}
  const [watches,setWatches]=useState([]),[matches,setMatches]=useState([]),[telegramConnected,setTelegramConnected]=useState(false),[telegramAvailable,setTelegramAvailable]=useState(false)
  const [matchPage,setMatchPage]=useState(1),[matchTotal,setMatchTotal]=useState(0)
  const [form,setForm]=useState(empty),[error,setError]=useState('')
  const threadSpecificKinds = new Set(['competitor_thread', 'contract_movement', 'owned_thread_activity'])
  const showThreadTid = access?.paid && threadSpecificKinds.has(form.watch_kind)
  const load=()=>api.get(`/api/market/watches?page=${matchPage}&perpage=25`).then(d=>{setWatches(d.watches||[]);setMatches(d.matches||[]);setMatchTotal(Number(d.total||0));setTelegramConnected(Boolean(d.telegram_connected));setTelegramAvailable(Boolean(d.telegram_delivery_available))}).catch(()=>{setWatches([]);setMatches([])})
  useEffect(()=>{if(access)load()},[access?.paid,matchPage])
  useEffect(()=>{if(!showThreadTid&&form.thread_tid)setForm(f=>({...f,thread_tid:''}))},[showThreadTid])
  if(!access)return <Empty>Loading alerts...</Empty>
  const submit=async e=>{e.preventDefault();setError('');try{await api.post('/api/market/watches',{name:form.name,watch_kind:form.watch_kind,required_phrase:form.required_phrase,optional_terms:form.optional.split(',').map(v=>v.trim()).filter(Boolean),excluded_terms:form.excluded.split(',').map(v=>v.trim()).filter(Boolean),fids:form.fid?[Number(form.fid)]:[],market_type:form.market_type,seller_uid:form.seller_uid,category:form.category,thread_tid:form.thread_tid?Number(form.thread_tid):null,telegram_enabled:form.telegram_enabled});setForm(empty);load()}catch(err){setError(err?.message||'Could not create alert')}}
  return <div>
    <div className="market-section-head"><div><div className="market-kicker">Market alerts</div><h3>Latest matches</h3><p>New and changed threads matching your saved rules. Use alerts for buyer phrases, competitor threads, seller UIDs, or exact products.</p></div></div>
    {matches.length===0?<Empty>No alert matches yet.</Empty>:<div className="market-match-list">{matches.map(m=><a key={m.id} href={`/dashboard/market?tid=${m.tid}`}><div><b>{m.subject}</b><span>{m.watch_name}  -  {m.market_type==='wtb'?'buyer request':'seller listing'}  -  {m.category}</span></div><div><b>{m.views}</b> views  -  <b>{m.replies}</b> replies<span>matched {ago(m.matched_at)}</span></div></a>)}</div>}
    {matchTotal>25&&<div className="market-demand-pages"><span>{matchTotal} matches</span><div><button className="btn btn-sm" disabled={matchPage===1} onClick={()=>setMatchPage(page=>page-1)}>Previous</button><span>Page {matchPage}</span><button className="btn btn-sm" disabled={matchPage*25>=matchTotal} onClick={()=>setMatchPage(page=>page+1)}>Next</button></div></div>}
    <div className="market-watch-guide"><div><div className="market-kicker">Alert rules</div><h3>Create a rule for one thing you do not want to miss.</h3><p>Match phrases, related terms, one seller, a forum/category, or one exact thread when you choose a thread-specific alert type.</p></div></div>
    <div className="market-watch-layout"><form onSubmit={submit} className="market-watch-form"><div className="col-lbl">Create alert</div>
      <label>Name<span>Shown in alerts</span><input className="inp" required maxLength={120} placeholder="Competitor launch monitor" value={form.name} onChange={e=>setForm(f=>({...f,name:e.target.value}))}/></label>
      <label>Alert type<select className="inp" value={form.watch_kind} onChange={e=>setForm(f=>({...f,watch_kind:e.target.value}))}><option value="phrase">Phrase or terms</option><option value="category">Category activity</option>{access.paid&&<><option value="buyer_demand">Buyer demand</option><option value="seller">Seller activity</option><option value="competitor_thread">Competitor thread</option><option value="contract_movement">Contract movement</option><option value="owned_thread_activity">My thread activity</option></>}</select></label>
      <label>Required phrase<span>Exact phrase that must appear</span><input className="inp" placeholder="managed hosting" value={form.required_phrase} onChange={e=>setForm(f=>({...f,required_phrase:e.target.value}))}/></label>
      <label>Optional terms<span>Any one may match, comma separated</span><input className="inp" placeholder="offshore, bulletproof, no KYC" value={form.optional} onChange={e=>setForm(f=>({...f,optional:e.target.value}))}/></label>
      <label>Exclude terms<span>Reject results containing these terms</span><input className="inp" placeholder="free, giveaway" value={form.excluded} onChange={e=>setForm(f=>({...f,excluded:e.target.value}))}/></label>
      <div className="market-form-row"><label>Listing type<select className="inp" value={form.market_type} onChange={e=>setForm(f=>({...f,market_type:e.target.value}))}><option value="any">Selling or buying</option><option value="wts">Selling only</option><option value="wtb">Buyer requests only</option></select></label>
      <label>Forum<select className="inp" value={form.fid} onChange={e=>setForm(f=>({...f,fid:e.target.value}))}><option value="">Any forum</option>{FORUMS.map(([id,n])=><option key={id} value={id}>{n}</option>)}</select></label></div>
      <label>Seller UID<span>Optional: only match one member</span><input className="inp" inputMode="numeric" value={form.seller_uid} onChange={e=>setForm(f=>({...f,seller_uid:e.target.value.replace(/\D/g,'')}))}/></label>
      <div className="market-form-row"><label>Category<select className="inp" value={form.category} onChange={e=>setForm(f=>({...f,category:e.target.value}))}><option value="">Any category</option>{CATEGORIES.map(value=><option key={value} value={value}>{value}</option>)}</select></label>{showThreadTid&&<label>Exact thread ID<span>Only for this thread-specific rule</span><input className="inp" inputMode="numeric" value={form.thread_tid} onChange={e=>setForm(f=>({...f,thread_tid:e.target.value.replace(/\D/g,'')}))}/></label>}</div>
      {access.paid&&telegramAvailable&&<label className="market-telegram-option"><span><b>Telegram delivery</b><small>Send a Telegram message when this rule matches.</small></span><input type="checkbox" checked={form.telegram_enabled} onChange={e=>setForm(f=>({...f,telegram_enabled:e.target.checked}))}/></label>}
      {access.paid&&!telegramConnected&&<a className="market-settings-link" href="/dashboard/settings">Connect Telegram in Settings</a>}
      {!access.paid&&<button className="btn" type="button" onClick={onPurchase}>Add Telegram delivery and 25 alerts</button>}
      {error&&<div className="market-error">{error}</div>}<button className="btn btn-acc" type="submit">Create alert</button></form>
      <section><div className="market-section-head"><div><div className="col-lbl">Saved alert rules</div><p>{watches.length} of {access.watch_limit} active{!access.paid?'  -  upgrade for 25 alerts and Telegram delivery':''}</p></div></div>
        {watches.length===0?<Empty>No alert rules yet. Try a product, competitor, or buyer-request phrase.</Empty>:<div className="market-watch-list">{watches.map(w=><article key={w.id}><header><div><b>{w.name}</b><span>{w.market_type==='wtb'?'Buyer requests':w.market_type==='wts'?'Seller listings':'All listing types'}</span></div><button className="btn btn-danger" onClick={async()=>{await api.delete(`/api/market/watches/${w.id}`);load()}}>Delete</button></header>
          <dl>{w.required_phrase&&<><dt>Must include</dt><dd>{w.required_phrase}</dd></>}{parseList(w.optional_terms).length>0&&<><dt>Any term</dt><dd>{parseList(w.optional_terms).join(', ')}</dd></>}{parseList(w.excluded_terms).length>0&&<><dt>Exclude</dt><dd>{parseList(w.excluded_terms).join(', ')}</dd></>}{w.seller_uid&&<><dt>Seller</dt><dd>UID {w.seller_uid}</dd></>}<dt>Alert</dt><dd>{w.telegram_enabled?'Dashboard and Telegram':'Dashboard only'}</dd></dl></article>)}</div>}</section>
    </div>
  </div>
}

export default function MarketPage() {
  const params=new URLSearchParams(window.location.search)
  const requestedTid=params.get('tid')
  const requestedTab=params.get('tab')
  const [tab,setTab]=useState(requestedTid?'explore':requestedTab||'overview'),[preset,setPreset]=useState(requestedTid?{tid:requestedTid}:{})
  const [access,setAccess]=useState(null),[purchasing,setPurchasing]=useState(false),[upgradeOpen,setUpgradeOpen]=useState(false),[purchaseId,setPurchaseId]=useState('')
  const loadAccess=()=>api.get('/api/market/access').then(setAccess).catch(()=>{})
  useEffect(()=>{loadAccess()},[])
  const open=(nextTab,nextPreset={})=>{setPreset(nextPreset);setTab(nextTab)}
  const purchase=()=>{setPurchaseId(newPurchaseId());setUpgradeOpen(true)}
  const confirmPurchase=async()=>{const id=purchaseId||newPurchaseId();setPurchaseId(id);setPurchasing(true);try{await api.post('/api/market/access/purchase',{idempotency_key:id});await loadAccess();setUpgradeOpen(false)}finally{setPurchasing(false)}}
  const setPreview=async mode=>{await api.post('/api/market/access/preview',{mode});await loadAccess()}
  const tabs=[['overview','Overview'],['business','My Business'],['explore','Explore'],['demand','Demand'],['movers','Movers'],['disputes','Disputes'],['watches','Alerts']]
  return <div className="content market-page"><header className="market-page-head"><div><h2>Marketplace</h2><p>Sales threads, buyer requests, disputes, and observed contract movement in one seller workspace.</p></div></header>
    <AccessStrip access={access} onPurchase={purchase} purchasing={purchasing} onPreview={setPreview}/>
    <nav className="mhq-tabs market-tabs">{tabs.map(([id,label])=><button key={id} className={`tab${tab===id?' on':''}`} onClick={()=>open(id,{})}>{label}</button>)}</nav>
    {tab==='overview'&&<Pulse access={access} onPurchase={purchase} openBrowse={p=>open('explore',p)} openDemand={()=>open('demand',{})} openSection={section=>open(section,{})}/>}
    {tab==='demand'&&<Demand access={access} onPurchase={purchase} openBrowse={p=>open('explore',p)}/>}
    {tab==='explore'&&<Threads preset={preset} onPresetUsed={()=>setPreset({})} access={access} onPurchase={purchase}/>}
    {tab==='movers'&&<Movers access={access} onPurchase={purchase}/>} {tab==='disputes'&&<Disputes access={access} onPurchase={purchase}/>} {tab==='watches'&&<Watches access={access} onPurchase={purchase}/>}
    {tab==='business'&&<MyBusiness access={access} onPurchase={purchase}/>}
    <UpgradeDialog access={access} open={upgradeOpen} onClose={()=>setUpgradeOpen(false)} onConfirm={confirmPurchase} purchasing={purchasing} purchaseId={purchaseId}/>
  </div>
}
