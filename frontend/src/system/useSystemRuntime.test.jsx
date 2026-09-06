import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { BOOT_STORAGE_KEY, useSystemRuntime } from './useSystemRuntime.js'

describe('useSystemRuntime', () => {
  beforeEach(() => {
    sessionStorage.clear()
    localStorage.clear()
    vi.useFakeTimers()
  })

  afterEach(() => vi.useRealTimers())

  it('completes the first boot and records it for the session', () => {
    const { result } = renderHook(() => useSystemRuntime())
    act(() => vi.runAllTimers())
    expect(result.current.phase).toBe('ready')
    expect(sessionStorage.getItem(BOOT_STORAGE_KEY)).toBe('1')
  })

  it('opens programs through whitelisted commands', () => {
    const { result } = renderHook(() => useSystemRuntime())
    act(() => {
      result.current.finishBoot()
      result.current.execute('open market')
    })
    expect(result.current.activeProgram.id).toBe('market')
    expect(result.current.output.at(-1).text).toContain('program opened: market')
  })

  it('uses the short resume sequence after a completed session boot', () => {
    sessionStorage.setItem(BOOT_STORAGE_KEY, '1')
    const { result } = renderHook(() => useSystemRuntime())
    expect(result.current.phase).toBe('resume')
    act(() => vi.advanceTimersByTime(320))
    expect(result.current.phase).toBe('ready')
  })

  it('changes motion explicitly and rejects unknown commands', () => {
    const { result } = renderHook(() => useSystemRuntime())
    act(() => result.current.execute('motion off'))
    expect(result.current.motionEnabled).toBe(false)
    expect(localStorage.getItem('hftb_os_motion')).toBe('off')
    act(() => result.current.execute('sudo anything'))
    expect(result.current.output.at(-1)).toEqual({ text: 'command not found: sudo', tone: 'error' })
  })

  it('completes known program commands without executing input', () => {
    const { result } = renderHook(() => useSystemRuntime())
    expect(result.current.complete('open mark')).toBe('open market')
    expect(result.current.activeProgram.id).toBe('home')
  })

  it('sends login to the selected program route', () => {
    const onLogin = vi.fn()
    const { result } = renderHook(() => useSystemRuntime({ onLogin }))
    act(() => result.current.execute('open bumps'))
    act(() => result.current.execute('login'))
    expect(onLogin).toHaveBeenCalledWith('/dashboard/bumper')
  })
})
