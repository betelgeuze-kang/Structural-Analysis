import { expect, test, type Locator, type Page } from '@playwright/test'
import { readFile } from 'node:fs/promises'

const baseUrl = process.env.WORKBENCH_V2_BASE_URL ?? 'http://127.0.0.1:4373'
const routeUrl = `${baseUrl}/#/workbench-v2`

function liveCase(): Record<string, unknown> {
  return {
    schemaVersion: 'workbench-case.v2',
    provenance: {
      sourcePath: 'tests/engineering-value-case.json',
      sourceSha256: `sha256:${'e'.repeat(64)}`,
      sourceCommitSha: 'engineering-value-state-test',
      engineVersion: 'test-engine',
      generatedAt: '2026-07-27T00:00:00Z',
    },
    model: {
      unitSystem: 'SI',
      coordinateSystem: 'global_xyz',
    },
    analysis: {
      type: 'nonlinear_static',
      solver: 'test-solver',
      converged: true,
      status: 'converged',
    },
    residualHistory: [
      { iteration: 1, residual: 0.25 },
    ],
  }
}

async function openLiveCase(page: Page, payload: Record<string, unknown>, body?: string): Promise<void> {
  await page.route('**/evidence/workbench-case.json', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json; charset=utf-8',
      body: body ?? JSON.stringify(payload),
    })
  })
  await page.goto(routeUrl, { waitUntil: 'load', timeout: 30000 })
  await page.locator('[data-wb2-root]').waitFor({ state: 'visible', timeout: 15000 })
  await page.locator('[data-wb2-provider="live"]').click()
  await expect(page.getByText('Case & provenance')).toBeVisible()
}

function valueFor(panel: Locator, label: string): Locator {
  const escaped = label.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  return panel
    .locator('dt')
    .filter({ hasText: new RegExp(`^${escaped}$`) })
    .locator('xpath=following-sibling::dd[1]//*[@data-engineering-value-state]')
}

