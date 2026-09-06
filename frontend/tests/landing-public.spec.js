import { expect, test } from '@playwright/test'

const VIEWPORTS = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'laptop', width: 1024, height: 768 },
  { name: 'tablet', width: 768, height: 1024 },
  { name: 'mobile', width: 390, height: 844 },
  { name: 'mobile-small', width: 360, height: 800 },
]

async function waitForBoot(page) {
  await expect(page.locator('.hero-instrument')).toHaveAttribute('data-boot-phase', 'ready', { timeout: 3000 })
  await expect(page.getByLabel('Terminal command')).toBeEnabled()
}

async function runCommand(page, command) {
  const input = page.getByLabel('Terminal command')
  await input.fill(command)
  await input.press('Enter')
}

for (const viewport of VIEWPORTS) {
  test(`${viewport.name} hero boots, accepts commands, and remains width-contained`, async ({ page }) => {
    await page.setViewportSize(viewport)
    await page.goto('/landing-mock')
    const hero = page.locator('.hero-instrument')
    const before = await hero.boundingBox()
    await waitForBoot(page)
    const after = await hero.boundingBox()

    expect(Math.abs((before?.height || 0) - (after?.height || 0))).toBeLessThanOrEqual(1)
    await expect(page.getByRole('heading', { name: 'HF Toolbox' })).toBeVisible()
    await expect(page.locator('.hero-program-grid button')).toHaveCount(7)
    await hero.screenshot({ path: `test-results/${viewport.name}-hero.png` })

    await runCommand(page, 'help')
    await runCommand(page, 'programs')
    await runCommand(page, 'about casino')
    await runCommand(page, 'not-a-command')
    const log = page.getByRole('log')
    await expect(log).toContainText('Example: about bumps')
    await expect(log).toContainText("Texas Hold'em")
    await expect(log).toContainText('command not found: not-a-command')

    const dimensions = await page.evaluate(() => ({
      bodyWidth: document.body.scrollWidth,
      viewportWidth: window.innerWidth,
      bodyHeight: document.body.scrollHeight,
      viewportHeight: window.innerHeight,
      clippedPrograms: [...document.querySelectorAll('.hero-program-grid button')].filter(element => element.scrollWidth > element.clientWidth + 1).length,
      heroBottom: document.querySelector('.hero-instrument').getBoundingClientRect().bottom,
      lastProgramBottom: [...document.querySelectorAll('.hero-program-grid button')].at(-1).getBoundingClientRect().bottom,
      heroFooterBottom: document.querySelector('.hero-instrument-foot').getBoundingClientRect().bottom,
      directoryTop: document.querySelector('#modules .lp-kicker').getBoundingClientRect().top,
    }))
    expect(dimensions.bodyWidth).toBeLessThanOrEqual(dimensions.viewportWidth)
    expect(dimensions.bodyHeight).toBeGreaterThan(dimensions.viewportHeight)
    expect(dimensions.clippedPrograms).toBe(0)
    expect(dimensions.lastProgramBottom).toBeLessThanOrEqual(dimensions.heroBottom + 1)
    expect(dimensions.heroFooterBottom).toBeLessThanOrEqual(dimensions.heroBottom + 1)
    if (viewport.name === 'desktop') expect(dimensions.directoryTop).toBeLessThan(viewport.height)

    await page.locator('#modules').scrollIntoViewIfNeeded()
    await expect(page.getByRole('heading', { name: 'The work is already separated for you.' })).toBeVisible()
    await page.screenshot({ path: `test-results/${viewport.name}.png`, fullPage: true })
  })
}

test('boot can be skipped without changing hero dimensions', async ({ page }) => {
  await page.goto('/landing-mock')
  const hero = page.locator('.hero-instrument')
  const before = await hero.boundingBox()
  await page.keyboard.press('Escape')
  await expect(hero).toHaveAttribute('data-boot-phase', 'ready')
  const after = await hero.boundingBox()
  expect(Math.abs((before?.height || 0) - (after?.height || 0))).toBeLessThanOrEqual(1)
})

