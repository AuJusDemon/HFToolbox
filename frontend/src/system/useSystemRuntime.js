import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { findProgram, PROGRAMS, PUBLIC_PROGRAMS, prefetchProgram } from './programRegistry.js'

export const BOOT_STORAGE_KEY = 'hftb_os_boot_v1'

const FULL_BOOT = [
  { phase: 'power-on', delay: 0, label: 'power.on', detail: 'display initialized' },
  { phase: 'interface-load', delay: 300, label: 'interface.load', detail: 'terminal geometry ready' },
  { phase: 'program-register', delay: 650, label: 'programs.register', detail: `${PROGRAMS.length} programs indexed` },
  { phase: 'session-restore', delay: 1000, label: 'session.restore', detail: 'preferences restored' },
  { phase: 'ready', delay: 1450, label: 'system.ready', detail: 'input enabled' },
]

function prefersReducedMotion() {
  return typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
}

function initialProgram() {
  if (typeof window === 'undefined') return PROGRAMS[0]
  const saved = sessionStorage.getItem('hftb_os_program')
  return findProgram(saved) || PROGRAMS[0]
}

export function useSystemRuntime({ onLogin } = {}) {
  const [activeProgram, setActiveProgram] = useState(initialProgram)
  const [phase, setPhase] = useState('power-on')
  const [bootLines, setBootLines] = useState([])
  const [bootRun, setBootRun] = useState(0)
  const [motionEnabled, setMotionEnabledState] = useState(() => {
    if (prefersReducedMotion()) return false
    return typeof window === 'undefined' || localStorage.getItem('hftb_os_motion') !== 'off'
  })
  const [output, setOutput] = useState([
    { tone: 'dim', text: 'Type help for commands or select a program.' },
  ])
  const [history, setHistory] = useState([])
  const [impulse, setImpulse] = useState(0)
  const timersRef = useRef([])

  const booting = phase !== 'ready'

  const finishBoot = useCallback(() => {
    timersRef.current.forEach(clearTimeout)
    timersRef.current = []
    sessionStorage.setItem(BOOT_STORAGE_KEY, '1')
    setBootLines(FULL_BOOT)
    setPhase('ready')
  }, [])

  useEffect(() => {
    timersRef.current.forEach(clearTimeout)
    timersRef.current = []
    const reduced = prefersReducedMotion()
    const returning = sessionStorage.getItem(BOOT_STORAGE_KEY) === '1' && bootRun === 0

    if (reduced) {
      finishBoot()
      return undefined
    }

    if (returning) {
      setPhase('resume')
      setBootLines([{ phase: 'resume', label: 'session.resume', detail: 'workspace restored' }])
      timersRef.current.push(setTimeout(finishBoot, 320))
      return () => timersRef.current.forEach(clearTimeout)
    }

    setPhase('power-on')
    setBootLines([])
    FULL_BOOT.forEach((step, index) => {
      timersRef.current.push(setTimeout(() => {
        setPhase(step.phase)
        setBootLines(FULL_BOOT.slice(0, index + 1))
        if (step.phase === 'ready') finishBoot()
      }, step.delay))
    })
    return () => timersRef.current.forEach(clearTimeout)
  }, [bootRun, finishBoot])

  const emit = useCallback((text, tone = 'normal') => {
    setOutput(current => [...current.slice(-5), { text, tone }])
  }, [])

  const openProgram = useCallback((program, announce = true) => {
    if (!program || program.operatorOnly) return
    setActiveProgram(program)
    sessionStorage.setItem('hftb_os_program', program.id)
    prefetchProgram(program)
    setImpulse(value => value + 1)
    if (announce) emit(`program opened: ${program.command}`, program.availability === 'coming-soon' ? 'warn' : 'accent')
  }, [emit])

  const replayBoot = useCallback(() => {
    sessionStorage.removeItem(BOOT_STORAGE_KEY)
    setBootRun(value => value + 1)
  }, [])

  const setMotionEnabled = useCallback((enabled) => {
    const next = Boolean(enabled)
    setMotionEnabledState(next)
    localStorage.setItem('hftb_os_motion', next ? 'on' : 'off')
  }, [])

  const execute = useCallback((rawCommand) => {
    const command = String(rawCommand || '').trim()
    if (!command) return
    setHistory(current => [...current.filter(item => item !== command), command].slice(-30))
    emit(`guest@hftoolbox:~$ ${command}`, 'command')

    const parts = command.toLowerCase().split(/\s+/)
    const [verb, ...args] = parts
    if (verb === 'help') {
      emit('help | programs [--all] | open <program> | login | clear | replay boot | motion on|off', 'dim')
      return
    }
    if (verb === 'programs') {
      const source = args.includes('--all') ? PROGRAMS.filter(program => !program.operatorOnly) : PUBLIC_PROGRAMS
      emit(source.map(program => program.command).join('  '), 'accent')
      return
    }
    if (verb === 'open' || verb === 'launch') {
      const program = findProgram(args.join(' '))
      if (!program || program.operatorOnly) emit(`program not found: ${args.join(' ') || '(missing)'}`, 'error')
      else openProgram(program)
      return
    }
    if (findProgram(verb) && !findProgram(verb).operatorOnly) {
      openProgram(findProgram(verb))
      return
    }
    if (verb === 'login') {
      onLogin?.(activeProgram.route)
      return
    }
    if (verb === 'clear') {
      setOutput([])
      return
    }
    if (verb === 'replay' && args[0] === 'boot') {
      replayBoot()
      return
    }
    if (verb === 'motion' && ['on', 'off'].includes(args[0])) {
      const enabled = args[0] === 'on'
      setMotionEnabled(enabled)
      emit(`motion ${enabled ? 'enabled' : 'disabled'}`, enabled ? 'accent' : 'dim')
      return
    }
    emit(`command not found: ${verb}`, 'error')
  }, [activeProgram.route, emit, onLogin, openProgram, replayBoot])

  const completions = useMemo(() => {
    const programNames = PROGRAMS.filter(program => !program.operatorOnly).flatMap(program => [program.command, ...program.aliases])
    return ['help', 'programs', 'programs --all', 'login', 'clear', 'replay boot', 'motion on', 'motion off', ...programNames.map(name => `open ${name}`)]
  }, [])

  const complete = useCallback((value) => {
    const query = String(value || '').toLowerCase()
    return completions.find(option => option.startsWith(query)) || value
  }, [completions])

  return {
    activeProgram,
    bootLines,
    booting,
    complete,
    execute,
    finishBoot,
    history,
    impulse,
    motionEnabled,
    openProgram,
    output,
    phase,
    replayBoot,
    setMotionEnabled,
  }
}
