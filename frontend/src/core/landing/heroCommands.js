import { findProgram } from '../../system/programRegistry.js'

export const HERO_COMMANDS = ['help', 'programs', 'about', 'open', 'login', 'clear']

export const CASINO_LINES = [
  'Texas Hold\'em / Blackjack / Baccarat / Roulette',
  'Games use Bytes with separate available, in-play, and pending balances.',
  'Completed games retain fairness and settlement records.',
]

export function getHeroPrograms(programs) {
  return programs.filter(program => program.publicPrimary && !program.operatorOnly)
}

function programList(programs) {
  return getHeroPrograms(programs).map(program => {
    const state = program.availability === 'available' ? 'AVAILABLE' : 'COMING SOON'
    return `${program.command.padEnd(10)} ${state}`
  })
}

export function resolveHeroCommand(rawInput, programs) {
  const input = String(rawInput || '').trim()
  const [command = '', ...args] = input.toLowerCase().split(/\s+/)
  const target = args.join(' ')

  if (!input) return { type: 'noop' }
  if (command === 'clear') return { type: 'clear' }
  if (command === 'login') return { type: 'login' }
  if (command === 'help') {
    return {
      type: 'output',
      lines: [
        'help / programs / about <program> / open <program> / login / clear',
        'Example: about bumps',
      ],
    }
  }
  if (command === 'programs') return { type: 'output', lines: programList(programs) }
  if (command === 'about' || command === 'open') {
    if (!target) {
      return { type: 'error', lines: [`usage: ${command} <program>`, 'Run programs to see accepted names.'] }
    }
    const program = findProgram(target)
    if (!program || program.operatorOnly || !program.publicPrimary) {
      return { type: 'error', lines: [`program not found: ${target}`, 'Run programs to see accepted names.'] }
    }
    if (command === 'about') {
      return {
        type: 'output',
        program,
        lines: [program.publicSummary, ...(program.id === 'casino' ? CASINO_LINES : [])],
      }
    }
    if (program.availability !== 'available' || !program.route) {
      return {
        type: 'unavailable',
        program,
        lines: [`${program.label} is coming soon.`, ...CASINO_LINES],
      }
    }
    return { type: 'open', program }
  }

  return { type: 'error', lines: [`command not found: ${command}`, 'Type help to list available commands.'] }
}

export function completeHeroCommand(rawInput, programs) {
  const input = String(rawInput || '')
  const leading = input.match(/^\s*/)?.[0] || ''
  const value = input.trimStart()
  const parts = value.split(/\s+/)

  if (parts.length === 1) {
    const matches = HERO_COMMANDS.filter(command => command.startsWith(parts[0].toLowerCase()))
    return matches.length === 1 ? `${leading}${matches[0]} ` : input
  }
  if (!['about', 'open'].includes(parts[0].toLowerCase()) || parts.length > 2) return input

  const fragment = parts[1].toLowerCase()
  const names = [...new Set(getHeroPrograms(programs).flatMap(program => [program.command, ...program.aliases]))]
  const matches = names.filter(name => name.startsWith(fragment))
  return matches.length === 1 ? `${leading}${parts[0]} ${matches[0]}` : input
}
