import { create } from 'zustand'
import { api } from './core/api.js'

// Default settings — used when user has no saved settings yet
export const SETTING_DEFAULTS = {
  apiFloorEnabled:   true,
  apiFloor:          30,       // pause polling when remaining < this
  bytesInterval:     120,      // seconds — balance polling
  contractsInterval: 300,      // seconds — contracts polling
  bumperInterval:    60,       // seconds — auto bumper polling
}

// ── TTLs (seconds) ─────────────────────────────────────────────────────────────
const TTL = {
  sigmarketStatus: 300,   // 5 min — background warms every 15 min
  sigmarketBrowse: 1200,  // 20 min — background warms every 25 min
}

const useStore = create((set, get) => ({

  // ── Auth ───────────────────────────────────────────────────────────────────
  user:        null,
  authLoading: true,

  fetchMe: async () => {
    try {
      const user = await api.get('/auth/me')
      set({ user, authLoading: false })
    } catch {
      set({ user: null, authLoading: false })
    }
  },

  logout: async () => {
    await api.post('/auth/logout')
    set({ user: null })
    window.location.href = '/'
  },

  // ── Module manifest ─────────────────────────────────────────────────────────
  modules:        [],
  modulesLoading: true,

  fetchModules: async () => {
    try {
      const { modules } = await api.get('/api/modules')
      set({ modules, modulesLoading: false })
    } catch {
      set({ modulesLoading: false })
    }
  },

  // ── Per-user prefs (persisted in backend DB) ───────────────────────────────
  prefs: {},

  fetchPrefs: async () => {
    try {
      const { prefs } = await api.get('/api/prefs')
      set({ prefs })
    } catch { /* non-fatal */ }
  },

  isEnabled: (moduleId) => {
    const { prefs, modules } = get()
    if (moduleId in prefs) return Boolean(prefs[moduleId])
    const meta = modules.find(m => m.id === moduleId)
    return meta ? Boolean(meta.default_on) : true
  },

  setEnabled: async (moduleId, enabled) => {
    set(s => ({ prefs: { ...s.prefs, [moduleId]: enabled } }))
    try {
      await api.post(`/api/prefs/${moduleId}?enabled=${enabled}`)
    } catch {
      set(s => {
        const prefs = { ...s.prefs }
        delete prefs[moduleId]
        return { prefs }
      })
    }
  },

  // ── User settings (polling intervals, API floor, etc.) ─────────────────────
  settings: { ...SETTING_DEFAULTS },

  fetchSettings: async () => {
    try {
      const { settings } = await api.get('/api/settings')
      set({ settings: { ...SETTING_DEFAULTS, ...(settings || {}) } })
    } catch { /* non-fatal — defaults remain */ }
  },

  saveSettings: async (partial) => {
    set(s => ({ settings: { ...s.settings, ...partial } }))
    try {
      const res = await api.post('/api/settings', partial)
      if (res?.settings) {
        set({ settings: { ...SETTING_DEFAULTS, ...res.settings } })
      }
    } catch {}
  },

  // ── API rate-limit protection ───────────────────────────────────────────────
  apiPaused: false,
  setApiPaused: (paused) => set({ apiPaused: paused }),
  throttle: "normal",   // "normal" | "caution" | "low" | "critical"
  setThrottle: (t) => set({ throttle: t }),

  // ── Shared user name cache (uid → username) ────────────────────────────────
  // Populated passively from any endpoint that returns user data.
  // Components read from here instead of making individual resolve calls.
  userCache: {},  // { [uid: string]: string }

  // Merge a uid→username map into the cache. Safe to call with empty obj.
  mergeUserCache: (map) => {
    if (!map || !Object.keys(map).length) return
    set(s => ({ userCache: { ...s.userCache, ...map } }))
  },

  // Resolve a list of UIDs against the cache + backend. Returns map of all known names.
  resolveUids: async (uids) => {
    if (!uids || !uids.length) return
    const { userCache } = get()
    const missing = uids.map(String).filter(u => u && !userCache[u])
    if (!missing.length) return
    try {
      const res = await fetch(`/api/users/resolve?uids=${missing.join(',')}`, { credentials: 'include' })
      const map = await res.json()
      if (map && typeof map === 'object') {
        set(s => ({ userCache: { ...s.userCache, ...map } }))
      }
    } catch { /* non-fatal */ }
  },

  // ── Sigmarket status (your listing + orders) ───────────────────────────────
  sigmarketStatus:   null,
  sigmarketStatusAt: 0,

  fetchSigmarketStatus: async (force = false) => {
    const { sigmarketStatus, sigmarketStatusAt } = get()
    const age = (Date.now() / 1000) - sigmarketStatusAt
    if (!force && sigmarketStatus && age < TTL.sigmarketStatus) return
    try {
      const url = '/api/sigmarket/status' + (force ? '?force=true' : '')
      const data = await api.get(url)
      if (data) set({ sigmarketStatus: data, sigmarketStatusAt: Date.now() / 1000 })
    } catch { /* non-fatal */ }
  },

  invalidateSigmarketStatus: () => set({ sigmarketStatusAt: 0 }),

  // ── Sigmarket browse (all active market listings) ──────────────────────────
  sigmarketBrowse:   null,
  sigmarketBrowseAt: 0,

  fetchSigmarketBrowse: async (force = false) => {
    const { sigmarketBrowse, sigmarketBrowseAt } = get()
    const age = (Date.now() / 1000) - sigmarketBrowseAt
    if (!force && sigmarketBrowse && age < TTL.sigmarketBrowse) return
    try {
      const url = '/api/sigmarket/browse' + (force ? '?force=true' : '')
      const data = await api.get(url)
      if (data) {
        set({ sigmarketBrowse: data, sigmarketBrowseAt: Date.now() / 1000 })
        // Seed userCache from browse listings
        if (data.listings) {
          const map = {}
          for (const l of data.listings) {
            if (l.uid && l.username) map[String(l.uid)] = l.username
          }
          get().mergeUserCache(map)
        }
      }
    } catch { /* non-fatal */ }
  },

  // ── Bootstrap ──────────────────────────────────────────────────────────────
  bootstrap: async () => {
    await Promise.all([get().fetchMe(), get().fetchModules()])
    await Promise.all([get().fetchPrefs(), get().fetchSettings()])
  },

}))

export default useStore
