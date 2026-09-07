import { expect, test } from '@playwright/test'

const ts = Math.floor(Date.now() / 1000)
const fixtures = {
  '/auth/me': { uid:'761578', username:'Au Jus Demon', avatar:'', groups:['78'], is_operator:true },
  '/api/modules': { modules:[] },
  '/api/prefs': { prefs:{} },
  '/api/settings': { settings:{ apiFloorEnabled:true, apiFloor:30 } },
  '/api/shell-data': { profile:{ groups:['78'], displaygroup:'78', myps:'55739.81' }, reply_count:2, notifications:[], unseen:0, token_expiry:ts + 864000 },
  '/api/rate-limit': { remaining:211, stale:false, hf_api:{ available:true }, throttle:'normal' },
  '/api/dashboard/snapshot': { profile:{ myps:'55739.81' }, reply_count:2, rate_remaining:211, bytes:{ balance:'55739.81', transactions:[{ id:'1', amount:'10', sent:false, reason:'Contract', dateline:ts - 300 }] }, contracts:{ counts:{ active:1, awaiting:1, disputed:0 }, contracts:[] } },
  '/api/merchant/overview': { action_queue:[{ type:'sla_breach', count:1, label:'1 late reply', severity:'high' },{ type:'awaiting_approval', count:1, label:'1 contract awaiting approval', severity:'high' }], today:{ active_contracts:1 }, pipeline:{ total:2, sla_breaches:1 }, contract_stage_counts:{ needs_review:1 }, threads_needing_attention:1, thread_health:[{ tid:'1', title:'Spotify Premium Family Plan', unread_replies:2, contracts_active:1, health:'needs_attention' }], recent_contracts:[{ cid:'413649', product:'Spotify Premium', stage:'active', dateline:ts - 3600 }] },
  '/api/autobump/jobs': { jobs:[{ id:1, tid:'6319077', thread_title:'Spotify Premium Family Plan', enabled:true, expired:false, next_bump:ts + 3600, seconds_until_bump:3600, bump_count:12, last_bumped:ts - 86400 }] },
  '/api/posting/queue': { queue:[] },
}

async function mockApp(page, owner = true) {
  await page.route('**/*', async route => {
    const url = new URL(route.request().url())
    if (url.hostname === 'fonts.googleapis.com' || url.hostname === 'fonts.gstatic.com') return route.abort()
    if (url.pathname === '/auth/me' && !owner) return route.fulfill({ json:{ ...fixtures['/auth/me'], uid:'42', is_operator:false } })
    const body = fixtures[url.pathname]
    if (body) return route.fulfill({ json:body })
    return route.continue()
  })
}

for (const viewport of [
  { name:'desktop', width:1440, height:900 }, { name:'tablet-wide', width:1024, height:768 },
  { name:'tablet', width:768, height:1024 }, { name:'mobile', width:390, height:844 }, { name:'mobile-small', width:360, height:800 },
]) {
  test(`authenticated overview layout at ${viewport.name}`, async ({ page }) => {
    await page.setViewportSize(viewport)
    await mockApp(page)
    await page.goto('/dashboard')
    await expect(page.getByRole('heading', { name:'Overview' })).toBeVisible()
    await expect(page.getByText('Work Queue')).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true)
    await page.screenshot({ path:`test-results/auth-${viewport.name}.png`, fullPage:true })
  })
}

test('desktop collapse persists and launcher resolves aliases', async ({ page }) => {
  await page.setViewportSize({ width:1440, height:900 })
  await mockApp(page)
  await page.goto('/dashboard')
  await page.getByRole('button', { name:'Collapse sidebar' }).click()
  await expect(page.locator('.shell')).toHaveClass(/nav-collapsed/)
  expect(await page.evaluate(() => localStorage.getItem('hftb_nav_collapsed'))).toBe('1')
  await page.keyboard.press('Control+K')
  await page.getByLabel('Open program').fill('bumps')
  await expect(page.getByRole('option')).toContainText('Bump Service')
  await page.screenshot({ path:'test-results/auth-launcher.png' })
  await page.keyboard.press('Enter')
  await expect(page).toHaveURL(/\/dashboard\/bumper/)
})

test('mobile drawer traps navigation and excludes Operator for non-owner', async ({ page }) => {
  await page.setViewportSize({ width:390, height:844 })
  await mockApp(page, false)
  await page.goto('/dashboard')
  await page.getByRole('button', { name:'Open navigation' }).click()
  await expect(page.getByRole('dialog', { name:'Program navigation' })).toBeVisible()
  await expect(page.getByRole('button', { name:/Operator/i })).toHaveCount(0)
  await page.screenshot({ path:'test-results/auth-mobile-drawer.png' })
  await page.keyboard.press('Escape')
  await expect(page.getByRole('dialog', { name:'Program navigation' })).toHaveCount(0)
})

test('reduced motion disables route transfer animation', async ({ page }) => {
  await page.emulateMedia({ reducedMotion:'reduce' })
  await mockApp(page)
  await page.goto('/dashboard')
  await expect(page.locator('.route-transfer')).toHaveCSS('display', 'none')
})

test('revisiting a program reuses its prefetched data without another request', async ({ page }) => {
  let merchantRequests = 0
  page.on('request', request => {
    if (new URL(request.url()).pathname === '/api/merchant/overview') merchantRequests += 1
  })
  await mockApp(page)
  await page.goto('/dashboard')
  await expect(page.getByRole('heading', { name:'Overview' })).toBeVisible()

  await page.getByRole('button', { name:'My Business', exact:true }).click()
  await expect(page.getByRole('heading', { name:'Today in My Business' })).toBeVisible()
  const requestsAfterFirstVisit = merchantRequests
  await page.getByRole('button', { name:'Overview', exact:true }).click()
  await page.getByRole('button', { name:'My Business', exact:true }).click()
  await expect(page.getByRole('heading', { name:'Today in My Business' })).toBeVisible()

  expect(merchantRequests).toBe(requestsAfterFirstVisit)
})
