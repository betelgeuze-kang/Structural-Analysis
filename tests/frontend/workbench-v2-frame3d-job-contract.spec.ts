import { expect, test } from '@playwright/test'
import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { validateFrame3DJobResult } from '../../src/workbench-v2/model/frame3dJobSchema'
import { loadWorkbenchJob } from '../../src/workbench-v2/model/jobProvider'
import { validateWorkbenchJobView, type WorkbenchJobView } from '../../src/workbench-v2/model/jobSchema'

// These are preserved Python producer bytes. JSON.stringify below binds only
// mutated HTTP artifacts; it never claims to reproduce Python logical hashes.
const fixtureDirectory = 'tests/frontend/fixtures/frame3d-durable-job/'
type JsonObject = Record<string, any>
type Fixture = {
  job: JsonObject
  result: JsonObject
  evidence: JsonObject
  resultBytes: Buffer
  evidenceBytes: Buffer
  checkpointBytes: Buffer
}

function fixture(directory = fixtureDirectory): Fixture {
  const resultBytes = readFileSync(`${directory}result.json`)
  const evidenceBytes = readFileSync(`${directory}evidence.json`)
  return {
    job: JSON.parse(readFileSync(`${directory}job.json`, 'utf8')),
    result: JSON.parse(resultBytes.toString('utf8')),
    evidence: JSON.parse(evidenceBytes.toString('utf8')),
    resultBytes,
    evidenceBytes,
    checkpointBytes: readFileSync(`${directory}checkpoint.json`),
  }
}

function digest(bytes: Uint8Array): string {
  return `sha256:${createHash('sha256').update(bytes).digest('hex')}`
}

function bytes(value: unknown): Buffer {
  return Buffer.from(JSON.stringify(value), 'utf8')
}

function typedJob(value: JsonObject): WorkbenchJobView {
  const validated = validateWorkbenchJobView(value)
  expect(validated.errors).toEqual([])
  expect(validated.value).not.toBeNull()
  return validated.value!
}

function bindTransport(source: Fixture, resultBytes = bytes(source.result)): Fixture {
  const evidence = structuredClone(source.evidence)
  evidence.result_artifact_hash = digest(resultBytes)
  const evidenceBytes = bytes(evidence)
  const job = structuredClone(source.job)
  job.result.content_hash = digest(resultBytes)
  job.result.byte_length = resultBytes.byteLength
  job.evidence.content_hash = digest(evidenceBytes)
  job.evidence.byte_length = evidenceBytes.byteLength
  return { ...source, job, evidence, resultBytes, evidenceBytes }
}

type FetchObservation = { url: string; init: RequestInit | undefined }

async function withFetch<T>(
  source: Fixture,
  run: (url: string, calls: FetchObservation[]) => Promise<T>,
  responseHeaders: Record<string, string> = {},
): Promise<T> {
  const url = `https://workbench.test/api/v1/jobs/${source.job.job_id}`
  const calls: FetchObservation[] = []
  const original = globalThis.fetch
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: String(input), init })
    if (init?.signal?.aborted) throw new DOMException('aborted', 'AbortError')
    const role = String(input).endsWith('/result') ? 'result'
      : String(input).endsWith('/evidence') ? 'evidence' : 'job'
    const payload = role === 'result' ? source.resultBytes
      : role === 'evidence' ? source.evidenceBytes : bytes(source.job)
    return new Response(payload, {
      headers: {
        'content-type': role === 'result' ? source.job.result.media_type : 'application/json',
        'content-length': String(payload.byteLength),
        ...(role === 'result' ? responseHeaders : {}),
      },
    })
  }) as typeof fetch
  try {
    return await run(url, calls)
  } finally {
    globalThis.fetch = original
  }
}

function expectNoFrame3DValues(value: JsonObject): void {
  expect(value.frame3dResult).toBeUndefined()
  expect(value.frame3dArtifacts).toBeUndefined()
  expect(value.engineeringResultIr).toBeUndefined()
}

