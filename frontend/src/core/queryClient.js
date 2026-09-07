import { QueryClient } from '@tanstack/react-query'

export const queryKeys = {
  api: path => ['api', path],
}

export function staleTimeFor(path) {
  if (/[?&](force|refresh)=true(?:&|$)/.test(path)) return 0
  if (/^\/api\/(modules|prefs|settings|market\/forums|market\/access)/.test(path)) return 5 * 60_000
  if (/^\/api\/(profile|shell-data)/.test(path) || path === '/auth/me') return 60_000
  if (/^\/api\/sigmarket\//.test(path)) return 5 * 60_000
  if (/^\/api\/(operator|crawl\/status)/.test(path)) return 30_000
  return 20_000
}

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 20_000,
      gcTime: 30 * 60_000,
      retry: (count, error) => count < 1 && ![401, 403, 404].includes(error?.status),
      refetchOnWindowFocus: false,
      refetchOnReconnect: true,
    },
    mutations: { retry: false },
  },
})

export function apiQueryOptions(path, queryFn, options = {}) {
  return {
    queryKey: queryKeys.api(path),
    queryFn,
    staleTime: options.staleTime ?? staleTimeFor(path),
    ...options,
  }
}
