import { expect, test } from '@playwright/test'
import { createHash } from 'node:crypto'
import { loadDesignComparison } from '../../src/workbench-v2/model/designComparisonProvider'
import { validateDesignComparisonManifest, validateDesignComparisonReport } from '../../src/workbench-v2/model/designComparisonSchema'
import { designComparisonFixture, designHash } from './designComparisonFixture'
import { designHistoryComparisonFixture, removeVerifiedHistory } from './designHistoryComparisonFixture'

const url = 'https://example.test/comparisons/manifest.json'
const bytes = (report: unknown) => new TextEncoder().encode(JSON.stringify(report))
const digest = (body: Uint8Array) => `sha256:${createHash('sha256').update(body).digest('hex')}`
function manifest(report = designComparisonFixture()) {
  const body = bytes(report)
  return { schema_version: 'rc-fiber-design-comparison-bundle.v1', source_revision: 'a'.repeat(40), report_file: 'comparison.json', report_byte_length: body.length, report_sha256: digest(body), report_hash: report.report_hash, experiment_identity_hash: report.experiment_identity_hash }
}

test('physical comparison uses one verified report object for all displayed numbers', () => {
  const report = designComparisonFixture()
  const checkedManifest = validateDesignComparisonManifest(manifest(report))
  const checked = validateDesignComparisonReport(report, checkedManifest)
  expect(checked).toBe(report)
  expect(checked.rows[1].material_estimate?.total).toBe(364)
})

test('history comparison rejects an intermediate violation even when terminal limits pass', () => {
  const report = designHistoryComparisonFixture()
  const checked = validateDesignComparisonReport(report, validateDesignComparisonManifest(manifest(report)))
  expect(checked.rows.every(row => row.terminal_limit_status === 'pass')).toBe(true)
  expect(checked.rows[1].history_limit_status).toBe('fail')
  expect(checked.rows[1].performance?.history_maximum_absolute_fiber_strain).toBe(0.0003)
  expect(checked.selection.candidate_id).toBe('baseline')
  expect(checked.selection.eligible_count).toBe(1)
})

for (const [name, mutate] of [
  ['missing history limits', (r: any) => { delete r.identity.history_limits }],
  ['missing sidecar', (r: any) => { r.rows[1].response_history = null }],
  ['unknown sidecar schema', (r: any) => { r.rows[1].response_history.schema_version = 'unknown.v1' }],
  ['wrong parent result hash', (r: any) => { r.rows[1].response_history.source_result_hash = designHash('0') }],
  ['wrong parent model hash', (r: any) => { r.rows[1].response_history.canonical_model_checksum = designHash('0') }],
  ['detached history hash', (r: any) => { r.rows[1].response_history.history_hash = designHash('0') }],
  ['wrong adapter source', (r: any) => { r.rows[1].response_history.history.bindings.source_result_adapter_hash = designHash('0') }],
  ['wrong checkpoint chain', (r: any) => { r.rows[1].response_history.history.bindings.checkpoint_chain_hash = designHash('0') }],
  ['partial epoch coverage', (r: any) => { r.rows[1].response_history.history.steps.shift() }],
  ['duplicate epoch', (r: any) => { r.rows[1].response_history.history.steps[0].epoch = 2 }],
  ['wrong target factor', (r: any) => { r.rows[1].response_history.history.steps[0].target_load_factor = 0.75 }],
  ['wrong accepted parent', (r: any) => { r.rows[1].response_history.history.steps[1].bindings.parent_checkpoint_state_hash = designHash('f') }],
  ['detached step receipt', (r: any) => { r.rows[1].response_history.history.steps[0].bindings.step_receipt_hash = designHash('f') }],
  ['detached Newton source', (r: any) => { r.rows[1].response_history.history.steps[0].bindings.source_solution_data_hash = designHash('f') }],
  ['terminal array mismatch', (r: any) => { r.rows[1].response_history.history.steps[1].fiber_results[0].stress_MPa = 21 }],
  ['missing displacement source', (r: any) => { r.rows[1].response_history.history.steps[0].displacement_canonical_si = [] }],
  ['missing fiber label in every source', (r: any) => { delete r.rows[1].result.fiber_results[0].fiber_id; r.rows[1].response_history.history.steps.forEach((step: any) => { delete step.fiber_results[0].fiber_id }) }],
  ['detached strain recovery array', (r: any) => { r.rows[1].response_history.history.steps[0].recovery_arrays.fiber_strain[0] = 0.0001 }],
  ['wrong step envelope', (r: any) => { r.rows[1].response_history.history.steps[0].envelope.maximum_translation_m = 0.001 }],
  ['wrong governing epoch', (r: any) => { r.rows[1].response_history.history.envelope.governing_translation.epoch = 2 }],
  ['wrong strain envelope', (r: any) => { r.rows[1].response_history.history.envelope.maximum_absolute_fiber_strain = 0.0001 }],
  ['wrong displayed history', (r: any) => { r.rows[1].performance.history_maximum_translation_m = 0.001 }],
  ['missing verification', (r: any) => { delete r.rows[1].full_history_verification_pass }],
  ['false history safe selection', (r: any) => { r.rows[1].history_limit_status = 'pass'; r.selection.candidate_id = 'narrow'; r.selection.eligible_count = 2 }],
  ['between-step authority', (r: any) => { r.rows[1].response_history.history.scope.between_step_extrema_verified = true }],
  ['genesis substitution', (r: any) => { r.rows[1].response_history.history.scope.genesis_included = true }],
] as const) {
  test(`history comparison rejects ${name}`, () => {
    const report = designHistoryComparisonFixture()
    const declared = validateDesignComparisonManifest(manifest(report))
    mutate(report)
    expect(() => validateDesignComparisonReport(report, declared)).toThrow()
  })
}

