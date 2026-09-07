import { expect, test } from '@playwright/test'

const now = Math.floor(Date.now() / 1000)

async function mockPosting(page) {
  await page.route('**/*', async route => {
    const url = new URL(route.request().url())
    if (url.hostname !== '127.0.0.1') return route.abort()
    const fixtures = {
      '/auth/me': { uid:'42', username:'tester', avatar:'', groups:['9'], is_operator:false },
      '/api/modules': { modules:[] },
      '/api/prefs': { prefs:{} },
      '/api/settings': { settings:{ postingFooter:false } },
      '/api/shell-data': { profile:{ groups:['9'] }, reply_count:0, notifications:[], unseen:0, token_expiry:now + 86400 },
      '/api/rate-limit': { remaining:200, stale:false, throttle:'normal' },
      '/api/posting/recents': { recents:[{ fid:'2', forum_name:'Site News', category_name:'Hack' }] },
      '/api/posting/replies/count': { count:0 },
      '/api/posting/threads': { threads:[{ tid:'123', title:'Owned thread', closed:0 }] },
      '/api/autobump/settings': { hf_fee:100, hf_fee_tier:'L33t', service_fee:10, total_cost:110 },
    }
    if (route.request().method() === 'POST' && url.pathname === '/api/posting/thread') {
      return route.fulfill({ json:{ ok:true, id:9, scheduled:false, fire_at:now, message:'Thread queued' } })
    }
    if (fixtures[url.pathname]) return route.fulfill({ json:fixtures[url.pathname] })
    if (url.pathname.startsWith('/api/')) return route.fulfill({ json:{} })
    return route.continue()
  })
}

test('thread editor keeps preview to the right and reviews before queueing', async ({ page }) => {
  await page.setViewportSize({ width:1440, height:900 })
  await mockPosting(page)
  await page.goto('/dashboard/posting')
  await page.getByRole('button', { name:'Site News' }).click()
  await page.getByPlaceholder('Thread title…').fill('Release notes')
  const editor = page.locator('.bb-ta').first()
  await editor.fill('selected words')
  const workspace = page.locator('.posting-workspace').first()
  const editorBox = await workspace.locator('.bb-ta').boundingBox()
  const previewBox = await workspace.locator('.post-preview').boundingBox()
  expect(editorBox.x).toBeLessThan(previewBox.x)
  const divider = page.getByRole('separator', { name:'Resize editor and preview' }).first()
  await expect(divider).toBeVisible()
  const initialSplit = await divider.getAttribute('aria-valuenow')
  await divider.focus()
  await page.keyboard.press('ArrowRight')
  expect(Number(await divider.getAttribute('aria-valuenow'))).toBeGreaterThan(Number(initialSplit))

  await editor.evaluate(node => { node.focus(); node.setSelectionRange(0, 8); node.dispatchEvent(new Event('select', { bubbles:true })) })
  await page.getByRole('button', { name:'URL', exact:true }).click()
  await expect(page.getByText('Link text', { exact:true })).toBeVisible()
  await expect(page.getByLabel('Link text')).toHaveValue('selected')
  await page.getByLabel('URL').fill('https://example.com/release')
  await page.getByRole('button', { name:'Insert' }).click()
  await expect(editor).toHaveValue('[url=https://example.com/release]selected[/url] words')

  await page.getByText('Add to Bump Service', { exact:true }).click()
  await expect(page.getByLabel('Mode')).toBeVisible()
  await page.getByLabel('Mode').selectOption('page1')
  await expect(page.getByText('A confirmed bump uses 100 Bytes')).toBeVisible()
  await page.getByRole('button', { name:'Review Thread' }).click()
  await expect(page.getByText('Queue this thread')).toBeVisible()
  await expect(page.getByText('Page 1 watch, 12 hours', { exact:true })).toBeVisible()
  await page.screenshot({ path:'test-results/posting-desktop.png', fullPage:true })
})

for (const viewport of [
  { name:'tablet-wide', width:1024, height:768 },
  { name:'tablet', width:768, height:1024 },
  { name:'mobile', width:390, height:844 },
  { name:'mobile-small', width:360, height:800 },
]) {
  test(`posting editor remains usable at ${viewport.name}`, async ({ page }) => {
    await page.setViewportSize(viewport)
    await mockPosting(page)
    await page.goto('/dashboard/posting')
    if (viewport.width <= 720) {
      await expect(page.getByRole('button', { name:'Preview', exact:true }).first()).toBeVisible()
      await page.getByRole('button', { name:'Preview', exact:true }).first().click()
      await expect(page.locator('.posting-workspace').first().locator('.post-preview')).toBeVisible()
      await expect(page.locator('.posting-workspace').first().locator('.bb-ta')).not.toBeVisible()
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true)
    await page.screenshot({ path:`test-results/posting-${viewport.name}.png`, fullPage:true })
  })
}
