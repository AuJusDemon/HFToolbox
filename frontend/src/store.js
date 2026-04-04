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

  // ── Bootstrap ──────────────────────────────────────────────────────────────
  bootstrap: async () => {
    await Promise.all([get().fetchMe(), get().fetchModules()])
    await Promise.all([get().fetchPrefs(), get().fetchSettings()])
  },

}))

export default useStore
