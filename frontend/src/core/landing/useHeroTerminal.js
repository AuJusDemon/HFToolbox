import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { completeHeroCommand, getHeroPrograms, resolveHeroCommand } from './heroCommands.js'

export const BOOT_PHASES = ['power', 'frame', 'dividers', 'labels', 'identity', 'messages', 'programs', 'ready']

const WELCOME_ENTRY = {
  id: 'welcome',
  tone: 'normal',
  lines: ['HF.TOOLBOX public interface', 'Type "help" or select a program.'],
}

function prefersReducedMotion() {
  return typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
}

export default function useHeroTerminal({ programs, authError, authReference, onOpen, onLogin }) {
  const reducedMotion = useMemo(prefersReducedMotion, [])
  const [phaseIndex, setPhaseIndex] = useState(reducedMotion ? BOOT_PHASES.length - 1 : 0)
  const [bootSkipped, setBootSkipped] = useState(reducedMotion)
  const [input, setInput] = useState('')
  const [entries, setEntries] = useState(() => [WELCOME_ENTRY, ...(authError ? [{
    id: 'auth-error', tone: 'error',
    lines: [authError, ...(authReference ? [`Reference: ${authReference}`] : [])],
  }] : [])])
  const [history, setHistory] = useState([])
  const [historyIndex, setHistoryIndex] = useState(-1)
  const [activeProgramId, setActiveProgramId] = useState('')
  const [pulseProgramId, setPulseProgramId] = useState('')
  const [authorizing, setAuthorizing] = useState(false)
  const inputRef = useRef(null)
  const pulseTimerRef = useRef(null)
  const entryIdRef = useRef(0)
  const phase = BOOT_PHASES[phaseIndex]
  const ready = phase === 'ready'
  const heroPrograms = useMemo(() => getHeroPrograms(programs), [programs])

  const finishBoot = useCallback(() => {
    setBootSkipped(true)
    setPhaseIndex(BOOT_PHASES.length - 1)
  }, [])

  useEffect(() => {
    if (reducedMotion || ready) return undefined
    const mobile = window.matchMedia('(max-width: 720px)').matches
    const schedule = mobile ? [90, 210, 330, 450, 610, 770, 930] : [160, 380, 560, 740, 1030, 1280, 1510]
    const timers = schedule.map((delay, index) => window.setTimeout(() => setPhaseIndex(index + 1), delay))
    return () => timers.forEach(window.clearTimeout)
  }, [ready, reducedMotion])

  useEffect(() => {
    if (ready) return undefined
    const skip = () => finishBoot()
    window.addEventListener('keydown', skip, { once: true })
    window.addEventListener('pointerdown', skip, { once: true })
    window.addEventListener('touchstart', skip, { once: true })
    return () => {
      window.removeEventListener('keydown', skip)
      window.removeEventListener('pointerdown', skip)
      window.removeEventListener('touchstart', skip)
    }
  }, [finishBoot, ready])

  useEffect(() => {
    if (!ready) return
    const active = document.activeElement
    if (!active || active === document.body) inputRef.current?.focus({ preventScroll: true })
  }, [ready])

  useEffect(() => () => window.clearTimeout(pulseTimerRef.current), [])

  const pulse = useCallback((programId) => {
    setPulseProgramId('')
    window.clearTimeout(pulseTimerRef.current)
    const beginPulse = () => setPulseProgramId(programId)
    if (window.requestAnimationFrame) window.requestAnimationFrame(beginPulse)
    else window.setTimeout(beginPulse, 0)
    pulseTimerRef.current = window.setTimeout(() => setPulseProgramId(''), 340)
  }, [])

  const appendEntry = useCallback((command, result) => {
    entryIdRef.current += 1
    setEntries(current => [...current, {
      id: `entry-${entryIdRef.current}`,
      command,
      tone: ['error', 'unavailable'].includes(result.type) ? 'waiting' : 'normal',
      lines: result.lines || [],
    }])
  }, [])

  const execute = useCallback((rawCommand) => {
    const command = String(rawCommand || '').trim()
    const result = resolveHeroCommand(command, programs)
    if (result.type === 'noop') return

    setHistory(current => [command, ...current.filter(item => item !== command)].slice(0, 20))
    setHistoryIndex(-1)
    setInput('')

    if (result.type === 'clear') {
      setEntries([WELCOME_ENTRY])
      return
    }
    if (result.program) {
      setActiveProgramId(result.program.id)
      pulse(result.program.id)
    }
    if (result.type === 'login') {
      setAuthorizing(true)
      appendEntry(command, { type: 'output', lines: ['Starting Hack Forums authorization...'] })
      onLogin()
      return
    }
    if (result.type === 'open') {
      setAuthorizing(true)
      appendEntry(command, { type: 'output', lines: [`Opening ${result.program.label}...`] })
      onOpen(result.program)
      return
    }
    appendEntry(command, result)
  }, [appendEntry, onLogin, onOpen, programs, pulse])

  const selectProgram = useCallback((program) => execute(`open ${program.command}`), [execute])

  const handleKeyDown = useCallback((event) => {
    if (event.ctrlKey && event.key.toLowerCase() === 'l') {
      event.preventDefault()
      execute('clear')
    } else if (event.key === 'Enter') {
      event.preventDefault()
      execute(input)
    } else if (event.key === 'Escape') {
      event.preventDefault()
      setInput('')
      setHistoryIndex(-1)
    } else if (event.key === 'Tab') {
      event.preventDefault()
      setInput(current => completeHeroCommand(current, programs))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      if (!history.length) return
      const nextIndex = Math.min(historyIndex + 1, history.length - 1)
      setHistoryIndex(nextIndex)
      setInput(history[nextIndex])
    } else if (event.key === 'ArrowDown') {
      event.preventDefault()
      if (historyIndex <= 0) {
        setHistoryIndex(-1)
        setInput('')
      } else {
        const nextIndex = historyIndex - 1
        setHistoryIndex(nextIndex)
        setInput(history[nextIndex])
      }
    }
  }, [execute, history, historyIndex, input, programs])

  return {
    activeProgramId, authorizing, bootSkipped, entries, execute, finishBoot, handleKeyDown,
    heroPrograms, input, inputRef, phase, phaseIndex, pulseProgramId, ready, selectProgram,
    setActiveProgramId, setInput,
  }
}
