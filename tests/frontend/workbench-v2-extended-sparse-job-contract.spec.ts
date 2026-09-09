import { expect, test, type BrowserContext, type Page } from '@playwright/test'
import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { loadWorkbenchJob } from '../../src/workbench-v2/model/jobProvider'
import { waitForJobService } from './jobServiceBrowserWait'

const fixtureDirectory = 'tests/frontend/fixtures/extended-sparse-durable-job/'
const baseUrl = process.env.WORKBENCH_V2_BASE_URL ?? 'http://127.0.0.1:4373'
const extendedBackend = 'scipy_sparse_splu_cpu_exact_1536'
const legacyBackend = 'scipy_sparse_spsolve_cpu'
const legacyPolicyHash = 'sha256:ed5b57b4fc1cf30c4d9cc8bb3e1201e92d7d9b2de510488d3dcf2e609a2f3347'
const extendedPolicyHash = 'sha256:dd4755cbb4469dff802b102b506b2a67f07272104931eb96b37b0fefa4d326b1'
type JsonObject = Record<string, any>
type Fixture = {
  job: JsonObject
  jobBytes: Buffer
  result: JsonObject
  evidence: JsonObject
  resultBytes: Buffer
  evidenceBytes: Buffer
}

function fixture(): Fixture {
  const jobBytes = readFileSync(`${fixtureDirectory}job.json`)
  const resultBytes = readFileSync(`${fixtureDirectory}result.json`)
  const evidenceBytes = readFileSync(`${fixtureDirectory}evidence.json`)
  return {
    job: JSON.parse(jobBytes.toString('utf8')),
    jobBytes,
    result: JSON.parse(resultBytes.toString('utf8')),
    evidence: JSON.parse(evidenceBytes.toString('utf8')),
    resultBytes,
    evidenceBytes,
  }
}

function digest(bytes: Uint8Array): string {
  return `sha256:${createHash('sha256').update(bytes).digest('hex')}`
}

function bytes(value: unknown): Buffer {
  return Buffer.from(JSON.stringify(value), 'utf8')
}

// Mutated cases exercise the browser's contract checks after rebinding HTTP
// byte identities. They do not claim to regenerate Python logical hashes or
// provide a new solver execution receipt for their altered backend declaration.
function bindTransport(source: Fixture): Fixture {
  const resultBytes = bytes(source.result)
  const evidence = structuredClone(source.evidence)
  evidence.result_artifact_hash = digest(resultBytes)
  const evidenceBytes = bytes(evidence)
  const job = structuredClone(source.job)
  job.result.content_hash = digest(resultBytes)
  job.result.byte_length = resultBytes.byteLength
  job.evidence.content_hash = digest(evidenceBytes)
  job.evidence.byte_length = evidenceBytes.byteLength
  return { ...source, job, jobBytes: bytes(job), evidence, resultBytes, evidenceBytes }
}

async function load(source: Fixture) {
  const calls: { url: string; init?: RequestInit }[] = []
  const url = `https://workbench.test/api/v1/jobs/${source.job.job_id}`
  const original = globalThis.fetch
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: String(input), init })
    const payload = String(input).endsWith('/result') ? source.resultBytes
      : String(input).endsWith('/evidence') ? source.evidenceBytes : source.jobBytes
    return new Response(payload, {
      headers: { 'content-type': 'application/json', 'content-length': String(payload.byteLength) },
    })
  }) as typeof fetch
  try {
    return { loaded: await loadWorkbenchJob(url), calls, url }
  } finally {
    globalThis.fetch = original
  }
}

test('actual exact-1536 Python job bytes produce only the verified read-only engineering projection', async () => {
  const source = fixture()
  expect(source.result.configuration.matrix_backend).toBe(extendedBackend)
  expect(source.result.metrics.sparse_factorization_policy_hash).toBe(extendedPolicyHash)
  expect(digest(source.resultBytes)).toBe(source.job.result.content_hash)
  expect(source.resultBytes.byteLength).toBe(source.job.result.byte_length)
  expect(digest(source.evidenceBytes)).toBe(source.job.evidence.content_hash)
  expect(source.evidenceBytes.byteLength).toBe(source.job.evidence.byte_length)
  const { loaded, calls, url } = await load(source)
  expect(loaded).toMatchObject({ status: 'ready', artifactStatus: 'verified', errors: [] })
  expect(loaded.engineeringResultIr?.engineering_result_hash).toBe(source.result.source_result_hash)
  expect(loaded.frame3dResult).toBeUndefined()
  expect(loaded).not.toHaveProperty('node_displacements')
  expect(calls.map((call) => call.url).sort()).toEqual([url, `${url}/evidence`, `${url}/result`].sort())
  for (const { init } of calls) {
    expect(init?.method).toBe('GET')
    expect(init?.credentials).toBe('include')
    expect(init?.cache).toBe('no-store')
    expect(init?.body).toBeUndefined()
  }
})

