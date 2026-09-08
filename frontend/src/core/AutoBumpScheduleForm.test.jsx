import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import AutoBumpScheduleForm, { defaultBumpSchedule, schedulePayload } from './AutoBumpScheduleForm.jsx'

describe('shared Auto-Bump schedule form', () => {
  it('defaults to unrestricted Activity Interval with no end condition', () => {
    const schedule = defaultBumpSchedule()
    expect(schedule).toMatchObject({ mode:'timer', allowed_windows:[], calendar_slots:[], end_mode:'unlimited' })
    expect(schedulePayload(schedule)).toMatchObject({ mode:'timer', end_mode:'unlimited', allowed_windows:[], calendar_slots:[] })
  })

  it('creates calendar slots and multiple allowed windows without submitting a form', () => {
    let value = defaultBumpSchedule()
    const onChange = vi.fn(next => { value = next })
    const { rerender } = render(<AutoBumpScheduleForm value={value} onChange={onChange} />)
    fireEvent.change(screen.getByLabelText('Schedule type'), { target:{ value:'calendar' } })
    rerender(<AutoBumpScheduleForm value={value} onChange={onChange} />)
    fireEvent.click(screen.getByRole('button', { name:'Add calendar slot' }))
    rerender(<AutoBumpScheduleForm value={value} onChange={onChange} />)
    expect(value.calendar_slots).toEqual([{ day:0, time:'10:00' }])
    fireEvent.click(screen.getByRole('button', { name:'Unrestricted' }))
    rerender(<AutoBumpScheduleForm value={value} onChange={onChange} />)
    fireEvent.click(screen.getByRole('button', { name:'Add time window' }))
    expect(value.allowed_windows).toHaveLength(2)
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