test('reduced motion renders the completed instrument immediately', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' })
  await page.goto('/landing-mock')
  await expect(page.locator('.hero-instrument')).toHaveAttribute('data-boot-phase', 'ready')
  await expect(page.getByLabel('Terminal command')).toBeEnabled()
  await expect(page.locator('.hero-program-grid button').first()).toBeVisible()
  await expect(page.locator('.hero-signal-raster')).toHaveAttribute('data-motion', 'still')
})

test('program click types the command and completes the route transfer before navigation', async ({ page }) => {
  await page.route('**/auth/login**', route => route.fulfill({ status: 200, body: 'redirect captured' }))
  await page.goto('/landing-mock')
  await waitForBoot(page)

  const input = page.getByLabel('Terminal command')
  const requestPromise = page.waitForRequest(request => request.url().includes('/auth/login'))
  await page.locator('.hero-program-grid').getByRole('button', { name: /Marketplace/ }).click()
  await expect(input).not.toHaveValue('', { timeout: 500 })
  await expect(input).toHaveValue('open market', { timeout: 1000 })
  await expect(page.getByRole('log')).toContainText('Route selected: /dashboard/market')
  await expect(page.locator('.hero-route-transition')).toHaveClass(/state-transfer/)
  await page.screenshot({ path: 'test-results/route-transfer.png' })
  await expect.poll(() => page.url()).toContain('/landing-mock')
  await expect(requestPromise).resolves.toBeTruthy()
})

test('signal raster draws nonblank pixels and continues changing after boot', async ({ page }) => {
  await page.goto('/landing-mock')
  await waitForBoot(page)
  const canvas = page.locator('.hero-signal-raster')
  await expect(canvas).toHaveAttribute('data-motion', 'running')

  const sample = () => canvas.evaluate(element => {
    const context = element.getContext('2d')
    const width = Math.min(element.width, 240)
    const height = Math.min(element.height, 180)
    const data = context.getImageData(0, 0, width, height).data
    let sum = 0
    for (let index = 3; index < data.length; index += 4) sum += data[index]
    return sum
  })
  const first = await sample()
  await page.waitForTimeout(180)
  const second = await sample()
  expect(first).toBeGreaterThan(0)
  expect(second).toBeGreaterThan(0)
  expect(second).not.toBe(first)
})

test('mobile route transfer remains contained inside the instrument', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.route('**/auth/login**', route => route.fulfill({ status: 200, body: 'redirect captured' }))
  await page.goto('/landing-mock')
  await page.keyboard.press('Escape')
  const requestPromise = page.waitForRequest(request => request.url().includes('/auth/login'))
  await page.locator('.hero-program-grid').getByRole('button', { name: /Bytes OPEN BYTES/ }).click()
  await expect(page.locator('.hero-route-transition')).toHaveClass(/state-transfer/)
  const bounds = await page.locator('.hero-route-transition').boundingBox()
  expect(bounds?.x).toBeGreaterThanOrEqual(0)
  expect((bounds?.x || 0) + (bounds?.width || 0)).toBeLessThanOrEqual(390)
  await page.screenshot({ path: 'test-results/mobile-route-transfer.png' })
  await expect(requestPromise).resolves.toBeTruthy()
})

test('keyboard history, completion, escape, and clear work in the browser', async ({ page }) => {
  await page.goto('/landing-mock')
  await waitForBoot(page)
  const input = page.getByLabel('Terminal command')
  await runCommand(page, 'help')
  await runCommand(page, 'programs')
  await input.press('ArrowUp')
  await expect(input).toHaveValue('programs')
  await input.press('ArrowUp')
  await expect(input).toHaveValue('help')
  await input.press('ArrowDown')
  await expect(input).toHaveValue('programs')
  await input.fill('about poke')
  await input.press('Tab')
  await expect(input).toHaveValue('about poker')
  await input.press('Escape')
  await expect(input).toHaveValue('')
  await input.press('Control+l')
  await expect(page.getByRole('log')).toContainText('HF.TOOLBOX public interface')
  await expect(page.getByRole('log')).not.toContainText('business')
})

