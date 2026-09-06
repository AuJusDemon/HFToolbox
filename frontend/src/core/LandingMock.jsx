import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import useStore from '../store.js'
import AsciiField from '../system/AsciiField.jsx'
import ProgramPreview from '../system/ProgramPreviews.jsx'
import {
  BootScreen,
  CommandDock,
  ProgramRail,
  ProgramViewport,
  SystemFrame,
  SystemStatusRail,
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

  const runtime = useSystemRuntime({ onLogin: beginLogin, identity: user?.username || 'guest' })

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
            onOpenProgram={runtime.openProgram}
            onPulse={runtime.pulse}
          />
        </ProgramViewport>
        <VisualViewport mode={runtime.activeProgram.visualizationMode}>
          <AsciiField
            mode={runtime.activeProgram.visualizationMode}
            motion={runtime.motionEnabled}
            impulse={runtime.impulse}
            program={runtime.activeProgram}
            onInteract={runtime.pulse}
          />
        </VisualViewport>
      </div>

      <CommandDock runtime={runtime} user={user} />
      <div className="os-disclaimer">HF Toolbox is an unofficial tool and is not affiliated with Hack Forums.</div>
      <BootScreen lines={runtime.bootLines} phase={runtime.phase} onSkip={runtime.finishBoot} />
    </SystemFrame>
  )
}
