import { expect, test, type Page } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import path from 'node:path'
import { createRcPortableReviewBlob } from '../../src/workbench-v2/model/rcPortableReviewSchema'

const origin = process.env.WORKBENCH_V2_BASE_URL ?? 'http://127.0.0.1:5128'
const retained = process.env.RC_COROTATIONAL_REPORT_FIXTURE_DIR

async function openFile(page: Page, bytes: Buffer): Promise<void> {
  await page.getByLabel('Open portable RC review file', { exact: true }).setInputFiles({
    name: 'saved-rc-review.json', mimeType: 'application/json', buffer: bytes,
  })
}
async function verified(page: Page): Promise<void> {
  await expect(page.locator('[data-rc-portable-review]')).toHaveAttribute('data-rc-portable-review', 'verified')
  await expect(page.locator('[data-rc-portable-selected]')).toBeVisible()
}

for (const profile of ['v6', 'v7'] as const) test.describe(`Portable RC nodal review ${profile}`, () => {
  test.skip(!retained, 'Retained hosted software fixtures are required; never generate a numerical fixture here.')
  let snapshot: any, request: Buffer, report: Buffer, detailBytes: Buffer, archive: Buffer, detailedArchive: Buffer
  test.beforeAll(async () => {
    snapshot = JSON.parse(readFileSync(path.join(retained!, `${profile}-review-snapshot.json`), 'utf8'))
    request = Buffer.from(snapshot.artifacts.request, 'base64')
    report = Buffer.from(snapshot.report.body_base64, 'base64')
    detailBytes = Buffer.from(snapshot.detail_report.body_base64, 'base64')
    archive = Buffer.from(await (await createRcPortableReviewBlob({ job: snapshot.job, tenantId: snapshot.tenant_id,
      requestBytes: request, reportBytes: report, reportId: snapshot.report.headers['x-structural-report-id'],
      contentHash: snapshot.report.headers['x-structural-report-sha256'] })).arrayBuffer())
    detailedArchive = Buffer.from(await (await createRcPortableReviewBlob({ job: snapshot.job, tenantId: snapshot.tenant_id,
      requestBytes: request, reportBytes: report, reportId: snapshot.report.headers['x-structural-report-id'],
      contentHash: snapshot.report.headers['x-structural-report-sha256'], detailReport: { bytes: detailBytes,
        reportId: snapshot.detail_report.headers['x-structural-report-id'], contentHash: snapshot.detail_report.headers['x-structural-report-sha256'] } })).arrayBuffer())
  })

  async function live(page: Page): Promise<Array<string>> {
    const calls: string[] = []
    await page.addInitScript(({ tenant }) => {
      const host = window as any; host.__portableTenant = tenant
      host.__STRUCTURAL_WORKBENCH_CONFIG__ = { rcJobCollectionUrl: '/v1/jobs',
        jobAuthorization: async () => { await host.__portableAuthorizationGate; return { tenantId: host.__portableTenant, bearerToken: 'synthetic-test-token' } } }
    }, { tenant: snapshot.tenant_id })
    await page.route('**/v1/jobs**', async route => {
      const req = route.request(), pathname = new URL(req.url()).pathname
      calls.push(`${req.method()} ${pathname}`)
      if (req.headers()['x-structural-tenant'] !== snapshot.tenant_id) return route.fulfill({ status: 401 })
      if (pathname.endsWith('/rc-corotational-detail-report')) return route.fulfill({ status: 200, headers: snapshot.detail_report.headers, body: detailBytes })
      if (pathname.endsWith('/rc-corotational-report')) return route.fulfill({ status: 200, headers: snapshot.report.headers, body: report })
      if (pathname.endsWith('/request')) return route.fulfill({ status: 200, contentType: 'application/json', body: request })
      if (pathname === `/v1/jobs/${snapshot.job.job_id}`) return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(snapshot.job) })
      return route.fulfill({ status: 404 })
    })
    await page.goto(`${origin}/?rcJob=${snapshot.job.job_id}#/workbench-v2`)
    await expect(page.locator('[data-rc-corotational-review]')).toHaveAttribute('data-rc-corotational-review', 'report_verified')
    return calls
  }

  test('exports through live authorization and opens on a fresh browser with the original service unavailable', async ({ page, browser }, testInfo) => {
    const calls = await live(page)
    const exported = page.waitForEvent('download')
    await page.getByRole('button', { name: 'Export portable RC review', exact: true }).click()
    const exportedBytes = readFileSync((await (await exported).path())!)
    expect(calls.filter(call => call.startsWith('POST'))).toEqual([])

    const context = await browser.newContext()
    try {
      await context.addInitScript(() => {
        const host = window as any; host.__portableAuthCalls = 0
        host.__STRUCTURAL_WORKBENCH_CONFIG__ = { rcJobCollectionUrl: '/v1/jobs', jobStatusUrl: '/v1/jobs/unavailable',
          jobAuthorization: async () => { host.__portableAuthCalls++; throw new Error('original_service_unavailable') } }
      })
      const serviceCalls: string[] = []
      await context.route('**/v1/jobs**', async route => { serviceCalls.push(route.request().url()); await route.abort() })
      const offline = await context.newPage()
      await offline.goto(`${origin}/#/rc-review`)
      await expect(offline.locator('[data-rc-project-workspace]')).toHaveCount(0)
      await openFile(offline, exportedBytes); await verified(offline)
      await expect(offline.locator('[data-rc-portable-custody]')).toHaveText('File integrity checked. Origin is not authenticated.')
      await expect(offline.locator('[data-rc-portable-unknown]')).toContainText('Unknown work remains')
      await expect(offline.locator('[data-rc-portable-details]')).toHaveAttribute('data-rc-portable-details', 'omitted')
      await expect(offline.locator('[data-rc-portable-detail-status]')).toContainText('nodal-only file does not include')
      await expect(offline.getByRole('button', { name: 'Open stored RC details', exact: true })).toHaveCount(0)
      await expect(offline.getByLabel('Portable accepted state', { exact: true })).toHaveValue('3')
      const response = JSON.parse(report.toString('utf8')).responses[3]
      for (const node of response.nodes) await expect(offline.locator('[data-rc-corotational-table="displacements_m_rad"] tbody tr')
        .filter({ has: offline.getByRole('rowheader', { name: node.node_id, exact: true }) }).locator('td')).toHaveText(node.displacements_m_rad.map(String))
      await expect(offline.locator('[data-rc-deformed-shape]')).toBeVisible()
      await offline.getByRole('button', { name: 'Previous accepted state', exact: true }).click()
      await expect(offline.locator('[data-rc-portable-selected]')).toContainText('Accepted state 2')
      await offline.getByRole('button', { name: 'Inspect stored state 0', exact: true }).click()
      await expect(offline.locator('[data-rc-portable-selected]')).toContainText('Accepted state 0 · preload')
      for (const [label, bytes] of [['Download original RC input', request], ['Download stored nodal report', report]] as const) {
        const event = offline.waitForEvent('download')
        await offline.getByRole('button', { name: label, exact: true }).click()
        expect(readFileSync((await (await event).path())!).equals(bytes)).toBe(true)
      }
      await expect(offline.getByRole('button', { name: /submit|resume|pause|cancel|run analysis/i })).toHaveCount(0)
      expect(await offline.evaluate(() => (window as any).__portableAuthCalls)).toBe(0)
      expect(serviceCalls).toEqual([])
      await offline.screenshot({ path: testInfo.outputPath('portable-offline-review.png'), fullPage: true })
    } finally { await context.close() }
    expect(calls.filter(call => call.endsWith('/rc-corotational-detail-report'))).toEqual([])
  })

  test('exports included details and reads exact member, section and fiber histories in a fresh session without service access', async ({ page, browser }, testInfo) => {
    const calls = await live(page)
    const event = page.waitForEvent('download')
    await page.getByRole('button', { name: 'Export portable RC review with details', exact: true }).click()
    const exportedBytes = readFileSync((await (await event).path())!)
    expect(calls.filter(call => call.endsWith('/rc-corotational-detail-report'))).toHaveLength(1)
    expect(calls.filter(call => !call.startsWith('GET '))).toEqual([])
    const detail = JSON.parse(detailBytes.toString('utf8'))
    const context = await browser.newContext()
    try {
      await context.addInitScript(() => {
        const host = window as any; host.__portableAuthCalls = 0
        host.__STRUCTURAL_WORKBENCH_CONFIG__ = { rcJobCollectionUrl: '/v1/jobs', jobStatusUrl: '/v1/jobs/unavailable',
          jobAuthorization: async () => { host.__portableAuthCalls++; throw new Error('original_service_unavailable') } }
      })
      const serviceCalls: string[] = []
      await context.route('**/v1/jobs**', async route => { serviceCalls.push(route.request().url()); await route.abort() })
      const offline = await context.newPage()
      await offline.goto(`${origin}/#/rc-review`); await openFile(offline, exportedBytes); await verified(offline)
      await expect(offline.locator('[data-rc-project-workspace]')).toHaveCount(0)
      await expect(offline.locator('[data-rc-portable-details]')).toHaveAttribute('data-rc-portable-details', 'included')
      await expect(offline.locator('[data-rc-portable-detail-status]')).toContainText('Origin is not authenticated')
      await offline.getByRole('button', { name: 'Open stored RC details', exact: true }).click()
      const panel = offline.locator('[data-rc-corotational-details="verified"]')
      await expect(panel).toBeVisible()
      for (const state of detail.responses) {
        await offline.getByLabel('Portable accepted state', { exact: true }).selectOption(String(state.state_index))
        for (const member of state.members) {
          await panel.getByLabel('Detail member', { exact: true }).selectOption(member.member_id)
          await expect(panel.locator('[data-rc-detail-member]')).toContainText(`Accepted state ${state.state_index} · ${member.member_id}:`)
          for (const frame of ['global', 'local']) for (const [end, offset] of [['i', 0], ['j', 3]] as const) {
            await expect(panel.locator(`[data-rc-detail-force="${frame}:${end}"] td`)).toHaveText([
              `${end}: ${member[`node_${end}`]}`, ...member[`end_force_${frame}_kn_knm`].slice(offset, offset + 3).map(String),
            ])
          }
          const section = member.sections.at(-1)
          await panel.getByLabel('Detail integration point', { exact: true }).selectOption(String(section.integration_point_index))
          await expect(panel.locator('[data-rc-detail-section-table] tbody td')).toHaveText([
            section.axial_strain, section.curvature_z_per_m, section.axial_force_kn, section.moment_z_kn_m,
          ].map(String))
          const fiber = section.fibers.at(-1)
          await panel.getByLabel('Detail fiber index', { exact: true }).fill(String(fiber.fiber_index))
          await expect(panel.locator('[data-rc-detail-fiber-table] tbody td')).toHaveText([
            fiber.fiber_index, fiber.material_kind, fiber.strain, fiber.stress_mpa,
          ].map(String))
        }
      }
      const member = detail.responses.at(-1).members.at(-1), section = member.sections.at(-1), fiber = section.fibers.at(-1)
      const sectionPlot = panel.locator('[data-rc-history-plot="Section moment–curvature history"]')
      const fiberPlot = panel.locator('[data-rc-history-plot="Fiber stress–strain history"]')
      for (const [plot, values] of [[sectionPlot, detail.responses.map((row: any) => {
        const selected = row.members[member.member_index].sections[section.integration_point_index]
        return { state: row.state_index, x: selected.curvature_z_per_m, y: selected.moment_z_kn_m }
      })], [fiberPlot, detail.responses.map((row: any) => {
        const selected = row.members[member.member_index].sections[section.integration_point_index].fibers[fiber.fiber_index]
        return { state: row.state_index, x: selected.strain, y: selected.stress_mpa }
      })]] as const) {
        await expect(plot.locator('[data-rc-history-point]')).toHaveCount(detail.responses.length)
        expect(await plot.locator('[data-rc-history-point]').evaluateAll(elements => elements.map(element => ({
          state: Number(element.getAttribute('data-rc-history-point')), x: Number(element.getAttribute('data-rc-x')), y: Number(element.getAttribute('data-rc-y')),
        })))).toEqual(values)
      }
      await sectionPlot.getByRole('button', { name: 'Inspect stored state 0', exact: true }).press('Enter')
      await expect(offline.getByLabel('Portable accepted state', { exact: true })).toHaveValue('0')
      await expect(panel.locator('[data-rc-detail-member]')).toContainText(`Accepted state 0 · ${member.member_id}:`)
      for (const [label, bytes] of [['Download original RC input', request], ['Download stored nodal report', report],
        ['Download corotational detail report', detailBytes]] as const) {
        const download = offline.waitForEvent('download')
        await offline.getByRole('button', { name: label, exact: true }).click()
        expect(readFileSync((await (await download).path())!).equals(bytes)).toBe(true)
      }
      await expect(offline.getByRole('button', { name: /submit|resume|pause|cancel|run analysis/i })).toHaveCount(0)
      expect(await offline.evaluate(() => (window as any).__portableAuthCalls)).toBe(0)
      expect(serviceCalls).toEqual([])
      await offline.screenshot({ path: testInfo.outputPath('portable-offline-details.png'), fullPage: true })
    } finally { await context.close() }
  })

  test('retains the last verified file and selected state after damaged or unsupported replacement files', async ({ page }) => {
    const serviceCalls: string[] = []
    await page.route('**/v1/jobs**', async route => { serviceCalls.push(route.request().url()); await route.abort() })
    await page.goto(`${origin}/#/rc-review`); await openFile(page, archive); await verified(page)
    await page.getByLabel('Portable accepted state', { exact: true }).selectOption('1')
    await expect(page.locator('[data-rc-portable-selected]')).toContainText('Accepted state 1')
    const damaged = JSON.parse(archive.toString('utf8'))
    damaged.report.body_base64 = `${damaged.report.body_base64[0] === 'A' ? 'B' : 'A'}${damaged.report.body_base64.slice(1)}`
    const unsupported = JSON.parse(archive.toString('utf8')); unsupported.schema_version = 'rc-portable-nodal-review.v999'
    for (const bytes of [Buffer.from(JSON.stringify(damaged)), Buffer.from(JSON.stringify(unsupported)), archive.subarray(0, 100)]) {
      await openFile(page, bytes)
      await expect(page.locator('[data-rc-portable-file-status]')).toContainText('previously opened review is retained')
      await expect(page.locator('[data-rc-portable-selected]')).toContainText('Accepted state 1')
      await verified(page)
    }
    const event = page.waitForEvent('download')
    await page.getByRole('button', { name: 'Download stored nodal report', exact: true }).click()
    expect(readFileSync((await (await event).path())!).equals(report)).toBe(true)
    expect(serviceCalls).toEqual([])
  })

  test('rejects corrupted and mismatched included details while retaining the previous nodal and detail selections', async ({ page }) => {
    const serviceCalls: string[] = []
    await page.route('**/v1/jobs**', async route => { serviceCalls.push(route.request().url()); await route.abort() })
    await page.goto(`${origin}/#/rc-review`); await openFile(page, detailedArchive); await verified(page)
    await page.getByRole('button', { name: 'Open stored RC details', exact: true }).click()
    const panel = page.locator('[data-rc-corotational-details="verified"]')
    await expect(panel).toBeVisible()
    await page.getByLabel('Portable accepted state', { exact: true }).selectOption('1')
    const detail = JSON.parse(detailBytes.toString('utf8')), member = detail.responses[1].members.at(-1)
    await panel.getByLabel('Detail member', { exact: true }).selectOption(member.member_id)
    const section = member.sections.at(-1), fiber = section.fibers.at(-1)
    await panel.getByLabel('Detail integration point', { exact: true }).selectOption(String(section.integration_point_index))
    await panel.getByLabel('Detail fiber index', { exact: true }).fill(String(fiber.fiber_index))
    const fiberCells = [fiber.fiber_index, fiber.material_kind, fiber.strain, fiber.stress_mpa].map(String)
    await expect(panel.locator('[data-rc-detail-fiber-table] tbody td')).toHaveText(fiberCells)
    const corrupted = JSON.parse(detailedArchive.toString('utf8'))
    corrupted.detail_report.body_base64 = `${corrupted.detail_report.body_base64[0] === 'A' ? 'B' : 'A'}${corrupted.detail_report.body_base64.slice(1)}`
    const other = JSON.parse(readFileSync(path.join(retained!, `${profile === 'v6' ? 'v7' : 'v6'}-review-snapshot.json`), 'utf8'))
    const otherBytes = Buffer.from(other.detail_report.body_base64, 'base64')
    const mismatched = JSON.parse(detailedArchive.toString('utf8'))
    mismatched.detail_report_id = other.detail_report.headers['x-structural-report-id']
    mismatched.detail_report = { encoding: 'base64', byte_length: otherBytes.byteLength,
      content_hash: `sha256:${createHash('sha256').update(otherBytes).digest('hex')}`, body_base64: otherBytes.toString('base64') }
    for (const bytes of [Buffer.from(JSON.stringify(corrupted)), Buffer.from(JSON.stringify(mismatched))]) {
      await openFile(page, bytes)
      await expect(page.locator('[data-rc-portable-file-status]')).toContainText('included detail report could not be verified')
      await expect(page.locator('[data-rc-portable-file-status]')).toContainText('previously opened review is retained')
      await expect(page.locator('[data-rc-portable-selected]')).toContainText('Accepted state 1')
      await expect(panel.locator('[data-rc-detail-member]')).toContainText(`Accepted state 1 · ${member.member_id}:`)
      await expect(panel.getByLabel('Detail integration point', { exact: true })).toHaveValue(String(section.integration_point_index))
      await expect(panel.getByLabel('Detail fiber index', { exact: true })).toHaveValue(String(fiber.fiber_index))
      await expect(panel.locator('[data-rc-detail-fiber-table] tbody td')).toHaveText(fiberCells)
      await verified(page)
    }
    for (const [label, bytes] of [['Download stored nodal report', report], ['Download corotational detail report', detailBytes]] as const) {
      const event = page.waitForEvent('download')
      await page.getByRole('button', { name: label, exact: true }).click()
      expect(readFileSync((await (await event).path())!).equals(bytes)).toBe(true)
    }
    expect(serviceCalls).toEqual([])
  })

  for (const failure of ['missing 404', 'malformed 200'] as const) test(`${failure} detailed export preserves nodal review and permits a separate nodal-only export`, async ({ page }) => {
    await live(page)
    let detailRequests = 0
    await page.route('**/rc-corotational-detail-report', route => {
      detailRequests++
      return route.fulfill(failure === 'missing 404' ? { status: 404 }
        : { status: 200, headers: snapshot.detail_report.headers, body: '{}' })
    })
    const downloads: string[] = []; page.on('download', download => downloads.push(download.suggestedFilename()))
    const withDetails = page.getByRole('button', { name: 'Export portable RC review with details', exact: true })
    await withDetails.click()
    await expect(page.locator('[data-rc-corotational-file-status]')).toContainText('with details could not be exported')
    await expect(page.locator('[data-rc-corotational-table="displacements_m_rad"]')).toBeVisible()
    await expect(withDetails).toBeEnabled()
    expect(downloads).toEqual([])
    expect(detailRequests).toBe(1)
    const event = page.waitForEvent('download')
    await page.getByRole('button', { name: 'Export portable RC review', exact: true }).click()
    const file = JSON.parse(readFileSync((await (await event).path())!, 'utf8'))
    expect(file.schema_version).toBe('rc-portable-nodal-review.v1')
    expect(file).not.toHaveProperty('detail_report')
    expect(detailRequests).toBe(1)
  })

  test('detail export authorization refusal revokes the retained live review and never downloads a file', async ({ page }) => {
    await live(page)
    await page.route('**/rc-corotational-detail-report', route => route.fulfill({ status: 403 }))
    const downloads: string[] = []; page.on('download', download => downloads.push(download.suggestedFilename()))
    await page.getByRole('button', { name: 'Export portable RC review with details', exact: true }).click()
    await expect(page.locator('[data-rc-corotational-table]')).toHaveCount(0)
    await expect(page.locator('[data-rc-detail-force-table]')).toHaveCount(0)
    expect(downloads).toEqual([])
  })

  test('revoked live account scope prevents exporting a portable file', async ({ page }) => {
    await live(page)
    const downloads: string[] = []; page.on('download', download => downloads.push(download.suggestedFilename()))
    await page.evaluate(() => { (window as any).__portableTenant = 'different-account' })
    await page.getByRole('button', { name: 'Export portable RC review', exact: true }).click()
    await expect(page.locator('[data-rc-corotational-table]')).toHaveCount(0)
    expect(downloads).toEqual([])
  })

  test('serializes live export and reopen and restores the export control after either file result', async ({ page }) => {
    await live(page)
    await page.evaluate(() => {
      const host = window as any
      host.__portableAuthorizationGate = new Promise<void>(resolve => { host.__releasePortableAuthorization = resolve })
    })
    const exported = page.waitForEvent('download')
    const exportButton = page.getByRole('button', { name: 'Export portable RC review', exact: true })
    const detailedExportButton = page.getByRole('button', { name: 'Export portable RC review with details', exact: true })
    const reopen = page.getByLabel('Reopen corotational report JSON', { exact: true })
    await exportButton.click()
    await expect(exportButton).toBeDisabled(); await expect(detailedExportButton).toBeDisabled(); await expect(reopen).toBeDisabled()
    await page.evaluate(() => { (window as any).__releasePortableAuthorization() })
    await exported
    await expect(exportButton).toBeEnabled(); await expect(detailedExportButton).toBeEnabled(); await expect(reopen).toBeEnabled()
    for (const [bytes, message] of [
      [Buffer.from('{}'), 'does not match'], [report, 'Reopened exact report bytes match'],
    ] as const) {
      await reopen.setInputFiles({ name: 'nodal-report.json', mimeType: 'application/json', buffer: bytes })
      await expect(page.locator('[data-rc-corotational-file-status]')).toContainText(message)
      await expect(exportButton).toBeEnabled()
    }
    const retried = page.waitForEvent('download'); await exportButton.click(); await retried
    await expect(exportButton).toBeEnabled()
  })
})

