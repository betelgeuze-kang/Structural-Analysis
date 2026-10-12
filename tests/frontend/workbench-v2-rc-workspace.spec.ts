import { expect, test } from '@playwright/test'

const baseUrl = process.env.WORKBENCH_V2_BASE_URL ?? 'http://127.0.0.1:4373'

test('configured RC workspace does not load or display an unrelated demo case', async ({ page }) => {
  const requests: string[] = []
  page.on('request', request => requests.push(request.url()))
  await page.addInitScript(() => {
    window.__STRUCTURAL_WORKBENCH_CONFIG__ = { rcJobCollectionUrl: '/v1/jobs' }
  })
  await page.goto(`${baseUrl}/#/workbench-v2`)
  await expect(page.getByRole('heading', { name: 'RC project', exact: true })).toBeVisible()
  await expect(page.locator('[data-rc-project-workspace]')).toBeVisible()
  await expect(page.getByRole('group', { name: 'Data provider' })).toHaveCount(0)
  await expect(page.locator('#wb2-sec-project, #wb2-sec-model, #wb2-sec-analysis, iframe')).toHaveCount(0)
  await expect(page.locator('[data-wb2-claim]')).toContainText('does not establish independent physical validation')
  await expect(page.locator('body')).not.toContainText('Converged (demo)')
  await expect(page.locator('body')).not.toContainText('demo/highrise')
  expect(requests.filter(url => /workbench-case\.json|index\.midas33|structure-viewer\/index/.test(url))).toEqual([])
})

test('ordinary workspace retains its demo and provider controls', async ({ page }) => {
  await page.goto(`${baseUrl}/#/workbench-v2`)
  await expect(page.getByRole('heading', { name: 'Workbench v2', exact: true })).toBeVisible()
  await expect(page.getByRole('group', { name: 'Data provider' })).toBeVisible()
  await expect(page.locator('[data-rc-project-workspace]')).toHaveCount(0)
  await expect(page.locator('#wb2-sec-project')).toContainText('demo/highrise')
})

test('an explicitly combined native and RC configuration keeps both work areas', async ({ page }) => {
  await page.addInitScript(() => {
    window.__STRUCTURAL_WORKBENCH_CONFIG__ = {
      rcJobCollectionUrl: '/v1/jobs', nativeFrameSubmissionUrl: '/native/jobs',
    }
  })
  await page.goto(`${baseUrl}/#/workbench-v2`)
  await expect(page.getByRole('heading', { name: 'Workbench v2', exact: true })).toBeVisible()
  await expect(page.locator('[data-rc-project-workspace]')).toHaveCount(0)
  await expect(page.locator('#wb2-sec-run')).toBeVisible()
  await expect(page.locator('#wb2-sec-results')).toBeVisible()
})
