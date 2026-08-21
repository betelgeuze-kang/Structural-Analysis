import { expect, test, type Page } from '@playwright/test'
import { readFile } from 'node:fs/promises'
import { createHash } from 'node:crypto'
import {
  artifactBytes,
  fixtureHash,
  nativeFrameComparisonFixture,
  nativeFrameReferenceFixture,
  nativeFrameReportFixture,
  nativeFrameResultFixture,
} from './nativeFrameFixture'

// End-to-end smoke for the Workbench v2 product shell. The runner builds and
// serves dist; the embedded Viewer must resolve to its emitted production entry,
// not to the server's Workbench SPA fallback.

const baseUrl = process.env.WORKBENCH_V2_BASE_URL ?? 'http://127.0.0.1:4373'
const routeUrl = `${baseUrl}/#/workbench-v2`
const defaultUrl = `${baseUrl}/`

test.setTimeout(60000)

async function open(page: Page): Promise<void> {
  await page.goto(routeUrl, { waitUntil: 'load', timeout: 30000 })
  await page.locator('[data-wb2-root]').waitFor({ state: 'visible', timeout: 15000 })
}

test.describe('Product surface routing', () => {
  test('renders Workbench v2 at the default root', async ({ page }) => {
    await page.goto(defaultUrl, { waitUntil: 'load', timeout: 30000 })
    await expect(page.locator('[data-wb2-root]')).toBeVisible()
    await expect(page.locator('[data-legacy-surface]')).toHaveCount(0)
    const eagerLegacyChunks = await page.evaluate(() => performance.getEntriesByType('resource')
      .map((entry) => entry.name)
      .filter((name) => /\/assets\/App-[^/]+\.js(?:\?|$)/.test(name)))
    expect(eagerLegacyChunks).toHaveLength(0)
  })

  test('switches to the compatibility desk only through the explicit legacy link', async ({ page }) => {
    await page.goto(defaultUrl, { waitUntil: 'load', timeout: 30000 })
    await page.locator('[data-wb2-legacy-link]').click()
    await expect(page.locator('[data-legacy-surface]')).toBeVisible()
    await expect(page.locator('.legacy-surface-route__notice')).toContainText(/legacy evidence desk/i)
    await expect(page.locator('[data-wb2-root]')).toHaveCount(0)
    await expect(page).toHaveURL(/#\/legacy$/)
    const loadedLegacyChunks = await page.evaluate(() => performance.getEntriesByType('resource')
      .map((entry) => entry.name)
      .filter((name) => /\/assets\/App-[^/]+\.js(?:\?|$)/.test(name)))
    expect(loadedLegacyChunks).toHaveLength(1)

    await page.getByRole('link', { name: /return to workbench v2/i }).click()
    await expect(page.locator('[data-wb2-root]')).toBeVisible()
    await expect(page.locator('[data-legacy-surface]')).toHaveCount(0)
  })
})

test.describe('Workbench v2 — shell & demo case', () => {
  test('renders the DEMO data-mode badge and claim boundary', async ({ page }) => {
    await open(page)
    await expect(page.locator('[data-wb2-root] .wb2-chip[data-state="DEMO"]').first()).toBeVisible()
    await expect(page.locator('[data-wb2-claim]')).toContainText(/claim boundary/i)
  })

  test('shows provenance + model health and a converged analysis', async ({ page }) => {
    await open(page)
    await expect(page.getByText('Case & provenance')).toBeVisible()
    await expect(page.getByText('Source checksum', { exact: true })).toBeVisible()
    await expect(page.locator('[data-wb2-root]')).toContainText(/Converged/i)
  })

  test('does not show an automated verdict (review decision UNAVAILABLE)', async ({ page }) => {
    await open(page)
    await expect(page.locator('[data-ec-decision="unavailable"], [data-state="UNAVAILABLE"]').first()).toBeVisible()
  })
})

test.describe('Workbench v2 — demo case samples', () => {
  test('demo case selector offers converged, failed, and unavailable samples', async ({ page }) => {
    await open(page)
    await expect(page.locator('[data-wb2-case-selector]')).toBeVisible()
    await expect(page.locator('[data-wb2-case="converged"]')).toBeVisible()
    await expect(page.locator('[data-wb2-case="failed"]')).toBeVisible()
    await expect(page.locator('[data-wb2-case="unavailable"]')).toBeVisible()
  })

  test('converged sample shows a converged verdict, residual chart, and within-tolerance', async ({ page }) => {
    await open(page)
    await page.locator('[data-wb2-case="converged"]').click()
    const card = page.locator('[data-result-verdict]')
    await expect(card).toHaveAttribute('data-result-verdict', 'converged')
    await expect(card.locator('[data-result-chip]')).toContainText(/Converged/i)
    await expect(page.locator('[data-wb2-residual-chart]')).toBeVisible()
    await expect(page.locator('[data-wb2-tol-line]')).toBeAttached()
    await expect(card.locator('[data-result-within-tol="true"]')).toBeVisible()
  })

  test('failed sample preserves execution failure while numerical convergence stays unavailable', async ({ page }) => {
    await open(page)
    await page.locator('[data-wb2-case="failed"]').click()
    const card = page.locator('[data-result-verdict]')
    await expect(card).toHaveAttribute('data-result-verdict', 'failed')
    await expect(card.locator('[data-result-chip]')).toContainText(/Analysis failed/i)
    const convergenceMetric = card.locator('.wb2-result-metric').filter({ hasText: 'Converged' })
    await expect(convergenceMetric).toContainText(/UNAVAILABLE/i)
    await expect(card.locator('[data-result-within-tol="false"]')).toBeVisible()
    await expect(page.locator('[data-run-status]')).toHaveText('Analysis failed')
    await expect(page.locator('#wb2-sec-analysis')).toContainText(/Analysis execution failed/i)
  })

  test('unavailable sample reports convergence UNAVAILABLE with no chart and no inferred status', async ({ page }) => {
    await open(page)
    await page.locator('[data-wb2-case="unavailable"]').click()
    const card = page.locator('[data-result-verdict]')
    await expect(card).toHaveAttribute('data-result-verdict', 'unavailable')
    await expect(card.locator('[data-result-chip]')).toContainText(/unavailable/i)
    // No fabricated residual trace for a case without analysis.
    await expect(page.locator('[data-wb2-residual-chart]')).toHaveCount(0)
  })
})

test.describe('Workbench v2 — provider, evidence, benchmarks', () => {
  test('demo/live provider toggle is present', async ({ page }) => {
    await open(page)
    await expect(page.locator('[data-wb2-provider="demo"]')).toBeVisible()
    await expect(page.locator('[data-wb2-provider="live"]')).toBeVisible()
  })

  test('benchmark browser lists cases and filters by lifecycle', async ({ page }) => {
    await open(page)
    const cards = page.locator('[data-bench-id]')
    expect(await cards.count()).toBeGreaterThan(5)
    // run command is hidden when no runner is registered
    await expect(page.locator('[data-run-blocked]').first()).toBeVisible()
  })

  test('generated capability registry preserves non-public and blocked rows', async ({ page }) => {
    await open(page)
    const generatedRegistry = JSON.parse(
      await readFile('src/workbench-v2/model/generatedCapabilities.json', 'utf8'),
    ) as { capabilities: unknown[] }
    const table = page.locator('[data-wb2-capability-table]')
    await expect(table).toBeVisible()
    await expect(table.locator('tbody tr')).toHaveCount(generatedRegistry.capabilities.length)
    await expect(
      table.locator('[data-capability-id="contract.result_quantity_catalog"]'),
    ).toHaveAttribute('data-capability-status', 'bounded_public')
    await expect(
      table.locator('[data-capability-id="vv.opensees_level2"]'),
    ).toHaveAttribute('data-capability-status', 'blocked')
    await expect(
      table.locator('[data-capability-id="ai.solver_shadow_control"]'),
    ).toHaveAttribute('data-capability-status', 'shadow_only')
    await expect(
      table.locator('[data-capability-id="backend.nonlinear_sparse"]'),
    ).toHaveAttribute('data-capability-status', 'experimental')
    await expect(
      table.locator('[data-capability-id="material.fracture_energy_concrete"]'),
    ).toHaveAttribute('data-capability-status', 'experimental')
  })

  test('evidence reader is present (bundle may be unavailable)', async ({ page }) => {
    await open(page)
    await expect(page.getByText('Read-only evidence')).toBeVisible()
  })

  test('unconfigured durable job service is explicit and infers no solver state', async ({ page }) => {
    await open(page)
    const panel = page.locator('[data-job-service="unconfigured"]')
    await expect(panel).toBeVisible()
    await expect(panel.locator('[data-state="UNAVAILABLE"]')).toBeVisible()
    await expect(panel).toContainText(/solver state is not inferred/i)
  })

  test('unconfigured native Frame3D artifacts infer no numerical or release authority', async ({ page }) => {
    await open(page)
    const panel = page.locator('[data-native-frame-artifacts="unconfigured"]')
    await expect(panel).toBeVisible()
    await expect(panel.locator('[data-state="UNAVAILABLE"]')).toBeVisible()
    await expect(panel).toContainText(/resultir url is configured/i)
    await expect(panel).toContainText(/numerical state, comparison, design and release readiness are not inferred/i)
    await expect(panel.locator('[data-native-frame-release-authority]')).toHaveCount(0)
  })

  test('renders a verified same-origin ResultIR/ReportIR pair without promoting authority', async ({ page }) => {
    const result = nativeFrameResultFixture()
    const report = nativeFrameReportFixture(result)
    await page.addInitScript(() => {
      window.__STRUCTURAL_WORKBENCH_CONFIG__ = {
        nativeFrameResultUrl: '/evidence/native-frame-result.json',
        nativeFrameReportUrl: '/evidence/native-frame-report.json',
      }
    })
    await page.route('**/evidence/native-frame-result.json', (route) => route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify(result),
    }))
    await page.route('**/evidence/native-frame-report.json', (route) => route.fulfill({
      contentType: 'application/json',
      body: JSON.stringify(report),
    }))

    await open(page)

    const panel = page.locator('[data-native-frame-artifacts="ready"]')
    await expect(panel).toHaveAttribute('data-native-frame-integrity', 'pair_verified')
    await expect(panel.locator('[data-native-frame-result-ir="verified"]')).toBeVisible()
    await expect(panel.locator('[data-native-frame-report-ir="verified"]')).toBeVisible()
    await expect(panel.locator('[data-native-frame-result-authority]')).toContainText('bounded_candidate')
    await expect(panel.locator('[data-native-frame-comparison-authority]')).toHaveText('not_evaluated')
    await expect(panel.locator('[data-native-frame-release-authority]')).toHaveText('not_authoritative')
    await expect(panel.locator('[data-native-frame-extrema] tbody tr')).toHaveCount(3)
    await expect(panel.locator('[data-native-frame-claim-boundary]')).toContainText(/does not submit or rerun/i)
  })

  test('source-replays a same-origin external comparison while keeping validation unestablished', async ({ page }) => {
    const result = nativeFrameResultFixture()
    const report = nativeFrameReportFixture(result)
    const reference = nativeFrameReferenceFixture(result)
    const comparison = nativeFrameComparisonFixture(result, reference)
    await page.addInitScript(() => {
      window.__STRUCTURAL_WORKBENCH_CONFIG__ = {
        nativeFrameResultUrl: '/evidence/native-frame-result.json',
        nativeFrameReportUrl: '/evidence/native-frame-report.json',
        nativeFrameReferenceUrl: '/evidence/native-frame-reference.json',
        nativeFrameComparisonUrl: '/evidence/native-frame-comparison.json',
      }
    })
    for (const [path, body] of [
      ['native-frame-result.json', result],
      ['native-frame-report.json', report],
      ['native-frame-reference.json', reference],
      ['native-frame-comparison.json', comparison],
    ] as const) {
      await page.route(`**/evidence/${path}`, (route) => route.fulfill({
        contentType: 'application/json', body: JSON.stringify(body),
      }))
    }

    await open(page)

    const panel = page.locator('[data-native-frame-artifacts="ready"]')
    const attached = panel.locator('[data-native-frame-comparison="verified"]')
    await expect(attached).toHaveAttribute('data-native-frame-comparison-integrity', 'source_replayed')
    await expect(attached.locator('[data-native-frame-reference-ir="verified"]')).toContainText('synthetic_fixture')
    await expect(attached.locator('[data-native-frame-comparison-ir="verified"]')).toBeVisible()
    await expect(attached.locator('[data-native-frame-comparison-gate="passed"]')).toContainText('PASS')
    await expect(attached.locator('[data-native-frame-comparison-families] tbody tr')).toHaveCount(3)
    await expect(panel.locator('[data-native-frame-comparison-authority]')).toHaveText('bounded_cross_code_evaluation')
    await expect(attached.locator('[data-native-frame-external-validation]')).toHaveText('not_established')
    await expect(attached.locator('[data-native-frame-comparison-claim-boundary]')).toContainText(/operator-declared mapping/i)
  })

  test('loads a manifest-complete native job bundle through the read-only runtime configuration', async ({ page }) => {
    const result = nativeFrameResultFixture()
    const modelBytes = artifactBytes({ model_id: 'frame-alpha' })
    ;(result.bindings as Record<string, unknown>).model_content_hash = `sha256:${createHash('sha256').update(modelBytes).digest('hex')}`
    const resultHashBody = { ...result }
    delete resultHashBody.result_hash
    result.result_hash = fixtureHash(resultHashBody)
    const report = nativeFrameReportFixture(result)
    const resultBytes = artifactBytes(result)
    const reportBytes = artifactBytes(report)
    const html = '<!doctype html>\n<title>Frame report</title>'
    const identity = (body: Uint8Array | string) => `sha256:${createHash('sha256').update(body).digest('hex')}`
    const manifest = {
      schema_version: 'structural-native-linear-frame3d-workbench-bundle.v1',
      status: 'complete',
      artifacts: {
        model_ir: { path: 'model-ir.json', media_type: 'application/json', content_hash: identity(modelBytes), byte_length: modelBytes.byteLength },
        result_ir: { path: 'result-ir.json', media_type: 'application/json', content_hash: identity(resultBytes), byte_length: resultBytes.byteLength },
        report_ir: { path: 'report-ir.json', media_type: 'application/json', content_hash: identity(reportBytes), byte_length: reportBytes.byteLength },
        html: { path: 'report.html', media_type: 'text/html', content_hash: identity(html), byte_length: Buffer.byteLength(html) },
      },
      bindings: {
        model_content_hash: (result.bindings as Record<string, unknown>).model_content_hash,
        result_id: result.result_id,
        result_hash: result.result_hash,
        report_id: report.report_id,
        report_hash: report.report_hash,
      },
      claim_boundary: 'completed_no_overwrite_cli_artifact_bundle_not_job_or_workbench_execution_authority',
    }
    const manifestBody = Buffer.from(JSON.stringify(manifest))
    const jobView = {
      schema_version: 'structural-native-linear-frame3d-job-view.v1',
      job_id: 'job_0123456789abcdef0123456789abcdef',
      request_hash: `sha256:${'d'.repeat(64)}`,
      model_content_hash: (result.bindings as Record<string, unknown>).model_content_hash,
      revision: 2,
      status: 'succeeded',
      created_unix_ms: 1700000000000,
      updated_unix_ms: 1700000000002,
      bundle_manifest: {
        path: 'bundle/manifest.json',
        content_hash: identity(manifestBody),
        byte_length: manifestBody.byteLength,
      },
      error: null,
      service_profile: 'filesystem_append_only_single_host.v1',
      capabilities: {
        process_isolation: false,
        cancellation: false,
        resume: false,
        crash_recovery: false,
        multi_host: false,
      },
      solver_truth_owner: 'structural_native_runtime',
      result_authority: 'referenced_hash_bound_bundle_contract_only',
      claim_boundary: 'single_host_materialized_view_not_release_or_durable_worker_authority',
    }
    await page.addInitScript(() => {
      window.__STRUCTURAL_WORKBENCH_CONFIG__ = {
        nativeFrameJobUrl: '/evidence/native-job/view.json',
      }
    })
    await page.route('**/evidence/native-job/view.json', (route) => route.fulfill({
      contentType: 'application/json', body: JSON.stringify(jobView),
    }))
    await page.route('**/evidence/native-job/bundle/manifest.json', (route) => route.fulfill({
      contentType: 'application/json', body: manifestBody,
    }))
    await page.route('**/evidence/native-job/bundle/result-ir.json', (route) => route.fulfill({
      contentType: 'application/json', body: Buffer.from(resultBytes),
    }))
    await page.route('**/evidence/native-job/bundle/model-ir.json', (route) => route.fulfill({
      contentType: 'application/json', body: Buffer.from(modelBytes),
    }))
    await page.route('**/evidence/native-job/bundle/report-ir.json', (route) => route.fulfill({
      contentType: 'application/json', body: Buffer.from(reportBytes),
    }))
    await page.route('**/evidence/native-job/bundle/report.html', (route) => route.fulfill({
      contentType: 'text/html', body: html,
    }))

    await open(page)

    const panel = page.locator('[data-native-frame-artifacts="ready"]')
    await expect(panel).toHaveAttribute('data-native-frame-integrity', 'bundle_verified')
    await expect(panel.locator('[data-native-frame-result-ir="verified"]')).toBeVisible()
    await expect(panel.locator('[data-native-frame-report-ir="verified"]')).toBeVisible()
    await expect(panel.locator('[data-native-frame-release-authority]')).toHaveText('not_authoritative')
  })

  test('with no published bundle, evidence reader shows only unavailable — readiness is not inferred', async ({ page }) => {
    await open(page)
    const evidence = page.locator('.wb2-evidence')
    await expect(evidence).toBeVisible()

    // When the bundle manifest cannot be fetched, the panel must surface a
    // bundle-missing / unavailable marker rather than rendering source cards.
    const missing = evidence.locator('[data-bundle-missing], [data-wb2-unavailable]')
    const cards = evidence.locator('[data-evidence-id]')

    const cardCount = await cards.count()
    if (cardCount === 0) {
      // No bundle published in this build: must be explicitly unavailable.
      await expect(missing.first()).toBeVisible()
      // Nothing may claim a positive release-ready verdict without evidence.
      await expect(evidence.locator('[data-release-ready="true"]')).toHaveCount(0)
    } else {
      // A bundle is present: every source card must carry an explicit gate
      // state and never an inferred/blank readiness.
      for (let i = 0; i < cardCount; i += 1) {
        const gate = await cards.nth(i).getAttribute('data-gate')
        expect(['ready', 'blocked', 'missing', 'unavailable']).toContain(gate)
      }
    }
  })
})

