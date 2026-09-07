import { useEffect, useMemo, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import { PROGRAMS, prefetchProgram } from './programRegistry.js'

export const NAV_GROUPS = [
  ['core', 'Core'],
  ['services', 'Services'],
  ['intelligence', 'Intelligence'],
  ['other', 'Other Programs'],
  ['system', 'System'],
]

const NAV_ORDER = ['home', 'bytes', 'contracts', 'posting', 'merchant', 'bumper', 'market', 'sigmarket', 'wire', 'casino', 'settings', 'operator']

export function visiblePrograms(user) {
  return PROGRAMS.filter(program => !program.operatorOnly || String(user?.uid || '') === '761578')
}

function isSelected(program, pathname) {
  return Boolean(program.route && (pathname === program.route || (program.route !== '/dashboard' && pathname.startsWith(program.route))))
}

export function ProgramNavigation({ user, collapsed, counters = {}, onSelect }) {
  const navigate = useNavigate()
  const location = useLocation()
  const programs = visiblePrograms(user)

  const prepare = program => prefetchProgram(program, { data: true })
  const open = program => {
    if (!program.route || program.availability !== 'available') return
    navigate(program.route)
    onSelect?.()
  }

  return (
    <nav className="app-program-nav" aria-label="Toolbox programs">
      {NAV_GROUPS.map(([group, label]) => {
        const entries = programs.filter(program => program.group === group).sort((a, b) => NAV_ORDER.indexOf(a.id) - NAV_ORDER.indexOf(b.id))
        if (!entries.length) return null
        return (
          <section className="app-program-group" key={group} aria-label={label}>
            <div className="app-program-group-label">{collapsed ? <span aria-hidden="true">--</span> : label}</div>
            {entries.map(program => {
              const selected = isSelected(program, location.pathname)
              const unavailable = program.availability !== 'available' || !program.route
              const count = Number(counters[program.id] || 0)
              return (
                <button
                  key={program.id}
                  type="button"
                  className={`app-program-link${selected ? ' selected' : ''}${unavailable ? ' unavailable' : ''}`}
                  aria-current={selected ? 'page' : undefined}
                  aria-disabled={unavailable || undefined}
                  title={collapsed ? `${program.label}${unavailable ? ' - Coming Soon' : ''}` : undefined}
                  onPointerEnter={() => !unavailable && prepare(program)}
                  onPointerDown={() => !unavailable && prepare(program)}
                  onTouchStart={() => !unavailable && prepare(program)}
                  onFocus={() => !unavailable && prepare(program)}
                  onClick={() => open(program)}
                >
                  <span className="app-program-glyph" aria-hidden="true">{program.glyph || program.shortLabel.slice(0, 2)}</span>
                  <span className="app-program-label">{program.id === 'home' ? 'Overview' : program.label}</span>
                  {unavailable && <span className="app-program-soon">Soon</span>}
                  {!unavailable && count > 0 && <span className="app-program-count" aria-label={`${count} items requiring action`}>{count}</span>}
                </button>
              )
            })}
          </section>
        )
      })}
    </nav>
  )
}

export function MobileProgramDrawer({ open, onClose, user, counters, account }) {
  const panelRef = useRef(null)
  useEffect(() => {
    if (!open) return undefined
    const previous = document.activeElement
    document.body.classList.add('drawer-open')
    const panel = panelRef.current
    panel?.querySelector('button')?.focus()
    const handle = event => {
      if (event.key === 'Escape') onClose()
      if (event.key !== 'Tab' || !panel) return
      const focusable = [...panel.querySelectorAll('button:not([disabled]),a[href],input')]
      if (!focusable.length) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
    }
    document.addEventListener('keydown', handle)
    return () => {
      document.body.classList.remove('drawer-open')
      document.removeEventListener('keydown', handle)
      previous?.focus?.()
    }
  }, [open, onClose])

  if (!open) return null
  return (
    <div className="app-drawer-layer" role="presentation" onMouseDown={event => event.target === event.currentTarget && onClose()}>
      <aside className="app-drawer" ref={panelRef} role="dialog" aria-modal="true" aria-label="Program navigation">
        <header>
          <div><b>HF.TOOLBOX</b><span>{account}</span></div>
          <button type="button" className="app-icon-button" onClick={onClose} aria-label="Close navigation">X</button>
        </header>
        <ProgramNavigation user={user} counters={counters} onSelect={onClose} />
      </aside>
    </div>
  )
}

export function CommandLauncher({ open, onClose, user }) {
  const navigate = useNavigate()
  const inputRef = useRef(null)
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const choices = useMemo(() => visiblePrograms(user).filter(program => {
    if (!program.route || program.availability !== 'available') return false
    const haystack = [program.label, program.command, program.publicSummary, program.group, ...program.aliases].join(' ').toLowerCase()
    return haystack.includes(query.trim().toLowerCase())
  }), [query, user])

  useEffect(() => {
    if (!open) return
    setQuery(''); setActive(0)
    requestAnimationFrame(() => inputRef.current?.focus())
  }, [open])
  useEffect(() => { if (active >= choices.length) setActive(0) }, [active, choices.length])

  if (!open) return null
  const select = program => { prefetchProgram(program, { data: true }); onClose(); navigate(program.route) }
  const keyDown = event => {
    if (event.key === 'Escape') { event.preventDefault(); onClose() }
    if (event.key === 'ArrowDown') { event.preventDefault(); setActive(i => Math.min(i + 1, choices.length - 1)) }
    if (event.key === 'ArrowUp') { event.preventDefault(); setActive(i => Math.max(i - 1, 0)) }
    if (event.key === 'Enter' && choices[active]) { event.preventDefault(); select(choices[active]) }
  }

  return (
    <div className="command-layer" role="presentation" onMouseDown={event => event.target === event.currentTarget && onClose()}>
      <section className="command-launcher" role="dialog" aria-modal="true" aria-label="Open a Toolbox program">
        <label htmlFor="command-search">Open program</label>
        <div className="command-input-row"><span aria-hidden="true">&gt;</span><input id="command-search" ref={inputRef} value={query} onChange={event => { setQuery(event.target.value); setActive(0) }} onKeyDown={keyDown} placeholder="Search programs or type an alias" autoComplete="off" /></div>
        <div className="command-results" role="listbox">
          {choices.map((program, index) => (
            <button key={program.id} type="button" role="option" aria-selected={index === active} className={index === active ? 'active' : ''} onMouseEnter={() => { setActive(index); prefetchProgram(program, { data: true }) }} onFocus={() => prefetchProgram(program, { data: true })} onClick={() => select(program)}>
              <span className="app-program-glyph" aria-hidden="true">{program.glyph}</span>
              <span><b>{program.id === 'home' ? 'Overview' : program.label}</b><small>{program.publicSummary}</small></span>
              <em>{program.group}</em>
            </button>
          ))}
          {!choices.length && <p>No matching program.</p>}
        </div>
        <footer><span>Up/Down select</span><span>Enter open</span><span>Esc close</span></footer>
      </section>
    </div>
  )
}