test('actual Python artifacts retain their producer bytes and provenance hashes', async () => {
  const source = fixture()
  const provenance = JSON.parse(readFileSync(`${fixtureDirectory}provenance.json`, 'utf8'))
  for (const artifact of provenance.artifacts) {
    const raw = readFileSync(`${fixtureDirectory}${artifact.path}`)
    expect(raw.byteLength).toBe(artifact.byte_length)
    expect(digest(raw)).toBe(artifact.sha256)
  }
  expect(source.resultBytes.byteLength).toBe(source.job.result.byte_length)
  expect(digest(source.resultBytes)).toBe(source.job.result.content_hash)
  expect(digest(source.evidenceBytes)).toBe(source.job.evidence.content_hash)
  expect(Buffer.from(source.result.terminal_checkpoint_artifact_base64, 'base64'))
    .toEqual(source.checkpointBytes)
  const review = await validateFrame3DJobResult(source.result, source.evidence, typedJob(source.job))
  expect(review.completedTargetCount).toBe(5)
  expect(review.totalTargetCount).toBe(5)
  expect(review.reservedAttempts).toBe(6)
  expect(review.confirmedAttempts).toBe(5)
  expect(review.abandonedReservations).toBe(1)
  expect(review.targets).toEqual([0.003, 0.006, 0.001, -0.004, 0.002])
  expect(review.controlUnit).toBe('m')
  expect(review.controlDof).toBe('UX')
  expect(review.controlNodeId).toBe('N2')
  expect(Buffer.from(review.terminalCheckpointBytes)).toEqual(source.checkpointBytes)
})

test('provider publishes the verified 3D review with exact downloadable bytes', async () => {
  const source = fixture()
  const controller = new AbortController()
  await withFetch(source, async (url, calls) => {
    const loaded = await loadWorkbenchJob(url, controller.signal)
    expect(loaded).toMatchObject({ status: 'ready', artifactStatus: 'verified', errors: [] })
    expect(loaded.frame3dResult?.completedTargetCount).toBe(5)
    expect(loaded.engineeringResultIr).toBeUndefined()
    expect(loaded.frame3dArtifacts).toBeDefined()
    expect(Buffer.from(loaded.frame3dArtifacts!.resultBytes)).toEqual(source.resultBytes)
    expect(Buffer.from(loaded.frame3dArtifacts!.evidenceBytes)).toEqual(source.evidenceBytes)
    expect(Buffer.from(loaded.frame3dArtifacts!.checkpointBytes)).toEqual(source.checkpointBytes)
    expect(calls.map((call) => call.url).sort()).toEqual([url, `${url}/evidence`, `${url}/result`].sort())
    for (const call of calls) {
      expect(call.init).toMatchObject({ method: 'GET', credentials: 'include', cache: 'no-store' })
      expect(call.init?.signal).toBe(controller.signal)
    }
  })
})

for (const [kind, targets, dof, unit] of [
  ['monotonic', [0.003, 0.006], 'UX', 'm'],
  ['rotational', [0.000001], 'RX', 'rad'],
] as const) {
  test(`actual ${kind} Python artifacts validate and retain v1 checkpoint bytes`, async () => {
    const directory = `${fixtureDirectory}${kind}/`
    const source = fixture(directory)
    const provenance = JSON.parse(readFileSync(`${directory}provenance.json`, 'utf8'))
    for (const artifact of provenance.artifacts) {
      const raw = readFileSync(`${directory}${artifact.path}`)
      expect(raw.byteLength).toBe(artifact.byte_length)
      expect(digest(raw)).toBe(artifact.sha256)
    }
    expect(JSON.parse(source.checkpointBytes.toString('utf8')).schema_version)
      .toBe('bounded-frame3d-direct-control-checkpoint-artifact.v1')
    const review = await validateFrame3DJobResult(source.result, source.evidence, typedJob(source.job))
    expect(review.targets).toEqual(targets)
    expect(review.controlDof).toBe(dof)
    expect(review.controlUnit).toBe(unit)
    expect(review.completedTargetCount).toBe(targets.length)
    expect(review.totalTargetCount).toBe(targets.length)
    expect(review.reservedAttempts).toBe(targets.length)
    expect(review.confirmedAttempts).toBe(targets.length)
    expect(review.abandonedReservations).toBe(0)
    expect(Buffer.from(review.terminalCheckpointBytes)).toEqual(source.checkpointBytes)
    await withFetch(source, async (url) => {
      const loaded = await loadWorkbenchJob(url)
      expect(loaded).toMatchObject({ status: 'ready', artifactStatus: 'verified', errors: [] })
      expect(loaded.frame3dResult?.controlDof).toBe(dof)
      expect(loaded.frame3dResult?.controlUnit).toBe(unit)
      expect(loaded.engineeringResultIr).toBeUndefined()
      expect(Buffer.from(loaded.frame3dArtifacts!.resultBytes)).toEqual(source.resultBytes)
      expect(Buffer.from(loaded.frame3dArtifacts!.evidenceBytes)).toEqual(source.evidenceBytes)
      expect(Buffer.from(loaded.frame3dArtifacts!.checkpointBytes)).toEqual(source.checkpointBytes)
    })
  })
}

