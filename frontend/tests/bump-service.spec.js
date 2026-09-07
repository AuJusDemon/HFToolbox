import { expect, test } from '@playwright/test'

const now = Math.floor(Date.now() / 1000)
const baseJobs = [
  { id:1, tid:'6319077', fid:'107', thread_title:'Spotify Premium Family Plan', mode:'timer', interval_h:12, enabled:true, expired:false, next_bump:now + 3600, seconds_until_bump:3600, last_bumped:now - 43200, lastpost_ts:now - 20000, lastposter:'Stanley', bump_count:18 },
  { id:2, tid:'6410000', fid:'107', thread_title:'Secondary sales thread', mode:'page1', interval_h:6, enabled:true, expired:false, next_bump:now + 900, seconds_until_bump:900, last_bumped:now - 86400, lastpost_ts:now - 5000, lastposter:'Buyer', bump_count:4 },
]
const attempt = { id:1, tid:'6319077', thread_title:'Spotify Premium Family Plan', action:'bumped', reason:'', ts:now - 43200 }
const fees = { weekly_budget:1000, bytes_this_week:220, remaining_budget:780, bumps_this_week:2, hf_fee:100, service_fee:10, total_cost:110 }
const stats = { total_bumps:18, total_skips:5, total_contracts:23, avg_reply_gain:1.4, bytes_spent:1980, hf_fee:100, service_fee:10, total_cost:110, bump_periods:[{ ts:now - 43200, next_ts:null, duration_s:43200, is_current:true, reply_gain:2, contracts:[{ cid:'413649', status_n:'6' }] }] }

async function mockBumper(page, state = 'populated') {
  await page.route('**/*', async route => {
    const url = new URL(route.request().url())
    if (url.hostname.includes('google')) return route.abort()
    if (url.pathname === '/auth/me') return route.fulfill({ json:{ uid:'42', username:'tester', avatar:'', groups:['9'], is_operator:false } })
    if (url.pathname === '/api/modules') return route.fulfill({ json:{ modules:[] } })
    if (url.pathname === '/api/prefs') return route.fulfill({ json:{ prefs:{} } })
    if (url.pathname === '/api/settings') return route.fulfill({ json:{ settings:{ bumperInterval:9999 } } })
    if (url.pathname === '/api/shell-data') return route.fulfill({ json:{ profile:{ groups:['9'] }, reply_count:0, notifications:[], unseen:0, token_expiry:now + 86400 } })
    if (url.pathname === '/api/rate-limit') return route.fulfill({ json:{ remaining:200, stale:false, throttle:'normal' } })
    if (url.pathname === '/api/autobump/jobs') {
      if (state === 'loading') { await new Promise(resolve => setTimeout(resolve, 1800)) }
      if (state === 'failure') return route.fulfill({ status:503, json:{ detail:'Scheduler unavailable' } })
      if (state === 'empty') return route.fulfill({ json:{ jobs:[] } })
      const jobs = structuredClone(baseJobs)
      if (state === 'paused') jobs[1].enabled = false
      if (state === 'due') { jobs[1].seconds_until_bump = 0; jobs[1].next_bump = now - 1 }
      return route.fulfill({ json:{ jobs } })
    }
    if (url.pathname === '/api/autobump/log') return route.fulfill({ json:{ log:[attempt] } })
    if (url.pathname === '/api/autobump/settings') return route.fulfill({ json:state === 'budget' ? { ...fees, weekly_budget:250, bytes_this_week:220, remaining_budget:30 } : fees })
    if (/\/api\/autobump\/jobs\/\d+\/stats/.test(url.pathname)) return route.fulfill({ json:stats })
    if (url.pathname.startsWith('/api/')) return route.fulfill({ json:{} })
    return route.continue()
  })
}

for (const viewport of [
  { name:'desktop', width:1440, height:900 },
  { name:'tablet-wide', width:1024, height:768 },
  { name:'tablet', width:768, height:1024 },
  { name:'mobile', width:390, height:844 },
  { name:'mobile-small', width:360, height:800 },
]) {
  test(`populated scheduler at ${viewport.name}`, async ({ page }) => {
    await page.setViewportSize(viewport)
    await mockBumper(page)
    await page.goto('/dashboard/bumper')
    await expect(page.getByRole('heading', { name:'Bump Service' })).toBeVisible()
    await expect(page.getByRole('heading', { name:'Secondary sales thread' })).toBeVisible()
    await expect(page.getByText('Successful bumps', { exact:true })).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true)
    await page.screenshot({ path:`test-results/bumper-${viewport.name}.png`, fullPage:true })
  })
}

for (const state of ['empty', 'failure', 'paused', 'due', 'budget']) {
  test(`${state} scheduler state`, async ({ page }) => {
    await page.setViewportSize({ width:1440, height:900 })
    await mockBumper(page, state)
    await page.goto('/dashboard/bumper')
    await expect(page.getByRole('heading', { name:'Bump Service' })).toBeVisible()
    if (state === 'empty') await expect(page.getByRole('heading', { name:'No bump jobs yet' })).toBeVisible()
    if (state === 'failure') await expect(page.getByText('Scheduler unavailable')).toBeVisible()
    if (state === 'paused') await expect(page.getByText('Paused').first()).toBeVisible()
    if (state === 'due') await expect(page.getByText('Checking').first()).toBeVisible()
    if (state === 'budget') await expect(page.getByText(/next successful bump would exceed/i)).toBeVisible()
    await page.screenshot({ path:`test-results/bumper-${state}.png`, fullPage:true })
  })
}

test('loading scheduler state', async ({ page }) => {
  await page.setViewportSize({ width:390, height:844 })
  await mockBumper(page, 'loading')
  await page.goto('/dashboard/bumper')
  await expect(page.getByLabel('Loading bump service')).toBeVisible()
  await page.screenshot({ path:'test-results/bumper-loading.png', fullPage:true })
})
