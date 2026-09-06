import { Fragment, useCallback, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import useStore from '../store.js'
import { PROGRAMS, PUBLIC_PROGRAMS } from '../system/programRegistry.js'
import HeroInstrumentFrame from './landing/HeroInstrumentFrame.jsx'
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
  merchant: {
    areas: ['Contract pipeline', 'Buyer history', 'Thread health'],
    readout: [
      ['HANDLES', 'Active deals, unanswered sales replies, repeat buyers, ratings, and follow-up work.'],
      ['KEEPS TOGETHER', 'The buyer, contract, sales thread, notes, and latest activity.'],
      ['RESULT', 'A work queue showing what needs attention and what happened next.'],
    ],
  },
  bumper: {
    areas: ['Next bump timing', 'Separate fee records', 'Failure visibility'],
    readout: [
      ['HANDLES', 'Owned-thread checks, permitted bump timing, queued jobs, and retry state.'],
      ['KEEPS TOGETHER', 'Every attempt, its forum cost, the Toolbox fee, and thread movement.'],
      ['RESULT', 'A visible schedule and an audit trail for each bump job.'],
    ],
  },
  posting: {
    areas: ['Draft and preview', 'Confirmation step', 'Reply monitoring'],
    readout: [
      ['HANDLES', 'New threads, replies, reusable drafts, previews, and watched responses.'],
      ['KEEPS TOGETHER', 'The editor, target thread, final confirmation, and posted result.'],
      ['RESULT', 'Forum posting without losing the surrounding conversation.'],
    ],
  },
  contracts: {
    areas: ['Responsibility', 'Terms and timeout', 'Full state history'],
    readout: [
      ['HANDLES', 'Review, approval, active work, waiting, completion, expiry, and disputes.'],
      ['KEEPS TOGETHER', 'Both members, payment side, terms, timeout, and required next action.'],
      ['RESULT', 'Contract state that can be checked without reconstructing the deal.'],
    ],
  },
  market: {
    areas: ['Market index', 'Buyer intent', 'Watched criteria'],
    readout: [
      ['HANDLES', 'Indexed sales threads, service requests, buyer phrases, and watched markets.'],
      ['KEEPS TOGETHER', 'Opening posts, observed activity, contract counts, and matching criteria.'],
      ['RESULT', 'A research view for finding demand and comparing active listings.'],
    ],
  },
  bytes: {
    areas: ['Balance', 'Reason', 'Action reference'],
    readout: [
      ['HANDLES', 'Balance changes, transfers, service charges, and related Toolbox actions.'],
      ['KEEPS TOGETHER', 'Amount, direction, reason, timestamp, and source reference.'],
      ['RESULT', 'A readable ledger explaining where Bytes moved.'],
    ],
  },
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
  const authLoading = useStore(state => state.authLoading)
  const [expandedProgram, setExpandedProgram] = useState('')
  const navigate = useNavigate()
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

      <div className="lp-hero-stage">
        <HeroInstrumentFrame
          programs={PROGRAMS}
          user={user}
          authLoading={authLoading}
          authError={authError}
          authReference={authReference}
          onOpen={openProgram}
          onLogin={() => user ? navigate('/dashboard') : beginLogin()}
        />
      </div>

      <section id="modules" className="lp-section lp-programs">
        <header className="lp-section-head">
          <div><span className="lp-kicker">PROGRAM DIRECTORY</span><h2>Each job has its own workspace.</h2></div>
          <p>Contracts, thread scheduling, posting, market research, and Bytes stay separated while sharing one HF account.</p>
        </header>
        <div className="lp-program-list">
          {PRIMARY_MODULES.map((program, index) => {
            const detail = MODULE_DETAIL[program.id]
            const expanded = expandedProgram === program.id
            const panelId = `program-detail-${program.id}`
            return (
              <Fragment key={program.id}>
                <button type="button" className={expanded ? 'is-expanded' : ''} aria-expanded={expanded} aria-controls={panelId} onClick={() => setExpandedProgram(current => current === program.id ? '' : program.id)}>
                  <span>{String(index + 1).padStart(2, '0')}</span>
                  <div><strong>{program.label}</strong><p>{program.publicSummary}</p></div>
                  <ul aria-label={`${program.label} areas`}>{detail.areas.map(item => <li key={item}>{item}</li>)}</ul>
                  <b>{expanded ? 'CLOSE DETAILS' : 'VIEW DETAILS'}</b>
                </button>
                <section id={panelId} className={`lp-program-readout${expanded ? ' is-open' : ''}`} aria-label={`${program.label} details`} hidden={!expanded}>
                  <header><span>{program.command.toUpperCase()}.INFO</span><b>PROGRAM MANIFEST</b></header>
                  <div>
                    {detail.readout.map(([label, value]) => <p key={label}><span>{label}</span><strong>{value}</strong></p>)}
                  </div>
                </section>
              </Fragment>
            )
          })}
        </div>
        <div className="lp-secondary-programs"><span>ALSO MOUNTED</span>{SECONDARY_MODULES.map(program => <b key={program.id}>{program.label}</b>)}</div>
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
          <div className="lp-copy-block lp-casino-copy">
            <span className="lp-kicker lp-kicker-amber">COMING SOON</span>
            <h2>Byte Casino</h2>
            <p>A multiplayer casino for the HF community. Play poker, blackjack, baccarat, and roulette using Bytes.</p>
            <div className="lp-casino-systems">
              <p><b>BYTE CASHIER</b><span>Available, in-play, and pending balances stay separate.</span></p>
              <p><b>FAIRNESS RECORDS</b><span>Completed games retain the records needed for verification.</span></p>
              <p><b>SERVER CONTROL</b><span>Game state, legal actions, balances, and settlement stay authoritative.</span></p>
            </div>
          </div>
          <div className="lp-game-list" aria-label="Byte Casino games">
            <article><span>01 / TABLE GAME</span><h3>Texas Hold'em</h3><p>Two-to-six-player no-limit poker with blinds, betting rounds, side pots, all-ins, and showdowns.</p></article>
            <article><span>02 / TABLE GAME</span><h3>Blackjack</h3><p>Casino blackjack with clear hand controls, table state, settlement, and round timing.</p></article>
            <article><span>03 / TABLE GAME</span><h3>Baccarat</h3><p>Player, Banker, and Tie wagering with visible dealing, outcomes, and table history.</p></article>
            <article><span>04 / TABLE GAME</span><h3>Roulette</h3><p>Full table wagering across numbers, colors, ranges, and standard roulette bet groups.</p></article>
          </div>
        </div>
      </section>

      <section className="lp-final"><span className="lp-kicker">READY WHEN YOU ARE</span><h2>Go straight to the Toolbox.</h2><button type="button" className="lp-login" onClick={() => user ? navigate('/dashboard') : beginLogin()}>{user ? 'Open Toolbox' : 'Login with Hack Forums'}</button></section>
      <footer className="lp-footer"><span>HF Toolbox is an unofficial tool and is not affiliated with Hack Forums.</span><a href="#top">Back to top</a></footer>
    </main>
  )
}
