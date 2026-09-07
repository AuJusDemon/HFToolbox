import { queryClient, staleTimeFor } from './queryClient.js'

async function req(method, path, body, signal) {
  const opts = {
    method,
    credentials: 'include',
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : {},
    signal,
  }
  if (body !== undefined) opts.body = JSON.stringify(body)

  const res = await fetch(path, opts)

  // Only auto-redirect on 401 for non-auth-check routes
  // fetchMe returning 401 just means not logged in — don't redirect
  if (res.status === 401) {
    queryClient.clear()
    if (path !== '/auth/me' && path !== '/api/prefs' && path !== '/api/wire/me') {
      if (window.location.pathname !== '/') window.location.href = '/'
    }
    return null
  }
  if (res.status === 204) return null
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    const failure = new Error(err.detail || err.error || err.message || `HTTP ${res.status}`)
    failure.status = res.status
    failure.payload = err
    throw failure
  }
  return res.json()
}

async function mutate(method, path, body) {
  const result = await req(method, path, body)
  await queryClient.invalidateQueries({ queryKey: ['api'], refetchType: 'none' })
  return result
}

export const api = {
  get: (path, options = {}) => options.cache === false
    ? req('GET', path, undefined, options.signal)
    : queryClient.fetchQuery({
        queryKey: ['api', path],
        queryFn: ({ signal }) => req('GET', path, undefined, signal),
        staleTime: options.staleTime ?? staleTimeFor(path),
      }),
  post:   (path, b)  => mutate('POST',   path, b),
  put:    (path, b)  => mutate('PUT',    path, b),
  patch:  (path, b)  => mutate('PATCH',  path, b),
  delete: path       => mutate('DELETE', path),
  queryOptions: (path, options = {}) => ({
    queryKey: ['api', path],
    queryFn: ({ signal }) => req('GET', path, undefined, signal),
    staleTime: options.staleTime ?? staleTimeFor(path),
    ...options,
  }),
  prefetch: (path, options = {}) => queryClient.prefetchQuery({
    queryKey: ['api', path],
    queryFn: ({ signal }) => req('GET', path, undefined, signal),
    staleTime: options.staleTime ?? staleTimeFor(path),
    ...options,
  }),
  invalidate: (path, exact = true) => queryClient.invalidateQueries({ queryKey: ['api', path], exact }),
}

// ── Throttle-aware polling multipliers ────────────────────────────────────────
// Import this + useStore in any component to get a dynamic interval.
// Normal: 1x. Caution: 1.5x. Low: 2x. Critical: 3x.
export const THROTTLE_MULT = {
  normal:   1,
  caution:  1.5,
  low:      2,
  critical: 3,
}

export function throttledInterval(baseMs, throttle) {
  const mult = THROTTLE_MULT[throttle] ?? 1
  return Math.round(baseMs * mult)
}
