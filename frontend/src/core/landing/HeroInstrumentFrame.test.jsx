import { act, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { PROGRAMS } from '../../system/programRegistry.js'
import HeroInstrumentFrame from './HeroInstrumentFrame.jsx'

function mockMotion(reduced = false, mobile = false) {
  window.matchMedia = vi.fn(query => ({
    matches: query.includes('prefers-reduced-motion') ? reduced : mobile,
    media: query,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
  }))
}

function renderHero(overrides = {}) {
  const props = {
    programs: PROGRAMS,
    user: null,
    authLoading: false,
    authError: '',
    authReference: '',
    onOpen: vi.fn(),
    onLogin: vi.fn(),
    ...overrides,
  }
  return { props, ...render(<HeroInstrumentFrame {...props} />) }
}

describe('interactive terminal hero', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    mockMotion(false, false)
    global.ResizeObserver = class ResizeObserver {
      observe() {}
      disconnect() {}
    }
    HTMLCanvasElement.prototype.getContext = vi.fn(() => ({
      clearRect: vi.fn(), save: vi.fn(), restore: vi.fn(), beginPath: vi.fn(),
      moveTo: vi.fn(), lineTo: vi.fn(), stroke: vi.fn(), fillRect: vi.fn(),
      fillText: vi.fn(), setTransform: vi.fn(),
    }))
  })

  afterEach(() => {
    vi.runOnlyPendingTimers()
    vi.useRealTimers()
  })

  it('completes the timed boot and enables the command input', () => {
    const { container } = renderHero()
    expect(container.querySelector('.hero-instrument')).toHaveAttribute('data-boot-phase', 'power')
    act(() => vi.advanceTimersByTime(1600))
    expect(container.querySelector('.hero-instrument')).toHaveAttribute('data-boot-phase', 'ready')
    expect(screen.getByLabelText('Terminal command')).toBeEnabled()
  })

  it('skips boot on the first pointer action', () => {
    const { container } = renderHero()
    fireEvent.pointerDown(window)
    expect(container.querySelector('.hero-instrument')).toHaveAttribute('data-boot-phase', 'ready')
  })

  it('bypasses boot when reduced motion is requested', () => {
    mockMotion(true, false)
    const { container } = renderHero()
    expect(container.querySelector('.hero-instrument')).toHaveAttribute('data-boot-phase', 'ready')
  })

  it('runs commands, completion, history, escape, and clear from the prompt', () => {
    renderHero()
    fireEvent.pointerDown(window)
    const input = screen.getByLabelText('Terminal command')
    fireEvent.change(input, { target: { value: 'prog' } })
    fireEvent.keyDown(input, { key: 'Tab' })
    expect(input).toHaveValue('programs ')
    fireEvent.keyDown(input, { key: 'Enter' })
    expect(screen.getByRole('log')).toHaveTextContent('business')
    fireEvent.keyDown(input, { key: 'ArrowUp' })
    expect(input).toHaveValue('programs')
    fireEvent.keyDown(input, { key: 'Escape' })
    expect(input).toHaveValue('')
    fireEvent.keyDown(input, { key: 'l', ctrlKey: true })
    expect(screen.getByRole('log')).toHaveTextContent('HF.TOOLBOX public interface')
    expect(screen.getByRole('log')).not.toHaveTextContent('business')
  })

  it('keeps Byte Casino on-page and routes available program clicks', () => {
    const { props } = renderHero()
    fireEvent.pointerDown(window)
    fireEvent.click(screen.getByRole('button', { name: /Byte Casino/ }))
    act(() => vi.advanceTimersByTime(1800))
    expect(screen.getByRole('log')).toHaveTextContent("Texas Hold'em")
    expect(props.onOpen).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: /Marketplace/ }))
    act(() => vi.advanceTimersByTime(1800))
    expect(props.onOpen).toHaveBeenCalledWith(expect.objectContaining({ route: '/dashboard/market' }))
  })

  it('types a clicked program command before route transfer and navigation', () => {
    const { props, container } = renderHero()
    fireEvent.pointerDown(window)
    fireEvent.click(screen.getByRole('button', { name: /Marketplace/ }))

    act(() => vi.advanceTimersByTime(140))
    expect(screen.getByLabelText('Terminal command').value).toMatch(/^open/)
    expect(screen.getByLabelText('Terminal command')).not.toHaveValue('open market')
    expect(props.onOpen).not.toHaveBeenCalled()

    act(() => vi.advanceTimersByTime(500))
    expect(screen.getByRole('log')).toHaveTextContent('Route selected: /dashboard/market')
    expect(container.querySelector('.hero-route-transition')).toHaveClass('state-resolving')
    expect(props.onOpen).not.toHaveBeenCalled()

    act(() => vi.advanceTimersByTime(260))
    expect(container.querySelector('.hero-route-transition')).toHaveClass('state-transfer')
    expect(props.onOpen).not.toHaveBeenCalled()

    act(() => vi.advanceTimersByTime(600))
    expect(props.onOpen).toHaveBeenCalledOnce()
  })

  it('dispatches login from the whitelisted terminal command', () => {
    const { props } = renderHero()
    fireEvent.pointerDown(window)
    const input = screen.getByLabelText('Terminal command')
    fireEvent.change(input, { target: { value: 'login' } })
    fireEvent.keyDown(input, { key: 'Enter' })
    act(() => vi.advanceTimersByTime(800))
    expect(props.onLogin).toHaveBeenCalledOnce()
  })

  it('renders the signal raster in running mode', () => {
    const { container } = renderHero()
    expect(container.querySelector('.hero-signal-raster')).toHaveAttribute('data-motion', 'running')
    expect(HTMLCanvasElement.prototype.getContext).toHaveBeenCalledWith('2d')
  })

  it('renders mapped OAuth errors and references in terminal output', () => {
    renderHero({ authError: 'Authorization was cancelled.', authReference: 'ref-123' })
    fireEvent.pointerDown(window)
    expect(screen.getByRole('log')).toHaveTextContent('Authorization was cancelled.')
    expect(screen.getByRole('log')).toHaveTextContent('Reference: ref-123')
  })
})
