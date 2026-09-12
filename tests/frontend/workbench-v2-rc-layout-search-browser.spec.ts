import { expect, test, type Page } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import { layoutFiles } from './layoutSearchFixture'
const base = process.env.WORKBENCH_V2_BASE_URL ?? 'http://127.0.0.1:4373'
async function setup(page: Page, tamper = false) {
  await page.addInitScript(() => { window.__STRUCTURAL_WORKBENCH_CONFIG__ = { rcControlSearchUrl: '/layout-search/result.json', jobAuthorization: () => ({ tenantId: 'synthetic-layout', bearerToken: 'synthetic-layout-token' }) } })
  await page.route('**/layout-search/**', async route => {
    expect(await route.request().headerValue('authorization')).toBe('Bearer synthetic-layout-token')
    const name = new URL(route.request().url()).pathname.replace('/layout-search/', '')
    const bytes = layoutFiles[name]
    expect(bytes).toBeDefined()
    await route.fulfill({ contentType: 'application/json', body: tamper && name === 'learned_order/large/baseline/result.json' ? Buffer.concat([bytes,Buffer.from(' ')]) : bytes })
  })
}
for (const width of [1440,390]) {
  test.describe(`RC layout search browser ${width}`, () => {
    test.use({ viewport: { width,height:1000 } })
    test('reviews missed cheaper feasible layout and exact original downloads',async ({page}) => {
      await setup(page);await page.goto(`${base}/#/workbench-v2`)
      const panel=page.locator('[data-rc-search]')
      await expect(panel).toHaveAttribute('data-rc-search','verified',{timeout:60000})
      await expect(panel.locator('[data-rc-search-layout]')).toContainText('equivalent building function')
      await expect(panel.locator('[data-rc-search-pool-minimum]')).toContainText('middle')
      await panel.getByRole('button',{name:'Review Learned order',exact:true}).click()
      await expect(panel.locator('[data-rc-design-selected]')).toHaveAttribute('data-rc-design-selected','large')
      for (const role of ['model','result','checkpoint','verification']) {
        const pending=page.waitForEvent('download')
        await panel.getByRole('button',{name:`Download large ${role}`,exact:true}).click()
        expect(await readFile((await (await pending).path())!)).toEqual(layoutFiles[`learned_order/large/baseline/${role}.json`])
      }
      for (const role of ['result','plan','policy','historical-training','price-table']) {
        const pending=page.waitForEvent('download')
        await panel.getByRole('button',{name:`Download search ${role}`,exact:true}).click()
        expect(await readFile((await (await pending).path())!)).toEqual(layoutFiles[`${role}.json`])
      }
      await panel.getByRole('button',{name:'Review Later exhaustive check',exact:true}).click()
      await expect(panel.locator('[data-rc-design-selected]')).toHaveAttribute('data-rc-design-selected','middle')
      const box=await panel.boundingBox();expect(box!.x+box!.width).toBeLessThanOrEqual(width+1)
    })
  })
}
test('RC layout search browser rejects changed original result before showing a selection',async ({page}) => {
  await setup(page,true);await page.goto(`${base}/#/workbench-v2`)
  await expect(page.locator('[data-rc-search]')).toHaveAttribute('data-rc-search','invalid',{timeout:60000})
  await expect(page.locator('[data-rc-design-selected]')).toHaveCount(0)
})
