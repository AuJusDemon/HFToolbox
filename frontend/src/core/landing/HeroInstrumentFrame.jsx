import useHeroTerminal from './useHeroTerminal.js'
import HeroProgramBus from './HeroProgramBus.jsx'
import HeroTerminal from './HeroTerminal.jsx'

export default function HeroInstrumentFrame({ programs, user, authLoading, authError, authReference, onOpen, onLogin }) {
  const runtime = useHeroTerminal({ programs, authError, authReference, onOpen, onLogin })
  const accountState = authLoading ? 'CHECKING ACCOUNT' : user ? user.username || `UID ${user.uid}` : 'GUEST'

  return (
    <section id="top" className={`hero-instrument phase-${runtime.phase}${runtime.bootSkipped ? ' boot-skipped' : ''}`} data-boot-phase={runtime.phase} onDoubleClick={runtime.finishBoot}>
      <i className="hero-frame-line line-top" aria-hidden="true" /><i className="hero-frame-line line-right" aria-hidden="true" />
      <i className="hero-frame-line line-bottom" aria-hidden="true" /><i className="hero-frame-line line-left" aria-hidden="true" />
      <i className="hero-corner corner-tl" aria-hidden="true" /><i className="hero-corner corner-tr" aria-hidden="true" />
      <i className="hero-corner corner-bl" aria-hidden="true" /><i className="hero-corner corner-br" aria-hidden="true" />
      <header className="hero-status-rail"><span>HF.TOOLBOX / PUBLIC ACCESS</span><b>{runtime.authorizing ? 'AUTHORIZING' : accountState}</b></header>
      <div className="hero-instrument-grid">
        <section className="hero-system-panel" aria-labelledby="hero-title">
          <header><span>SYSTEM.TXT</span><b>PUBLIC INTERFACE</b></header>
          <div className="hero-system-copy">
            <span className="hero-title-mask" aria-hidden="true">## #######</span>
            <h1 id="hero-title"><span>HF</span> Toolbox</h1>
            <p>Contracts, marketplace research, posting, thread bumps, buyers, and Bytes in one account.</p>
            <small>Type a command or select a program below.</small>
            <button type="button" className="lp-login" onClick={onLogin}>{user ? 'Open Toolbox' : 'Login with Hack Forums'}</button>
          </div>
        </section>
        <HeroTerminal runtime={runtime} />
      </div>
      <HeroProgramBus runtime={runtime} />
      <footer className="hero-instrument-foot"><span>KEYBOARD / POINTER / TOUCH</span><b>{runtime.ready ? 'INTERACTION READY' : 'INITIALIZING'}</b></footer>
    </section>
  )
}