// Consumer compatibility checks only: these changed declarations are not new
// Python executions, rehashed logical artifacts, or source attestations.
for (const [name, alter] of [
  ['tiny positive characteristic length', (solver: JsonObject) => {
    solver.frame_config.minimum_characteristic_length_m = Number.MIN_VALUE
  }],
  ['long strictly decreasing line search', (solver: JsonObject) => {
    const count = 65537
    solver.line_search.alphas = Array.from({ length: count }, (_, index) => 1 - index / (count + 1))
  }],
] as const) {
  test(`synthetic consumer config compatibility retains ${name}`, async () => {
    const source = fixture(`${fixtureDirectory}rotational/`)
    for (const receipt of source.result.receipts) alter(receipt.api_result.control.solver_config)
    const review = await validateFrame3DJobResult(source.result, source.evidence, typedJob(source.job))
    expect(review.controlDof).toBe('RX')
    expect(review.controlUnit).toBe('rad')
    expect(review.targets).toEqual([0.000001])
    expect(Buffer.from(review.terminalCheckpointBytes)).toEqual(source.checkpointBytes)
  })
}

test('missing WebCrypto exposes no 3D engineering values or raw exports', async () => {
  const source = fixture()
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, 'crypto')
  Object.defineProperty(globalThis, 'crypto', { configurable: true, value: undefined })
  try {
    await expect(validateFrame3DJobResult(source.result, source.evidence, typedJob(source.job)))
      .rejects.toThrow('frame3d_job_integrity_unavailable')
    await withFetch(source, async (url) => {
      const loaded = await loadWorkbenchJob(url)
      expect(loaded.artifactStatus).toBe('integrity_unavailable')
      expectNoFrame3DValues(loaded)
    })
  } finally {
    if (descriptor) Object.defineProperty(globalThis, 'crypto', descriptor)
    else delete (globalThis as unknown as JsonObject).crypto
  }
})

const semanticMutations: Array<[string, (source: Fixture) => void]> = [
  ['detached report hash', ({ evidence }) => { evidence.validation_report.result_hash = `sha256:${'1'.repeat(64)}` }],
  ['report receipt omission', ({ evidence }) => { evidence.validation_report.receipt_hashes.pop() }],
  ['wrapper authority promotion', ({ result }) => { result.authority.design_authority = true }],
  ['report authority boolean alias', ({ evidence }) => { evidence.validation_report.authority.external_vv_level = false }],
  ['raw API authority promotion', ({ result }) => { result.receipts[0].api_result.authority.release_eligible = true }],
  ['invalid source revision', ({ result }) => { result.source_revision = 'not-a-full-revision' }],
  ['source attestation promotion', ({ result }) => { result.source_revision_is_attestation = true }],
  ['source node order', ({ result }) => { result.receipts[1].api_result.source_binding.node_ids.reverse() }],
  ['source model identity', ({ result }) => { result.receipts[1].api_result.source_binding.model_ir_content_hash = `sha256:${'2'.repeat(64)}` }],
  ['full target schedule', ({ result }) => { result.control_targets[2] = 0.0011 }],
  ['raw API target scope', ({ result }) => { result.receipts[0].api_result.control.control_targets = [...result.control_targets] }],
  ['authored cursor', ({ result }) => { result.completed_target_count = 4 }],
  ['fractional cursor', ({ result }) => { result.completed_target_count = 4.5 }],
  ['budget arithmetic', ({ result }) => { result.execution_budget.remaining_attempts += 1 }],
  ['detached report budget', ({ evidence }) => { evidence.validation_report.execution_budget.reserved_attempts -= 1 }],
  ['cutback usage without retained failure', ({ result }) => { result.receipts[0].api_result.metrics.adaptive_target_cutback_used = true }],
  ['more accepted checkpoints than attempts', ({ result }) => { result.receipts[0].api_result.metrics.accepted_checkpoint_count = 2 }],
  ['duplicate reservation ordinal', ({ result }) => { result.receipts[2].reserved_attempt_ordinals = [2] }],
  ['missing reservation ordinal', ({ result }) => { result.receipts[2].reserved_attempt_ordinals = [] }],
  ['boolean reservation ordinal', ({ result }) => { result.receipts[0].reserved_attempt_ordinals = [true] }],
  ['unsafe reservation integer', ({ result }) => { result.receipts[2].reserved_attempt_ordinals = [Number.MAX_SAFE_INTEGER + 1] }],
  ['checkpoint base64', ({ result }) => { result.receipts[0].checkpoint_artifact_base64 = '!!!' }],
  ['checkpoint hash', ({ result }) => { result.receipts[0].checkpoint_sha256 = `sha256:${'3'.repeat(64)}` }],
  ['terminal artifact mismatch', ({ result }) => { result.terminal_checkpoint_artifact_base64 = result.receipts[0].checkpoint_artifact_base64 }],
  ['node identity', ({ result }) => { result.receipts[0].api_result.node_displacements[0].node_id = 'UNKNOWN' }],
  ['material identity', ({ result }) => { result.receipts[0].api_result.material_states[0].material_id = 'UNKNOWN' }],
  ['control unit', ({ result }) => { result.receipts[0].api_result.control.control_unit = 'rad' }],
  ['reaction unit', ({ result }) => { result.receipts[0].api_result.support_reactions[0].unit = 'N' }],
  ['duplicate node row', ({ result }) => { result.receipts[0].api_result.node_displacements.push(structuredClone(result.receipts[0].api_result.node_displacements[0])) }],
]