test.describe('Workbench v2 — commercial layout, review draft, benchmarks', () => {
  test('left navigation lists the commercial sections in order', async ({ page }) => {
    await open(page)
    await expect(page.locator('[data-wb2-nav]')).toBeVisible()
    for (const id of ['wb2-sec-project', 'wb2-sec-model', 'wb2-sec-analysis', 'wb2-sec-run', 'wb2-sec-results', 'wb2-sec-capabilities', 'wb2-sec-evidence', 'wb2-sec-benchmarks', 'wb2-sec-review', 'wb2-sec-export']) {
      await expect(page.locator(`[data-wb2-nav-link="${id}"]`)).toBeVisible()
    }
  })

  test('Compare section is an honest placeholder, never synthesized', async ({ page }) => {
    await open(page)
    const compare = page.locator('#wb2-sec-compare')
    await expect(compare.locator('[data-wb2-unavailable]')).toBeVisible()
  })

  test('reviewer draft persists locally and never becomes an automated verdict', async ({ page }) => {
    await open(page)
    // Automated verdict stays UNAVAILABLE.
    await expect(page.locator('[data-state="UNAVAILABLE"]').first()).toBeVisible()
    const draft = page.locator('[data-wb2-review-draft]')
    await expect(draft).toBeVisible()
    await draft.locator('[data-wb2-decision="review"]').click()
    await draft.locator('[data-wb2-review-reviewer]').fill('QA')
    await expect(draft.locator('[data-wb2-review-state="review"]')).toBeVisible()
    await expect(draft.locator('[data-wb2-persistence-display="Saved locally"]')).toBeVisible()
    // Reload: the draft is restored from localStorage for the same source commit.
    await page.reload({ waitUntil: 'load' })
    await page.locator('[data-wb2-root]').waitFor({ state: 'visible' })
    await expect(page.locator('[data-wb2-review-reviewer]')).toHaveValue('QA')
    await expect(page.locator('[data-wb2-review-state="review"]')).toBeVisible()
    await expect(page.locator('[data-wb2-persistence-display="Saved locally"]')).toBeVisible()

    const downloadPromise = page.waitForEvent('download')
    await page.locator('[data-wb2-export]').click()
    const download = await downloadPromise
    const downloadPath = await download.path()
    expect(downloadPath).not.toBeNull()
    const bundle = JSON.parse(await readFile(downloadPath!, 'utf8')) as {
      reviewer_draft: { reviewer: string; decision: string }
      reviewer_draft_persistence: { display_status: string }
    }
    expect(bundle.reviewer_draft).toMatchObject({ reviewer: 'QA', decision: 'review' })
    expect(bundle.reviewer_draft_persistence.display_status).toBe('Saved locally')
  })

  test('quota failure retains and exports the exact draft as Session-only', async ({ page }) => {
    await page.addInitScript(() => {
      const nativeSetItem = Storage.prototype.setItem
      Storage.prototype.setItem = function setItem(key: string, value: string): void {
        if (String(key).startsWith('wb2-review-draft:')) {
          throw new DOMException('SECRET_QUOTA_DETAIL', 'QuotaExceededError')
        }
        nativeSetItem.call(this, key, value)
      }
    })
    await open(page)

    const draft = page.locator('[data-wb2-review-draft]')
    await draft.locator('[data-wb2-review-reviewer]').fill('SESSION-QA')
    const persistence = draft.locator('[data-wb2-persistence-display="Session-only"]')
    await expect(persistence).toBeVisible()
    await expect(persistence).toHaveAttribute('data-wb2-persistence', 'memory_only')
    await expect(persistence).toHaveAttribute('data-wb2-persistence-error-code', 'review_draft_storage_quota_exceeded')
    await expect(draft.locator('[data-wb2-review-reviewer]')).toHaveValue('SESSION-QA')
    await expect(draft.locator('[data-wb2-review-meta]')).not.toContainText('Saved locally')
    await expect(draft).not.toContainText('SECRET_QUOTA_DETAIL')

    const downloadPromise = page.waitForEvent('download')
    await page.locator('[data-wb2-export]').click()
    const download = await downloadPromise
    const downloadPath = await download.path()
    expect(downloadPath).not.toBeNull()
    const bundle = JSON.parse(await readFile(downloadPath!, 'utf8')) as {
      reviewer_draft: { reviewer: string }
      reviewer_draft_persistence: { display_status: string; persistence: string; error_code: string }
    }
    expect(bundle.reviewer_draft.reviewer).toBe('SESSION-QA')
    expect(bundle.reviewer_draft_persistence).toMatchObject({
      display_status: 'Session-only',
      persistence: 'memory_only',
      error_code: 'review_draft_storage_quota_exceeded',
    })
  })

  test('read denial is surfaced as Storage unavailable without leaking exception text', async ({ page }) => {
    await page.addInitScript(() => {
      const nativeGetItem = Storage.prototype.getItem
      Storage.prototype.getItem = function getItem(key: string): string | null {
        if (String(key).startsWith('wb2-review-draft:')) {
          throw new DOMException('SECRET_STORAGE_DETAIL', 'SecurityError')
        }
        return nativeGetItem.call(this, key)
      }
    })
    await open(page)

    const draft = page.locator('[data-wb2-review-draft]')
    const persistence = draft.locator('[data-wb2-persistence-display="Storage unavailable"]')
    await expect(persistence).toBeVisible()
    await expect(persistence).toHaveAttribute('data-wb2-persistence', 'none')
    await expect(persistence).toHaveAttribute('data-wb2-persistence-error-code', 'review_draft_storage_access_denied')
    await expect(draft).not.toContainText('SECRET_STORAGE_DETAIL')
  })

  test('serialization failure keeps the previous validated draft', async ({ page }) => {
    await open(page)
    const draft = page.locator('[data-wb2-review-draft]')
    await draft.locator('[data-wb2-review-reviewer]').fill('SAFE-QA')
    await expect(draft.locator('[data-wb2-persistence-display="Saved locally"]')).toBeVisible()

    await page.evaluate(() => {
      Date.prototype.toISOString = function toISOString(): string {
        throw new Error('SECRET_TIMESTAMP_DETAIL')
      }
    })
    await draft.locator('[data-wb2-decision="pass"]').click()

    const persistence = draft.locator('[data-wb2-persistence-display="Previous state retained"]')
    await expect(persistence).toBeVisible()
    await expect(persistence).toHaveAttribute('data-wb2-persistence-error-code', 'review_draft_serialization_failed')
    await expect(draft.locator('[data-wb2-review-reviewer]')).toHaveValue('SAFE-QA')
    await expect(draft.locator('[data-wb2-decision="pass"]')).toHaveAttribute('aria-checked', 'false')
    await expect(draft).not.toContainText('SECRET_TIMESTAMP_DETAIL')
  })

  test('benchmark cards expose copy buttons and a geometry-only exclusion', async ({ page }) => {
    await open(page)
    await expect(page.locator('[data-wb2-copy]').first()).toBeVisible()
    await expect(page.locator('[data-geometry-excluded-count]')).toBeVisible()
    const geo = page.locator('[data-bench-id][data-geometry-only="true"]')
    if (await geo.count()) {
      await expect(geo.first().locator('[data-geometry-excluded]')).toBeVisible()
    }
  })
})

