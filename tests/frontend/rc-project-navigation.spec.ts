import { expect, test, type Page } from '@playwright/test'
import { createRcPortalEditorExample } from '../../src/workbench-v2/model/rcModelEditor'

const baseUrl = process.env.WORKBENCH_V2_BASE_URL ?? 'http://127.0.0.1:4373'

async function workspace(page: Page): Promise<string[]> {
  const posts: string[] = []
  page.on('request', request => { if (request.method() === 'POST') posts.push(request.url()) })
  await page.addInitScript(() => {
    window.__STRUCTURAL_WORKBENCH_CONFIG__ = { rcJobCollectionUrl: '/v1/jobs' }
  })
  await page.route('**/v1/jobs**', route => route.fulfill({ status: 404, contentType: 'application/json', body: '{}' }))
  await page.goto(`${baseUrl}/#/workbench-v2`)
  await expect(page.getByRole('button', { name: 'Save RC project', exact: true })).toBeEnabled()
  return posts
}

async function editDraft(page: Page, text = '{"incomplete":'): Promise<void> {
  const draft = page.getByLabel('Typed RC request JSON', { exact: true })
  if (!await draft.isVisible()) await page.getByText('Submit a new RC input', { exact: true }).click()
  await draft.fill(text)
  await expect(page.locator('[data-rc-project-dirty]')).toHaveAttribute('data-rc-project-dirty', 'true')
}

async function exportProject(page: Page): Promise<void> {
  const download = page.waitForEvent('download')
  await page.getByRole('button', { name: 'Save RC project', exact: true }).click()
  expect((await download).suggestedFilename()).toBe('rc-workbench-project.json')
  await expect(page.locator('[data-rc-project-dirty]')).toHaveAttribute('data-rc-project-dirty', 'false')
}

test('RC project navigation keeps edits on rejection and disposes the guard after accepted departure', async ({ page }) => {
  const posts = await workspace(page)
  await editDraft(page)
  const originalUrl = page.url(), draft = page.getByLabel('Typed RC request JSON', { exact: true })
  const decisions: string[] = []
  page.once('dialog', async dialog => { decisions.push(dialog.type()); await dialog.dismiss() })
  await page.locator('[data-wb2-legacy-link]').click()
  await expect(page).toHaveURL(originalUrl)
  await expect(draft).toHaveValue('{"incomplete":')
  await expect(page.locator('[data-legacy-surface]')).toHaveCount(0)
  expect(decisions).toEqual(['confirm'])

  page.once('dialog', async dialog => { decisions.push(dialog.type()); await dialog.accept() })
  await page.locator('[data-wb2-legacy-link]').click()
  await expect(page.locator('[data-legacy-surface]')).toBeVisible()
  await expect(page.locator('[data-rc-workflow]')).toHaveCount(0)
  let unexpected = 0
  page.on('dialog', async dialog => { unexpected++; await dialog.dismiss() })
  await page.getByRole('link', { name: /return to workbench v2/i }).click()
  await expect(page.locator('[data-rc-project-dirty]')).toHaveAttribute('data-rc-project-dirty', 'false')
  expect(await page.getByLabel('Typed RC request JSON', { exact: true }).inputValue()).toBe('')
  expect(decisions).toEqual(['confirm', 'confirm'])
  expect(unexpected).toBe(0)
  expect(posts).toEqual([])
})

test('RC project navigation rejects Back once across paired history events without losing the current project', async ({ page }) => {
  const posts = await workspace(page)
  await page.locator('[data-wb2-legacy-link]').click()
  await expect(page.locator('[data-legacy-surface]')).toBeVisible()
  await page.getByRole('link', { name: /return to workbench v2/i }).click()
  await expect(page.getByRole('button', { name: 'Save RC project', exact: true })).toBeEnabled()
  await editDraft(page, '{"retained":"back navigation"}')
  let prompts = 0
  page.on('dialog', async dialog => { prompts++; expect(dialog.type()).toBe('confirm'); await dialog.dismiss() })
  const observed = page.waitForEvent('dialog')
  await page.evaluate(() => history.back())
  await observed
  await expect(page).toHaveURL(`${baseUrl}/#/workbench-v2`)
  await expect(page.getByLabel('Typed RC request JSON', { exact: true })).toHaveValue('{"retained":"back navigation"}')
  // Exercise a paired event after rejection: accepted href is already restored.
  await page.evaluate(() => window.dispatchEvent(new HashChangeEvent('hashchange')))
  expect(prompts).toBe(1)
  expect(posts).toEqual([])
})

