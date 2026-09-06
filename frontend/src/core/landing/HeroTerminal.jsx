import { useEffect, useMemo, useRef } from 'react'
import HeroBootSequence from './HeroBootSequence.jsx'

function InputTrace({ value }) {
  const bars = useMemo(() => Array.from({ length: 14 }, (_, index) => {
    if (!value) return 1
    const code = value.charCodeAt(index % value.length)
    return 2 + ((code + index * 3 + value.length) % 10)
  }), [value])

  return <div className={`hero-input-trace${value ? ' is-active' : ''}`} aria-hidden="true">
    {bars.map((height, index) => <i key={index} style={{ '--trace-height': `${height}px` }} />)}
  </div>
}

export default function HeroTerminal({ runtime }) {
  const outputRef = useRef(null)
  useEffect(() => {
    const output = outputRef.current
    if (output) output.scrollTop = output.scrollHeight
  }, [runtime.entries])

  return (
    <section className={`hero-terminal${runtime.entries.at(-1)?.tone === 'error' ? ' has-error' : ''}${runtime.entries.at(-1)?.tone === 'waiting' ? ' has-interrupt' : ''}`} aria-label="Command terminal">
      <header><span>COMMAND TERMINAL</span><b>{runtime.interactionState === 'typing' ? 'AUTO INPUT' : runtime.interactionState === 'resolving' ? 'ROUTE READY' : runtime.interactionState === 'transfer' ? 'TRANSFER' : runtime.ready ? 'INPUT READY' : 'STARTING'}</b></header>
      <div className="hero-terminal-screen">
        {!runtime.ready && <HeroBootSequence phaseIndex={runtime.phaseIndex} />}
        <div ref={outputRef} className={`hero-terminal-output${runtime.ready ? ' is-visible' : ''}`} role="log" aria-live="polite" aria-label="Terminal output">
          {runtime.entries.map(entry => <div key={entry.id} className={`hero-terminal-entry tone-${entry.tone}`}>
            {entry.command && <div className="hero-command-echo"><span>guest@hftoolbox:~$</span> {entry.command}</div>}
            {entry.lines.map((line, index) => <span key={`${entry.id}-${index}`} style={{ '--line-index': index }}>{line}</span>)}
          </div>)}
        </div>
      </div>
      <form className={`hero-terminal-prompt${runtime.ready ? ' is-visible' : ''}`} onSubmit={(event) => { event.preventDefault(); runtime.execute(runtime.input) }}>
        <label htmlFor="hero-command">Terminal command</label>
        <span aria-hidden="true">guest@hftoolbox:~$</span>
        <input ref={runtime.inputRef} id="hero-command" value={runtime.input} onChange={event => runtime.setInput(event.target.value)} onKeyDown={runtime.handleKeyDown} autoCapitalize="none" autoComplete="off" autoCorrect="off" spellCheck="false" disabled={!runtime.ready || runtime.interactionState !== 'idle'} />
        <i aria-hidden="true" />
        <button type="submit" disabled={!runtime.input.trim() || runtime.interactionState !== 'idle'}>RUN</button>
      </form>
      <InputTrace value={runtime.input} />
    </section>
  )
}
