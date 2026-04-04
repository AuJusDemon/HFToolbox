import { useEffect, Suspense, lazy } from 'react'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import './index.css'
import useStore    from './store.js'
import Shell       from './core/Shell.jsx'
import Login       from './core/Login.jsx'
import Dashboard   from './core/Dashboard.jsx'
import Settings    from './core/Settings.jsx'
import BytesPage   from './core/BytesPage.jsx'
import extraRoutes from './modules.jsx'

// Lazy-load heavier pages
const ContractsPage      = lazy(() => import('./core/ContractsPage.jsx'))
const BumperPage         = lazy(() => import('./core/BumperPage.jsx'))
const ContractDetailPage = lazy(() => import('./core/ContractDetailPage.jsx'))
const GroupsPage         = lazy(() => import('./core/GroupsPage.jsx'))
const UserPage           = lazy(() => import('./core/UserPage.jsx'))
const PostingPage        = lazy(() => import('./core/PostingPage.jsx'))
const SigmarketPage      = lazy(() => import('./core/SigmarketPage.jsx'))

function RequireAuth({ children }) {
  const { user, authLoading } = useStore()
  if (authLoading) return (
    <div className="empty" style={{ height:'100vh' }}>
      <div className="spin" />
    </div>
  )
  if (!user) return <Navigate to="/" replace />
  return children
}

const Spin = () => (
  <div className="empty" style={{ padding:60 }}>
    <div className="spin" />
  </div>
)

export default function App() {
  const bootstrap = useStore(s => s.bootstrap)
  useEffect(() => { bootstrap() }, [])

  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Login />} />
        <Route path="/dashboard" element={<RequireAuth><Shell /></RequireAuth>}>
          <Route index element={<Dashboard />} />
          <Route path="bytes"          element={<BytesPage />} />
          <Route path="contracts"      element={<Suspense fallback={<Spin/>}><ContractsPage /></Suspense>} />
          <Route path="contracts/:cid" element={<Suspense fallback={<Spin/>}><ContractDetailPage /></Suspense>} />
          <Route path="bumper"         element={<Suspense fallback={<Spin/>}><BumperPage /></Suspense>} />
          <Route path="settings"       element={<Settings />} />
          <Route path="user/:uid"      element={<Suspense fallback={<Spin/>}><UserPage /></Suspense>} />
          <Route path="posting"        element={<Suspense fallback={<Spin/>}><PostingPage /></Suspense>} />
          <Route path="sigmarket"      element={<Suspense fallback={<Spin/>}><SigmarketPage /></Suspense>} />
          {extraRoutes}
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