test.describe('Workbench v2 — run monitor, viewer focus, richer export', () => {
  test('run monitor reflects the converged sample with progress and within-tolerance', async ({ page }) => {
    await open(page)
    await page.locator('[data-wb2-case="converged"]').click()
    const monitor = page.locator('[data-run-monitor]')
    await expect(monitor).toHaveAttribute('data-run-monitor', 'converged')
    await expect(monitor.locator('[data-run-progress]')).toBeVisible()
    await expect(monitor.locator('[data-run-within-tol="true"]')).toBeVisible()
  })

  test('run monitor reports UNAVAILABLE for the no-convergence sample, inferring nothing', async ({ page }) => {
    await open(page)
    await page.locator('[data-wb2-case="unavailable"]').click()
    const monitor = page.locator('[data-run-monitor]')
    await expect(monitor).toHaveAttribute('data-run-monitor', 'unavailable')
    await expect(monitor.locator('[data-wb2-unavailable]')).toBeVisible()
    await expect(monitor.locator('[data-run-progress]')).toHaveCount(0)
  })

  test('member focus round-trips to the inspector and clears', async ({ page }) => {
    await open(page)
    const inspector = page.locator('[data-wb2-member-inspector]')
    await expect(inspector).toBeVisible()
    await inspector.locator('[data-wb2-member-input]').fill('C12')
    await inspector.locator('[data-wb2-member-focus]').click()
    await expect(page.locator('[data-wb2-selected-member]')).toHaveText('C12')
    await page.locator('[data-wb2-member-clear]').click()
    await expect(page.locator('[data-wb2-selected-member]')).toHaveText(/none selected/i)
  })

  test('export panel lists blockers/comparison counts and selecting a benchmark updates the count', async ({ page }) => {
    await open(page)
    const exportContents = page.locator('.wb2-export-contents')
    await expect(exportContents).toContainText(/selected comparison rows \(0\)/i)
    const compare = page.locator('[data-bench-compare]').first()
    await compare.scrollIntoViewIfNeeded()
    await compare.check()
    await expect(exportContents).toContainText(/selected comparison rows \(1\)/i)
  })
})

