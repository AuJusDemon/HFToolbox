import { fireEvent, render, screen, within } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import AutoBumpScheduleForm, { availableTimezones, defaultBumpSchedule, schedulePayload, timezoneOption, WEEKDAYS } from './AutoBumpScheduleForm.jsx'

describe('shared Auto-Bump schedule form', () => {
  it('defaults to unrestricted Activity Interval with no end condition', () => {
    const schedule = defaultBumpSchedule()
    expect(schedule).toMatchObject({ mode:'timer', allowed_windows:[], calendar_slots:[], end_mode:'unlimited' })
    expect(schedulePayload(schedule)).toMatchObject({ mode:'timer', end_mode:'unlimited', allowed_windows:[], calendar_slots:[] })
  })

  it('shows one calendar time with all weekday buttons immediately', () => {
    let value = defaultBumpSchedule()
    const onChange = vi.fn(next => { value = next })
    const { rerender } = render(<AutoBumpScheduleForm value={value} onChange={onChange} />)
    fireEvent.change(screen.getByLabelText('Schedule type'), { target:{ value:'calendar' } })
    rerender(<AutoBumpScheduleForm value={value} onChange={onChange} />)
    expect(value.calendar_slots).toEqual(WEEKDAYS.map((_, day) => ({ day, time:'10:00' })))
    const calendarDays = screen.getByLabelText('Calendar days')
    expect(within(calendarDays).getByRole('button', { name:'Saturday' })).toHaveAttribute('aria-pressed', 'true')
    expect(within(calendarDays).getByRole('button', { name:'Sunday' })).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(within(calendarDays).getByRole('button', { name:'Wednesday' }))
    rerender(<AutoBumpScheduleForm value={value} onChange={onChange} />)
    expect(value.calendar_slots).not.toContainEqual({ day:2, time:'10:00' })
    fireEvent.change(screen.getByLabelText('Calendar time'), { target:{ value:'18:00' } })
    expect(value.calendar_slots).toEqual(expect.arrayContaining([{ day:0, time:'18:00' }, { day:6, time:'18:00' }]))
    expect(screen.queryByRole('button', { name:/another time/i })).not.toBeInTheDocument()
  })

  it('creates multiple allowed windows without submitting a form', () => {
    let value = defaultBumpSchedule()
    const onChange = vi.fn(next => { value = next })
    const { rerender } = render(<AutoBumpScheduleForm value={value} onChange={onChange} />)
    fireEvent.click(screen.getByRole('button', { name:'Unrestricted' }))
    rerender(<AutoBumpScheduleForm value={value} onChange={onChange} />)
    expect(value.allowed_windows[0].days).toEqual([0, 1, 2, 3, 4, 5, 6])
    expect(screen.getByRole('button', { name:'Sat' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name:'Sun' })).toHaveAttribute('aria-pressed', 'true')
    fireEvent.click(screen.getByRole('button', { name:'Add time window' }))
    expect(value.allowed_windows).toHaveLength(2)
  })

  it('searches and selects supported IANA timezones using friendly names and offsets', () => {
    const schedule = { ...defaultBumpSchedule(), timezone:'America/New_York' }
    const onChange = vi.fn()
    render(<AutoBumpScheduleForm value={schedule} onChange={onChange} />)
    const timezone = screen.getByRole('combobox', { name:'Timezone' })
    expect(timezone.tagName).toBe('INPUT')
    expect(timezone).toHaveValue(timezoneOption('America/New_York').name)
    fireEvent.focus(timezone)
    fireEvent.change(timezone, { target:{ value:'Tokyo' } })
    fireEvent.click(screen.getByRole('option', { name:/Tokyo/i }))
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ timezone:'Asia/Tokyo' }))
    expect(availableTimezones('America/New_York')).toEqual(expect.arrayContaining(['UTC', 'America/New_York']))
  })

  it('serializes each end condition using the same API contract', () => {
    const base = defaultBumpSchedule()
    expect(schedulePayload({ ...base, end_mode:'duration', end_days:'14' })).toMatchObject({ end_mode:'duration', end_days:14 })
    expect(schedulePayload({ ...base, end_mode:'successes', end_limit:'20' })).toMatchObject({ end_mode:'successes', end_limit:20 })
    expect(schedulePayload({ ...base, end_mode:'bytes', end_limit:'1000' })).toMatchObject({ end_mode:'bytes', end_limit:1000 })
    expect(schedulePayload({ ...base, end_mode:'date', end_at:'2026-09-30' })).toMatchObject({ end_mode:'date', end_date:'2026-09-30' })
    expect(schedulePayload({ ...base, end_mode:'duration', end_days:'14', fixed_end_at:2000000000 })).toMatchObject({ end_mode:'duration', end_at:2000000000 })
  })
})
