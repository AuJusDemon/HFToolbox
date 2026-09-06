import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import { CommandLauncher, MobileProgramDrawer, ProgramNavigation, visiblePrograms } from './AppNavigation.jsx'

function LocationProbe() {
  const location = useLocation()
  return <output data-testid="location">{location.pathname}</output>
}

describe('authenticated program navigation', () => {
  it('uses the registry groups, marks the current route, and keeps Casino unavailable', () => {
    render(<MemoryRouter initialEntries={['/dashboard/bumper']}><ProgramNavigation user={{ uid:'42' }} counters={{ posting:3 }} /><LocationProbe /></MemoryRouter>)
    expect(screen.getByRole('button', { name:/Bump Service/i })).toHaveAttribute('aria-current', 'page')
    expect(screen.getByRole('button', { name:/Posting/i })).toHaveTextContent('3')
    const casino = screen.getByRole('button', { name:/Byte Casino/i })
    expect(casino).toHaveAttribute('aria-disabled', 'true')
    fireEvent.click(casino)
    expect(screen.getByTestId('location')).toHaveTextContent('/dashboard/bumper')
  })

  it('never returns Operator for a non-owner UID', () => {
    expect(visiblePrograms({ uid:'42' }).some(program => program.id === 'operator')).toBe(false)
    expect(visiblePrograms({ uid:'761578' }).some(program => program.id === 'operator')).toBe(true)
  })

  it('searches aliases and opens the selected route by keyboard', () => {
    render(<MemoryRouter initialEntries={['/dashboard']}><CommandLauncher open onClose={vi.fn()} user={{ uid:'42' }} /><LocationProbe /></MemoryRouter>)
    const input = screen.getByLabelText('Open program')
    fireEvent.change(input, { target:{ value:'bumps' } })
    expect(screen.getByRole('option')).toHaveTextContent('Bump Service')
    fireEvent.keyDown(input, { key:'Enter' })
    expect(screen.getByTestId('location')).toHaveTextContent('/dashboard/bumper')
  })

  it('closes the mobile drawer with Escape', () => {
    const close = vi.fn()
    render(<MemoryRouter><MobileProgramDrawer open onClose={close} user={{ uid:'42' }} counters={{}} account="tester" /></MemoryRouter>)
    fireEvent.keyDown(document, { key:'Escape' })
    expect(close).toHaveBeenCalledOnce()
  })
})