test.describe('Workbench v2 — explicit engineering value states', () => {
  test('missing engineering numbers stay unavailable and never become synthetic zeroes or ones', async ({ page }) => {
    await openLiveCase(page, liveCase())

    const summary = page.locator('#wb2-sec-project')
    for (const label of ['Nodes', 'Elements', 'DOF']) {
      await expect(valueFor(summary, label)).toHaveAttribute('data-engineering-value-state', 'unavailable')
      await expect(valueFor(summary, label)).toHaveText('UNAVAILABLE')
    }

    const results = page.locator('[data-result-verdict]')
    for (const label of ['Final residual', 'Tolerance', 'Iterations', 'Load scale']) {
      await expect(valueFor(results, label)).toHaveAttribute('data-engineering-value-state', 'unavailable')
      await expect(valueFor(results, label)).toHaveText('UNAVAILABLE')
    }
    await expect(results.locator('[data-result-within-tol="unavailable"]')).toBeVisible()

    const monitor = page.locator('[data-run-monitor]')
    await expect(monitor.locator('[data-run-progress]')).toHaveCount(0)
    await expect(valueFor(monitor, 'Final rel. increment')).toHaveAttribute(
      'data-engineering-value-state',
      'unavailable',
    )

    const scaling = page.locator('[data-equation-scaling-6dof]')
    for (const label of [
      'Reference force',
      'Characteristic length',
      'Scaled residual norm',
      'Scaled tangent condition',
      'Scaling hash',
    ]) {
      await expect(valueFor(scaling, label)).toHaveAttribute('data-engineering-value-state', 'unavailable')
      await expect(valueFor(scaling, label)).toHaveText('UNAVAILABLE')
    }

    const residualRow = page.locator('#wb2-sec-results .wb2-table tbody tr').first()
    const cells = residualRow.locator('[data-engineering-value-state]')
    await expect(cells.nth(0)).toHaveAttribute('data-engineering-value-state', 'available')
    await expect(cells.nth(1)).toHaveAttribute('data-engineering-value-state', 'available')
    await expect(cells.nth(2)).toHaveAttribute('data-engineering-value-state', 'unavailable')
    await expect(cells.nth(2)).toHaveText('UNAVAILABLE')
    await expect(cells.nth(3)).toHaveAttribute('data-engineering-value-state', 'unavailable')
    await expect(cells.nth(3)).toHaveText('UNAVAILABLE')
    await expect(page.locator('[data-wb2-tol-line]')).toHaveCount(0)
  })

  test('malformed, non-finite, and wrong-domain numbers remain invalid', async ({ page }) => {
    const payload = liveCase()
    payload.model = {
      unitSystem: 'SI',
      coordinateSystem: 'global_xyz',
      nodeCount: -1,
      elementCount: 1.5,
      dofCount: '12',
    }
    payload.analysis = {
      type: 'nonlinear_static',
      solver: 'test-solver',
      converged: true,
      loadScale: '1',
      iterationCount: -1,
      residualTolerance: 0,
      finalNormalizedResidual: -0.1,
      finalRelativeIncrement: 'NONFINITE',
      equation_scaling_6dof: {
        reference_force: 0,
        characteristic_length: -1,
        translation_residual_norm: -1,
        rotation_residual_norm: 'bad',
        scaled_residual_norm: -1,
        translation_increment_norm: -1,
        rotation_increment_norm: -1,
        scaled_increment_norm: -1,
        scaled_tangent_condition: 0.5,
        scaling_hash: 'not-a-sha256',
      },
      status: 'converged',
    }
    payload.residualHistory = [
      { iteration: -1, residual: '0.25', relativeIncrement: -0.2, alpha: null },
    ]
    const body = JSON.stringify(payload).replace(
      '"finalRelativeIncrement":"NONFINITE"',
      '"finalRelativeIncrement":1e999',
    )

    await openLiveCase(page, payload, body)

    const summary = page.locator('#wb2-sec-project')
    for (const label of ['Nodes', 'Elements', 'DOF']) {
      await expect(valueFor(summary, label)).toHaveAttribute('data-engineering-value-state', 'invalid')
      await expect(valueFor(summary, label)).toHaveText('INVALID')
    }

    const analysis = page.locator('#wb2-sec-analysis')
    for (const label of [
      'Load scale',
      'Iterations',
      'Residual tolerance',
      'Final normalized residual',
      'Final relative increment',
    ]) {
      await expect(valueFor(analysis, label)).toHaveAttribute('data-engineering-value-state', 'invalid')
      await expect(valueFor(analysis, label)).toHaveText('INVALID')
    }

    const residualCells = page.locator('#wb2-sec-results .wb2-table tbody tr').first()
      .locator('[data-engineering-value-state]')
    await expect(residualCells).toHaveCount(4)
    for (let index = 0; index < 4; index += 1) {
      await expect(residualCells.nth(index)).toHaveAttribute('data-engineering-value-state', 'invalid')
      await expect(residualCells.nth(index)).toHaveText('INVALID')
    }
    await expect(page.locator('[data-result-within-tol="unavailable"]')).toBeVisible()
    await expect(page.locator('[data-wb2-residual-chart]')).toHaveCount(0)
    const scaling = page.locator('[data-equation-scaling-6dof]')
    for (const label of [
      'Reference force',
      'Characteristic length',
      'Translation residual norm',
      'Rotation residual norm',
      'Scaled residual norm',
      'Translation increment norm',
      'Rotation increment norm',
      'Scaled increment norm',
      'Scaled tangent condition',
      'Scaling hash',
    ]) {
      await expect(valueFor(scaling, label)).toHaveAttribute('data-engineering-value-state', 'invalid')
      await expect(valueFor(scaling, label)).toHaveText('INVALID')
    }
  })

  test('explicit zeroes and ones remain available even when convergence itself is unavailable', async ({ page }) => {
    const payload = liveCase()
    payload.model = {
      unitSystem: 'SI',
      coordinateSystem: 'global_xyz',
      nodeCount: 0,
      elementCount: 0,
      dofCount: 0,
    }
    payload.analysis = {
      type: 'nonlinear_static',
      solver: 'test-solver',
      loadScale: 1,
      iterationCount: 0,
      residualTolerance: 1,
      finalNormalizedResidual: 0,
      finalRelativeIncrement: 0,
      equation_scaling_6dof: {
        reference_force: 1,
        characteristic_length: 1,
        translation_residual_norm: 0,
        rotation_residual_norm: 0,
        scaled_residual_norm: 0,
        translation_increment_norm: 0,
        rotation_increment_norm: 0,
        scaled_increment_norm: 0,
        scaled_tangent_condition: 1,
        scaling_hash: `sha256:${'0'.repeat(64)}`,
      },
    }
    payload.residualHistory = [
      { iteration: 0, residual: 0, relativeIncrement: 0, alpha: 1 },
    ]

    await openLiveCase(page, payload)

    await expect(page.locator('[data-result-verdict]')).toHaveAttribute('data-result-verdict', 'unavailable')
    const availableValues = page.locator(
      '#wb2-sec-project [data-engineering-value-state], '
      + '#wb2-sec-analysis [data-engineering-value-state], '
      + '#wb2-sec-results .wb2-table [data-engineering-value-state]',
    )
    expect(await availableValues.count()).toBeGreaterThan(0)
    for (let index = 0; index < await availableValues.count(); index += 1) {
      await expect(availableValues.nth(index)).toHaveAttribute('data-engineering-value-state', 'available')
    }
    await expect(valueFor(page.locator('#wb2-sec-analysis'), 'Load scale')).toHaveText('1')
    await expect(valueFor(page.locator('#wb2-sec-analysis'), 'Final normalized residual')).toHaveText('0')
    const scaling = page.locator('[data-equation-scaling-6dof]')
    for (const label of [
      'Reference force',
      'Characteristic length',
      'Translation residual norm',
      'Rotation residual norm',
      'Scaled residual norm',
      'Translation increment norm',
      'Rotation increment norm',
      'Scaled increment norm',
      'Scaled tangent condition',
      'Scaling hash',
    ]) {
      await expect(valueFor(scaling, label)).toHaveAttribute('data-engineering-value-state', 'available')
    }
  })

  test('explicit unsupported evidence remains distinct from unavailable and invalid', async ({ page }) => {
    const payload = liveCase()
    payload.model = {
      unitSystem: 'SI',
      coordinateSystem: 'global_xyz',
      nodeCount: { status: 'unsupported', reason: 'producer does not expose mesh counts' },
      elementCount: 0,
      dofCount: 0,
    }
    payload.analysis = {
      type: 'nonlinear_static',
      solver: 'test-solver',
      converged: true,
      loadScale: { status: 'unsupported', reason: 'load control is not supported' },
      iterationCount: 1,
      residualTolerance: 1e-6,
      finalNormalizedResidual: 0,
      finalRelativeIncrement: 0,
    }
    payload.residualHistory = [
      {
        iteration: 1,
        residual: 0,
        relativeIncrement: { status: 'unsupported', reason: 'increment trace disabled' },
        alpha: 1,
      },
    ]

    await openLiveCase(page, payload)

    const nodeCount = valueFor(page.locator('#wb2-sec-project'), 'Nodes')
    await expect(nodeCount).toHaveAttribute('data-engineering-value-state', 'unsupported')
    await expect(nodeCount).toHaveText('UNSUPPORTED')
    const loadScale = valueFor(page.locator('#wb2-sec-analysis'), 'Load scale')
    await expect(loadScale).toHaveAttribute('data-engineering-value-state', 'unsupported')
    await expect(loadScale).toHaveText('UNSUPPORTED')
    const residualCells = page.locator('#wb2-sec-results .wb2-table tbody tr').first()
      .locator('[data-engineering-value-state]')
    await expect(residualCells.nth(2)).toHaveAttribute('data-engineering-value-state', 'unsupported')
    await expect(residualCells.nth(2)).toHaveText('UNSUPPORTED')
  })

  test('history iteration order, duplicates, and alpha outside (0, 1] are invalid', async ({ page }) => {
    const payload = liveCase()
    payload.residualHistory = [
      { iteration: 2, residual: 0.3, relativeIncrement: 0.2, alpha: 1 },
      { iteration: 2, residual: 0.2, relativeIncrement: 0.1, alpha: 0 },
      { iteration: 1, residual: 0.1, relativeIncrement: 0.05, alpha: 1.01 },
    ]

    await openLiveCase(page, payload)

    const rows = page.locator('#wb2-sec-results .wb2-table tbody tr')
    await expect(rows).toHaveCount(3)
    await expect(rows.nth(0).locator('[data-engineering-value-state]').nth(0))
      .toHaveAttribute('data-engineering-value-state', 'available')
    for (const index of [1, 2]) {
      const cells = rows.nth(index).locator('[data-engineering-value-state]')
      await expect(cells.nth(0)).toHaveAttribute('data-engineering-value-state', 'invalid')
      await expect(cells.nth(3)).toHaveAttribute('data-engineering-value-state', 'invalid')
    }
  })

  test('nested unknown fields survive normalization and export', async ({ page }) => {
    const payload = liveCase()
    payload.provenance = {
      ...(payload.provenance as Record<string, unknown>),
      producerExtension: { authority: 'candidate' },
    }
    payload.model = {
      ...(payload.model as Record<string, unknown>),
      meshExtension: { partition: 'p0' },
    }
    payload.analysis = {
      ...(payload.analysis as Record<string, unknown>),
      solverExtension: { backend: 'test' },
      equation_scaling_6dof: {
        scalingExtension: { policy: 'custom' },
      },
    }
    payload.residualHistory = [
      {
        iteration: 1,
        residual: 0.25,
        rowExtension: { source: 'solver-trace' },
      },
    ]

    await openLiveCase(page, payload)
    const downloadPromise = page.waitForEvent('download')
    await page.locator('[data-wb2-export]').click()
    const download = await downloadPromise
    const path = await download.path()
    expect(path).not.toBeNull()
    const bundle = JSON.parse(await readFile(path as string, 'utf8')) as Record<string, any>

    expect(bundle.provenance.producerExtension).toEqual({ authority: 'candidate' })
    expect(bundle.model.meshExtension).toEqual({ partition: 'p0' })
    expect(bundle.analysis.solverExtension).toEqual({ backend: 'test' })
    expect(bundle.analysis.equationScaling6DOF.scalingExtension).toEqual({ policy: 'custom' })
    expect(bundle.residual_history[0].rowExtension).toEqual({ source: 'solver-trace' })
  })

  test('a missing source checksum remains a hard block', async ({ page }) => {
    const payload = liveCase()
    payload.provenance = {
      sourcePath: 'tests/no-checksum.json',
      sourceCommitSha: 'no-checksum',
      engineVersion: 'test-engine',
      generatedAt: '2026-07-27T00:00:00Z',
    }

    await page.route('**/evidence/workbench-case.json', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json; charset=utf-8',
        body: JSON.stringify(payload),
      })
    })
    await page.goto(routeUrl, { waitUntil: 'load', timeout: 30000 })
    await page.locator('[data-wb2-root]').waitFor({ state: 'visible', timeout: 15000 })
    await page.locator('[data-wb2-provider="live"]').click()

    await expect(page.locator('#wb2-sec-project [data-wb2-unavailable]')).toContainText(
      /provenance\.sourceSha256 is missing/,
    )
    await expect(page.getByText('Case & provenance')).toHaveCount(0)
  })

  test('a non-canonical source checksum is INVALID and remains a hard block', async ({ page }) => {
    const payload = liveCase()
    ;(payload.provenance as Record<string, unknown>).sourceSha256 = `sha256:${'A'.repeat(64)}`

    await page.route('**/evidence/workbench-case.json', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json; charset=utf-8',
        body: JSON.stringify(payload),
      })
    })
    await page.goto(routeUrl, { waitUntil: 'load', timeout: 30000 })
    await page.locator('[data-wb2-root]').waitFor({ state: 'visible', timeout: 15000 })
    await page.locator('[data-wb2-provider="live"]').click()

    await expect(page.locator('#wb2-sec-project [data-wb2-unavailable]')).toContainText(
      /provenance\.sourceSha256 is INVALID/,
    )
    await expect(page.getByText('Case & provenance')).toHaveCount(0)
  })
})
