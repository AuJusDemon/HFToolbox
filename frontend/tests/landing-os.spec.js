import { expect, test } from '@playwright/test'

const VIEWPORTS = [
  { name: 'desktop', width: 1440, height: 900 },
  { name: 'laptop', width: 1024, height: 768 },
  { name: 'tablet', width: 768, height: 1024 },
  { name: 'mobile', width: 390, height: 844 },
  { name: 'mobile-small', width: 360, height: 800 },
]

for (const viewport of VIEWPORTS) {
  test(`${viewport.name} layout remains contained and renders ASCII output`, async ({ page }) => {
    await page.setViewportSize(viewport)
    await page.goto('/landing-mock')
    await expect(page.getByRole('status', { name: 'HF Toolbox starting' })).toBeVisible()
    await page.keyboard.press('Escape')
    await expect(page.getByRole('heading', { name: 'HF Toolbox' })).toBeVisible()
    await expect(page.locator('.os-ascii-canvas')).toBeVisible()
    await page.waitForTimeout(150)

    const layout = await page.evaluate(() => ({
      bodyWidth: document.body.scrollWidth,
      viewportWidth: window.innerWidth,
      bodyHeight: document.body.scrollHeight,
      viewportHeight: window.innerHeight,
    }))
    expect(layout.bodyWidth).toBeLessThanOrEqual(layout.viewportWidth)
    expect(layout.bodyHeight).toBeLessThanOrEqual(layout.viewportHeight)

    const paintedPixels = await page.locator('.os-ascii-canvas').evaluate(canvas => {
      const context = canvas.getContext('2d')
      const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data
      let nonBlack = 0
      for (let index = 0; index < pixels.length; index += 64) {
        if (pixels[index] > 8 || pixels[index + 1] > 8 || pixels[index + 2] > 8) nonBlack += 1
      }
      return nonBlack
    })
    expect(paintedPixels).toBeGreaterThan(20)
    await page.screenshot({ path: `test-results/${viewport.name}.png`, fullPage: true })
  })
}

test('program clicks and commands share the active program state', async ({ page }) => {
  await page.goto('/landing-mock')
  await page.keyboard.press('Escape')
  await page.getByLabel('Toolbox programs').getByRole('button', { name: /Bump Service/ }).click()
  await expect(page.getByRole('heading', { name: 'Bump Service' })).toBeVisible()
  await page.screenshot({ path: 'test-results/program-bumps.png', fullPage: true })

  const command = page.getByLabel('Toolbox command')
  await command.fill('open casino')
  await command.press('Enter')
  await expect(page.getByRole('heading', { name: 'Byte Casino' })).toBeVisible()
  await expect(page.getByRole('button', { name: 'NOT YET AVAILABLE' })).toBeDisabled()
})

test('mobile program drawer opens and selects a program', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await page.goto('/landing-mock')
  await page.keyboard.press('Escape')
  await page.getByRole('button', { name: 'PROGRAMS' }).click()
  await expect(page.getByLabel('Toolbox programs')).toHaveClass(/is-open/)
  await page.getByLabel('Toolbox programs').getByRole('button', { name: /Marketplace/ }).click()
  await expect(page.getByRole('heading', { name: 'Marketplace' })).toBeVisible()
  await page.screenshot({ path: 'test-results/program-market-mobile.png', fullPage: true })
  await expect(page.getByLabel('Toolbox programs')).not.toHaveClass(/is-open/)
})

test('guest OAuth carries only the selected internal program route', async ({ page }) => {
  await page.route('**/auth/login**', route => route.fulfill({ status: 200, body: 'redirect captured' }))
  await page.goto('/landing-mock?next=//example.invalid')
  await page.keyboard.press('Escape')
  await page.getByLabel('Toolbox programs').getByRole('button', { name: /Marketplace/ }).click()
  const requestPromise = page.waitForRequest(request => request.url().includes('/auth/login'))
  await page.getByRole('button', { name: 'AUTHENTICATE AND ENTER' }).click()
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
  await page.keyboard.press('Escape')
  await page.getByLabel('Toolbox programs').getByRole('button', { name: /Bump Service/ }).click()
  await page.getByRole('button', { name: 'ENTER PROGRAM' }).click()
  await expect(page).toHaveURL(/\/dashboard\/bumper$/)
})