for (const [name, mutate] of semanticMutations) {
  test(`updated outer artifact hashes cannot hide ${name}`, async () => {
    const source = fixture()
    mutate(source)
    const rebound = bindTransport(source)
    expect(digest(rebound.resultBytes)).toBe(rebound.job.result.content_hash)
    expect(digest(rebound.evidenceBytes)).toBe(rebound.job.evidence.content_hash)
    expect(rebound.evidence.result_artifact_hash).toBe(rebound.job.result.content_hash)
    await withFetch(rebound, async (url) => {
      const loaded = await loadWorkbenchJob(url)
      expect(loaded.status).toBe('invalid')
      expect(loaded.artifactStatus).toBe('invalid')
      expect(loaded.errors.length).toBeGreaterThan(0)
      expectNoFrame3DValues(loaded)
    })
  })
}

for (const [name, mutate] of [
  ['duplicate field', (raw: string) => raw.replace('{', '{"status":"ready",')],
  ['non-finite exponent', (raw: string) => raw.replace('"reserved_attempts":6', '"reserved_attempts":1e400')],
  ['non-JSON number', (raw: string) => raw.replace('"reserved_attempts":6', '"reserved_attempts":NaN')],
] as const) {
  test(`provider rejects ${name} even with matching raw transport hashes`, async () => {
    const source = fixture()
    const changed = Buffer.from(mutate(source.resultBytes.toString('utf8')))
    expect(changed).not.toEqual(source.resultBytes)
    await withFetch(bindTransport(source, changed), async (url) => {
      const loaded = await loadWorkbenchJob(url)
      expect(['invalid', 'error']).toContain(loaded.status)
      expectNoFrame3DValues(loaded)
    })
  })
}

for (const [name, headers] of [
  ['non-JSON media', { 'content-type': 'text/html' }],
  ['oversize declared body', { 'content-length': String(64 * 1024 * 1024 + 1) }],
] as const) {
  test(`provider rejects ${name} before exposing artifacts`, async () => {
    await withFetch(fixture(), async (url) => {
      const loaded = await loadWorkbenchJob(url)
      expect(['invalid', 'error']).toContain(loaded.status)
      expectNoFrame3DValues(loaded)
    }, headers)
  })
}

test('cancelled loads publish no stale 3D values', async () => {
  const controller = new AbortController()
  controller.abort()
  await withFetch(fixture(), async (url, calls) => {
    const loaded = await loadWorkbenchJob(url, controller.signal)
    expect(loaded).toMatchObject({ status: 'unconfigured', job: null })
    expect(calls).toHaveLength(0)
    expectNoFrame3DValues(loaded)
  })
})

test('cancellation during artifact retrieval cannot publish a completed 3D review', async () => {
  const controller = new AbortController()
  await withFetch(fixture(), async (url, calls) => {
    const transport = globalThis.fetch
    globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
      const response = await transport(input, init)
      if (String(input).endsWith('/evidence')) controller.abort()
      return response
    }) as typeof fetch
    const loaded = await loadWorkbenchJob(url, controller.signal)
    expect(calls).toHaveLength(3)
    expect(loaded).toMatchObject({ status: 'unconfigured', job: null })
    expectNoFrame3DValues(loaded)
  })
})
