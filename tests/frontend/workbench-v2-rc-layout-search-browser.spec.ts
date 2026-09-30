import { expect, test, type Page } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import { readFileSync } from 'node:fs'
import { gunzipSync } from 'node:zlib'
import { createHash } from 'node:crypto'
import { layoutFiles } from './layoutSearchFixture'
const base = process.env.WORKBENCH_V2_BASE_URL ?? 'http://127.0.0.1:4373'

const pinLayoutPacket = JSON.parse(gunzipSync(readFileSync('tests/frontend/fixtures/rc-pin-roller-layout-originals.json.gz')).toString('utf8'))
for (const entry of pinLayoutPacket.cases) {
  test(`actual v4 pin/roller ${entry.case_id} layout originals remain reviewable`, async ({ page }) => {
    const files: Record<string, Buffer> = Object.fromEntries(Object.entries(entry.originals as Record<string, string>).map(([path, raw]) => [path, Buffer.from(raw)]))
    for (const [path, body] of Object.entries(files)) {
      expect(body.length).toBe(entry.inventory[path].byte_length)
      expect(createHash('sha256').update(body).digest('hex')).toBe(entry.inventory[path].sha256)
    }
    const result = JSON.parse(files['result.json'].toString()), arm = result.arms.price_order
    const comparison = JSON.parse(files[arm.comparison_path].toString())
    const selected = comparison.rows.find((row: any) => row.candidate_id === comparison.selected_candidate_id)
    expect(result.strategy).toBe('price_order')
    expect(result.claims.independent_generalization).toBe(false)
    expect(result.claims.net_savings_proved).toBe(false)
    expect(selected.full_reference_verification_pass).toBe(true)
    const plan = JSON.parse(files['plan.json'].toString())
    expect(plan.control_request.experimental_pin_roller_beam).toBe(true)
    expect(Boolean(plan.control_request.constant_nodal_loads)).toBe(entry.has_preload)
    await page.addInitScript(() => { window.__STRUCTURAL_WORKBENCH_CONFIG__ = { rcControlSearchUrl: '/actual-pin-layout/result.json' } })
    await page.route('**/actual-pin-layout/**', async route => {
      const path = new URL(route.request().url()).pathname.replace('/actual-pin-layout/', '')
      expect(files[path]).toBeDefined()
      await route.fulfill({ contentType: 'application/json', body: files[path] })
    })
    await page.goto(`${base}/#/workbench-v2`)
    const panel = page.locator('[data-rc-search]')
    await expect(panel).toHaveAttribute('data-rc-search', 'verified', { timeout: 60000 })
    await expect(panel.locator('[data-rc-search-arm]')).toHaveCount(1)
    await expect(panel.locator('[data-rc-search-training]')).toContainText('No learned policy')
    await expect(panel.locator('[data-rc-search-authority]')).toContainText('does not establish independent physical validation')
    await expect(panel.locator('[data-rc-search-layout]')).toContainText('do not establish equivalent building function')
    await expect(panel.locator('[data-rc-design-selected]')).toHaveAttribute('data-rc-design-selected', comparison.selected_candidate_id)
    await expect(panel.locator(`[data-rc-design-members="${comparison.selected_candidate_id}"] tbody tr`)).toHaveCount(selected.quantities.members.length)
    if (entry.mode === 'staged') await expect(panel.locator('[data-rc-search-staging]')).toBeVisible()
    if (entry.mode !== 'full') await expect(panel.locator('[data-rc-search-pruning]')).toContainText('physical feasibility remains unknown')
    for (const role of ['model', 'result', 'checkpoint', 'verification']) {
      const pending = page.waitForEvent('download')
      await panel.getByRole('button', { name: `Download ${comparison.selected_candidate_id} ${role}`, exact: true }).click()
      expect((await readFile((await (await pending).path())!)).equals(files[`price_order/${selected.artifacts[role].path}`])).toBe(true)
    }
    for (const role of ['result', 'plan', 'price-table']) {
      const pending = page.waitForEvent('download')
      await panel.getByRole('button', { name: `Download search ${role}`, exact: true }).click()
      expect((await readFile((await (await pending).path())!)).equals(files[`${role}.json`])).toBe(true)
    }
  })
}

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
        expect((await readFile((await (await pending).path())!)).equals(layoutFiles[`learned_order/large/baseline/${role}.json`])).toBe(true)
      }
      for (const role of ['result','plan','policy','historical-training','price-table']) {
        const pending=page.waitForEvent('download')
        await panel.getByRole('button',{name:`Download search ${role}`,exact:true}).click()
        expect((await readFile((await (await pending).path())!)).equals(layoutFiles[`${role}.json`])).toBe(true)
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
      // Include verification and every original download in the bounded test budget.
      test.setTimeout(60000)
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
        // Pace user downloads below Chromium's ten-download burst limit.
        await page.waitForTimeout(250)
        const pending = page.waitForEvent('download')
        await row.getByRole('button', { name: `Download pool ${key} model`, exact: true }).click()
        expect((await readFile((await (await pending).path())!)).equals(files[`pool/${key}.json`])).toBe(true)
      }
      for (const decision of pruning.decisions) {
        await page.waitForTimeout(250)
        const pending = page.waitForEvent('download')
        await panel.getByRole('button', { name: `Download ${decision.candidate_id} decision`, exact: true }).click()
        expect((await readFile((await (await pending).path())!)).equals(files[`${strategy}/${decision.artifact.path}`])).toBe(true)
      }
      if (id !== 'horizon') {
        await expect(panel.locator('[data-rc-design-selected]')).toHaveAttribute('data-rc-design-selected', 'middle')
        for (const role of ['model', 'result', 'checkpoint', 'verification']) {
          await page.waitForTimeout(250)
          const pending = page.waitForEvent('download')
          await panel.getByRole('button', { name: `Download middle ${role}`, exact: true }).click()
          expect((await readFile((await (await pending).path())!)).equals(files[`${strategy}/middle/baseline/${role}.json`])).toBe(true)
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
        expect((await readFile((await (await pending).path())!)).equals(files[`${role}.json`])).toBe(true)
      }
      for(const role of ['model','result','checkpoint','verification']){
        const pending=page.waitForEvent('download');await panel.getByRole('button',{name:`Download middle ${role}`,exact:true}).click()
        expect((await readFile((await (await pending).path())!)).equals(files[`${strategy}/middle/baseline/${role}.json`])).toBe(true)
      }
      const box=await panel.boundingBox();expect(box!.x+box!.width).toBeLessThanOrEqual(width+1)
    })
  })
}

