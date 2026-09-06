import { useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import useStore from '../store.js'

const AUTH_ERROR_MESSAGES = {
  cancelled: 'Authorization was cancelled. No changes were made.',
  session_expired: 'Your sign-in session expired. Start again.',
  oauth_failed: 'Hack Forums did not complete sign-in. Try again.',
  hf_unavailable: 'Hack Forums is temporarily unavailable. Wait a moment and try again.',
  invalid_response: 'Hack Forums returned an incomplete sign-in response. Try again.',
  login_failed: 'Sign-in could not be completed. Try again.',
}

const MODULES = [
  {
    code: 'BUSINESS',
    title: 'My Business',
    status: 'READY',
    text: 'Sales threads, contracts, buyers, leads, ratings, and follow-up work in one place.',
    metrics: ['open replies', 'active contracts', 'thread health'],
  },
  {
    code: 'BUMPS',
    title: 'Bump Service',
    status: 'READY',
    text: 'Run bump jobs, track next bump time, monitor spend, and see if bumps create movement.',
    metrics: ['next bump', 'bytes spent', 'post-bump replies'],
  },
  {
    code: 'MARKET',
    title: 'Marketplace',
    status: 'READY',
    text: 'Browse indexed market activity, buyer demand, contract movement, and watched threads.',
    metrics: ['buyer intent', 'market movement', 'watch rules'],
  },
  {
    code: 'CASINO',
    title: 'Byte Casino',
    status: 'SOON',
    text: 'A separate Toolbox module for table games and Byte-based play once the casino work is ready.',
    metrics: ['poker tables', 'blackjack tables', 'fairness logs'],
  },
]

const BOOT_LINES = [
  ['boot.hftoolbox', 'ready'],
  ['auth.gateway', 'waiting'],
  ['market.index', 'tracking'],
  ['business.workspace', 'ready'],
  ['bump.service', 'ready'],
  ['byte.casino', 'queued'],
]

function LoginButton({ authError, requestedReturn }) {
  return (
    <button
      className="landing-login-btn"
      onClick={() => {
        const returnTo = requestedReturn || sessionStorage.getItem('auth_return_to') || ''
        sessionStorage.removeItem('auth_return_to')
        const url = returnTo ? `/auth/login?next=${encodeURIComponent(returnTo)}` : '/auth/login'
        window.location.href = url
      }}
    >
      {authError ? 'Try Hack Forums Sign-In Again' : 'Login With Hack Forums'}
    </button>
  )
}

function TerminalWindow({ title, children, className = '' }) {
  return (
    <section className={`landing-window ${className}`}>
      <div className="landing-window-bar">
        <span>{title}</span>
        <i />
      </div>
      {children}
    </section>
  )
}

function ModuleCard({ item }) {
  return (
    <article className="landing-module-card">
      <div className="landing-module-top">
        <span>{item.code}</span>
        <b className={item.status === 'SOON' ? 'soon' : ''}>{item.status}</b>
      </div>
      <h3>{item.title}</h3>
      <p>{item.text}</p>
      <div className="landing-module-metrics">
        {item.metrics.map(metric => <small key={metric}>{metric}</small>)}
      </div>
    </article>
  )
}

function BumpMock() {
  return (
    <TerminalWindow title="bump-service.thread.6319077" className="landing-bump-mock">
      <div className="landing-bump-row head">
        <span>Thread</span><span>Next</span><span>Spend</span><span>Result</span>
      </div>
      <div className="landing-bump-row">
        <strong>Spotify Premium Family Plan Slot</strong>
        <span>9h 56m</span>
        <span>240 bytes</span>
        <span className="good">+4 replies</span>
      </div>
      <div className="landing-bump-row">
        <strong>Premium account upgrades</strong>
        <span>2h 14m</span>
        <span>120 bytes</span>
        <span className="warn">watch</span>
      </div>
      <div className="landing-bump-detail">
        <div><span>contracts after bumps</span><b>3</b></div>
        <div><span>reply lift</span><b>+18%</b></div>
        <div><span>wasted bumps</span><b>0</b></div>
      </div>
    </TerminalWindow>
  )
}

function DashboardMock() {
  return (
    <TerminalWindow title="workspace.preview" className="landing-dashboard-mock">
      <div className="landing-preview-grid">
        <div><span>active contracts</span><b>12</b></div>
        <div><span>open replies</span><b>4</b></div>
        <div><span>next bumps</span><b>7</b></div>
        <div><span>market watches</span><b>25</b></div>
      </div>
      <div className="landing-preview-list">
        <p><span>BUSINESS</span> contract #413748 needs review</p>
        <p><span>BUMPS</span> thread movement updated after last bump</p>
        <p><span>MARKET</span> buyer request matched one watched phrase</p>
      </div>
    </TerminalWindow>
  )
}

export default function Login() {
  const { user, authLoading } = useStore()
  const nav = useNavigate()

  const query = new URLSearchParams(window.location.search)
  const authErrorCode = query.get('auth_error') || ''
  const authReference = query.get('auth_ref') || ''
  const requestedReturn = query.get('next') || ''
  const authError = authErrorCode
    ? (AUTH_ERROR_MESSAGES[authErrorCode] || AUTH_ERROR_MESSAGES.login_failed)
    : ''

  useEffect(() => {
    if (!authLoading && user) nav('/dashboard', { replace: true })
  }, [user, authLoading, nav])

  return (
    <main className="landing-page">
      <header className="landing-nav">
        <a className="landing-mark" href="/">
          <span>HF</span>.TOOLBOX
        </a>
        <nav>
          <a href="#modules">Modules</a>
          <a href="#bump-service">Bump Service</a>
          <a href="#roadmap">Roadmap</a>
        </nav>
        <LoginButton authError={authError} requestedReturn={requestedReturn} />
      </header>

      <section className="landing-hero">
        <div className="landing-hero-copy">
          <div className="landing-kicker">Hack Forums Utility Terminal</div>
          <h1>HF Toolbox</h1>
          <p>
            A terminal-style workspace for active Hack Forums members who sell, buy,
            post, watch threads, and keep market work moving.
          </p>
          {authError && (
            <div className="landing-auth-error" role="alert">
              <b>Sign-in was not completed</b>
              <span>{authError}</span>
              {authReference && <small>Reference: {authReference}</small>}
            </div>
          )}
          <div className="landing-hero-actions">
            <LoginButton authError={authError} requestedReturn={requestedReturn} />
            <a className="landing-secondary-btn" href="#modules">View Modules</a>
          </div>
        </div>

        <TerminalWindow title="system.boot">
          <div className="landing-boot">
            {BOOT_LINES.map(([name, state], index) => (
              <div key={name} style={{ '--i': index }}>
                <span>load {name}</span>
                <b>{state}</b>
              </div>
            ))}
          </div>
          <div className="landing-command">
            <span>root@hftoolbox:~$</span>
            <strong>open workspace</strong>
            <i />
          </div>
        </TerminalWindow>
      </section>

      <section id="modules" className="landing-section">
        <div className="landing-section-head">
          <span>Modules</span>
          <h2>Built as a Toolbox, not a single-purpose app.</h2>
          <p>
            Current modules focus on marketplace work. New modules can sit beside them
            without changing the whole product into something else.
          </p>
        </div>
        <div className="landing-module-grid">
          {MODULES.map(item => <ModuleCard key={item.code} item={item} />)}
        </div>
      </section>

      <section className="landing-split">
        <div>
          <div className="landing-section-head compact">
            <span>Workflow</span>
            <h2>See what needs action first.</h2>
            <p>
              The logged-in console should answer what moved, what costs bytes, and
              what needs a response before users dig through pages.
            </p>
          </div>
          <div className="landing-flow">
            <div><b>01</b><span>Thread reply or buyer request appears.</span></div>
            <div><b>02</b><span>Toolbox turns it into work: lead, contract, reply, or bump.</span></div>
            <div><b>03</b><span>User handles the action from the right module.</span></div>
            <div><b>04</b><span>Movement shows up in My Business and reporting.</span></div>
          </div>
        </div>
        <DashboardMock />
      </section>

      <section id="bump-service" className="landing-split landing-split-reverse">
        <BumpMock />
        <div>
          <div className="landing-section-head compact">
            <span>Bump Service</span>
            <h2>Do not bump blind.</h2>
            <p>
              Bumping should show more than whether a job exists. The service page
              should show performance, spend, failures, and movement after each bump.
            </p>
          </div>
          <div className="landing-bullets">
            <p><b>Next bump timing</b><span>Know exactly when each watched thread is scheduled.</span></p>
            <p><b>Spend view</b><span>See service fees, HF bump cost, weekly budget, and pauses.</span></p>
            <p><b>Thread result</b><span>Track replies, views, contracts, and stale activity after bumps.</span></p>
          </div>
        </div>
      </section>

      <section id="roadmap" className="landing-section landing-roadmap">
        <div className="landing-section-head">
          <span>Roadmap</span>
          <h2>More Toolbox sections can come online later.</h2>
          <p>
            Byte Casino should be visible as future direction without taking over the
            marketplace-focused product today.
          </p>
        </div>
        <div className="landing-roadmap-grid">
          <TerminalWindow title="byte-casino.soon">
            <div className="landing-roadmap-terminal">
              <p><span>poker.tables</span><b>in progress</b></p>
              <p><span>blackjack.tables</span><b>planned</b></p>
              <p><span>byte.cashier</span><b>planned</b></p>
              <p><span>fairness.logs</span><b>planned</b></p>
            </div>
          </TerminalWindow>
          <TerminalWindow title="toolbox.core">
            <div className="landing-roadmap-terminal">
              <p><span>my.business</span><b>ready</b></p>
              <p><span>bump.service</span><b>ready</b></p>
              <p><span>marketplace</span><b>ready</b></p>
              <p><span>posting</span><b>ready</b></p>
            </div>
          </TerminalWindow>
        </div>
      </section>

      <section className="landing-final">
        <h2>Open the console.</h2>
        <p>One login into the Toolbox workspace.</p>
        <LoginButton authError={authError} requestedReturn={requestedReturn} />
      </section>

      <footer className="landing-footer">
        <span>Unofficial tool. Not affiliated with Hack Forums.</span>
      </footer>
    </main>
  )
}