test('RC project navigation protects an actual reload until the current project is exported', async ({ page }) => {
  const posts = await workspace(page)
  await editDraft(page, '{"retained":"reload"}')
  const pendingDialog = page.waitForEvent('dialog')
  const reload = page.reload({ timeout: 5000 }).catch(() => null)
  const dialog = await pendingDialog
  expect(dialog.type()).toBe('beforeunload')
  await dialog.dismiss()
  await reload
  await expect(page.getByLabel('Typed RC request JSON', { exact: true })).toHaveValue('{"retained":"reload"}')
  await exportProject(page)
  let unexpected = 0
  page.on('dialog', async next => { unexpected++; await next.dismiss() })
  await page.reload()
  await expect(page.locator('[data-rc-project-dirty]')).toHaveAttribute('data-rc-project-dirty', 'false')
  expect(unexpected).toBe(0)
  expect(posts).toEqual([])
})

test('RC project navigation protects unapplied portal dimensions and clears only after Undo', async ({ page }) => {
  const posts = await workspace(page)
  const original = JSON.stringify(createRcPortalEditorExample('a'.repeat(40)))
  await editDraft(page, original)
  await exportProject(page)
  await page.getByLabel('Portal span (m)', { exact: true }).fill('6.25')
  await expect(page.locator('[data-rc-project-dirty]')).toHaveAttribute('data-rc-project-dirty', 'true')
  await expect(page.getByRole('button', { name: 'Save RC project', exact: true })).toBeDisabled()
  page.once('dialog', async dialog => { expect(dialog.type()).toBe('confirm'); await dialog.dismiss() })
  await page.locator('[data-wb2-legacy-link]').click()
  await expect(page.getByLabel('Portal span (m)', { exact: true })).toHaveValue('6.25')
  await expect(page.getByLabel('Typed RC request JSON', { exact: true })).toHaveValue(original)
  await page.getByRole('button', { name: 'Undo local model changes', exact: true }).click()
  await expect(page.locator('[data-rc-project-dirty]')).toHaveAttribute('data-rc-project-dirty', 'false')
  await page.locator('[data-wb2-legacy-link]').click()
  await expect(page.locator('[data-legacy-surface]')).toBeVisible()
  expect(posts).toEqual([])
})

test('RC project navigation leaves a dirty project intact when a link opens in another tab', async ({ page }) => {
  const posts = await workspace(page)
  await editDraft(page, '{"retained":"new tab"}')
  let prompts = 0
  page.on('dialog', async dialog => { prompts++; await dialog.dismiss() })
  await page.evaluate(() => {
    const anchor = document.createElement('a')
    anchor.href = '#/legacy'; anchor.target = '_blank'; anchor.rel = 'noopener'; anchor.textContent = 'Open separate view'
    document.body.append(anchor)
  })
  const popupReady = page.waitForEvent('popup')
  await page.getByRole('link', { name: 'Open separate view', exact: true }).click()
  const popup = await popupReady
  await popup.waitForLoadState('domcontentloaded')
  await popup.close()
  await expect(page.getByLabel('Typed RC request JSON', { exact: true })).toHaveValue('{"retained":"new tab"}')
  await expect(page.locator('[data-rc-project-dirty]')).toHaveAttribute('data-rc-project-dirty', 'true')
  expect(prompts).toBe(0)
  expect(posts).toEqual([])
})
