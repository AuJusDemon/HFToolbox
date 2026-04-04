async function req(method, path, body) {
  const opts = {
    method,
    credentials: 'include',
    headers: body !== undefined ? { 'Content-Type': 'application/json' } : {},
  }
  if (body !== undefined) opts.body = JSON.stringify(body)

  const res = await fetch(path, opts)

  // Only auto-redirect on 401 for non-auth-check routes
  // fetchMe returning 401 just means not logged in — don't redirect
  if (res.status === 401) {
    if (path !== '/auth/me' && path !== '/api/prefs') {
      if (window.location.pathname !== '/') window.location.href = '/'
    }
    return null
  }
  if (res.status === 204) return null
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(err.detail || err.error || err.message || `HTTP ${res.status}`)
  }
  return res.json()
}

export const api = {
  get:    path       => req('GET',    path),
  post:   (path, b)  => req('POST',   path, b),
  patch:  (path, b)  => req('PATCH',  path, b),
  delete: path       => req('DELETE', path),
}
