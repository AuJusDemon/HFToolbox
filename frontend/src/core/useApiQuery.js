import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { api } from './api.js'

export function useApiQuery(path, options = {}) {
  return useQuery({
    ...api.queryOptions(path),
    placeholderData: keepPreviousData,
    enabled: Boolean(path),
    ...options,
  })
}
