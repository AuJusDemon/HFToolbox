import { expect, test } from '@playwright/test'

const now = Math.floor(Date.now() / 1000)

async function mockPosting(page, threadRequests = []) {
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
      '/api/posting/drafts': { drafts:[{
        id:7, fid:'2', forum_name:'Site News', subject:'Saved release', message:'Saved body',
        reply1:'', reply2:'', version:1, updated_at:now, is_owner:true, collab_count:0,
      }] },
      '/api/posting/drafts/shared': { drafts:[] },
      '/api/posting/drafts/7/collaborators': { collaborators:[] },
      '/api/posting/queue': { queue:[{
        id:12, fid:'2', forum_name:'Site News', subject:'Failed release', message:'Retry body',
        status:'failed', error:'Temporary failure', fire_at:now - 60,
      }] },
      '/api/posting/sent': { sent:[] },
      '/api/autobump/settings': { hf_fee:100, hf_fee_tier:'L33t', service_fee:10, total_cost:110 },
    }
    if (route.request().method() === 'POST' && url.pathname === '/api/posting/thread') {
      threadRequests.push(route.request().postDataJSON())
      return route.fulfill({ json:{ ok:true, id:9, scheduled:false, fire_at:now, message:'Thread queued' } })
    }
    if (fixtures[url.pathname]) return route.fulfill({ json:fixtures[url.pathname] })
    if (url.pathname.startsWith('/api/')) return route.fulfill({ json:{} })
    return route.continue()
  })
}

test('draft editor keeps preview beside current content and confirms before publishing', async ({ page }) => {
  await page.setViewportSize({ width:1440, height:900 })
  const threadRequests = []
  await mockPosting(page, threadRequests)
  await page.goto('/dashboard/posting')
  await page.getByRole('button', { name:'Drafts', exact:true }).click()
  await page.getByRole('button', { name:'Edit', exact:true }).click()

  const workspace = page.locator('.posting-workspace').last()
  const editor = workspace.locator('.bb-ta')
  const editorBox = await editor.boundingBox()
  const previewBox = await workspace.locator('.post-preview').boundingBox()
  expect(editorBox.x).toBeLessThan(previewBox.x)
  await editor.fill('Current unsaved body')

  await page.getByRole('button', { name:'Post now', exact:true }).click()
  await expect(page.getByRole('region', { name:'Review draft publication' })).toBeVisible()
  expect(threadRequests).toHaveLength(0)
  await page.getByRole('button', { name:'Confirm and post', exact:true }).click()
  await expect.poll(() => threadRequests.length).toBe(1)
  expect(threadRequests[0].message).toBe('Current unsaved body')
  expect(threadRequests[0].subject).toBe('Saved release')
})

test('draft editor stacks its preview on mobile without controls or horizontal overflow', async ({ page }) => {
  await page.setViewportSize({ width:390, height:844 })
  await mockPosting(page)
  await page.goto('/dashboard/posting')
  await page.getByRole('button', { name:'Drafts', exact:true }).click()
  await page.getByRole('button', { name:'Edit', exact:true }).click()
  const workspace = page.locator('.posting-workspace').last()
  const editorBox = await workspace.locator('.bb-ta').boundingBox()
  const previewBox = await workspace.locator('.post-preview').boundingBox()
  expect(editorBox).not.toBeNull()
  expect(previewBox.y).toBeGreaterThan(editorBox.y + editorBox.height)
  await expect(page.getByText('Editor + preview', { exact:true })).toBeVisible()
  await expect(page.getByRole('tablist', { name:'Draft editor view' })).toHaveCount(0)
  await page.screenshot({ path:'test-results/posting-draft-mobile-stacked.png', fullPage:true })
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true)
})

test('draft scheduling requires review before creating the scheduled post', async ({ page }) => {
  const threadRequests = []
  await mockPosting(page, threadRequests)
  await page.goto('/dashboard/posting')
  await page.getByRole('button', { name:'Drafts', exact:true }).click()
  await page.getByRole('button', { name:'Schedule', exact:true }).click()
  await page.getByRole('button', { name:/Review schedule/ }).click()
  await expect(page.getByRole('region', { name:'Review draft publication' })).toBeVisible()
  expect(threadRequests).toHaveLength(0)
  await page.getByRole('button', { name:'Confirm schedule', exact:true }).click()
  await expect.poll(() => threadRequests.length).toBe(1)
  expect(threadRequests[0].fire_at).toBeGreaterThan(now)
})

test('failed scheduled posts require confirmation before retry', async ({ page }) => {
  const retryRequests = []
  page.on('request', request => {
    if (request.method() === 'POST' && request.url().includes('/api/posting/queue/12/retry')) retryRequests.push(request)
  })
  await mockPosting(page)
  await page.goto('/dashboard/posting')
  await page.getByRole('button', { name:'Scheduled', exact:true }).click()
  await page.getByRole('button', { name:'Retry now', exact:true }).click()
  await expect(page.getByText('Send this failed thread again?')).toBeVisible()
  expect(retryRequests).toHaveLength(0)
  await page.getByRole('button', { name:'Confirm retry', exact:true }).click()
  await expect.poll(() => retryRequests.length).toBe(1)
})

test('thread editor keeps preview to the right and reviews before queueing', async ({ page }) => {
  await page.setViewportSize({ width:1440, height:900 })
  const threadRequests = []
  await mockPosting(page, threadRequests)
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
  await expect(page.getByLabel('Schedule type')).toBeVisible()
  await page.getByLabel('Schedule type').selectOption('calendar')
  await page.getByRole('button', { name:'Add calendar slot' }).click()
  await expect(page.getByText('A confirmed bump uses 100 Bytes')).toBeVisible()
  await page.getByRole('button', { name:'Review Thread' }).click()
  await expect(page.getByText('Queue this thread')).toBeVisible()
  await expect(page.getByText('Calendar Scheduling, 12 hours minimum inactivity', { exact:true })).toBeVisible()
  await page.screenshot({ path:'test-results/posting-desktop.png', fullPage:true })
  await page.getByRole('button', { name:'Confirm Post', exact:true }).click()
  await expect.poll(() => threadRequests.length).toBe(1)
  expect(threadRequests[0].bump_schedule).toMatchObject({
    mode:'calendar',
    interval_h:12,
    end_mode:'unlimited',
    calendar_slots:[{ day:0, time:'10:00' }],
  })
  expect(threadRequests[0].bump_schedule.timezone).toBeTruthy()
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
      const workspace = page.locator('.posting-workspace').first()
      const editorBox = await workspace.locator('.bb-ta').boundingBox()
      const previewBox = await workspace.locator('.post-preview').boundingBox()
      expect(previewBox.y).toBeGreaterThan(editorBox.y + editorBox.height)
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true)
    await page.screenshot({ path:`test-results/posting-${viewport.name}.png`, fullPage:true })
  })
}
