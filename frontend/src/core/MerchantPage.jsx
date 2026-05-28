import { useState, useEffect } from 'react'
import { api } from './api.js'
import MerchantOverview  from './merchant/MerchantOverview.jsx'
import MerchantOffers    from './merchant/MerchantOffers.jsx'
import MerchantPipeline  from './merchant/MerchantPipeline.jsx'
import MerchantDeals     from './merchant/MerchantDeals.jsx'
import MerchantCustomers from './merchant/MerchantCustomers.jsx'
import MerchantPromotion from './merchant/MerchantPromotion.jsx'
import MerchantReports   from './merchant/MerchantReports.jsx'

const TABS = [
  { id:'overview',   label:'Overview'   },
  { id:'offers',     label:'Offers'     },
  { id:'pipeline',   label:'Pipeline'   },
  { id:'deals',      label:'Deals'      },
  { id:'customers',  label:'Customers'  },
  { id:'promotion',  label:'Promotion'  },
  { id:'reports',    label:'Reports'    },
]

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

export default function MerchantPage() {
  const [tab, setTab] = useState('overview')

  const content = {
    overview:  <MerchantOverview setTab={setTab} />,
    offers:    <MerchantOffers />,
    pipeline:  <MerchantPipeline />,
    deals:     <MerchantDeals />,
    customers: <MerchantCustomers />,
    promotion: <MerchantPromotion />,
    reports:   <MerchantReports />,
  }[tab]

  return (
    <div className="content">

      {/* Page header */}
      <div style={{
        display:'flex', alignItems:'center', gap:10, marginBottom:10,
        flexWrap:'wrap',
      }}>
        <h2 style={{
          fontFamily:'var(--mono)', fontSize:15, color:'var(--acc)',
          letterSpacing:'.06em', margin:0, textTransform:'uppercase',
        }}>
          Merchant HQ
        </h2>
        <FreshnessBadge />
      </div>

      {/* Tab bar — sticky on mobile */}
      <div className="mhq-tabs" style={{marginBottom:14}}>
        {TABS.map(t => (
          <button
            key={t.id}
            className={`tab${tab === t.id ? ' on' : ''}`}
            onClick={() => setTab(t.id)}
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
