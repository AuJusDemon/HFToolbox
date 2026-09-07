import { api } from '../core/api.js'

export const PROGRAMS = [
  {
    id: 'home', label: 'Home', shortLabel: 'HOME', command: 'home', aliases: ['home', 'overview'],
    route: '/dashboard', group: 'core', availability: 'available', publicPrimary: false, glyph: 'OV',
    publicSummary: 'A single console for marketplace work, account tools, and future Toolbox programs.',
    visualizationMode: 'home', operatorOnly: false, previewComponent: 'home', prefetch: null,
    dataPaths: ['/api/dashboard/snapshot', '/api/merchant/overview', '/api/autobump/jobs', '/api/posting/queue'],
  },
  {
    id: 'merchant', label: 'My Business', shortLabel: 'BIZ', command: 'business',
    aliases: ['business', 'biz', 'merchant', 'sales'], route: '/dashboard/merchant', group: 'services', glyph: 'MB',
    availability: 'available', publicPrimary: true,
    publicSummary: 'Contracts, replies, buyers, sales threads, and follow-up work in one workspace.',
    visualizationMode: 'business', operatorOnly: false, previewComponent: 'business',
    prefetch: () => import('../core/MerchantPage.jsx'),
    dataPaths: ['/api/merchant/overview', '/api/merchant/freshness'],
  },
  {
    id: 'bumper', label: 'Bump Service', shortLabel: 'BUMPS', command: 'bumps',
    aliases: ['bumps', 'bump', 'bumper'], route: '/dashboard/bumper', group: 'services', glyph: 'BP',
    availability: 'available', publicPrimary: true,
    publicSummary: 'Schedule thread bumps and inspect timing, spend, failures, and movement afterward.',
    visualizationMode: 'bumps', operatorOnly: false, previewComponent: 'bumps',
    prefetch: () => import('../core/BumperPageV2.jsx'),
    dataPaths: ['/api/autobump/jobs', '/api/autobump/log', '/api/autobump/settings'],
  },
  {
    id: 'posting', label: 'Posting', shortLabel: 'POST', command: 'posting',
    aliases: ['posting', 'post', 'replies'], route: '/dashboard/posting', group: 'core', glyph: 'PO',
    availability: 'available', publicPrimary: true, badgeKey: 'replyCount',
    publicSummary: 'Draft, preview, and manage forum posts and watched replies from one editor.',
    visualizationMode: 'posting', operatorOnly: false, previewComponent: 'posting',
    prefetch: () => import('../core/PostingPage.jsx'),
    dataPaths: ['/api/posting/replies/count', '/api/posting/recents', '/api/settings'],
  },
  {
    id: 'contracts', label: 'Contracts', shortLabel: 'DEALS', command: 'contracts',
    aliases: ['contracts', 'contract', 'deals'], route: '/dashboard/contracts', group: 'core', glyph: 'CT',
    availability: 'available', publicPrimary: true,
    publicSummary: 'Review contract state, outstanding actions, completion, expiry, and disputes.',
    visualizationMode: 'contracts', operatorOnly: false, previewComponent: 'contracts',
    prefetch: () => import('../core/ContractsPage.jsx'),
    dataPaths: ['/api/dash/contracts', '/api/contracts/history?page=1&perpage=20', '/api/contracts/stats'],
  },
  {
    id: 'market', label: 'Marketplace', shortLabel: 'MARKET', command: 'market',
    aliases: ['market', 'marketplace', 'watch'], route: '/dashboard/market', group: 'intelligence', glyph: 'MK',
    availability: 'available', publicPrimary: true,
    publicSummary: 'Inspect indexed threads, buyer intent, watched phrases, and contract movement.',
    visualizationMode: 'market', operatorOnly: false, previewComponent: 'market',
    prefetch: () => import('../core/MarketPage.jsx'),
    dataPaths: ['/api/market/access', '/api/market/forums', '/api/market/pulse'],
  },
  {
    id: 'bytes', label: 'Bytes', shortLabel: 'BYTES', command: 'bytes', aliases: ['bytes', 'ledger'],
    route: '/dashboard/bytes', group: 'core', availability: 'available', publicPrimary: true, glyph: 'BY',
    publicSummary: 'Review balance activity and the Toolbox actions that consume or move Bytes.',
    visualizationMode: 'bytes', operatorOnly: false, previewComponent: 'bytes',
    prefetch: () => import('../core/BytesPage.jsx'),
    dataPaths: ['/api/dash/bytes', '/api/bytes/history?page=1&perpage=30&direction=all'],
  },
  {
    id: 'sigmarket', label: 'Sig Market', shortLabel: 'SIG MKT', command: 'sigmarket',
    aliases: ['sigmarket', 'sig', 'signatures'], route: '/dashboard/sigmarket', group: 'intelligence', glyph: 'SM',
    availability: 'available', publicPrimary: false,
    publicSummary: 'Manage signature-market listings and status from the same account shell.',
    visualizationMode: 'market', operatorOnly: false, previewComponent: 'market',
    prefetch: () => import('../core/SigmarketPage.jsx'),
    dataPaths: ['/api/sigmarket/status'],
  },
  {
    id: 'wire', label: 'The Wire', shortLabel: 'WIRE', command: 'wire', aliases: ['wire'],
    route: '/dashboard/wire', group: 'intelligence', availability: 'available', publicPrimary: false, glyph: 'WR',
    publicSummary: 'Read supported forum activity through the Toolbox interface.',
    visualizationMode: 'posting', operatorOnly: false, previewComponent: 'posting',
    prefetch: () => import('../core/WirePage.jsx'),
    dataPaths: ['/api/wire/me', '/api/wire/threads?tag=all&page=1&sort=recent', '/api/wire/hf-news'],
  },
  {
    id: 'casino', label: 'Byte Casino', shortLabel: 'CASINO', command: 'casino',
    aliases: ['casino', 'poker', 'blackjack', 'baccarat', 'roulette'], route: null, group: 'other', glyph: 'BC',
    availability: 'coming-soon', publicPrimary: true,
    publicSummary: 'Play multiplayer poker, blackjack, baccarat, and roulette using Bytes.',
    visualizationMode: 'casino', operatorOnly: false, previewComponent: 'casino', prefetch: null,
  },
  {
    id: 'operator', label: 'Operator', shortLabel: 'OPS', command: 'operator', aliases: ['operator', 'ops'],
    route: '/dashboard/operator', group: 'system', availability: 'available', publicPrimary: false, glyph: 'OP',
    publicSummary: 'Owner-only service health and operational visibility.',
    visualizationMode: 'home', operatorOnly: true, previewComponent: null,
    prefetch: () => import('../core/OperatorPage.jsx'),
    dataPaths: ['/api/operator/summary'],
  },
  {
    id: 'settings', label: 'Settings', shortLabel: 'SETTINGS', command: 'settings', aliases: ['settings', 'config'],
    route: '/dashboard/settings', group: 'system', availability: 'available', publicPrimary: false, glyph: 'ST',
    publicSummary: 'Account preferences and Toolbox behavior.',
    visualizationMode: 'home', operatorOnly: false, previewComponent: null,
    prefetch: () => import('../core/Settings.jsx'),
    dataPaths: ['/api/crawl/status', '/api/telegram/status', '/api/telegram/delivery-status'],
  },
]

export const PUBLIC_PROGRAMS = PROGRAMS.filter(program => program.publicPrimary)

export function findProgram(value) {
  const query = String(value || '').trim().toLowerCase()
  return PROGRAMS.find(program => program.id === query || program.aliases.includes(query)) || null
}

export function getProgramByRoute(pathname) {
  return PROGRAMS
    .filter(program => program.route)
    .sort((a, b) => b.route.length - a.route.length)
    .find(program => pathname === program.route || (program.route !== '/dashboard' && pathname.startsWith(program.route))) || PROGRAMS[0]
}

export function prefetchProgram(program, { data = false } = {}) {
  const work = []
  if (program?.prefetch) work.push(program.prefetch())
  if (data) work.push(...(program?.dataPaths || []).map(path => api.prefetch(path)))
  return Promise.allSettled(work)
}
