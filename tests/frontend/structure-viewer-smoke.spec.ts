import { expect, test } from '@playwright/test'

const baseUrl = process.env.STRUCTURE_VIEWER_BASE_URL ?? 'http://127.0.0.1:4173'
const mode = process.env.STRUCTURE_VIEWER_BROWSER_SMOKE_MODE ?? 'full'

test.setTimeout(90000)

async function openViewer(page, viewport) {
  await page.setViewportSize(viewport)
  const errors: string[] = []
  page.on('pageerror', (error) => errors.push(error.message))
  page.on('console', (message) => {
    if (message.type() === 'error') {
      errors.push(message.text())
    }
  })
  await page.goto(
    `${baseUrl}/src/structure-viewer/index.html?preset=real_drawing_private_3d&member=RD-001&drawing_asset=RD-001`,
    { timeout: 90000, waitUntil: 'commit' },
  )
  await page.locator('#viewport canvas').waitFor({ state: 'visible', timeout: 30000 })
  await expect(page.locator('#provenance-source-label')).not.toHaveText('--', { timeout: 30000 })
  await expect(page.locator('#real-drawing-quality-panel')).toContainText('RD-', { timeout: 30000 })
  await page.waitForFunction(() => {
    const canvas = document.querySelector('#viewport canvas') as HTMLCanvasElement | null
    return Boolean(canvas && canvas.width > 10 && canvas.height > 10)
  })
  expect(errors).toEqual([])
}

async function expectCanvasNonBlank(page) {
  const nonBlank = await page.locator('#viewport canvas').evaluate((canvas: HTMLCanvasElement) => {
    const probe = document.createElement('canvas')
    const width = Math.min(96, Math.max(1, canvas.width))
    const height = Math.min(96, Math.max(1, canvas.height))
    probe.width = width
    probe.height = height
    const context = probe.getContext('2d')
    if (!context) {
      return false
    }
    context.drawImage(canvas, 0, 0, width, height)
    const pixels = context.getImageData(0, 0, width, height).data
    let variedPixels = 0
    for (let index = 0; index < pixels.length; index += 4) {
      const red = pixels[index]
      const green = pixels[index + 1]
      const blue = pixels[index + 2]
      const alpha = pixels[index + 3]
      if (alpha > 0 && (red > 8 || green > 8 || blue > 8)) {
        variedPixels += 1
      }
      if (variedPixels > 24) {
        return true
      }
    }
    return false
  })
  expect(nonBlank).toBe(true)
}

test('structure viewer renders real drawing stage and supports core controls', async ({ page }) => {
  await openViewer(page, { width: 1440, height: 1000 })
  await expectCanvasNonBlank(page)

  await page.locator('#member-search-input').fill('RD-001')
  await expect(page.locator('#search-results')).toContainText('RD-001')
  await page.locator('#btn-solid').click()
  await expect(page.locator('#btn-solid')).toHaveClass(/active/)
  await page.getByRole('button', { name: 'Fit All' }).click()
  await page.getByRole('button', { name: 'Reset' }).click()
  await expect(page.locator('#stage-selection-chip')).toContainText('RD-001')
  await expect(page.locator('#footer-selection-context')).toContainText('selected')
})

test('structure viewer keeps the mobile real drawing workflow usable', async ({ page }) => {
  test.skip(mode === 'minimal', 'minimal smoke runs only the desktop browser path')
  await openViewer(page, { width: 390, height: 844 })
  await expectCanvasNonBlank(page)
  await expect(page.locator('#stage-panel')).toBeVisible()
  await expect(page.locator('#real-drawing-quality-panel')).toContainText('RD-')
  await page.locator('#btn-wireframe').click()
  await expect(page.locator('#btn-wireframe')).toHaveClass(/active/)
})