import { stagedFiles } from './layoutStagedFixture'
async function setupStaged(page: Page, tamper: 'none' | 'initial' | 'download' = 'none') {
  await page.addInitScript(() => { window.__STRUCTURAL_WORKBENCH_CONFIG__ = { rcControlSearchUrl: '/layout-staged/result.json', jobAuthorization: () => ({ tenantId: 'synthetic-layout', bearerToken: 'synthetic-layout-token' }) } })
  let resultReads = 0
  await page.route('**/layout-staged/**', async route => {
    expect(await route.request().headerValue('authorization')).toBe('Bearer synthetic-layout-token')
    const path = new URL(route.request().url()).pathname.replace('/layout-staged/', '')
    if (path === 'price_order/prefix/small/baseline/result.json') resultReads++
    const corrupt = tamper === 'initial' && path === 'price_order/prefix/small/decision.json'
      || tamper === 'download' && path === 'price_order/prefix/small/baseline/result.json' && resultReads > 1
    await route.fulfill({ contentType: 'application/json', body: corrupt ? Buffer.concat([stagedFiles[path], Buffer.from(' ')]) : stagedFiles[path] })
  })
}
for (const width of [1440, 390]) test.describe(`RC staged layout browser ${width}`, () => {
  test.use({ viewport: { width, height: 1000 } })
  test('shows prefix rejection and downloads exact prefix and full originals', async ({ page }) => {
    test.setTimeout(60000)
    await setupStaged(page); await page.goto(`${base}/#/workbench-v2`)
    const panel = page.locator('[data-rc-search]')
    await expect(panel).toHaveAttribute('data-rc-search', 'verified', { timeout: 60000 })
    await expect(panel.locator('[data-rc-search-staging]')).toContainText('Prefix steps: 8; full steps: 24')
    await expect(panel.locator('[data-rc-pruning-candidate="small"]')).toContainText('Rejected: verified prefix limit violation')
    await expect(panel.locator('[data-rc-pruning-candidate="large"]')).toContainText('Skipped: higher cost')
    await expect(panel.locator('[data-rc-design-selected]')).toHaveAttribute('data-rc-design-selected', 'middle')
    for (const key of ['small', 'middle']) for (const role of ['decision', 'request', 'row', 'model', 'result', 'checkpoint', 'verification']) {
      // Pace repeated user downloads below Chromium's burst limit.
      await page.waitForTimeout(250)
      const pending = page.waitForEvent('download')
      await panel.getByRole('button', { name: `Download prefix ${key} ${role}`, exact: true }).click()
      const raw = await readFile((await (await pending).path())!)
      const relative = ['decision', 'request', 'row'].includes(role) ? `${role}.json` : `baseline/${role}.json`
      expect(raw.equals(stagedFiles[`price_order/prefix/${key}/${relative}`])).toBe(true)
    }
    for (const role of ['model', 'result', 'checkpoint', 'verification']) {
      // Pace repeated user downloads below Chromium's burst limit.
      await page.waitForTimeout(250)
      const pending = page.waitForEvent('download')
      await panel.getByRole('button', { name: `Download middle ${role}`, exact: true }).click()
      expect((await readFile((await (await pending).path())!)).equals(stagedFiles[`price_order/middle/baseline/${role}.json`])).toBe(true)
    }
    const box = await panel.boundingBox(); expect(box!.x + box!.width).toBeLessThanOrEqual(width + 1)
  })
})
for (const tamper of ['initial', 'download'] as const) test(`RC staged layout browser invalidates ${tamper} corruption`, async ({ page }) => {
  await setupStaged(page, tamper); await page.goto(`${base}/#/workbench-v2`)
  const panel = page.locator('[data-rc-search]')
  if (tamper === 'download') {
    await expect(panel).toHaveAttribute('data-rc-search', 'verified', { timeout: 60000 })
    await panel.getByRole('button', { name: 'Download prefix small result', exact: true }).click()
  }
  await expect(panel).toHaveAttribute('data-rc-search', 'invalid', { timeout: 60000 })
  await expect(panel.locator('[data-rc-design-selected]')).toHaveCount(0)
  await expect(panel.locator('[data-rc-prefix-candidate]')).toHaveCount(0)
})