test('history comparison preserves terminal numbers when history recovery is unavailable', () => {
  const report = designHistoryComparisonFixture()
  const terminal = structuredClone(report.rows[1].result)
  removeVerifiedHistory(report, 1)
  const checked = validateDesignComparisonReport(report, validateDesignComparisonManifest(manifest(report)))
  expect(checked.rows[1].result).toEqual(terminal)
  expect(checked.rows[1].full_reference_verification_pass).toBe(true)
  expect(checked.rows[1].performance?.terminal_maximum_translation_m).toBe(0.001)
  expect(checked.rows[1].history_limit_status).toBe('unavailable')
  expect(checked.rows[1].performance?.history_maximum_translation_m).toBeUndefined()
  expect(checked.selection.candidate_id).toBe('baseline')
})

test('history comparison requires verified baseline history for a relative selection', () => {
  const report = designHistoryComparisonFixture()
  removeVerifiedHistory(report, 0)
  const checked = validateDesignComparisonReport(report, validateDesignComparisonManifest(manifest(report)))
  expect(checked.rows[0].full_reference_verification_pass).toBe(true)
  expect(checked.selection.candidate_id).toBeNull()
})

test('history comparison cannot be silently presented as a terminal-only v1 report', () => {
  const report = designHistoryComparisonFixture()
  report.schema_version = report.identity.schema_version = 'public-rc-fiber-design-comparison.v1'
  expect(() => validateDesignComparisonReport(report, validateDesignComparisonManifest(manifest(report)))).toThrow()
})

test('history comparison computes translation magnitude at one committed node state', () => {
  const report = designHistoryComparisonFixture()
  const history = report.rows[1].response_history.history
  const step = history.steps[0]
  step.node_displacements[1].UX_m = 0.0024
  step.node_displacements[1].UY_m = 0.0018
  step.displacement_canonical_si[6] = 0.0024
  step.displacement_canonical_si[7] = 0.0018
  const magnitude = Math.hypot(0.0024, 0.0018)
  step.envelope.maximum_translation_m = magnitude
  step.envelope.governing_translation = { epoch: 1, ...step.node_displacements[1], translation_m: magnitude }
  history.envelope = structuredClone(step.envelope)
  report.rows[1].performance.history_maximum_translation_m = magnitude
  const checked = validateDesignComparisonReport(report, validateDesignComparisonManifest(manifest(report)))
  expect(checked.rows[1].performance?.history_maximum_translation_m).toBeCloseTo(0.003)
})

