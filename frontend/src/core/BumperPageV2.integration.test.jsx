import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'

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
const stats = { tid:'222', range:{key:'30d'}, freshness:{thread_observed_at:null}, current_period:{started_at:null,replies_since_latest_bump:{value:null,available:false,source:'observed'},contracts_opened:{value:0,available:true,source:'observed'}}, metrics:{successful_bumps:{value:1,available:true,source:'observed'},skips:{value:0,available:true,source:'observed'},failures:{value:0,available:true,source:'observed'},tracked_replies:{value:0,available:true,source:'observed'},contracts_opened:{value:0,available:true,source:'observed'},estimated_bytes_spent:{value:110,available:true,source:'estimated'}},fees:{hf_fee:100,service_fee:10,total_cost:110},activity:[],attempts:[],pagination:{page:1,total_pages:1,has_previous:false,has_next:false} }
const renderPage = (route = '/dashboard/bumper') => render(<MemoryRouter initialEntries={[route]}><BumperPageV2 /></MemoryRouter>)

function mockLoads({ logFailure = false } = {}) {
  apiMock.get.mockImplementation(path => {
    if (path === '/api/autobump/jobs') return Promise.resolve({ jobs })
    if (path === '/api/autobump/log') return logFailure ? Promise.reject(new Error('log down')) : Promise.resolve({ log })
    if (path === '/api/autobump/settings') return Promise.resolve(fees)
    if (path.includes('/performance?')) return Promise.resolve(stats)
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
    renderPage()
    expect(await screen.findByRole('heading', { name: 'Broken thread' })).toBeInTheDocument()
    expect(screen.getAllByText('Needs attention').length).toBeGreaterThan(0)
  })

  it('switches the detail workspace and requests stats for that thread', async () => {
    renderPage()
    await screen.findByRole('heading', { name: 'Broken thread' })
    fireEvent.click(screen.getByRole('button', { name: /Scheduled thread/ }))
    expect(await screen.findByRole('heading', { name: 'Scheduled thread' })).toBeInTheDocument()
    await waitFor(() => expect(apiMock.get).toHaveBeenCalledWith('/api/autobump/jobs/111/performance?range=30d&page=1&page_size=5'))
  })

  it('rolls an optimistic pause back when the request fails', async () => {
    apiMock.patch.mockRejectedValueOnce(new Error('pause failed'))
    renderPage()
    const pause = await screen.findByRole('button', { name: 'Pause job' })
    fireEvent.click(pause)
    await waitFor(() => expect(screen.getByRole('button', { name: 'Pause job' })).toBeInTheDocument())
    expect(screen.getByText('pause failed')).toBeInTheDocument()
  })

  it('requires inline removal confirmation before deleting', async () => {
    renderPage()
    fireEvent.click(await screen.findByRole('button', { name: 'Remove job' }))
    expect(apiMock.delete).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'Confirm remove' }))
    await waitFor(() => expect(apiMock.delete).toHaveBeenCalledWith('/api/autobump/jobs/222'))
  })

  it('keeps jobs usable when attempt history fails independently', async () => {
    mockLoads({ logFailure: true })
    renderPage()
    expect(await screen.findByRole('heading', { name: 'Broken thread' })).toBeInTheDocument()
    expect(screen.getByText(/Attempt history is unavailable/)).toBeInTheDocument()
  })

  it('selects an owned thread from the query string and opens schedule editing', async () => {
    renderPage('/dashboard/bumper?tid=111')
    expect(await screen.findByRole('heading', { name:'Scheduled thread' })).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name:'Edit schedule' }))
    expect(screen.getByRole('region', { name:'Edit schedule' })).toHaveTextContent('cannot be changed here')
    expect(screen.getByRole('button', { name:'Save schedule' })).toBeDisabled()
  })
})
