import { expect, test, type Page } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import { layoutFiles } from './layoutSearchFixture'
const base = process.env.WORKBENCH_V2_BASE_URL ?? 'http://127.0.0.1:4373'

test('viewer runtime assets preserve originals and load configured preset', async ({ page, request }) => {
  const manifest: string[] = JSON.parse(await readFile('src/structure-viewer/viewer-runtime-assets.json', 'utf8'))
  for (const relative of manifest) {
    const response = await request.get(`${base}/src/structure-viewer/${relative}`)
    expect(response.status()).toBe(200)
    expect((await response.body()).equals(await readFile(`src/structure-viewer/${relative}`))).toBe(true)
    await response.dispose()
  }
  const messages: string[] = []
  page.on('console', m => messages.push(m.text()))
  await page.goto(`${base}/src/structure-viewer/index.html?preset=midas33_optimized`)
  await expect(page.locator('#provenance-source-label')).not.toHaveText('--', { timeout: 60000 })
  const source = await page.locator('#provenance-source-label').innerText()
  expect(source.toLowerCase()).not.toContain('demo')
  expect(source.toLowerCase()).toContain('midas')
  expect(messages.some(m => m.includes('Preset sidecar unavailable'))).toBe(false)
  expect(messages.some(m => m.includes('initLog is not defined'))).toBe(false)
  expect(messages.some(m => m.includes('Drawing comparison presentation failed'))).toBe(false)
  await expect(page.locator('#viewer-optimization-timeline-slider')).toBeDisabled()
  await expect(page.locator('[data-optimization-timeline-step-label]')).toHaveText('Optimization history unavailable')
  await expect(page.locator('[data-optimization-timeline-meta]')).toHaveText('No optimization change history loaded')
})
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

import { standaloneLayouts } from './layoutStandaloneFixture'
import { prunedLayouts } from './layoutPrunedFixture'

test('RC layout pruned browser hides selections when a decision changes', async ({ page }) => {
  const files = prunedLayouts.price
  await page.addInitScript(() => { window.__STRUCTURAL_WORKBENCH_CONFIG__ = { rcControlSearchUrl: '/pruned-invalid/result.json' } })
  await page.route('**/pruned-invalid/**', async route => {
    const path = new URL(route.request().url()).pathname.replace('/pruned-invalid/', '')
    await route.fulfill({ contentType: 'application/json', body: path.endsWith('decisions/03.json') ? Buffer.concat([files[path], Buffer.from(' ')]) : files[path] })
  })
  await page.goto(`${base}/#/workbench-v2`)
  await expect(page.locator('[data-rc-search]')).toHaveAttribute('data-rc-search', 'invalid', { timeout: 60000 })
  await expect(page.locator('[data-rc-design-selected]')).toHaveCount(0)
  await expect(page.locator('[data-rc-pruning-candidate]')).toHaveCount(0)
})