for (const historyAvailable of [true, false]) {
  test(`browser history comparison keeps terminal and committed history distinct with history ${historyAvailable ? 'verified' : 'unavailable'}`, async ({ page }) => {
    const report = designHistoryComparisonFixture()
    if (!historyAvailable) removeVerifiedHistory(report, 1)
    const declared = manifest(report)
    await page.addInitScript(() => {
      window.__STRUCTURAL_WORKBENCH_CONFIG__ = { designComparisonUrl: '/comparisons/manifest.json' }
    })
    await page.route('**/comparisons/manifest.json', route => route.fulfill({ json: declared }))
    await page.route('**/comparisons/comparison.json', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify(report) }))
    await page.goto(process.env.WORKBENCH_V2_BASE_URL || 'http://127.0.0.1:4173')
    const panel = page.locator('[data-design-comparison="verified"]')
    await expect(panel.locator('[data-design-history-scope]')).toContainText('positive committed load step')
    await expect(panel.locator('[data-design-history-scope]')).toContainText('do not verify extrema between steps')
    const candidate = panel.locator('[data-design-candidate="narrow"]')
    await expect(candidate).toHaveAttribute('data-design-selected', 'false')
    await expect(panel.locator('[data-design-candidate="baseline"]')).toHaveAttribute('data-design-selected', 'true')
    await expect(candidate).toContainText('terminal pass')
    await expect(candidate.locator('[data-design-history-status]')).toContainText(historyAvailable ? 'committed history verified / fail' : 'committed history UNAVAILABLE / unavailable')
    for (const attribute of ['data-design-history-translation', 'data-design-history-strain']) {
      if (historyAvailable) await expect(candidate.locator(`[${attribute}]`)).not.toContainText('UNAVAILABLE')
      else await expect(candidate.locator(`[${attribute}]`)).toContainText('UNAVAILABLE')
    }
    await expect(candidate.locator('td').nth(5)).not.toContainText('UNAVAILABLE')
    const downloadPromise = page.waitForEvent('download')
    await page.locator('[data-wb2-export]').click()
    const stream = await (await downloadPromise).createReadStream()
    let exported = ''
    for await (const chunk of stream!) exported += chunk.toString()
    expect(JSON.parse(exported).physical_design_comparison.report).toEqual(report)
    await page.setViewportSize({ width: 390, height: 844 })
    const bounds = await panel.evaluate(element => ({ right: element.getBoundingClientRect().right, viewport: innerWidth, width: element.clientWidth, content: element.scrollWidth }))
    expect(bounds.right).toBeLessThanOrEqual(bounds.viewport)
    expect(bounds.content).toBeLessThanOrEqual(bounds.width)
    await expect(panel.getByRole('region', { name: 'Physical alternatives' })).toHaveAttribute('tabindex', '0')
  })
}

for (const [name, mutate] of [
  ['wrong source', (r: any) => { r.identity.source_revision = 'b'.repeat(40) }],
  ['wrong result model', (r: any) => { r.rows[1].result.canonical_model_checksum = designHash('7') }],
  ['wrong fiber authority', (r: any) => { r.rows[1].result.authority.fiber_strain_stress = 'not_authoritative' }],
  ['wrong checkpoint chain', (r: any) => { r.rows[1].result.contract_bindings.checkpoint_chain_hash = designHash('7') }],
  ['wrong validation result', (r: any) => { r.rows[1].validation.result_hash = designHash('7') }],
  ['wrong quantity model', (r: any) => { r.rows[1].quantities.model_checksum = designHash('7') }],
  ['wrong price hash', (r: any) => { r.rows[1].material_estimate.price_table_hash = designHash('7') }],
  ['wrong currency', (r: any) => { r.rows[1].material_estimate.currency = 'USD' }],
  ['wrong scope', (r: any) => { r.rows[1].material_estimate.scope = 'complete_takeoff' }],
  ['negative quantity', (r: any) => { r.rows[1].quantities.members[0].longitudinal_rebar_mass_kg = -1 }],
  ['nonfinite response', (r: any) => { r.rows[1].performance.terminal_maximum_translation_m = Number.NaN }],
  ['mutated physical load', (r: any) => { r.rows[1].canonical_model.loads = [] }],
  ['hidden model own key', (r: any) => { Object.defineProperty(r.rows[1].canonical_model, '__proto__', { value: { hidden: true }, enumerable: true }) }],
  ['quantity geometry mismatch', (r: any) => { r.rows[1].quantities.members[0].length_m = 2 }],
  ['summary result mismatch', (r: any) => { r.rows[1].result.node_displacements[1].UY_m = 0.003 }],
  ['wrong member binding', (r: any) => { r.rows[1].quantities.members[0].member_id = 'M2' }],
  ['wrong estimate total', (r: any) => { r.rows[1].material_estimate.total = 1 }],
  ['wrong difference', (r: any) => { r.rows[1].difference_from_baseline.scoped_material_estimate_reduction = 10000 }],
  ['wrong quantity delta', (r: any) => { r.rows[1].difference_from_baseline.quantity_delta.gross_concrete_volume_m3 = 0.5 }],
  ['wrong translation delta', (r: any) => { r.rows[1].difference_from_baseline.terminal_performance_delta.terminal_maximum_translation_m = 0.1 }],
  ['wrong fiber strain delta', (r: any) => { r.rows[1].difference_from_baseline.terminal_performance_delta.terminal_maximum_absolute_fiber_strain = -0.1 }],
  ['false safe selection', (r: any) => { r.rows[1].terminal_limit_status = 'fail' }],
  ['unverified selection', (r: any) => { r.rows[1].full_reference_verification_pass = false }],
  ['claimed approval', (r: any) => { r.claims.engineering_approval = true }],
] as const) {
  test(`physical comparison rejects ${name}`, () => {
    const report = designComparisonFixture()
    const checkedManifest = validateDesignComparisonManifest(manifest(report))
    mutate(report)
    expect(() => validateDesignComparisonReport(report, checkedManifest)).toThrow()
  })
}

