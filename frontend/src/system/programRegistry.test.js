import { describe, expect, it } from 'vitest'
import { findProgram, getProgramByRoute, PROGRAMS, PUBLIC_PROGRAMS } from './programRegistry.js'

describe('program registry', () => {
  it('keeps program ids, commands, and routes unique', () => {
    expect(new Set(PROGRAMS.map(program => program.id)).size).toBe(PROGRAMS.length)
    expect(new Set(PROGRAMS.map(program => program.command)).size).toBe(PROGRAMS.length)
    const routes = PROGRAMS.filter(program => program.route).map(program => program.route)
    expect(new Set(routes).size).toBe(routes.length)
  })

  it('resolves command aliases and nested dashboard routes', () => {
    expect(findProgram('biz')?.id).toBe('merchant')
    expect(findProgram('blackjack')?.id).toBe('casino')
    expect(getProgramByRoute('/dashboard/contracts/413649').id).toBe('contracts')
  })

  it('keeps owner-only tools out of the public directory', () => {
    expect(PUBLIC_PROGRAMS.some(program => program.operatorOnly)).toBe(false)
    expect(PUBLIC_PROGRAMS.some(program => program.id === 'casino')).toBe(true)
  })
})
