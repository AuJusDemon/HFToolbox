import { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api } from './api.js'
import MerchantOverview  from './merchant/MerchantOverview.jsx'
import MerchantOffers    from './merchant/MerchantOffers.jsx'
import MerchantPipeline  from './merchant/MerchantPipeline.jsx'
import MerchantDeals     from './merchant/MerchantDeals.jsx'
import MerchantCustomers from './merchant/MerchantCustomers.jsx'
import MerchantThreadUpdates from './merchant/MerchantThreadUpdates.jsx'
import MerchantReports   from './merchant/MerchantReports.jsx'

const TABS = [
  { id:'overview',   label:'Today' },
  { id:'offers',     label:'Sales Threads' },
  { id:'pipeline',   label:'Leads'         },
  { id:'deals',      label:'Contracts'     },
  { id:'customers',  label:'Buyers'        },
  { id:'updates',    label:'Thread Updates'},
  { id:'reports',    label:'Reports'       },
  { id:'settings',   label:'Settings'      },
]

const TAB_META = {
  overview:  ['Today in My Business', 'Contracts, ratings, replies, and sales thread problems waiting on you.'],
  offers:    ['Sales Threads', 'Track thread health, replies, contracts, and bump activity.'],
  pipeline:  ['Leads', 'Review buyer conversations, priorities, and follow-up work.'],
  deals:     ['Contracts', 'Review, approve, complete, rate, and follow up on your contracts.'],
  customers: ['Buyers', 'Customer history, active contracts, follow-up dates, tags, and notes.'],
  updates:   ['Thread Updates', 'Write fresh sales-thread replies, post them through HF, and track what moved afterward.'],
  reports:   ['Reports', 'Completed work, new contracts, leads, buyers, and thread performance by period.'],
  settings:  ['Settings', 'Seller goals, reply expectations, follow-up defaults, and message templates.'],
}

function MerchantSettings({marketAccess=null}) {
  const [goals,setGoals]=useState(null),[templates,setTemplates]=useState([]),[saved,setSaved]=useState(false)
  const [notifications,setNotifications]=useState(null)
  useEffect(()=>{api.get('/api/merchant/goals').then(setGoals);api.get('/api/merchant/pm-templates').then(setTemplates)},[])
  useEffect(()=>{if(marketAccess?.paid)api.get('/api/merchant/notification-preferences').then(setNotifications)},[marketAccess?.paid])
  if(!goals)return <div className="empty">Loading seller settings...</div>
  const save=async()=>{setSaved(false);await api.patch('/api/merchant/goals',goals);setSaved(true)}
  return <div className="mhq-shell"><section><div className="mhq-section-head"><div><h3>Seller Workflow Defaults</h3><p>These rules control due work and performance warnings across My Business.</p></div></div>
    <div className="mhq-filterbar"><label>Reply SLA hours<input className="inp" type="number" min="1" value={goals.reply_sla_hours} onChange={e=>setGoals({...goals,reply_sla_hours:Number(e.target.value)})}/></label><label>Weekly completed goal<input className="inp" type="number" min="0" value={goals.weekly_completed_deal_goal||0} onChange={e=>setGoals({...goals,weekly_completed_deal_goal:Number(e.target.value)})}/></label><label>Stale thread days<input className="inp" type="number" min="1" value={goals.max_stale_offer_days||30} onChange={e=>setGoals({...goals,max_stale_offer_days:Number(e.target.value)})}/></label></div>
    <button className="btn btn-acc" onClick={save}>Save settings</button>{saved&&<span className="market-note"> Saved.</span>}
    </section><section className="mhq-section"><div className="mhq-section-head"><div><h3>PM Templates</h3><p>{templates.length} templates available for contract and lead follow-ups.</p></div></div>
    <div className="mhq-table-wrap"><table className="mhq-table"><thead><tr><th>Template</th><th>Subject</th></tr></thead><tbody>{templates.map(t=><tr key={t.template_id}><td className="mhq-table-primary">{t.name}</td><td>{t.subject||'No subject'}</td></tr>)}</tbody></table></div>
    </section>{marketAccess?.paid&&notifications&&<section className="mhq-section"><div className="mhq-section-head"><div><h3>Telegram reminders</h3><p>Choose which seller tasks are delivered to your connected Telegram account.</p></div></div><div className="mhq-settings-checks"><label><input type="checkbox" checked={notifications.telegram_replies} onChange={e=>setNotifications({...notifications,telegram_replies:e.target.checked})}/> New replies to owned sales threads</label><label><input type="checkbox" checked={notifications.telegram_followups} onChange={e=>setNotifications({...notifications,telegram_followups:e.target.checked})}/> Follow-ups that are due</label><label><input type="checkbox" checked={notifications.telegram_ratings} onChange={e=>setNotifications({...notifications,telegram_ratings:e.target.checked})}/> Contracts waiting for a rating</label></div><button className="btn" onClick={()=>api.put('/api/merchant/notification-preferences',notifications)}>Save reminder settings</button></section>}
  </div>
}

