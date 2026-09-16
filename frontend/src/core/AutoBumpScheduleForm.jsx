import { useEffect, useMemo, useRef, useState } from 'react'
import { BUMP_INTERVALS, BUMP_MODES, bumpMode } from './autobumpModes.js'
import './AutoBumpScheduleForm.css'

export const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

const COMMON_TIMEZONES = [
  'UTC',
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'Europe/London',
  'Europe/Paris',
  'Asia/Dubai',
  'Asia/Kolkata',
  'Asia/Singapore',
  'Asia/Tokyo',
  'Australia/Sydney',
]

const browserTimezone = () => {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC' }
  catch { return 'UTC' }
}

export const availableTimezones = current => {
  let supported = []
  try { supported = Intl.supportedValuesOf?.('timeZone') || [] }
  catch { supported = [] }
  const zones = new Set([...COMMON_TIMEZONES, ...supported])
  if (current) zones.add(current)
  return [...zones].sort((left, right) => {
    const leftRank = COMMON_TIMEZONES.indexOf(left)
    const rightRank = COMMON_TIMEZONES.indexOf(right)
    if (leftRank !== -1 || rightRank !== -1) {
      if (leftRank === -1) return 1
      if (rightRank === -1) return -1
      return leftRank - rightRank
    }
    return left.localeCompare(right)
  })
}

const timezoneDetails = zone => {
  try {
    const date = new Date()
    const name = new Intl.DateTimeFormat('en-US', { timeZone:zone, timeZoneName:'longGeneric' })
      .formatToParts(date).find(part => part.type === 'timeZoneName')?.value
    const offset = new Intl.DateTimeFormat('en-US', { timeZone:zone, timeZoneName:'longOffset' })
      .formatToParts(date).find(part => part.type === 'timeZoneName')?.value
      ?.replace('GMT', 'UTC')
    return { name:name || zone.replaceAll('_', ' '), offset:offset || 'UTC' }
  } catch {
    return { name:zone.replaceAll('_', ' '), offset:'' }
  }
}

export const timezoneOption = zone => {
  const { name, offset } = timezoneDetails(zone)
  return { zone, name, offset, label:`${name} (${offset})` }
}

function TimezonePicker({ value, onChange, id }) {
  const options = useMemo(() => availableTimezones(value).map(timezoneOption), [value])
  const selected = useMemo(() => timezoneOption(value), [value])
  const [query, setQuery] = useState(selected.name)
  const [open, setOpen] = useState(false)
  const [activeIndex, setActiveIndex] = useState(0)
  const activeRef = useRef(null)
  const listId = `${id}-options`
  const normalizedQuery = query.trim().toLocaleLowerCase()
  const matches = useMemo(() => {
    if (!normalizedQuery || query === selected.name) return options
    return options.filter(option => `${option.name} ${option.offset} ${option.zone.replaceAll('_', ' ')}`.toLocaleLowerCase().includes(normalizedQuery))
  }, [normalizedQuery, options, query, selected.name])

  useEffect(() => setQuery(selected.name), [selected.name])
  useEffect(() => setActiveIndex(index => Math.min(index, Math.max(matches.length - 1, 0))), [matches.length])
  useEffect(() => activeRef.current?.scrollIntoView({ block:'nearest' }), [activeIndex])

  const choose = option => {
    onChange(option.zone)
    setQuery(option.name)
    setOpen(false)
  }
  const handleKeyDown = event => {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setOpen(true)
      setActiveIndex(index => Math.min(index + 1, matches.length - 1))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setOpen(true)
      setActiveIndex(index => Math.max(index - 1, 0))
    } else if (event.key === 'Enter' && open && matches[activeIndex]) {
      event.preventDefault()
      choose(matches[activeIndex])
    } else if (event.key === 'Escape') {
      setQuery(selected.name)
      setOpen(false)
    }
  }

  return <div className="abs-timezone" onBlur={event => {
    if (!event.currentTarget.contains(event.relatedTarget)) {
      setQuery(selected.name)
      setOpen(false)
    }
  }}>
    <input
      id={id}
      role="combobox"
      aria-label="Timezone"
      aria-autocomplete="list"
      aria-controls={listId}
      aria-expanded={open}
      aria-activedescendant={open && matches[activeIndex] ? `${id}-option-${activeIndex}` : undefined}
      autoComplete="off"
      value={query}
      onFocus={event => { event.target.select(); setOpen(true) }}
      onChange={event => { setQuery(event.target.value); setActiveIndex(0); setOpen(true) }}
      onKeyDown={handleKeyDown}
    />
    {open && <div id={listId} className="abs-timezone-list" role="listbox" aria-label="Timezone results">
      {matches.length ? matches.map((option, index) => <button
        id={`${id}-option-${index}`}
        ref={index === activeIndex ? activeRef : null}
        key={option.zone}
        type="button"
        role="option"
        aria-selected={option.zone === value}
        className={index === activeIndex ? 'is-active' : ''}
        onMouseDown={event => event.preventDefault()}
        onClick={() => choose(option)}
      >
        <span>{option.name} <b>{option.offset}</b></span>
        <small>{option.zone}</small>
      </button>) : <p className="abs-timezone-empty">No matching timezone</p>}
    </div>}
  </div>
}