import { portalSpanBytes, type PortalSpanRun } from './rcPortalLayoutSpanFixture'

for (const run of ['staged', 'full'] as const satisfies readonly PortalSpanRun[]) {
  for (const width of [1440, 390]) {
    test(`two-fixed portal span ${run} original review at ${width}px`, async ({ page }) => {
      test.setTimeout(60000)
      await page.setViewportSize({ width, height: 1000 })
      await page.addInitScript((mode) => {
        window.__STRUCTURAL_WORKBENCH_CONFIG__ = {
          rcControlSearchUrl: `/portal-span-${mode}/result.json`,
          jobAuthorization: () => ({ tenantId: 'synthetic-portal-span', bearerToken: 'synthetic-portal-span-token' }),
        }
      }, run)
      await page.route(`**/portal-span-${run}/**`, async route => {
        expect(await route.request().headerValue('authorization')).toBe('Bearer synthetic-portal-span-token')
        const path = new URL(route.request().url()).pathname.replace(`/portal-span-${run}/`, '')
        await route.fulfill({ contentType: 'application/json', body: Buffer.from(portalSpanBytes(run, path)) })
      })
      await page.goto(`${base}/#/workbench-v2`)
      const panel = page.locator('[data-rc-search]')
      await expect(panel).toHaveAttribute('data-rc-search', 'verified', { timeout: 60000 })
      await expect(panel.locator('[data-rc-design-selected]')).toHaveAttribute('data-rc-design-selected', 'shorter_span_360')
      await expect(panel.locator('[data-rc-search-layout]')).toContainText('equivalent building function')
      const planDownload = page.waitForEvent('download')
      await panel.getByRole('button', { name: 'Download search plan', exact: true }).click()
      expect(await readFile((await (await planDownload).path())!)).toEqual(Buffer.from(portalSpanBytes(run, 'plan.json')))
      if (run === 'staged') {
        await expect(panel.locator('[data-rc-search-staging]')).toContainText('Prefix steps: 4; full steps: 16')
        await expect(panel.locator('[data-rc-search-pool-minimum]')).toContainText('unavailable')
        await expect(panel.locator('[data-rc-pruning-candidate="longer_span_440"]')).toContainText('Unknown')
        await expect(panel.locator('[data-rc-pruning-candidate="longer_span_440"]')).toContainText('Skipped: higher cost')
        for (const [label, path] of [
          ['Download pool longer_span_440 model', 'pool/longer_span_440.json'],
          ['Download longer_span_440 decision', 'price_order/decisions/02.json'],
          ['Download prefix shorter_span_360 result', 'price_order/prefix/shorter_span_360/baseline/result.json'],
        ]) {
          const pending = page.waitForEvent('download')
          await panel.getByRole('button', { name: label, exact: true }).click()
          expect(await readFile((await (await pending).path())!)).toEqual(Buffer.from(portalSpanBytes(run, path)))
        }
      } else {
        await expect(panel.locator('[data-rc-pruning-candidate]')).toHaveCount(0)
        await panel.getByRole('button', { name: 'Select longer_span_440', exact: true }).click()
        const details = panel.locator('[data-rc-design-details="longer_span_440"]')
        await expect(panel.locator('[data-rc-design-candidate="longer_span_440"]')).toContainText('502.35744')
        const pending = page.waitForEvent('download')
        await details.getByRole('button', { name: 'Download longer_span_440 result', exact: true }).click()
        expect(await readFile((await (await pending).path())!)).toEqual(Buffer.from(portalSpanBytes(run, 'price_order/longer_span_440/baseline/result.json')))
      }
      const bounds = await panel.boundingBox()
      expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(width + 1)
    })
  }
}
