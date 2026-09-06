import { useCallback, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import useStore from '../store.js'
import AsciiField from '../system/AsciiField.jsx'
import { PROGRAMS, PUBLIC_PROGRAMS } from '../system/programRegistry.js'
import './landing-public.css'

const AUTH_ERROR_MESSAGES = {
  cancelled: 'Authorization was cancelled. No changes were made.',
  session_expired: 'Your sign-in session expired. Start again.',
  oauth_failed: 'Hack Forums did not complete sign-in. Try again.',
  hf_unavailable: 'Hack Forums is temporarily unavailable. Wait a moment and try again.',
  invalid_response: 'Hack Forums returned an incomplete sign-in response. Try again.',
  login_failed: 'Sign-in could not be completed. Try again.',
}

const PRIMARY_MODULES = PUBLIC_PROGRAMS.filter(program => program.id !== 'casino')
const SECONDARY_MODULES = PROGRAMS.filter(program => ['sigmarket', 'wire'].includes(program.id))
const MODULE_DETAIL = {
  merchant: ['Contract pipeline', 'Buyer history', 'Thread health'],
  bumper: ['Next bump timing', 'Separate fee records', 'Failure visibility'],
  posting: ['Draft and preview', 'Confirmation step', 'Reply monitoring'],
  contracts: ['Responsibility', 'Terms and timeout', 'Full state history'],
  market: ['Market index', 'Buyer intent', 'Watched criteria'],
  bytes: ['Balance', 'Reason', 'Action reference'],
}

function MiniTerminal({ impulse, onPulse }) {
  return (
    <div className="lp-terminal" aria-label="Toolbox interface preview">
      <div className="lp-terminal-head"><span>hftoolbox / public-interface</span><b>GUEST</b></div>
      <div className="lp-terminal-body">
        <div className="lp-boot-copy" aria-hidden="true">
          <p><span>[OK]</span> program registry mounted</p>
          <p><span>[OK]</span> public module directory ready</p>
          <p><span>[--]</span> account data waits for authentication</p>
        </div>
        <div className="lp-canvas-wrap"><AsciiField mode="home" impulse={impulse} motion onInteract={onPulse} /></div>
        <div className="lp-terminal-command"><span>guest@hftoolbox:~$</span> programs <i /></div>
      </div>
    </div>
  )
}

function InterfaceSample() {
  return (
    <div className="lp-sample" aria-label="Bump Service interface sample">
      <div className="lp-sample-head"><span>BUMP SERVICE / JOB VIEW</span><b>INTERFACE SAMPLE</b></div>
      <div className="lp-sample-thread"><span>THREAD</span><strong>Your sales thread</strong><small>Eligibility and ownership checked before scheduling</small></div>
      <div className="lp-sample-timeline">
        <div className="done"><i /><span>ELIGIBLE</span><small>thread checked</small></div>
        <div className="active"><i /><span>QUEUED</span><small>countdown visible</small></div>
        <div><i /><span>POSTED</span><small>attempt recorded</small></div>
        <div><i /><span>RESULT</span><small>movement attached</small></div>
      </div>
      <div className="lp-sample-ledger">
        <p><span>Toolbox service fee</span><b>10 Bytes after success</b></p>
        <p><span>HF thread bump fee</span><b>Recorded separately</b></p>
        <p><span>Failed attempt</span><b>No successful-service charge</b></p>
      </div>
    </div>
  )
}

export default function LandingMock() {
  const user = useStore(state => state.user)
  const navigate = useNavigate()
  const [impulse, setImpulse] = useState(0)
  const query = new URLSearchParams(window.location.search)
  const authErrorCode = query.get('auth_error') || ''
  const authReference = query.get('auth_ref') || ''
  const requestedReturn = query.get('next') || ''
  const authError = authErrorCode ? (AUTH_ERROR_MESSAGES[authErrorCode] || AUTH_ERROR_MESSAGES.login_failed) : ''

  const beginLogin = useCallback((route = '') => {
    const candidate = route || requestedReturn || sessionStorage.getItem('auth_return_to') || ''
    const returnTo = candidate.startsWith('/dashboard') && !candidate.startsWith('//') ? candidate : ''
    if (returnTo) sessionStorage.setItem('auth_return_to', returnTo)
    window.location.href = returnTo ? `/auth/login?next=${encodeURIComponent(returnTo)}` : '/auth/login'
  }, [requestedReturn])

  const openProgram = (program) => {
    if (!program?.route) return
    if (user) navigate(program.route)
    else beginLogin(program.route)
  }

  return (
    <main className="lp-page">
      <header className="lp-nav">
        <a className="lp-mark" href="#top"><span>HF</span>.TOOLBOX</a>
        <nav aria-label="Landing navigation"><a href="#modules">Programs</a><a href="#bump-service">Bump Service</a><a href="#casino">Casino</a></nav>
        <button type="button" className="lp-login lp-login-compact" onClick={() => user ? navigate('/dashboard') : beginLogin()}>{user ? 'Open Toolbox' : 'Login with HF'}</button>
      </header>

      <section id="top" className="lp-hero">
        <div className="lp-hero-copy">
          <span className="lp-kicker">UNOFFICIAL HACK FORUMS TOOLBOX</span>
          <h1><span>HF</span> Toolbox</h1>
          <p className="lp-lead">A working console for contracts, marketplace research, posting, thread bumps, buyers, and Bytes.</p>
          <p className="lp-hero-note">Open the program you need, handle the work, and return without losing the surrounding context.</p>
          {authError && <div className="lp-auth-error" role="alert"><strong>Sign-in was not completed</strong><span>{authError}</span>{authReference && <small>Reference: {authReference}</small>}</div>}
          <div className="lp-actions">
            <button type="button" className="lp-login" onClick={() => user ? navigate('/dashboard') : beginLogin()}>{user ? 'Open Toolbox' : 'Login with Hack Forums'}</button>
            <a href="#modules" className="lp-secondary">See what is inside</a>
          </div>
          <div className="lp-input-strip" aria-label="Supported input methods"><span>ONE ACCOUNT</span><span>DIRECT PROGRAM ROUTES</span><span>DESKTOP + MOBILE</span></div>
        </div>
        <MiniTerminal impulse={impulse} onPulse={() => setImpulse(value => value + 1)} />
      </section>

      <section id="modules" className="lp-section lp-programs">
        <header className="lp-section-head">
          <div><span className="lp-kicker">PROGRAM DIRECTORY</span><h2>The work is already separated for you.</h2></div>
          <p>Everything is visible here. Select a program to authenticate and land directly in it.</p>
        </header>
        <div className="lp-program-list">
          {PRIMARY_MODULES.map((program, index) => (
            <button type="button" key={program.id} onClick={() => openProgram(program)}>
              <span>{String(index + 1).padStart(2, '0')}</span>
              <div><strong>{program.label}</strong><p>{program.publicSummary}</p></div>
              <ul aria-label={`${program.label} areas`}>{MODULE_DETAIL[program.id].map(item => <li key={item}>{item}</li>)}</ul>
              <b>OPEN PROGRAM</b>
            </button>
          ))}
        </div>
        <div className="lp-secondary-programs"><span>ALSO MOUNTED</span>{SECONDARY_MODULES.map(program => <button type="button" key={program.id} onClick={() => openProgram(program)}>{program.label}</button>)}</div>
      </section>

      <section id="bump-service" className="lp-band">
        <div className="lp-band-inner">
          <div className="lp-copy-block">
            <span className="lp-kicker">BUMPS AS A SERVICE</span><h2>Know what the scheduler is doing.</h2>
            <p>The Bump Service is a dedicated program, but it still connects back to My Business so the thread, spend, replies, and contract results stay together.</p>
            <dl>
              <div><dt>BEFORE</dt><dd>Ownership, thread state, and the next permitted time are checked.</dd></div>
              <div><dt>DURING</dt><dd>The next attempt and job state remain visible.</dd></div>
              <div><dt>AFTER</dt><dd>The result, forum cost, and Toolbox service fee are recorded separately.</dd></div>
            </dl>
            <button type="button" className="lp-inline-action" onClick={() => openProgram(PROGRAMS.find(item => item.id === 'bumper'))}>Open Bump Service</button>
          </div>
          <InterfaceSample />
        </div>
      </section>

      <section className="lp-section lp-workflow">
        <header className="lp-section-head"><div><span className="lp-kicker">ONE WORKFLOW</span><h2>Forum activity becomes something you can act on.</h2></div></header>
        <div className="lp-flow-line">
          <div><span>01</span><strong>Observe</strong><p>A contract changes, a buyer posts, or a watched thread receives a reply.</p></div>
          <div><span>02</span><strong>Route</strong><p>Toolbox places it in the relevant program with the surrounding account context.</p></div>
          <div><span>03</span><strong>Confirm</strong><p>You review supported writes before anything public is sent through your account.</p></div>
          <div><span>04</span><strong>Return</strong><p>The result remains connected to the thread, buyer, contract, or ledger entry.</p></div>
        </div>
      </section>

      <section id="casino" className="lp-band lp-casino">
        <div className="lp-band-inner">
          <div className="lp-copy-block"><span className="lp-kicker lp-kicker-amber">COMING SOON</span><h2>Byte Casino will be another program, not another landing page.</h2><p>Poker, blackjack, cashier boundaries, and fairness records will use the same account shell when that system is ready.</p></div>
          <div className="lp-casino-map" aria-label="Byte Casino areas">
            <div><span>TABLE 01</span><b>POKER</b></div><i>+</i><div><span>TABLE 02</span><b>BLACKJACK</b></div><i>+</i><div><span>ACCOUNT</span><b>CASHIER</b></div><i>+</i><div><span>RECORDS</span><b>VERIFY</b></div>
          </div>
        </div>
      </section>

      <section className="lp-final"><span className="lp-kicker">READY WHEN YOU ARE</span><h2>Go straight to the Toolbox.</h2><button type="button" className="lp-login" onClick={() => user ? navigate('/dashboard') : beginLogin()}>{user ? 'Open Toolbox' : 'Login with Hack Forums'}</button></section>
      <footer className="lp-footer"><span>HF Toolbox is an unofficial tool and is not affiliated with Hack Forums.</span><a href="#top">Back to top</a></footer>
    </main>
  )
}