function FreshnessBadge() {
  const [fresh, setFresh] = useState(null)
  useEffect(() => {
    api.get('/api/merchant/freshness')
      .then(d => setFresh(d))
      .catch(() => {})
  }, [])
  if (!fresh) return null
  const age = fresh.contracts_last_crawl
    ? Math.floor((Date.now()/1000 - fresh.contracts_last_crawl) / 60)
    : null
  return (
    <span style={{
      fontSize:9, fontFamily:'var(--mono)', color:'var(--dim)',
      marginLeft:'auto', letterSpacing:'.03em',
    }}>
      {age !== null ? `data ~${age < 60 ? `${age}m` : `${Math.floor(age/60)}h`} old` : 'data age unknown'}
    </span>
  )
}

export default function MerchantPage({embedded=false, marketAccess=null}) {
  const [searchParams] = useSearchParams()
  const initialTab = searchParams.get('tab')
  const initialTid = searchParams.get('tid')

  const [tab, setTab]                         = useState(TABS.some(t => t.id === initialTab) ? initialTab : 'overview')
  const [dealStage, setDealStage]             = useState(null)
  const [dealRatingFilter, setDealRatingFilter] = useState(null)

  // Navigate to Contracts - accepts optional stage and/or rating filter
  const goToDealsWithStage = (stage, ratingFilter = null) => {
    setDealStage(stage)
    setDealRatingFilter(ratingFilter)
    setTab('deals')
  }

  // Tab bar click clears all deal filters so direct nav always shows All
  const handleTabClick = (id) => {
    setDealStage(null)
    setDealRatingFilter(null)
    setTab(id)
  }

  const content = {
    overview:  <MerchantOverview setTab={setTab} onGoToDeals={goToDealsWithStage} />,
    offers:    <MerchantOffers />,
    pipeline:  <MerchantPipeline marketAccess={marketAccess} />,
    deals:     <MerchantDeals initialStage={dealStage} initialRatingFilter={dealRatingFilter} />,
    customers: <MerchantCustomers />,
    updates:   <MerchantThreadUpdates initialTid={initialTab === 'updates' ? initialTid : null} />,
    reports:   <MerchantReports />,
    settings:  <MerchantSettings marketAccess={marketAccess} />,
  }[tab]

  return (
    <div className="content mhq-shell">
      <div className="mhq-page-head">
        <div><h2>{TAB_META[tab][0]}</h2><p>{TAB_META[tab][1]}</p></div>
        <div className="mhq-page-meta"><FreshnessBadge /></div>
      </div>

      {/* Tab bar - sticky on mobile */}
      <div className="mhq-tabs" style={{marginBottom:14}}>
        {TABS.map(t => (
          <button
            key={t.id}
            className={`tab${tab === t.id ? ' on' : ''}`}
            onClick={() => handleTabClick(t.id)}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      {content}

    </div>
  )
}