test('every Program Bus entry follows its registry behavior', async ({ page }) => {
  const destinations = [
    ['My Business', '/dashboard/merchant'], ['Bump Service', '/dashboard/bumper'],
    ['Posting', '/dashboard/posting'], ['Contracts', '/dashboard/contracts'],
    ['Marketplace', '/dashboard/market'], ['Bytes', '/dashboard/bytes'],
  ]
  await page.route('**/auth/login**', route => route.fulfill({ status: 200, body: 'redirect captured' }))

  for (const [label, route] of destinations) {
    await page.goto('/landing-mock')
    await page.keyboard.press('Escape')
    const requestPromise = page.waitForRequest(request => request.url().includes('/auth/login'))
    await page.locator('.hero-program-grid').getByRole('button', { name: new RegExp(label) }).click()
    const request = await requestPromise
    expect(request.url()).toContain(`next=${encodeURIComponent(route)}`)
  }

  await page.goto('/landing-mock')
  await page.keyboard.press('Escape')
  await page.locator('.hero-program-grid').getByRole('button', { name: /Byte Casino/ }).click()
  await expect(page).toHaveURL(/\/landing-mock$/)
  await expect(page.getByRole('log')).toContainText('Byte Casino is coming soon.')
})

test('terminal open command preserves the selected internal OAuth route', async ({ page }) => {
  await page.route('**/auth/login**', route => route.fulfill({ status: 200, body: 'redirect captured' }))
  await page.goto('/landing-mock?next=//example.invalid')
  await waitForBoot(page)
  const requestPromise = page.waitForRequest(request => request.url().includes('/auth/login'))
  await runCommand(page, 'open market')
  const request = await requestPromise
  expect(request.url()).toContain('next=%2Fdashboard%2Fmarket')
  expect(request.url()).not.toContain('example.invalid')
})

test('authenticated Program Bus entry navigates directly to its dashboard route', async ({ page }) => {
  await page.route('**/auth/me', route => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ uid: '761578', username: 'PreviewUser', groups: [] }) }))
  await page.goto('/landing-mock')
  await page.keyboard.press('Escape')
  await page.locator('.hero-program-grid').getByRole('button', { name: /Bump Service/ }).click()
  await expect(page).toHaveURL(/\/dashboard\/bumper$/)
})

test('OAuth errors appear inside the terminal with their reference', async ({ page }) => {
  await page.goto('/landing-mock?auth_error=cancelled&auth_ref=test-ref-123')
  await page.keyboard.press('Escape')
  await expect(page.getByRole('log')).toContainText('Authorization was cancelled. No changes were made.')
  await expect(page.getByRole('log')).toContainText('Reference: test-ref-123')
})

test('mobile prompt remains visible when focused and normal landing sections remain present', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/landing-mock')
  await page.keyboard.press('Escape')
  const input = page.getByLabel('Terminal command')
  await input.focus()
  const prompt = await page.locator('.hero-terminal-prompt').boundingBox()
  expect(prompt?.x).toBeGreaterThanOrEqual(0)
  expect((prompt?.x || 0) + (prompt?.width || 0)).toBeLessThanOrEqual(390)
  await expect(page.getByRole('heading', { name: 'Know what the scheduler is doing.' })).toBeAttached()
  await expect(page.getByRole('heading', { name: 'Byte Casino' })).toBeAttached()
  await expect(page.getByRole('heading', { name: "Texas Hold'em" })).toBeAttached()
  await expect(page.getByRole('heading', { name: 'Blackjack' })).toBeAttached()
  await expect(page.getByRole('heading', { name: 'Baccarat' })).toBeAttached()
  await expect(page.getByRole('heading', { name: 'Roulette' })).toBeAttached()
  await expect(page.getByRole('tab')).toHaveCount(0)
})
