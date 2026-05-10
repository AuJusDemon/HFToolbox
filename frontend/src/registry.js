export const MODULES = []
export const getPath = id => MODULES.find(m => m.id === id)?.path ?? '/dashboard'