export function defaultBumpSchedule() {
  return {
    mode: 'timer', interval_h: 24, timezone: browserTimezone(),
    allowed_windows: [], calendar_slots: [], end_mode: 'unlimited',
    end_at: '', end_days: '', end_limit: '', fixed_end_at: '', enabled: true,
  }
}

export function scheduleFromJob(job = {}) {
  const timezone = job.timezone || browserTimezone()
  const localDate = job.bump_until ? new Intl.DateTimeFormat('en-CA', { timeZone:timezone, year:'numeric', month:'2-digit', day:'2-digit' }).formatToParts(new Date(Number(job.bump_until) * 1000)).reduce((parts, part) => ({ ...parts, [part.type]:part.value }), {}) : null
  return {
    ...defaultBumpSchedule(),
    mode: job.mode === 'calendar' ? 'calendar' : 'timer',
    interval_h: Number(job.interval_h || 24),
    timezone,
    allowed_windows: Array.isArray(job.allowed_windows) ? job.allowed_windows : [],
    calendar_slots: Array.isArray(job.calendar_slots) ? job.calendar_slots : [],
    end_mode: job.end_mode || (job.bump_until ? 'date' : 'unlimited'),
    end_at: localDate ? `${localDate.year}-${localDate.month}-${localDate.day}` : '',
    end_days: job.end_mode === 'duration' ? job.end_limit ?? '' : '',
    end_limit: job.end_mode === 'duration' ? '' : job.end_limit ?? '',
    fixed_end_at: job.end_mode === 'duration' ? job.bump_until || '' : '', enabled: Boolean(job.enabled),
  }
}

export function schedulePayload(schedule) {
  const payload = {
    mode: schedule.mode,
    interval_h: Number(schedule.interval_h),
    timezone: schedule.timezone.trim(),
    allowed_windows: schedule.allowed_windows,
    calendar_slots: schedule.mode === 'calendar' ? schedule.calendar_slots : [],
    end_mode: schedule.end_mode,
  }
  if (schedule.end_mode === 'date') payload.end_date = schedule.end_at
  if (schedule.end_mode === 'duration') {
    if (schedule.fixed_end_at) payload.end_at = Number(schedule.fixed_end_at)
    else payload.end_days = Number(schedule.end_days)
  }
  if (schedule.end_mode === 'successes' || schedule.end_mode === 'bytes') payload.end_limit = Number(schedule.end_limit)
  return payload
}

const changeAt = (rows, index, patch) => rows.map((row, rowIndex) => rowIndex === index ? { ...row, ...patch } : row)

