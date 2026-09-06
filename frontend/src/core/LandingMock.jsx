import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import useStore from '../store.js'
import AsciiField from '../system/AsciiField.jsx'
import {
  BootScreen,
  CommandDock,
  ProgramRail,
  ProgramViewport,
  SystemFrame,
  SystemStatusRail,
  TerminalButton,
  TerminalMeter,
  VisualViewport,
} from '../system/TerminalOS.jsx'
import { getProgramByRoute, PROGRAMS, PUBLIC_PROGRAMS } from '../system/programRegistry.js'
import { useSystemRuntime } from '../system/useSystemRuntime.js'
import '../system/terminal-os.css'

const AUTH_ERROR_MESSAGES = {
  cancelled: 'Authorization was cancelled. No changes were made.',
  session_expired: 'Your sign-in session expired. Start again.',
  oauth_failed: 'Hack Forums did not complete sign-in. Try again.',
  hf_unavailable: 'Hack Forums is temporarily unavailable. Wait a moment and try again.',
  invalid_response: 'Hack Forums returned an incomplete sign-in response. Try again.',
  login_failed: 'Sign-in could not be completed. Try again.',
}

const PREVIEW_ROWS = {
  home: [
    ['MY BUSINESS', 'contracts, replies, buyers, threads'],
    ['BUMP SERVICE', 'timing, spend, failures, results'],
    ['MARKETPLACE', 'indexed threads and buyer intent'],
    ['ACCOUNT TOOLS', 'posting, Bytes, contracts, Wire'],
  ],
  business: [
    ['NEEDS REVIEW', 'open a contract and decide the next action'],
    ['IN PROGRESS', 'keep current deals separate from waiting work'],
    ['FOLLOW-UP', 'return to buyers, replies, and ratings'],
    ['THREAD HEALTH', 'connect bumps and replies to actual movement'],
  ],
  bumps: [
    ['QUEUE', 'eligible thread enters the service schedule'],
    ['TIMER', 'next permitted bump stays visible'],
    ['POST', 'successful attempts are recorded and charged'],
    ['RESULT', 'inspect replies, views, contracts, and failures'],
  ],
  market: [
    ['INDEX', 'browse observed marketplace threads'],
    ['WATCH', 'save phrases and areas worth monitoring'],
    ['MATCH', 'find buyer requests connected to your offers'],
    ['CONTEXT', 'open thread activity and contract history together'],
  ],
  contracts: [
    ['REVIEW', 'approve or deny contracts that need a decision'],
    ['ACTIVE', 'track work that both sides have accepted'],
    ['WAITING', 'see who needs to act next'],
    ['CLOSED', 'separate completed, expired, cancelled, and disputed'],
  ],
  posting: [
    ['DRAFT', 'write without immediately sending anything'],
    ['PREVIEW', 'inspect the exact post before confirmation'],
    ['SUBMIT', 'send through the supported account action'],
    ['WATCH', 'return when the thread receives a reply'],
  ],
  bytes: [
    ['BALANCE', 'see the current account value'],
    ['LEDGER', 'inspect incoming and outgoing activity'],
    ['SERVICE COST', 'identify Toolbox charges such as bumps'],
    ['REFERENCE', 'retain the reason and related forum action'],
  ],
  casino: [
    ['POKER', 'multiplayer table program'],
    ['BLACKJACK', 'separate table program'],
    ['CASHIER', 'available, in-play, and pending balances'],
    ['VERIFY', 'inspect completed game records'],
  ],
}

function ProgramPreview({ program, user, authError, authReference, onEnter }) {
  const mode = program.previewComponent || 'home'
  const rows = PREVIEW_ROWS[mode] || PREVIEW_ROWS.home
  const comingSoon = program.availability === 'coming-soon'

  return (
    <div className="os-preview">
      <div className="os-program-heading">
        <span>{comingSoon ? 'COMING SOON' : mode === 'home' ? 'SYSTEM HOME' : 'PROGRAM PREVIEW'}</span>
        <h1>{mode === 'home' ? 'HF Toolbox' : program.label}</h1>
        <p>{program.publicSummary}</p>
      </div>

      {authError && (
        <div className="os-auth-error" role="alert">
          <strong>AUTHENTICATION NOT COMPLETED</strong>
          <span>{authError}</span>
          {authReference && <small>REFERENCE: {authReference}</small>}
        </div>
      )}

      <div className="os-preview-rows">
        {rows.map(([label, detail], index) => (
          <div key={label}>
            <span>{String(index + 1).padStart(2, '0')}</span>
            <strong>{label}</strong>
            <p>{detail}</p>
          </div>
        ))}
      </div>

      {mode === 'home' && (
        <div className="os-home-meters">
          <TerminalMeter label="ACCESS" value={user ? 'AUTHED' : 'GUEST'} detail={user ? user.username : 'HF login available'} />
          <TerminalMeter label="PROGRAMS" value={String(PUBLIC_PROGRAMS.length).padStart(2, '0')} detail="public directory" />
          <TerminalMeter label="INTERFACE" value="TUI/02" detail="keyboard, mouse, touch" />
        </div>
      )}

      <div className="os-preview-action">
        {comingSoon ? (
          <TerminalButton disabled tone="warn">PROGRAM NOT YET AVAILABLE</TerminalButton>
        ) : (
          <TerminalButton onClick={() => onEnter(program)}>
            {mode === 'home' ? (user ? 'OPEN TOOLBOX' : 'LOGIN WITH HACK FORUMS') : `OPEN ${program.label.toUpperCase()}`}
          </TerminalButton>
        )}
        <span>{comingSoon ? 'This entry will activate when the Casino is ready.' : user ? `route ${program.route}` : 'OAuth returns to the selected program.'}</span>
      </div>
    </div>
  )
}