const invalidBackendChanges: [string, (result: JsonObject) => void][] = [
  ['configuration deleted', (result) => { delete result.configuration }],
  ['all execution metadata deleted', (result) => {
    delete result.configuration
    delete result.metrics
    delete result.convergence_history
  }],
  ['metrics deleted', (result) => { delete result.metrics }],
  ['history deleted', (result) => { delete result.convergence_history }],
  ['unknown backend', (result) => { result.configuration.matrix_backend = 'scipy_sparse_splu_cpu_exact_unbounded' }],
  ['Frame3D backend promoted to planar', (result) => { result.configuration.matrix_backend = 'scipy_superlu_splu_cpu_exact_condition_fail_closed' }],
  ['old 256 policy relabeled as extended', (result) => { result.metrics.sparse_factorization_policy_hash = legacyPolicyHash }],
  ['extended policy relabeled as old 256', (result) => { result.configuration.matrix_backend = legacyBackend }],
  ['sparse diagnostics relabeled as dense', (result) => { result.configuration.matrix_backend = 'numpy_linalg_solve_dense' }],
  ['wrong storage', (result) => { result.configuration.stiffness_storage = 'numpy_dense_ndarray' }],
  ['configuration profile detached', (result) => { result.configuration.profile = 'fixed_chord_serial_cantilever.v1' }],
  ['no solver execution', (result) => { result.metrics.solver_executed = false }],
  ['no native sparse assembly', (result) => { result.metrics.native_sparse_assembly_used = false }],
  ['diagnostics not passed', (result) => { result.metrics.sparse_factorization_diagnostics_passed = false }],
  ['diagnostic hash omitted', (result) => { result.metrics.sparse_factorization_diagnostic_hashes.pop() }],
  ['diagnostic hash invalid', (result) => { result.metrics.sparse_factorization_diagnostic_hashes[0] = 'invalid' }],
  ['count detached from history', (result) => { result.metrics.sparse_factorization_count += 1 }],
  ['condition limit exceeded', (result) => { result.metrics.sparse_factorization_max_condition_number_1 = 1e12 + 1 }],
  ['pivot limit violated', (result) => { result.metrics.sparse_factorization_min_normalized_absolute_pivot = 0 }],
  ['backward error limit exceeded', (result) => { result.metrics.sparse_factorization_max_backward_error = 2e-12 }],
  ['history vector length changed', (result) => { result.convergence_history[0].residual_kn.pop() }],
  ['extended equation limit exceeded', (result) => {
    for (const row of result.convergence_history) {
      for (const name of ['free_displacements_m', 'residual_kn', 'newton_increment_m']) row[name] = Array(1537).fill(0)
    }
  }],
]

for (const [label, mutate] of invalidBackendChanges) {
  test(`Workbench rejects ${label} even with matching transport hashes`, async () => {
    const source = fixture()
    mutate(source.result)
    const { loaded } = await load(bindTransport(source))
    expect(loaded).toMatchObject({ status: 'invalid', artifactStatus: 'invalid' })
    expect(loaded.errors).toContain('published planar backend contract is invalid')
    expect(loaded.engineeringResultIr).toBeUndefined()
    expect(loaded.frame3dResult).toBeUndefined()
  })
}

test('the legacy 256 backend retains its separate policy and equation cap', async () => {
  const source = fixture()
  source.result.configuration.matrix_backend = legacyBackend
  source.result.metrics.sparse_factorization_policy_hash = legacyPolicyHash
  // This is a contract-only declaration variant, not an old-backend execution.
  expect((await load(bindTransport(source))).loaded).toMatchObject({ status: 'ready', artifactStatus: 'verified' })
  for (const row of source.result.convergence_history) {
    for (const name of ['free_displacements_m', 'residual_kn', 'newton_increment_m']) row[name] = Array(257).fill(0)
  }
  expect((await load(bindTransport(source))).loaded.errors).toContain('published planar backend contract is invalid')
})

for (const schema of ['bounded-frame3d-job-result.v1', 'structural-native-linear-frame3d-result-ir.v1']) {
  test(`an extended planar result cannot promote itself to ${schema}`, async () => {
    const source = fixture()
    source.result.schema_version = schema
    const { loaded } = await load(bindTransport(source))
    expect(loaded.status).toBe('invalid')
    expect(loaded.engineeringResultIr).toBeUndefined()
    expect(loaded.frame3dResult).toBeUndefined()
  })
}

