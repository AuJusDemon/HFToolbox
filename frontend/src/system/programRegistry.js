export const PROGRAMS = [
  {
    id: 'home', label: 'Home', shortLabel: 'HOME', command: 'home', aliases: ['home', 'overview'],
    route: '/dashboard', group: 'navigation', availability: 'available', publicPrimary: false,
    publicSummary: 'A single console for marketplace work, account tools, and future Toolbox programs.',
    visualizationMode: 'home', operatorOnly: false, previewComponent: 'home', prefetch: null,
  },
  {
    id: 'merchant', label: 'My Business', shortLabel: 'BIZ', command: 'business',
    aliases: ['business', 'biz', 'merchant', 'sales'], route: '/dashboard/merchant', group: 'modules',
    availability: 'available', publicPrimary: true,
    publicSummary: 'Contracts, replies, buyers, sales threads, and follow-up work in one workspace.',
    visualizationMode: 'business', operatorOnly: false, previewComponent: 'business',
    prefetch: () => import('../core/MerchantPage.jsx'),
  },
  {
    id: 'bumper', label: 'Bump Service', shortLabel: 'BUMPS', command: 'bumps',
    aliases: ['bumps', 'bump', 'bumper'], route: '/dashboard/bumper', group: 'modules',
    availability: 'available', publicPrimary: true,
    publicSummary: 'Schedule thread bumps and inspect timing, spend, failures, and movement afterward.',
    visualizationMode: 'bumps', operatorOnly: false, previewComponent: 'bumps',
    prefetch: () => import('../core/BumperPage.jsx'),
  },
  {
    id: 'posting', label: 'Posting', shortLabel: 'POST', command: 'posting',
    aliases: ['posting', 'post', 'replies'], route: '/dashboard/posting', group: 'modules',
    availability: 'available', publicPrimary: true, badgeKey: 'replyCount',
    publicSummary: 'Draft, preview, and manage forum posts and watched replies from one editor.',
    visualizationMode: 'posting', operatorOnly: false, previewComponent: 'posting',
    prefetch: () => import('../core/PostingPage.jsx'),
  },
  {
    id: 'contracts', label: 'Contracts', shortLabel: 'DEALS', command: 'contracts',
    aliases: ['contracts', 'contract', 'deals'], route: '/dashboard/contracts', group: 'modules',
    availability: 'available', publicPrimary: true,
    publicSummary: 'Review contract state, outstanding actions, completion, expiry, and disputes.',
    visualizationMode: 'contracts', operatorOnly: false, previewComponent: 'contracts',
    prefetch: () => import('../core/ContractsPage.jsx'),
  },
  {
    id: 'market', label: 'Marketplace', shortLabel: 'MARKET', command: 'market',
    aliases: ['market', 'marketplace', 'watch'], route: '/dashboard/market', group: 'modules',
    availability: 'available', publicPrimary: true,
    publicSummary: 'Inspect indexed threads, buyer intent, watched phrases, and contract movement.',
    visualizationMode: 'market', operatorOnly: false, previewComponent: 'market',
    prefetch: () => import('../core/MarketPage.jsx'),
  },
  {
    id: 'bytes', label: 'Bytes', shortLabel: 'BYTES', command: 'bytes', aliases: ['bytes', 'ledger'],
    route: '/dashboard/bytes', group: 'modules', availability: 'available', publicPrimary: true,
    publicSummary: 'Review balance activity and the Toolbox actions that consume or move Bytes.',
    visualizationMode: 'bytes', operatorOnly: false, previewComponent: 'bytes',
    prefetch: () => import('../core/BytesPage.jsx'),
  },
  {
    id: 'sigmarket', label: 'Sig Market', shortLabel: 'SIG MKT', command: 'sigmarket',
    aliases: ['sigmarket', 'sig', 'signatures'], route: '/dashboard/sigmarket', group: 'modules',
    availability: 'available', publicPrimary: false,
    publicSummary: 'Manage signature-market listings and status from the same account shell.',
    visualizationMode: 'market', operatorOnly: false, previewComponent: 'market',
    prefetch: () => import('../core/SigmarketPage.jsx'),
  },
  {
    id: 'wire', label: 'The Wire', shortLabel: 'WIRE', command: 'wire', aliases: ['wire'],
    route: '/dashboard/wire', group: 'modules', availability: 'available', publicPrimary: false,
    publicSummary: 'Read supported forum activity through the Toolbox interface.',
    visualizationMode: 'posting', operatorOnly: false, previewComponent: 'posting',
    prefetch: () => import('../core/WirePage.jsx'),
  },
  {
    id: 'casino', label: 'Byte Casino', shortLabel: 'CASINO', command: 'casino',
    aliases: ['casino', 'poker', 'blackjack', 'baccarat', 'roulette'], route: null, group: 'future',
    availability: 'coming-soon', publicPrimary: true,
    publicSummary: 'Play multiplayer poker, blackjack, baccarat, and roulette using Bytes.',
    visualizationMode: 'casino', operatorOnly: false, previewComponent: 'casino', prefetch: null,
  },
  {
    id: 'operator', label: 'Operator', shortLabel: 'OPS', command: 'operator', aliases: ['operator', 'ops'],
    route: '/dashboard/operator', group: 'system', availability: 'available', publicPrimary: false,
    publicSummary: 'Owner-only service health and operational visibility.',
    visualizationMode: 'home', operatorOnly: true, previewComponent: null,
    prefetch: () => import('../core/OperatorPage.jsx'),
  },
  {
    id: 'settings', label: 'Settings', shortLabel: 'SETTINGS', command: 'settings', aliases: ['settings', 'config'],
    route: '/dashboard/settings', group: 'system', availability: 'available', publicPrimary: false,
    publicSummary: 'Account preferences and Toolbox behavior.',
    visualizationMode: 'home', operatorOnly: false, previewComponent: null,
    prefetch: () => import('../core/Settings.jsx'),
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

export function prefetchProgram(program) {
  if (program?.prefetch) program.prefetch().catch(() => {})
}
