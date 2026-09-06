import { useState } from 'react'
import { PROGRAMS } from './programRegistry.js'
import { TerminalButton } from './TerminalOS.jsx'

const WORKFLOWS = {
  business: {
    index: '01', kicker: 'SALES WORKSTATION', title: 'My Business',
    summary: 'Keep contracts, buyers, thread replies, and follow-up work in one operating view.',
    stages: [
      ['REVIEW', 'Contract decisions'], ['ACTIVE', 'Work underway'], ['WAITING', 'Their move'], ['FOLLOW-UP', 'Ratings and replies'],
    ],
    inspector: [
      ['CONTRACT PIPELINE', 'Review through dispute'], ['BUYER MEMORY', 'Notes, tags, repeat work'],
      ['THREAD SIGNAL', 'Replies, bumps, outcomes'], ['NEXT ACTION', 'What needs attention'],
    ],
    callout: 'Open a contract without leaving the workspace, then return to the exact queue that surfaced it.',
  },
  bumps: {
    index: '02', kicker: 'SCHEDULE CONTROL', title: 'Bump Service',
    summary: 'Schedule eligible sales threads, see the next attempt, and audit every service charge.',
    stages: [
      ['ELIGIBLE', 'Thread checked'], ['QUEUED', 'Timer running'], ['POSTED', 'Attempt recorded'], ['MEASURED', 'Movement attached'],
    ],
    inspector: [
      ['NEXT WINDOW', 'Visible countdown'], ['SERVICE FEE', '10 Bytes per success'],
      ['HF BUMP FEE', 'Shown separately'], ['FAILURE STATE', 'Reason and retry path'],
    ],
    callout: 'A bump is charged only when the scheduled post succeeds. Service and forum costs stay separate.',
  },
  market: {
    index: '03', kicker: 'MARKET OBSERVER', title: 'Marketplace',
    summary: 'Scan indexed market activity, narrow it by area, and connect buyer intent to your offers.',
    stages: [
      ['INDEX', 'Observed threads'], ['FILTER', 'Category and intent'], ['WATCH', 'Saved criteria'], ['OPEN', 'Forum context'],
    ],
    inspector: [
      ['MARKET AREAS', 'Bazaar through Auxiliary'], ['INTENT MATCH', 'Phrases worth reviewing'],
      ['THREAD HISTORY', 'Movement over time'], ['CONTRACT SIGNAL', 'Observed deal context'],
    ],
    callout: 'Marketplace data is evidence for review, not an invented recommendation or automatic sales claim.',
  },
  contracts: {
    index: '04', kicker: 'DEAL STATE MACHINE', title: 'Contracts',
    summary: 'See contract state, responsibility, and the next supported action without mixing dead deals into active work.',
    stages: [
      ['REVIEW', 'Approve or deny'], ['PROGRESS', 'Both sides active'], ['WAITING', 'One side pending'], ['CLOSED', 'Final outcome'],
    ],
    inspector: [
      ['PARTIES', 'Buyer and seller'], ['TERMS', 'Value, timeout, positions'],
      ['RESPONSIBILITY', 'Who acts next'], ['OUTCOME', 'Complete, expire, dispute'],
    ],
    callout: 'Supported actions stay in Toolbox. Contract ratings still open on HF where the API requires it.',
  },
  posting: {
    index: '05', kicker: 'POSTING CONSOLE', title: 'Posting',
    summary: 'Move from a private draft to an exact preview and a confirmed forum action.',
    stages: [
      ['DRAFT', 'Write privately'], ['PREVIEW', 'Inspect output'], ['CONFIRM', 'Approve action'], ['WATCH', 'Return on reply'],
    ],
    inspector: [
      ['EDITOR', 'Thread and reply modes'], ['TEMPLATES', 'Reusable response text'],
      ['PREVIEW', 'Exact public payload'], ['REPLY WATCH', 'Thread response state'],
    ],
    callout: 'Nothing posts while you are drafting. The final public action always has a confirmation step.',
  },
  bytes: {
    index: '06', kicker: 'ACCOUNT LEDGER', title: 'Bytes',
    summary: 'Inspect account value and connect each Toolbox charge to the action that created it.',
    stages: [
      ['BALANCE', 'Current account value'], ['ENTRY', 'Debit or credit'], ['REASON', 'Human-readable cause'], ['REFERENCE', 'Related action'],
    ],
    inspector: [
      ['LEDGER', 'Ordered account activity'], ['SEND', 'UID or profile target'],
      ['SERVICE COSTS', 'Toolbox charges labeled'], ['FORUM COSTS', 'Kept distinct'],
    ],
    callout: 'Amounts, reasons, and references stay together so a balance change can be traced instead of guessed.',
  },
  casino: {
    index: '07', kicker: 'PROGRAM RESERVED', title: 'Byte Casino',
    summary: 'A separate table-game system is being built on the same interface language.',
    stages: [
      ['LOBBY', 'Find a table'], ['TABLE', 'Server-held state'], ['CASHIER', 'Balance boundaries'], ['VERIFY', 'Completed record'],
    ],
    inspector: [
      ['POKER', "Multiplayer Hold'em"], ['BLACKJACK', 'Separate game tables'],
      ['CASHIER', 'Available and in-play'], ['FAIRNESS', 'Hand verification'],
    ],
    callout: 'Coming soon. No progress meter, simulated players, or invented activity is shown here.',
  },
}