test('missing prices leave estimates and selection unavailable', () => {
  const report = designComparisonFixture()
  report.price_basis = null; report.identity.price_table_hash = null
  report.rows.forEach((row: any) => { row.material_estimate = null; row.difference_from_baseline.scoped_material_estimate_reduction = null })
  Object.assign(report.selection, { candidate_id: null, eligible_count: 0, reason: 'reference_or_limits_or_prices_unavailable_or_no_candidate_passes' })
  const checked = validateDesignComparisonReport(report, validateDesignComparisonManifest(manifest(report)))
  expect(checked.selection.candidate_id).toBeNull()
})

test('physical comparison accepts a bound source SHA-256 identity supported by the producer', () => {
  const report = designComparisonFixture()
  report.identity.source_revision = designHash('a')
  const declared = validateDesignComparisonManifest({ ...manifest(report), source_revision: designHash('a') })
  expect(validateDesignComparisonReport(report, declared).identity.source_revision).toBe(designHash('a'))
})

test('a failed alternative remains in the denominator with no physical values or selection credit', () => {
  const report = designComparisonFixture()
  Object.assign(report.rows[1], { status: 'error', full_reference_verification_pass: false, result: null, validation: null, quantities: null, material_estimate: null, performance: null, terminal_limit_status: 'unavailable', failure: { kind: 'evaluation_exception' }, comparable_to_baseline: false, difference_from_baseline: null })
  report.status = 'partial'
  report.claims.all_requested_models_verified = false
  Object.assign(report.selection, { candidate_id: 'baseline', eligible_count: 1 })
  const checked = validateDesignComparisonReport(report, validateDesignComparisonManifest(manifest(report)))
  expect(checked.rows).toHaveLength(2)
  expect(checked.rows[1].material_estimate).toBeNull()
  expect(checked.selection.candidate_id).toBe('baseline')
})

for (const path of ['../comparison.json', '/comparison.json', 'https://other.test/comparison.json', '%2e%2e/comparison.json', 'sub/comparison.json', 'comparison.json?x=1', 'comparison.json#part', 'comparison\\.json']) {
  test(`manifest rejects report path ${path}`, () => expect(() => validateDesignComparisonManifest({ ...manifest(), report_file: path })).toThrow())
}

async function withFetch(body: Uint8Array, manifestBody: unknown, action: () => Promise<void>) {
  const windowDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'window')
  const fetchDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'fetch')
  Object.defineProperty(globalThis, 'window', { configurable: true, value: { location: { href: 'https://example.test/', origin: 'https://example.test' } } })
  Object.defineProperty(globalThis, 'fetch', { configurable: true, value: async (input: string, init?: RequestInit) => {
    expect(init?.redirect).toBe('error')
    expect(init?.credentials).toBe('same-origin')
    if (input === url) return Response.json(manifestBody)
    expect(input).toBe('https://example.test/comparisons/comparison.json')
    return new Response(body, { headers: { 'content-type': 'application/json' } })
  } })
  try { await action() } finally {
    if (windowDescriptor) Object.defineProperty(globalThis, 'window', windowDescriptor); else Reflect.deleteProperty(globalThis, 'window')
    if (fetchDescriptor) Object.defineProperty(globalThis, 'fetch', fetchDescriptor); else Reflect.deleteProperty(globalThis, 'fetch')
  }
}

