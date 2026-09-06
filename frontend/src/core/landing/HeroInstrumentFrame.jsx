import useHeroTerminal from './useHeroTerminal.js'
import HeroProgramBus from './HeroProgramBus.jsx'
import HeroRouteTransition from './HeroRouteTransition.jsx'
import HeroSignalRaster from './HeroSignalRaster.jsx'
import HeroTerminal from './HeroTerminal.jsx'

export default function HeroInstrumentFrame({ programs, user, authLoading, authError, authReference, onOpen, onLogin }) {
  const runtime = useHeroTerminal({ programs, authError, authReference, loginTarget: user ? '/dashboard' : '/auth/login', onOpen, onLogin })
  const accountState = authLoading ? 'CHECKING ACCOUNT' : user ? user.username || `UID ${user.uid}` : 'GUEST'
  const busy = runtime.interactionState !== 'idle'
  const systemState = runtime.interactionState === 'typing' ? 'ENTERING COMMAND' : runtime.interactionState === 'resolving' ? 'ROUTE SELECTED' : runtime.interactionState === 'transfer' ? 'TRANSFERRING' : accountState

  return (
    <section id="top" className={`hero-instrument phase-${runtime.phase}${runtime.bootSkipped ? ' boot-skipped' : ''}`} data-boot-phase={runtime.phase} onDoubleClick={runtime.finishBoot}>
      <i className="hero-frame-line line-top" aria-hidden="true" /><i className="hero-frame-line line-right" aria-hidden="true" />
      <i className="hero-frame-line line-bottom" aria-hidden="true" /><i className="hero-frame-line line-left" aria-hidden="true" />
      <i className="hero-corner corner-tl" aria-hidden="true" /><i className="hero-corner corner-tr" aria-hidden="true" />
      <i className="hero-corner corner-bl" aria-hidden="true" /><i className="hero-corner corner-br" aria-hidden="true" />
      <header className="hero-status-rail"><span>HF.TOOLBOX / PUBLIC ACCESS</span><b>{systemState}</b></header>
      <div className="hero-instrument-grid">
        <section className="hero-system-panel" aria-labelledby="hero-title">
          <header><span>SYSTEM.TXT</span><b>PUBLIC INTERFACE</b></header>
          <HeroSignalRaster active={busy || Boolean(runtime.input)} reducedMotion={runtime.reducedMotion} />
          <div className="hero-system-copy">
            <span className="hero-title-mask" aria-hidden="true">## #######</span>
            <h1 id="hero-title"><span>HF</span> Toolbox</h1>
            <p>Contracts, marketplace research, posting, thread bumps, buyers, and Bytes in one account.</p>
            <small>Type a command or select a program below.</small>
            <button type="button" className="lp-login" disabled={busy} onClick={() => runtime.typeCommand('login')}>{user ? 'Open Toolbox' : 'Login with Hack Forums'}</button>
          </div>
        </section>
        <HeroTerminal runtime={runtime} />
      </div>
      <HeroProgramBus runtime={runtime} />
      <footer className="hero-instrument-foot"><span>KEYBOARD / POINTER / TOUCH</span><b>{runtime.ready ? 'INTERACTION READY' : 'INITIALIZING'}</b></footer>
      <HeroRouteTransition state={runtime.interactionState} target={runtime.routeTarget} />
    </section>
  )
}