for (const width of [1440, 390]) for (const id of ['price', 'learned', 'horizon']) {
  test.describe(`RC layout pruned browser ${width} ${id}`, () => {
    test.use({ viewport: { width, height: 1000 } })
    test('shows verified decisions, unknown feasibility and original downloads', async ({ page }) => {
      const files = prunedLayouts[id], result = JSON.parse(files['result.json'].toString()), strategy = result.strategy
      const pruning = result.arms[strategy].cost_pruning
      await page.addInitScript(() => { window.__STRUCTURAL_WORKBENCH_CONFIG__ = { rcControlSearchUrl: '/layout-pruned/result.json', jobAuthorization: () => ({ tenantId: 'synthetic-layout', bearerToken: 'synthetic-layout-token' }) } })
      await page.route('**/layout-pruned/**', async route => {
        expect(await route.request().headerValue('authorization')).toBe('Bearer synthetic-layout-token')
        const path = new URL(route.request().url()).pathname.replace('/layout-pruned/', '')
        expect(files[path]).toBeDefined(); await route.fulfill({ contentType: 'application/json', body: files[path] })
      })
      await page.goto(`${base}/#/workbench-v2`)
      const panel = page.locator('[data-rc-search]')
      await expect(panel).toHaveAttribute('data-rc-search', 'verified', { timeout: 60000 })
      await expect(panel.locator('[data-rc-search-pruning]')).toContainText('physical feasibility remains unknown')
      await expect(panel.locator('[data-rc-search-pool-minimum]')).toContainText('unavailable')
      await expect(panel.locator('[data-rc-search-arm]')).toHaveCount(1)
      for (const key of pruning.unevaluated_candidate_ids) {
        const row = panel.locator(`[data-rc-pruning-candidate="${key}"]`)
        await expect(row).toContainText('Unknown')
        await expect(row).toContainText(id === 'horizon' ? 'Outside consideration horizon' : 'Skipped: higher cost')
        const pending = page.waitForEvent('download')
        await row.getByRole('button', { name: `Download pool ${key} model`, exact: true }).click()
        expect(await readFile((await (await pending).path())!)).toEqual(files[`pool/${key}.json`])
      }
      for (const decision of pruning.decisions) {
        const pending = page.waitForEvent('download')
        await panel.getByRole('button', { name: `Download ${decision.candidate_id} decision`, exact: true }).click()
        expect(await readFile((await (await pending).path())!)).toEqual(files[`${strategy}/${decision.artifact.path}`])
      }
      if (id !== 'horizon') {
        await expect(panel.locator('[data-rc-design-selected]')).toHaveAttribute('data-rc-design-selected', 'middle')
        for (const role of ['model', 'result', 'checkpoint', 'verification']) {
          const pending = page.waitForEvent('download')
          await panel.getByRole('button', { name: `Download middle ${role}`, exact: true }).click()
          expect(await readFile((await (await pending).path())!)).toEqual(files[`${strategy}/middle/baseline/${role}.json`])
        }
      }
      const box = await panel.boundingBox(); expect(box!.x + box!.width).toBeLessThanOrEqual(width + 1)
    })
  })
}
for (const width of [1440,390]) for (const strategy of ['price_order','learned_order']) {
  test.describe(`RC layout standalone browser ${width} ${strategy}`,()=>{
    test.use({viewport:{width,height:1000}})
    test('single strategy selection and exact original downloads',async({page})=>{
      const files=standaloneLayouts[`b3-o0-${strategy}`]
      await page.addInitScript(()=>{window.__STRUCTURAL_WORKBENCH_CONFIG__={rcControlSearchUrl:'/layout-single/result.json',jobAuthorization:()=>({tenantId:'synthetic-layout',bearerToken:'synthetic-layout-token'})}})
      await page.route('**/layout-single/**',async route=>{
        const path=new URL(route.request().url()).pathname.replace('/layout-single/','')
        expect(files[path]).toBeDefined();await route.fulfill({contentType:'application/json',body:files[path]})
      })
      await page.goto(`${base}/#/workbench-v2`)
      const panel=page.locator('[data-rc-search]')
      await expect(panel).toHaveAttribute('data-rc-search','verified',{timeout:60000})
      await expect(panel.locator('[data-rc-search-arm]')).toHaveCount(1)
      await expect(panel.locator('[data-rc-search-standalone]')).toContainText('No other strategy')
      await expect(panel.locator('[data-rc-search-layout]')).toContainText('equivalent building function')
      await expect(panel.locator('[data-rc-search-pool-minimum]')).toContainText('unavailable')
      await expect(panel.locator('[data-rc-design-selected]')).toHaveAttribute('data-rc-design-selected','middle')
      const metadata=['result','plan','price-table',...(strategy==='learned_order'?['policy','historical-training']:[])]
      if(strategy==='price_order') await expect(panel.getByRole('button',{name:'Download search policy',exact:true})).toHaveCount(0)
      for(const role of metadata){
        const pending=page.waitForEvent('download');await panel.getByRole('button',{name:`Download search ${role}`,exact:true}).click()
        expect(await readFile((await (await pending).path())!)).toEqual(files[`${role}.json`])
      }
      for(const role of ['model','result','checkpoint','verification']){
        const pending=page.waitForEvent('download');await panel.getByRole('button',{name:`Download middle ${role}`,exact:true}).click()
        expect(await readFile((await (await pending).path())!)).toEqual(files[`${strategy}/middle/baseline/${role}.json`])
      }
      const box=await panel.boundingBox();expect(box!.x+box!.width).toBeLessThanOrEqual(width+1)
    })
  })
}
