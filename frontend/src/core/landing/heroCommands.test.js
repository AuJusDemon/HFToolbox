import { describe, expect, it } from 'vitest'
import { PROGRAMS } from '../../system/programRegistry.js'
import { completeHeroCommand, getHeroPrograms, resolveHeroCommand } from './heroCommands.js'

describe('hero command language', () => {
  it('lists only public programs from the shared registry', () => {
    const result = resolveHeroCommand('programs', PROGRAMS)
    expect(result.type).toBe('output')
    expect(result.lines).toHaveLength(getHeroPrograms(PROGRAMS).length)
    expect(result.lines.join('\n')).toContain('business')
    expect(result.lines.join('\n')).not.toContain('operator')
  })

  it('returns help and dispatches non-program commands', () => {
    expect(resolveHeroCommand('help', PROGRAMS).lines[0]).toContain('about <program>')
    expect(resolveHeroCommand('login', PROGRAMS).type).toBe('login')
    expect(resolveHeroCommand('clear', PROGRAMS).type).toBe('clear')
    expect(resolveHeroCommand('', PROGRAMS).type).toBe('noop')
  })

  it('describes programs and includes the complete casino roster', () => {
    expect(resolveHeroCommand('about biz', PROGRAMS).program.id).toBe('merchant')
    const casino = resolveHeroCommand('about casino', PROGRAMS)
    expect(casino.lines.join(' ')).toContain("Texas Hold'em")
    expect(casino.lines.join(' ')).toContain('Blackjack')
    expect(casino.lines.join(' ')).toContain('Baccarat')
    expect(casino.lines.join(' ')).toContain('Roulette')
  })

  it('opens available programs and keeps unavailable programs inside the terminal', () => {
    const market = resolveHeroCommand('open marketplace', PROGRAMS)
    expect(market.type).toBe('open')
    expect(market.program.route).toBe('/dashboard/market')
    const casino = resolveHeroCommand('open poker', PROGRAMS)
    expect(casino.type).toBe('unavailable')
    expect(casino.lines[0]).toContain('coming soon')
  })

  it('explains missing and unknown commands without accepting private programs', () => {
    expect(resolveHeroCommand('open', PROGRAMS).lines[0]).toBe('usage: open <program>')
    expect(resolveHeroCommand('about operator', PROGRAMS).type).toBe('error')
    expect(resolveHeroCommand('sudo anything', PROGRAMS).lines[0]).toBe('command not found: sudo')
  })

  it('completes unique commands and program aliases only', () => {
    expect(completeHeroCommand('prog', PROGRAMS)).toBe('programs ')
    expect(completeHeroCommand('about poke', PROGRAMS)).toBe('about poker')
    expect(completeHeroCommand('open b', PROGRAMS)).toBe('open b')
  })
})