for (const configured of [false, true]) test(`portable workspace is reachable from ${configured ? 'configured RC' : 'general'} Workbench`, async ({ page }) => {
  if (configured) await page.addInitScript(() => {
    ;(window as any).__STRUCTURAL_WORKBENCH_CONFIG__ = { rcJobCollectionUrl: '/v1/jobs' }
  })
  await page.goto(`${origin}/#/workbench-v2`)
  await page.keyboard.press('Tab')
  await expect(page.getByRole('link', { name: 'Skip to workbench', exact: true })).toBeFocused()
  await page.getByRole('link', { name: 'Open a portable RC review', exact: true }).click()
  await expect(page.locator('[data-rc-portable-workspace]')).toBeVisible()
  await expect(page.locator('[data-rc-project-workspace]')).toHaveCount(0)
})

for (const [route, base] of [['/rc-review', '/'], ['/rc-review//', '/'], ['/nested/rc-review/', '/nested/']] as const)
test(`direct portable path ${route} returns to Workbench and preserves its internal navigation`, async ({ page }) => {
  await page.goto(`${origin}${route}`)
  await expect(page.locator('[data-rc-portable-workspace]')).toBeVisible()
  await page.getByRole('link', { name: 'Return to Workbench', exact: true }).click()
  await expect(page.locator('[data-rc-portable-workspace]')).toHaveCount(0)
  expect(new URL(page.url()).pathname).toBe(base)
  const skip = page.getByRole('link', { name: 'Skip to workbench', exact: true })
  await expect(skip).toBeAttached()
  await page.keyboard.press('Tab')
  await expect(skip).toBeFocused()
  await page.keyboard.press('Enter')
  await expect(page.getByRole('main', { name: 'Workbench content', exact: true })).toBeFocused()
  await expect(page.locator('[data-rc-portable-workspace]')).toHaveCount(0)
  await page.getByRole('link', { name: 'Open a portable RC review', exact: true }).click()
  await expect(page.locator('[data-rc-portable-workspace]')).toBeVisible()
})
