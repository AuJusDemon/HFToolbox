import { Component, useEffect, Suspense, lazy } from 'react'
import { BrowserRouter, Routes, Route, Navigate, useParams, useNavigate } from 'react-router-dom'
import './index.css'
import useStore    from './store.js'
import Shell       from './core/Shell.jsx'
import Login       from './core/Login.jsx'
import Dashboard   from './core/Dashboard.jsx'
import Settings    from './core/Settings.jsx'
import BytesPage   from './core/BytesPage.jsx'
import { api }     from './core/api.js'

// Lazy-load heavier pages. They preload immediately so first nav is instant.
const _preloadContracts = import('./core/ContractsPage.jsx')
const _preloadBumper    = import('./core/BumperPage.jsx')
const _preloadDetail    = import('./core/ContractDetailPage.jsx')
const _preloadGroups    = import('./core/GroupsPage.jsx')
const _preloadUser      = import('./core/UserPage.jsx')
const _preloadPosting   = import('./core/PostingPage.jsx')
const _preloadSigmarket = import('./core/SigmarketPage.jsx')
const _preloadWire      = import('./core/WirePage.jsx')
const _preloadMerchant  = import('./core/MerchantPage.jsx')
const _preloadMarket    = import('./core/MarketPage.jsx')

const ContractsPage      = lazy(() => _preloadContracts)
const BumperPage         = lazy(() => _preloadBumper)
const ContractDetailPage = lazy(() => _preloadDetail)
const GroupsPage         = lazy(() => _preloadGroups)
const UserPage           = lazy(() => _preloadUser)
const PostingPage        = lazy(() => _preloadPosting)
const SigmarketPage      = lazy(() => _preloadSigmarket)
const WirePage           = lazy(() => _preloadWire)
const MerchantPage       = lazy(() => _preloadMerchant)
const MarketPage         = lazy(() => _preloadMarket)

function RequireAuth({ children }) {
  const { user, authLoading } = useStore()
  if (authLoading) return (
    <div className="empty" style={{ height:'100vh' }}>
      <div className="spin" />
    </div>
  )
  if (!user) {
    // Save the path they were trying to reach so we can redirect after OAuth
    if (typeof window !== 'undefined' && window.location.pathname !== '/') {
      sessionStorage.setItem('auth_return_to', window.location.pathname + window.location.search)
    }
    return <Navigate to="/" replace />
  }
  return children
}

// Invisible fallback. Chunks preload immediately so this rarely shows.
const Spin = () => (
  <div className="empty" style={{ minHeight: 220 }}>
    <div className="spin" />
  </div>
)

class RouteErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }
  static getDerivedStateFromError(error) {
    return { error }
  }
  componentDidUpdate(prevProps) {
    if (prevProps.locationKey !== this.props.locationKey && this.state.error) {
      this.setState({ error: null })
    }
  }
  render() {
    if (!this.state.error) return this.props.children
    return (
      <div className="content">
        <div className="card" style={{maxWidth:720, margin:'48px auto'}}>
          <div className="card-head"><span>Page crashed</span></div>
          <div className="card-body">
            <p style={{color:'var(--sub)', marginTop:0}}>
              This tab hit a frontend error. Your session is still active.
            </p>
            <div style={{display:'flex', gap:8, flexWrap:'wrap'}}>
              <button className="btn btn-acc" onClick={() => this.setState({ error: null })}>Try again</button>
              <button className="btn" onClick={() => window.location.reload()}>Reload page</button>
            </div>
            <pre style={{marginTop:14, color:'var(--dim)', whiteSpace:'pre-wrap', fontSize:11}}>
              {this.state.error?.message || 'Unknown frontend error'}
            </pre>
          </div>
        </div>
      </div>
    )
  }
}

function GuardedRoute({ children }) {
  const locationKey = window.location.pathname + window.location.search
  return <RouteErrorBoundary locationKey={locationKey}>{children}</RouteErrorBoundary>
}

// Resolve a draft invite token. Navigate to the draft if authorized, dashboard if not.
// The token never grants access on its own; the collaborator list is the real gate.
function DraftJoinRedirect() {
  const { token } = useParams()
  const navigate  = useNavigate()
  useEffect(() => {
    api.get(`/api/posting/drafts/join/${token}`)
      .then(r => {
        if (r?.authorized && r?.draft_id) {
          navigate('/dashboard/posting', { replace: true, state: { openDraftId: r.draft_id } })
        } else {
          navigate('/dashboard', { replace: true })
        }
      })
      .catch(() => navigate('/dashboard', { replace: true }))
  }, [token, navigate])
  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', padding: 60 }}>
      <div className="spin" />
    </div>
  )
}

export default function App() {
  const bootstrap = useStore(s => s.bootstrap)
  useEffect(() => { bootstrap() }, [])

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Login />} />
        <Route path="/dashboard" element={<RequireAuth><Shell /></RequireAuth>}>
          <Route index element={<GuardedRoute><Dashboard /></GuardedRoute>} />
          <Route path="bytes"          element={<GuardedRoute><BytesPage /></GuardedRoute>} />
          <Route path="contracts"      element={<GuardedRoute><Suspense fallback={<Spin/>}><ContractsPage /></Suspense></GuardedRoute>} />
          <Route path="contracts/:cid" element={<GuardedRoute><Suspense fallback={<Spin/>}><ContractDetailPage /></Suspense></GuardedRoute>} />
          <Route path="bumper"         element={<GuardedRoute><Suspense fallback={<Spin/>}><BumperPage /></Suspense></GuardedRoute>} />
          <Route path="settings"       element={<GuardedRoute><Settings /></GuardedRoute>} />
          <Route path="user/:uid"      element={<GuardedRoute><Suspense fallback={<Spin/>}><UserPage /></Suspense></GuardedRoute>} />
          <Route path="posting/join/:token" element={<DraftJoinRedirect />} />
          <Route path="posting"        element={<GuardedRoute><Suspense fallback={<Spin/>}><PostingPage /></Suspense></GuardedRoute>} />
          <Route path="sigmarket"      element={<GuardedRoute><Suspense fallback={<Spin/>}><SigmarketPage /></Suspense></GuardedRoute>} />
          <Route path="wire"           element={<GuardedRoute><Suspense fallback={<Spin/>}><WirePage /></Suspense></GuardedRoute>} />
          <Route path="merchant"       element={<Navigate to="/dashboard/market?tab=business" replace />} />
          <Route path="market"         element={<GuardedRoute><Suspense fallback={<Spin/>}><MarketPage /></Suspense></GuardedRoute>} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
