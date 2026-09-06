import { useEffect, useRef, useState } from 'react'
import { PROGRAMS, PUBLIC_PROGRAMS, prefetchProgram } from './programRegistry.js'

export function SystemFrame({ children, phase, className = '' }) {
  return <main className={`os-root os-phase-${phase} ${className}`}>{children}</main>
}

export function SystemStatusRail({ activeProgram, user, phase, menuOpen, onToggleMenu }) {
  const ready = phase === 'ready'
  return (
    <header className="os-status-rail">
      <div className="os-brand"><span>HF</span>.TOOLBOX <small>OS/03</small></div>
      <div className="os-path"><span>ROOT</span><i>/</i><span>PROGRAMS</span><i>/</i><b>{activeProgram.command.toUpperCase()}</b></div>
      <div className="os-clock" aria-hidden="true"><span>LOCAL SESSION</span><b>{String(activeProgram.id.length * 17).padStart(3, '0')}</b></div>
      <div className="os-session">
        <span>{user?.username || 'GUEST'}</span>
        <b className={ready ? 'is-ready' : ''}>{ready ? 'READY' : phase.toUpperCase()}</b>
      </div>
      <button className="os-menu-button" type="button" aria-expanded={menuOpen} onClick={onToggleMenu}>
        {menuOpen ? 'CLOSE' : 'PROGRAMS'}
      </button>
    </header>
  )
}

export function ProgramRail({ activeProgram, open, onOpenProgram, onClose }) {
  const railRef = useRef(null)

  useEffect(() => {
    if (open) railRef.current?.querySelector('button')?.focus()
  }, [open])

  return (
    <aside ref={railRef} className={`os-program-rail${open ? ' is-open' : ''}`} aria-label="Toolbox programs">
      <div className="os-pane-label"><span>MOUNTED PROGRAMS</span><b>{String(PUBLIC_PROGRAMS.length).padStart(2, '0')}</b></div>
      <div className="os-program-list">
        {PUBLIC_PROGRAMS.map((program, index) => {
          const selected = program.id === activeProgram.id
          return (
            <button
              key={program.id}
              type="button"
              className={selected ? 'is-selected' : ''}
              aria-current={selected ? 'page' : undefined}
              onPointerEnter={() => prefetchProgram(program)}
              onFocus={() => prefetchProgram(program)}
              onClick={() => { onOpenProgram(program); onClose?.() }}
            >
              <span>{selected ? '>' : String(index + 1).padStart(2, '0')}</span>
              <strong>{program.label}</strong>
              <small>{program.availability === 'coming-soon' ? 'SOON' : 'OPEN'}</small>
            </button>
          )
        })}
      </div>
      <div className="os-rail-hint">
        <span>COMMAND ENTRY</span>
        <code>open market</code><code>programs --all</code>
      </div>
    </aside>
  )
}

export function ProgramViewport({ activeProgram, children }) {
  return (
    <section className="os-program-viewport" aria-live="polite">
      <div className="os-pane-label">
        <span>PROGRAM / {activeProgram.group.toUpperCase()}</span>
        <b>{activeProgram.command.toUpperCase()}::{activeProgram.availability === 'coming-soon' ? 'LOCKED' : 'READY'}</b>
      </div>
      <div className="os-program-content">{children}</div>
    </section>
  )
}

export function VisualViewport({ mode, children }) {
  return (
    <aside className="os-visual-viewport" aria-label={`${mode} system visualization`}>
      <div className="os-pane-label"><span>SIGNAL FIELD</span><b>MODE::{mode.toUpperCase()}</b></div>
      <div className="os-visual-content">{children}</div>
      <div className="os-visual-legend" aria-hidden="true">
        <span><i className="is-green" /> PROGRAM NODE</span>
        <span><i className="is-amber" /> INPUT IMPULSE</span>
        <b>PTR / KEY / CMD</b>
      </div>
    </aside>
  )
}

export function CommandDock({ runtime, user }) {
  const [value, setValue] = useState('')
  const [historyIndex, setHistoryIndex] = useState(-1)
  const inputRef = useRef(null)

  const submit = (event) => {
    event.preventDefault()
    runtime.execute(value)
    setValue('')
    setHistoryIndex(-1)
  }

  const keyDown = (event) => {
    if (event.key === 'Tab') {
      event.preventDefault()
      setValue(runtime.complete(value))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      const next = Math.min(runtime.history.length - 1, historyIndex + 1)
      setHistoryIndex(next)
      if (next >= 0) setValue(runtime.history[runtime.history.length - 1 - next])
    } else if (event.key === 'ArrowDown') {
      event.preventDefault()
      const next = Math.max(-1, historyIndex - 1)
      setHistoryIndex(next)
      setValue(next < 0 ? '' : runtime.history[runtime.history.length - 1 - next])
    } else if (event.key === 'Escape') {
      event.preventDefault()
      runtime.openProgram(PROGRAMS[0], false)
      setValue('')
    }
  }

  return (
    <footer className="os-command-dock" onClick={() => inputRef.current?.focus()}>
      <div className="os-command-output" aria-live="polite">
        {runtime.output.slice(-5).map((line, index) => (
          <div key={`${line.text}-${index}`} className={`tone-${line.tone}`}>{line.text}</div>
        ))}
      </div>
      <form onSubmit={submit}>
        <label htmlFor="os-command-input">{user?.username || 'guest'}@hftoolbox:~$</label>
        <input
          ref={inputRef}
          id="os-command-input"
          value={value}
          onChange={event => setValue(event.target.value)}
          onKeyDown={keyDown}
          autoComplete="off"
          autoCapitalize="none"
          spellCheck="false"
          aria-label="Toolbox command"
        />
        <span className="os-block-cursor" aria-hidden="true" />
      </form>
      <div className="os-command-help"><span>COMMAND CHANNEL</span><b>TAB COMPLETE / UP HISTORY / HELP</b></div>
    </footer>
  )
}

export function BootScreen({ lines, phase, onSkip }) {
  if (phase === 'ready') return null
  return (
    <div className="os-boot" role="status" aria-label="HF Toolbox starting" onClick={onSkip}>
      <div className="os-boot-scope" aria-hidden="true"><span /><span /><span /><span /></div>
      <div className="os-boot-mark"><span>HF</span>.TOOLBOX</div>
      <div className="os-boot-version">TERMINAL OPERATING SYSTEM / BUILD 03</div>
      <div className="os-boot-lines">
        {lines.map(line => (
          <div key={line.label}>
            <span>{line.label}</span>
            <b>{line.detail}</b>
          </div>
        ))}
      </div>
      <button type="button" onClick={onSkip}>SKIP BOOT [ESC]</button>
      <div className="os-boot-rule" aria-hidden="true"><i /><b>INPUT READY AFTER INITIALIZATION</b><i /></div>
    </div>
  )
}

export function TerminalButton({ children, onClick, disabled = false, tone = 'accent' }) {
  return <button type="button" className={`os-action tone-${tone}`} onClick={onClick} disabled={disabled}>{children}</button>
}

export function TerminalMeter({ label, value, detail, tone = 'accent' }) {
  return (
    <div className={`os-meter tone-${tone}`}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  )
}