function RouteAction({ program, user, onEnter }) {
  const unavailable = program.availability === 'coming-soon'
  return (
    <div className="os-route-action">
      <div>
        <span>EXECUTION TARGET</span>
        <code>{unavailable ? 'PROGRAM LOCKED / COMING SOON' : user ? program.route : `HF AUTH -> ${program.route}`}</code>
      </div>
      <TerminalButton disabled={unavailable} tone={unavailable ? 'warn' : 'accent'} onClick={() => onEnter(program)}>
        {unavailable ? 'NOT YET AVAILABLE' : user ? 'ENTER PROGRAM' : 'AUTHENTICATE AND ENTER'}
      </TerminalButton>
    </div>
  )
}

function WorkflowPreview({ program, user, onEnter, onPulse }) {
  const data = WORKFLOWS[program.previewComponent]
  const [selectedStage, setSelectedStage] = useState(0)
  return (
    <article className="os-work-program">
      <header className="os-work-header">
        <div className="os-program-index">{data.index}</div>
        <div>
          <span className="os-kicker">{data.kicker}</span>
          <h1>{data.title}</h1>
          <p>{data.summary}</p>
        </div>
      </header>

      <RouteAction program={program} user={user} onEnter={onEnter} />

      <section className="os-sequence" aria-label={`${data.title} workflow`}>
        <div className="os-section-label"><span>WORKFLOW</span><b>SELECT A STAGE TO PULSE THE FIELD</b></div>
        <div className="os-stage-line">
          {data.stages.map(([label, detail], index) => (
            <button
              type="button"
              key={label}
              className={selectedStage === index ? 'is-active' : ''}
              aria-pressed={selectedStage === index}
              data-stage={index + 1}
              onClick={() => { setSelectedStage(index); onPulse?.() }}
            >
              <span>{String(index + 1).padStart(2, '0')}</span>
              <strong>{label}</strong>
              <small>{detail}</small>
            </button>
          ))}
        </div>
      </section>

      <div className="os-program-grid">
        <section className="os-capability-index">
          <div className="os-section-label"><span>PROGRAM INDEX</span><b>{data.inspector.length} CHANNELS</b></div>
          {data.inspector.map(([label, detail], index) => (
            <div className="os-index-row" key={label}>
              <span>{String(index + 1).padStart(2, '0')}</span><strong>{label}</strong><p>{detail}</p><i aria-hidden="true" />
            </div>
          ))}
        </section>
        <aside className="os-readout">
          <div className="os-section-label"><span>OPERATING NOTE</span><b>PUBLIC PREVIEW</b></div>
          <p>{data.callout}</p>
          <dl>
            <div><dt>INPUT</dt><dd>HF ACCOUNT</dd></div>
            <div><dt>CONTROL</dt><dd>USER CONFIRMED</dd></div>
            <div><dt>OUTPUT</dt><dd>{program.shortLabel}</dd></div>
          </dl>
        </aside>
      </div>
    </article>
  )
}

function HomePreview({ user, onOpenProgram, onEnter }) {
  const primary = PROGRAMS.filter(program => program.publicPrimary && program.id !== 'casino')
  return (
    <article className="os-home-program">
      <header className="os-home-header">
        <h1 className="os-home-wordmark" aria-label="HF Toolbox">
          <span>HF</span><b>TOOLBOX</b><i>/ SYSTEM 03</i>
        </h1>
        <p>Forum work, organized as programs.</p>
      </header>

      <div className="os-home-console">
        <section className="os-manifest">
          <div className="os-section-label"><span>MANIFEST</span><b>GUEST INTERFACE</b></div>
          <h2>Open the work.<br />Keep the context.</h2>
          <p>Manage marketplace activity, contracts, posting, thread bumps, and Bytes without turning every task into another disconnected tab.</p>
          <div className="os-home-actions">
            <TerminalButton onClick={() => onEnter(PROGRAMS[0])}>{user ? 'OPEN TOOLBOX' : 'LOGIN WITH HACK FORUMS'}</TerminalButton>
            <button type="button" className="os-text-command" onClick={() => onOpenProgram(primary[0])}>inspect business --public</button>
          </div>
        </section>

        <section className="os-directory" aria-label="Program directory">
          <div className="os-section-label"><span>PROGRAM DIRECTORY</span><b>{String(primary.length).padStart(2, '0')} MOUNTED</b></div>
          <div className="os-directory-list">
            {primary.map((program, index) => (
              <button type="button" key={program.id} onClick={() => onOpenProgram(program)}>
                <span>{String(index + 1).padStart(2, '0')}</span>
                <strong>{program.label}</strong>
                <small>{program.publicSummary}</small>
                <b>OPEN</b>
              </button>
            ))}
          </div>
        </section>
      </div>

      <footer className="os-home-foot">
        <div><span>ACCESS</span><b>{user ? user.username : 'GUEST / HF OAUTH'}</b></div>
        <div><span>CONTROL MODEL</span><b>PREVIEW / CONFIRM / EXECUTE</b></div>
        <div><span>INPUT</span><b>POINTER / TOUCH / COMMAND</b></div>
      </footer>
    </article>
  )
}

export default function ProgramPreview({ program, user, authError, authReference, onEnter, onOpenProgram, onPulse }) {
  return (
    <div className="os-preview">
      {authError && (
        <div className="os-auth-error" role="alert">
          <strong>AUTHENTICATION NOT COMPLETED</strong>
          <span>{authError}</span>
          {authReference && <small>REFERENCE: {authReference}</small>}
        </div>
      )}
      {program.id === 'home'
        ? <HomePreview user={user} onOpenProgram={onOpenProgram} onEnter={onEnter} />
        : <WorkflowPreview program={program} user={user} onEnter={onEnter} onPulse={onPulse} />}
    </div>
  )
}