test('provider verifies raw bytes without rehashing Python float spellings', async () => {
  const report = designComparisonFixture()
  const body = new TextEncoder().encode(JSON.stringify(report).replace('"maximum_iterations":40', '"maximum_iterations":40.0'))
  const declared = { ...manifest(report), report_byte_length: body.length, report_sha256: digest(body) }
  await withFetch(body, declared, async () => {
    const result = await loadDesignComparison(url)
    expect(result.status).toBe('verified')
    expect(result.bundle?.report.selection.candidate_id).toBe('narrow')
  })
})

test('provider rejects mutated bytes and length before exposing any data', async () => {
  const report = designComparisonFixture()
  for (const declared of [{ ...manifest(report), report_sha256: designHash('0') }, { ...manifest(report), report_byte_length: 1 }]) {
    await withFetch(bytes(report), declared, async () => expect(await loadDesignComparison(url)).toMatchObject({ status: 'invalid', bundle: null }))
  }
})

test('provider rejects cross-origin manifests without fetching', async () => {
  await withFetch(bytes({}), {}, async () => expect(await loadDesignComparison('https://other.test/manifest.json')).toMatchObject({ status: 'invalid', bundle: null }))
})

test('missing Web Crypto exposes no comparison numbers', async () => {
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, 'crypto')
  Object.defineProperty(globalThis, 'crypto', { configurable: true, value: undefined })
  try {
    const report = designComparisonFixture()
    await withFetch(bytes(report), manifest(report), async () => expect(await loadDesignComparison(url)).toMatchObject({ status: 'integrity_unavailable', bundle: null }))
  } finally {
    if (descriptor) Object.defineProperty(globalThis, 'crypto', descriptor)
    else Reflect.deleteProperty(globalThis, 'crypto')
  }
})

test('unconfigured comparison is explicitly unavailable', async () => {
  const load = await loadDesignComparison(undefined)
  expect(load).toMatchObject({ status: 'unconfigured', bundle: null })
})

test('browser renders the bound comparison and exports the same report', async ({ page }) => {
  const base = process.env.WORKBENCH_V2_BASE_URL || 'http://127.0.0.1:4173'
  const report = designComparisonFixture()
  const declared = manifest(report)
  await page.addInitScript(() => {
    Object.defineProperty(window, '__STRUCTURAL_WORKBENCH_CONFIG__', { value: { designComparisonUrl: '/comparisons/manifest.json' } })
  })
  await page.route('**/comparisons/manifest.json', (route) => route.fulfill({ json: declared }))
  await page.route('**/comparisons/comparison.json', (route) => route.fulfill({ contentType: 'application/json', body: JSON.stringify(report) }))
  await page.goto(base)
  await expect(page.locator('[data-design-comparison="verified"]')).toBeVisible()
  await expect(page.locator('[data-design-candidate="narrow"]')).toContainText('364')
  await expect(page.locator('[data-design-candidate="narrow"]')).toHaveAttribute('data-design-selected', 'true')
  const downloadPromise = page.waitForEvent('download')
  await page.locator('[data-wb2-export]').click()
  const download = await downloadPromise
  const stream = await download.createReadStream()
  let text = ''
  for await (const chunk of stream!) text += chunk.toString()
  const exported = JSON.parse(text)
  expect(exported.physical_design_comparison.report).toEqual(report)
  expect(exported.physical_design_comparison.manifest).toEqual(declared)
})

test('browser keeps comparison unavailable when no manifest is configured', async ({ page }) => {
  await page.goto(process.env.WORKBENCH_V2_BASE_URL || 'http://127.0.0.1:4173')
  await expect(page.locator('[data-design-comparison="unconfigured"]')).toContainText('UNAVAILABLE')
  await expect(page.locator('[data-design-candidate]')).toHaveCount(0)
})