test.describe('Workbench v2 — compare set & live mode', () => {
  test('compare set is empty until a benchmark is added, then shows a row with status', async ({ page }) => {
    await open(page)
    const compare = page.locator('[data-compare-panel]')
    await expect(compare.locator('[data-compare-empty]')).toBeVisible()
    const box = page.locator('[data-bench-compare]').first()
    await box.scrollIntoViewIfNeeded()
    await box.check()
    await expect(compare.locator('[data-compare-table]')).toBeVisible()
    const row = compare.locator('[data-compare-row]').first()
    await expect(row).toBeVisible()
    // Status must be an explicit ready/blocked state, never a synthesized delta.
    const status = await row.locator('[data-compare-status]').getAttribute('data-compare-status')
    expect(['ready', 'blocked']).toContain(status)
  })

  test('compare clear resets the set', async ({ page }) => {
    await open(page)
    const box = page.locator('[data-bench-compare]').first()
    await box.scrollIntoViewIfNeeded()
    await box.check()
    const compare = page.locator('[data-compare-panel]')
    await expect(compare.locator('[data-compare-table]')).toBeVisible()
    await compare.locator('[data-compare-clear]').click()
    await expect(compare.locator('[data-compare-empty]')).toBeVisible()
  })

  test('live mode reports MISSING when no case is published — nothing is fabricated', async ({ page }) => {
    await open(page)
    await page.locator('[data-wb2-provider="live"]').click()
    // No bundle is committed/served in the build, so the live case is unavailable.
    await expect(page.locator('#wb2-sec-project [data-wb2-unavailable]')).toBeVisible()
    // The data-mode badge reflects LIVE even though the case is missing.
    await expect(page.locator('[data-wb2-provider="live"]')).toHaveAttribute('aria-pressed', 'true')
  })
})

test.describe('Workbench v2 — viewer, mobile, a11y', () => {
  test('embeds the structure viewer iframe with a deep-linkable src', async ({ page }) => {
    await open(page)
    const iframe = page.locator('.wb2-viewport-iframe')
    await expect(iframe).toHaveAttribute('src', /structure-viewer\/index\.html/)
    const viewer = page.frameLocator('.wb2-viewport-iframe')
    await expect(viewer.locator('body[data-si-shell="product"]')).toBeVisible({ timeout: 30000 })
    await expect(viewer.locator('body[data-viewer-workflow="model"]')).toBeVisible()
    await expect(viewer.locator('[data-wb2-root]')).toHaveCount(0)
  })

  test('is keyboard operable and has a skip link on mobile', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 720 })
    await open(page)
    await page.keyboard.press('Tab')
    const active = await page.evaluate(() => document.activeElement?.className ?? '')
    expect(active).toContain('wb2-skip-link')
  })
})