export default function AutoBumpScheduleForm({ value, onChange, idPrefix = 'bump' }) {
  const schedule = value
  const set = patch => onChange({ ...schedule, ...patch })
  const restricted = schedule.allowed_windows.length > 0
  const activeDays = restricted ? schedule.allowed_windows[0]?.days || [] : [0, 1, 2, 3, 4, 5, 6]
  const windows = restricted ? schedule.allowed_windows : [{ days: activeDays, start: '09:00', end: '22:00' }]
  const setWindows = next => set({ allowed_windows: next })
  const toggleRestriction = () => setWindows(restricted ? [] : windows)
  const toggleDay = day => {
    const days = activeDays.includes(day) ? activeDays.filter(item => item !== day) : [...activeDays, day].sort()
    setWindows(windows.map(window => ({ ...window, days })))
  }

  return <div className="abs-form">
    <div className="abs-grid">
      <label htmlFor={`${idPrefix}-mode`}>Schedule type
        <select id={`${idPrefix}-mode`} aria-label="Schedule type" value={schedule.mode} onChange={event => set({ mode: event.target.value })}>
          {BUMP_MODES.map(mode => <option key={mode.id} value={mode.id}>{mode.label}</option>)}
        </select>
        <small>{bumpMode(schedule.mode).description}</small>
      </label>
      <label htmlFor={`${idPrefix}-interval`}>Minimum inactivity
        <select id={`${idPrefix}-interval`} aria-label="Minimum inactivity" value={schedule.interval_h} onChange={event => set({ interval_h: Number(event.target.value) })}>
          {BUMP_INTERVALS.map(([hours, label]) => <option key={hours} value={hours}>{label}</option>)}
        </select>
        <small>Every attempt waits for this much thread inactivity.</small>
      </label>
      <label htmlFor={`${idPrefix}-timezone`}>Timezone
        <TimezonePicker id={`${idPrefix}-timezone`} value={schedule.timezone} onChange={timezone => set({ timezone })} />
        <small>Times use this timezone. Daylight saving changes are handled automatically.</small>
      </label>
    </div>

    {schedule.mode === 'calendar' && <fieldset className="abs-section">
      <legend>Weekly calendar slots</legend>
      <p>The job checks at each selected slot. A missed or ineligible slot advances to the next one.</p>
      <div className="abs-rows">
        {schedule.calendar_slots.map((slot, index) => <div className="abs-row" key={`${slot.day}-${slot.time}-${index}`}>
          <label>Day<select aria-label={`Calendar slot ${index + 1} day`} value={slot.day} onChange={event => set({ calendar_slots: changeAt(schedule.calendar_slots, index, { day: Number(event.target.value) }) })}>{WEEKDAYS.map((day, dayIndex) => <option key={day} value={dayIndex}>{day}</option>)}</select></label>
          <label>Time<input aria-label={`Calendar slot ${index + 1} time`} type="time" value={slot.time} onChange={event => set({ calendar_slots: changeAt(schedule.calendar_slots, index, { time: event.target.value }) })} /></label>
          <button type="button" onClick={() => set({ calendar_slots: schedule.calendar_slots.filter((_, rowIndex) => rowIndex !== index) })}>Remove slot</button>
        </div>)}
      </div>
      <button type="button" onClick={() => set({ calendar_slots: [...schedule.calendar_slots, { day: 0, time: '10:00' }] })}>Add calendar slot</button>
    </fieldset>}

    <fieldset className="abs-section">
      <legend>Allowed hours</legend>
      <button className={`abs-toggle ${restricted ? 'is-on' : ''}`} type="button" aria-pressed={restricted} onClick={toggleRestriction}>{restricted ? 'Restricted to selected hours' : 'Unrestricted'}</button>
      {restricted && <>
        <div className="abs-days" aria-label="Allowed weekdays">{WEEKDAYS.map((day, index) => <button type="button" aria-pressed={activeDays.includes(index)} className={activeDays.includes(index) ? 'is-on' : ''} key={day} onClick={() => toggleDay(index)}>{day.slice(0, 3)}</button>)}</div>
        <div className="abs-rows">{windows.map((window, index) => <div className="abs-row" key={`${window.start}-${window.end}-${index}`}>
          <label>From<input aria-label={`Allowed window ${index + 1} start`} type="time" value={window.start} onChange={event => setWindows(changeAt(windows, index, { start: event.target.value }))} /></label>
          <label>Until<input aria-label={`Allowed window ${index + 1} end`} type="time" value={window.end} onChange={event => setWindows(changeAt(windows, index, { end: event.target.value }))} /></label>
          <button type="button" onClick={() => setWindows(windows.filter((_, rowIndex) => rowIndex !== index))}>Remove window</button>
        </div>)}</div>
        <button type="button" onClick={() => setWindows([...windows, { days: activeDays, start: '09:00', end: '17:00' }])}>Add time window</button>
        <small>End times earlier than start times continue overnight into the next day.</small>
      </>}
    </fieldset>

    <fieldset className="abs-section">
      <legend>End condition</legend>
      <label htmlFor={`${idPrefix}-end-mode`}>Stop this job
        <select id={`${idPrefix}-end-mode`} aria-label="End condition" value={schedule.end_mode} onChange={event => set({ end_mode: event.target.value })}>
          <option value="unlimited">Unlimited</option><option value="date">On a date</option><option value="duration">After a number of days</option><option value="successes">After successful bumps</option><option value="bytes">After Bytes spent</option>
        </select>
      </label>
      {schedule.end_mode === 'date' && <label>End date<input type="date" value={schedule.end_at} onChange={event => set({ end_at: event.target.value })} /></label>}
      {schedule.end_mode === 'duration' && <label>Duration in days<input type="number" min="1" value={schedule.end_days} onChange={event => set({ end_days: event.target.value, fixed_end_at:'' })} /></label>}
      {schedule.end_mode === 'successes' && <label>Successful bumps<input type="number" min="1" value={schedule.end_limit} onChange={event => set({ end_limit: event.target.value })} /></label>}
      {schedule.end_mode === 'bytes' && <label>Bytes spending limit<input type="number" min="1" value={schedule.end_limit} onChange={event => set({ end_limit: event.target.value })} /></label>}
    </fieldset>
  </div>
}