for (const priceAvailable of [true, false]) {
  test(`browser displays verified signed physical changes with prices ${priceAvailable ? 'available' : 'unavailable'}`, async ({ page }) => {
    const report = designComparisonFixture()
    const candidate = report.rows[1]
    candidate.result.node_displacements[1].UY_m = 0.0008
    candidate.result.fiber_results[0].strain = 0.00012
    candidate.performance.terminal_maximum_translation_m = 0.0008
    candidate.performance.terminal_maximum_absolute_fiber_strain = 0.00012
    candidate.difference_from_baseline.terminal_performance_delta = {
      terminal_maximum_translation_m: 0.0008 - 0.001,
      terminal_maximum_absolute_fiber_strain: 0.00012 - 0.0001,
    }
    if (!priceAvailable) {
      report.price_basis = null
      report.identity.price_table_hash = null
      report.rows.forEach((row: any) => {
        row.material_estimate = null
        row.difference_from_baseline.scoped_material_estimate_reduction = null
      })
      Object.assign(report.selection, { candidate_id: null, eligible_count: 0, reason: 'reference_or_limits_or_prices_unavailable_or_no_candidate_passes' })
    }
    await page.addInitScript(() => {
      window.__STRUCTURAL_WORKBENCH_CONFIG__ = { designComparisonUrl: '/comparisons/manifest.json' }
    })
    await page.route('**/comparisons/manifest.json', route => route.fulfill({ json: manifest(report) }))
    await page.route('**/comparisons/comparison.json', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify(report) }))
    await page.goto(process.env.WORKBENCH_V2_BASE_URL || 'http://127.0.0.1:4173')
    const panel = page.locator('[data-design-comparison="verified"]')
    await expect(panel).toContainText('candidate minus baseline')
    await expect(panel).toContainText('Estimate reduction is baseline minus candidate')
    const row = panel.locator('[data-design-candidate="narrow"]')
    await expect(row.locator('[data-design-delta="gross_concrete_volume_m3"]')).toHaveText('Change: -0.5')
    await expect(row.locator('[data-design-delta="longitudinal_rebar_mass_kg"]')).toHaveText('Change: 0')
    await expect(row.locator('[data-design-delta="terminal_maximum_translation_m"]')).toHaveText('Change: -2.000e-4')
    await expect(row.locator('[data-design-delta="terminal_maximum_absolute_fiber_strain"]')).toHaveText('Change: 2.000e-5')
    await expect(row.locator('td').nth(4)).toHaveText(priceAvailable ? '50' : 'UNAVAILABLE')
    await expect(row).toHaveAttribute('data-design-selected', String(priceAvailable))
    const downloadPromise = page.waitForEvent('download')
    await page.locator('[data-wb2-export]').click()
    const stream = await (await downloadPromise).createReadStream()
    let text = ''
    for await (const chunk of stream!) text += chunk.toString()
    expect(JSON.parse(text).physical_design_comparison.report).toEqual(report)
    await page.setViewportSize({ width: 390, height: 844 })
    const bounds = await panel.evaluate(element => ({ viewport: innerWidth, right: element.getBoundingClientRect().right, content: element.scrollWidth, width: element.clientWidth }))
    expect(bounds.right).toBeLessThanOrEqual(bounds.viewport)
    expect(bounds.content).toBeLessThanOrEqual(bounds.width)
    const table = panel.getByRole('region', { name: 'Physical alternatives' })
    await expect(table).toHaveAttribute('tabindex', '0')
    expect(await table.evaluate(element => element.scrollWidth > element.clientWidth)).toBe(true)
  })
}

test('browser keeps changes unavailable when baseline verification fails', async ({ page }) => {
  const report = designComparisonFixture()
  Object.assign(report.rows[0], { status: 'error', full_reference_verification_pass: false, result: null, validation: null, quantities: null, material_estimate: null, performance: null, terminal_limit_status: 'unavailable', failure: { kind: 'evaluation_exception' } })
  report.rows.forEach((row: any) => { row.comparable_to_baseline = false; row.difference_from_baseline = null })
  report.status = 'partial'
  report.claims.all_requested_models_verified = false
  Object.assign(report.selection, { candidate_id: null, eligible_count: 1, reason: 'reference_or_limits_or_prices_unavailable_or_no_candidate_passes' })
  await page.addInitScript(() => {
    window.__STRUCTURAL_WORKBENCH_CONFIG__ = { designComparisonUrl: '/comparisons/manifest.json' }
  })
  await page.route('**/comparisons/manifest.json', route => route.fulfill({ json: manifest(report) }))
  await page.route('**/comparisons/comparison.json', route => route.fulfill({ contentType: 'application/json', body: JSON.stringify(report) }))
  await page.goto(process.env.WORKBENCH_V2_BASE_URL || 'http://127.0.0.1:4173')
  const panel = page.locator('[data-design-comparison="verified"]')
  const deltas = panel.locator('[data-design-delta]')
  await expect(deltas).toHaveCount(8)
  for (const delta of await deltas.all()) {
    await expect(delta).toHaveText('Change: UNAVAILABLE')
    await expect(delta.locator('[data-engineering-value-state="unavailable"]')).toBeVisible()
  }
  await expect(panel.locator('[data-design-selected="true"]')).toHaveCount(0)
})
