import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMock = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), put: vi.fn(), patch: vi.fn(), delete: vi.fn() }))

vi.mock('./api.js', () => ({ api: apiMock }))
vi.mock('../store.js', () => ({
  default: selector => selector({ user: { groups: ['9'] }, settings: { bumperInterval: 9999 }, apiPaused: true }),
}))

import BumperPageV2 from './BumperPageV2.jsx'

const jobs = [
  { id: 1, tid: '111', thread_title: 'Scheduled thread', enabled: true, expired: false, mode: 'timer', interval_h: 24, next_bump: 9999999999, seconds_until_bump: 500, bump_count: 2 },
  { id: 2, tid: '222', thread_title: 'Broken thread', enabled: true, expired: false, mode: 'timer', interval_h: 24, next_bump: 9999999998, seconds_until_bump: 400, bump_count: 1 },
]
const log = [{ id: 10, tid: '222', thread_title: 'Broken thread', action: 'error', reason: 'HF request failed', ts: 200 }]
const fees = { weekly_budget: 500, bytes_this_week: 110, remaining_budget: 390, bumps_this_week: 1, hf_fee: 100, service_fee: 10, total_cost: 110 }
const stats = { total_bumps: 1, total_skips: 0, total_contracts: 0, bytes_spent: 110, hf_fee: 100, service_fee: 10, total_cost: 110, avg_reply_gain: null, bump_periods: [] }

function mockLoads({ logFailure = false } = {}) {
  apiMock.get.mockImplementation(path => {
    if (path === '/api/autobump/jobs') return Promise.resolve({ jobs })
    if (path === '/api/autobump/log') return logFailure ? Promise.reject(new Error('log down')) : Promise.resolve({ log })
    if (path === '/api/autobump/settings') return Promise.resolve(fees)
    if (path.includes('/stats')) return Promise.resolve(stats)
    throw new Error(`Unexpected GET ${path}`)
  })
}

beforeEach(() => {
  vi.clearAllMocks()
  apiMock.patch.mockResolvedValue({ ok: true })
  apiMock.delete.mockResolvedValue({ ok: true })
  mockLoads()
})

describe('Bump Service page interactions', () => {
  it('automatically selects the failed job ahead of scheduled jobs', async () => {
    render(<BumperPageV2 />)
    expect(await screen.findByRole('heading', { name: 'Broken thread' })).toBeInTheDocument()
    expect(screen.getAllByText('Needs attention').length).toBeGreaterThan(0)
  })

  it('rolls an optimistic pause back when the request fails', async () => {
    apiMock.patch.mockRejectedValueOnce(new Error('pause failed'))
    render(<BumperPageV2 />)
    const pause = await screen.findByRole('button', { name: 'Pause job' })
    fireEvent.click(pause)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Pause job' })).toBeInTheDocument())
    expect(screen.getByText('pause failed')).toBeInTheDocument()
  })

  it('requires inline removal confirmation before deleting', async () => {
    render(<BumperPageV2 />)
    fireEvent.click(await screen.findByRole('button', { name: 'Remove job' }))
    expect(apiMock.delete).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Confirm remove' }))
    await waitFor(() => expect(apiMock.delete).toHaveBeenCalledWith('/api/autobump/jobs/222'))
  })

  it('keeps jobs usable when attempt history fails independently', async () => {
    mockLoads({ logFailure: true })
    render(<BumperPageV2 />)
    expect(await screen.findByRole('heading', { name: 'Broken thread' })).toBeInTheDocument()
    expect(screen.getByText('Attempt history is unavailable.')).toBeInTheDocument()
  })
})