export default function LandingMock() {
  const user = useStore(state => state.user)
  const navigate = useNavigate()
  const [menuOpen, setMenuOpen] = useState(false)
  const query = new URLSearchParams(window.location.search)
  const authErrorCode = query.get('auth_error') || ''
  const authReference = query.get('auth_ref') || ''
  const requestedReturn = query.get('next') || ''
  const authError = authErrorCode ? (AUTH_ERROR_MESSAGES[authErrorCode] || AUTH_ERROR_MESSAGES.login_failed) : ''

  const beginLogin = useCallback((route = '') => {
    const candidate = route || requestedReturn || sessionStorage.getItem('auth_return_to') || ''
    const returnTo = candidate.startsWith('/dashboard') && !candidate.startsWith('//') ? candidate : ''
    if (returnTo) sessionStorage.setItem('auth_return_to', returnTo)
    const url = returnTo ? `/auth/login?next=${encodeURIComponent(returnTo)}` : '/auth/login'
    window.location.href = url
  }, [requestedReturn])

  const runtime = useSystemRuntime({ onLogin: beginLogin })

  useEffect(() => {
    if (requestedReturn) runtime.openProgram(getProgramByRoute(requestedReturn), false)
  }, [])

  useEffect(() => {
    const handleKey = (event) => {
      if (runtime.booting && ['Escape', 'Enter', ' '].includes(event.key)) {
        event.preventDefault()
        runtime.finishBoot()
        return
      }
      const target = event.target
      if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement || event.metaKey || event.ctrlKey || event.altKey) return
      if (event.key === 'Escape') runtime.openProgram(PROGRAMS[0], false)
      const index = Number(event.key) - 1
      if (index >= 0 && index < PUBLIC_PROGRAMS.length) runtime.openProgram(PUBLIC_PROGRAMS[index])
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [runtime.booting, runtime.finishBoot, runtime.openProgram])

  const enterProgram = (program) => {
    if (program.availability === 'coming-soon') return
    const route = program.route || '/dashboard'
    if (user) navigate(route)
    else beginLogin(route)
  }

  return (
    <SystemFrame phase={runtime.phase} className={runtime.motionEnabled ? 'motion-on' : 'motion-off'}>
      <SystemStatusRail
        activeProgram={runtime.activeProgram}
        user={user}
        phase={runtime.phase}
        menuOpen={menuOpen}
        onToggleMenu={() => setMenuOpen(open => !open)}
      />

      <div className="os-workspace">
        <ProgramRail
          activeProgram={runtime.activeProgram}
          open={menuOpen}
          onOpenProgram={runtime.openProgram}
          onClose={() => setMenuOpen(false)}
        />
        <ProgramViewport activeProgram={runtime.activeProgram}>
          <ProgramPreview
            program={runtime.activeProgram}
            user={user}
            authError={authError}
            authReference={authReference}
            onEnter={enterProgram}
          />
        </ProgramViewport>
        <VisualViewport mode={runtime.activeProgram.visualizationMode}>
          <AsciiField
            mode={runtime.activeProgram.visualizationMode}
            motion={runtime.motionEnabled}
            impulse={runtime.impulse}
          />
        </VisualViewport>
      </div>

      <CommandDock runtime={runtime} user={user} />
      <div className="os-disclaimer">HF Toolbox is an unofficial tool and is not affiliated with Hack Forums.</div>
      <BootScreen lines={runtime.bootLines} phase={runtime.phase} onSkip={runtime.finishBoot} />
    </SystemFrame>
  )
}
