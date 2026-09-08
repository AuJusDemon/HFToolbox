export const BUMP_INTERVALS = [
  [6, '6 hours'],
  [8, '8 hours'],
  [12, '12 hours'],
  [16, '16 hours'],
  [24, '1 day'],
  [48, '2 days'],
  [72, '3 days'],
  [120, '5 days'],
  [168, '1 week'],
]

export const BUMP_EXPIRIES = [
  [0, 'No end date'],
  [7, '1 week'],
  [14, '2 weeks'],
  [30, '1 month'],
  [60, '2 months'],
]

export const BUMP_MODES = [
  {
    id: 'timer',
    label: 'Activity Interval',
    intervalLabel: 'Minimum inactivity',
    description: 'Becomes due after the thread has remained inactive for the selected interval.',
  },
  {
    id: 'calendar',
    label: 'Calendar Scheduling',
    intervalLabel: 'Minimum inactivity',
    description: 'Checks at selected weekly times and bumps only after the inactivity requirement is met.',
  },
]

export function bumpMode(id) {
  return BUMP_MODES.find(mode => mode.id === id) || BUMP_MODES[0]
}
