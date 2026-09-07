import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from './api.js'
import { queryClient } from './queryClient.js'

function jsonResponse(value) {
  return new Response(JSON.stringify(value), {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('shared API query cache', () => {
  beforeEach(() => {
    queryClient.clear()
    vi.restoreAllMocks()
  })

  it('deduplicates concurrent reads and reuses fresh data', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(() => Promise.resolve(jsonResponse({ ok: true })))

    const [first, second] = await Promise.all([
      api.get('/api/cache-test'),
      api.get('/api/cache-test'),
    ])
    const third = await api.get('/api/cache-test')

    expect(first).toEqual({ ok: true })
    expect(second).toEqual(first)
    expect(third).toEqual(first)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('marks reads stale after a successful mutation', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation((path, options = {}) =>
      Promise.resolve(jsonResponse({ path, method: options.method || 'GET' })))

    await api.get('/api/cache-test')
    await api.post('/api/cache-test', { enabled: true })
    await api.get('/api/cache-test')

    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(fetchMock.mock.calls[2][1].method).toBe('GET')
  })

  it('never caches an explicit force refresh', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockImplementation(() => Promise.resolve(jsonResponse({ ok: true })))

    await api.get('/api/cache-test?force=true')
    await api.get('/api/cache-test?force=true')

    expect(fetchMock).toHaveBeenCalledTimes(2)
  })
})
