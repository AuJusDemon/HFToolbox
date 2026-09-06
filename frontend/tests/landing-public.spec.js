import { expect, test } from '@playwright/test'

const VIEWPORTS = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'laptop', width: 1024, height: 768 },
  { name: 'tablet', width: 768, height: 1024 },
  { name: 'mobile', width: 390, height: 844 },
  { name: 'mobile-small', width: 360, height: 800 },
]

for (const viewport of VIEWPORTS) {
  test(`${viewport.name} layout remains width-contained and renders the terminal directory`, async ({ page }) => {
    await page.setViewportSize(viewport)
    await page.goto('/landing-mock')
    await expect(page.getByRole('heading', { name: 'HF Toolbox' })).toBeVisible()
    await expect(page.locator('.lp-terminal')).toBeVisible()
    await expect(page.locator('.lp-terminal-programs > div')).toHaveCount(6)

    const layout = await page.evaluate(() => ({
      bodyWidth: document.body.scrollWidth,
      viewportWidth: window.innerWidth,
      bodyHeight: document.body.scrollHeight,
      viewportHeight: window.innerHeight,
    }))
    expect(layout.bodyWidth).toBeLessThanOrEqual(layout.viewportWidth)
    expect(layout.bodyHeight).toBeGreaterThan(layout.viewportHeight)

    await page.screenshot({ path: `test-results/${viewport.name}.png`, fullPage: true })
  })
}

test('all program information is available on one page without tabs', async ({ page }) => {
  await page.goto('/landing-mock')
  await expect(page.getByRole('heading', { name: 'The work is already separated for you.' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Know what the scheduler is doing.' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Byte Casino' })).toBeVisible()
  await expect(page.getByRole('heading', { name: "Texas Hold'em" })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Blackjack' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Baccarat' })).toBeVisible()
  await expect(page.getByRole('heading', { name: 'Roulette' })).toBeVisible()
  await expect(page.getByRole('tab')).toHaveCount(0)
})

test('mobile exposes the program directory in the normal page flow', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/landing-mock')
  await page.getByRole('heading', { name: 'The work is already separated for you.' }).scrollIntoViewIfNeeded()
  await expect(page.getByRole('button', { name: /Marketplace/ })).toBeVisible()
  await page.screenshot({ path: 'test-results/program-market-mobile.png', fullPage: true })
})

test('guest OAuth carries only the selected internal program route', async ({ page }) => {
  await page.route('**/auth/login**', route => route.fulfill({ status: 200, body: 'redirect captured' }))
  await page.goto('/landing-mock?next=//example.invalid')
  const requestPromise = page.waitForRequest(request => request.url().includes('/auth/login'))
  await page.getByRole('button', { name: /Marketplace/ }).click()
  const request = await requestPromise
  expect(request.url()).toContain('next=%2Fdashboard%2Fmarket')
  expect(request.url()).not.toContain('example.invalid')
})

test('authenticated program entry navigates directly to its dashboard route', async ({ page }) => {
  await page.route('**/auth/me', route => route.fulfill({
    status: 200,
    contentType: 'application/json',
    body: JSON.stringify({ uid: '761578', username: 'PreviewUser', groups: [] }),
  }))
  await page.goto('/landing-mock')
  await page.getByRole('button', { name: /Bump Service/ }).first().click()
  await expect(page).toHaveURL(/\/dashboard\/bumper$/)
})