// Chromium renders the real app against recorded producer bytes served by mocked
// same-origin GETs. This is local browser coverage, not deployed-service evidence.
async function mockPublishedJob(page: Page, context: BrowserContext, source: Fixture, tamperResult = false) {
  const statusPath = `/api/v1/jobs/${source.job.job_id}`
  const requests: string[] = []
  await context.addCookies([{ name: 'extended-sparse-review-session', value: 'test-session', url: baseUrl }])
  await page.addInitScript((url) => {
    window.__STRUCTURAL_WORKBENCH_CONFIG__ = { jobStatusUrl: url }
  }, statusPath)
  await page.route('**/api/v1/jobs/**', async (route) => {
    const request = route.request()
    const path = new URL(request.url()).pathname
    requests.push(path)
    expect(request.method()).toBe('GET')
    expect(request.postData()).toBeNull()
    expect(await request.headerValue('cookie')).toContain('extended-sparse-review-session=test-session')
    if (path === statusPath) {
      await route.fulfill({ contentType: 'application/json', body: source.jobBytes })
    } else if (path === `${statusPath}/result`) {
      expect(await request.headerValue('accept')).toBe(source.job.result.media_type)
      await route.fulfill({
        contentType: source.job.result.media_type,
        body: tamperResult ? Buffer.concat([source.resultBytes, Buffer.from('\n')]) : source.resultBytes,
      })
    } else if (path === `${statusPath}/evidence`) {
      expect(await request.headerValue('accept')).toBe(source.job.evidence.media_type)
      await route.fulfill({ contentType: source.job.evidence.media_type, body: source.evidenceBytes })
    } else {
      await route.fulfill({ status: 404, contentType: 'application/json', body: '{}' })
    }
  })
  return { requests, statusPath }
}

for (const [name, viewport] of [
  ['desktop', { width: 1440, height: 1000 }],
  ['mobile', { width: 390, height: 844 }],
] as const) {
  test.describe(`extended sparse job browser on ${name}`, () => {
    test.use({ viewport })

    test('renders the verified engineering identity and preserves read-only authority', async ({ page, context }, testInfo) => {
      const source = fixture()
      const { requests, statusPath } = await mockPublishedJob(page, context, source)
      await page.goto(`${baseUrl}/#/workbench-v2`, { waitUntil: 'load' })
      const panel = await waitForJobService(page)
      await expect(panel).toHaveAttribute('data-job-status', 'succeeded')
      await expect(panel.getByRole('heading', { name: 'Durable job service' })).toBeVisible()
      await expect(panel.getByText('verified', { exact: true })).toBeVisible()
      await expect(panel.getByRole('progressbar')).toHaveAttribute('aria-valuenow', String(source.job.progress.completed_steps))
      await expect(panel.getByRole('progressbar')).toHaveAttribute('aria-valuemax', String(source.job.progress.total_steps))
      const ir = source.result.engineering_result_ir
      const resultHash = ir.engineering_result_hash as string
      await expect(panel.locator('[data-job-result-ir="verified"]')).toHaveText(`${resultHash.slice(0, 15)}…${resultHash.slice(-8)}`)
      await expect(panel.locator('[data-job-result-ir-authority]')).toHaveText(
        `convergence=${ir.authority_axes.convergence}; displacement=${ir.authority_axes.displacement}; reaction=${ir.authority_axes.reaction}`,
      )
      await expect(panel.locator('[data-job-convergence="unavailable"]')).toHaveText('UNAVAILABLE')
      await expect(panel).toContainText('Job state is orchestration evidence only.')
      await expect(page.locator('[data-frame3d-job-review]')).toHaveCount(0)
      await expect(panel.locator('input, select, button, table')).toHaveCount(0)
      // This panel renders identity and authority only. Unit-bearing numerical
      // tables are not implemented here; retain the producer's unit contract.
      for (const [quantity, unit] of [
        ['node_translation_m', 'm'], ['node_rotation_rad', 'rad'],
        ['reaction_force_n', 'N'], ['reaction_moment_nm', 'N*m'],
      ]) {
        expect(ir.array_descriptors.find((row: JsonObject) => row.name === quantity)?.unit).toBe(unit)
      }
      const bounds = await panel.boundingBox()
      expect(bounds).not.toBeNull()
      expect(bounds!.x).toBeGreaterThanOrEqual(0)
      expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(viewport.width + 1)
      // Development StrictMode may cancel and repeat the initial status GET;
      // both builds must use only the three read endpoints checked above.
      expect([...new Set(requests)].sort()).toEqual([statusPath, `${statusPath}/result`, `${statusPath}/evidence`].sort())
      await panel.screenshot({ path: testInfo.outputPath(`extended-sparse-${name}.png`) })
    })
  })
}

test('extended sparse job browser exposes unavailable state after raw artifact tampering', async ({ page, context }) => {
  await mockPublishedJob(page, context, fixture(), true)
  await page.goto(`${baseUrl}/#/workbench-v2`, { waitUntil: 'load' })
  const panel = await waitForJobService(page, 'invalid')
  await expect(panel).toContainText('Durable job status unavailable')
  await expect(panel.locator('[data-state="UNAVAILABLE"]')).toBeVisible()
  await expect(page.locator('[data-frame3d-job-review]')).toHaveCount(0)
  await expect(panel.locator('[data-job-result-ir="verified"], table, button')).toHaveCount(0)
})
