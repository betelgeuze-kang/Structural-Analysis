import { expect, test } from '@playwright/test'
import { createHash } from 'node:crypto'
import { readFile } from 'node:fs/promises'
import {
  canonicalNativeJson,
  loadNativeFrameBundle,
  loadNativeFrameJob,
  loadNativeFrameArtifacts,
  nativeFrameModelIdentity,
  parseNativeJsonStrict,
} from '../../src/workbench-v2/model/nativeFrameProvider'
import { loadNativeFrameComparison } from '../../src/workbench-v2/model/nativeFrameComparisonProvider'
import {
  cancelNativeFrameJob,
  submitAndRunNativeFrameJob,
} from '../../src/workbench-v2/model/nativeFrameRunClient'
import {
  artifactBytes as bytes,
  fixedHash,
  fixtureHash as hash,
  nativeFrameReportFixture as reportIr,
  nativeFrameReferenceFixture as referenceIr,
  nativeFrameComparisonFixture as comparisonIr,
  nativeFrameResultFixture as resultIr,
} from './nativeFrameFixture'

const resultUrl = 'https://example.test/evidence/native-frame-result.json'
const reportUrl = 'https://example.test/evidence/native-frame-report.json'
const bundleUrl = 'https://example.test/evidence/frame-bundle/manifest.json'
const jobUrl = 'https://example.test/evidence/native-job/view.json'
const referenceUrl = 'https://example.test/evidence/native-frame-reference.json'
const comparisonUrl = 'https://example.test/evidence/native-frame-comparison.json'

function bytesHash(value: Uint8Array): string {
  return `sha256:${createHash('sha256').update(value).digest('hex')}`
}

async function boundModelBody(result: Record<string, unknown>): Promise<Uint8Array> {
  const model = JSON.parse(
    await readFile('native/distribution/frame-alpha-cantilever.model-ir.json', 'utf8'),
  ) as Record<string, unknown>
  model.model_id = (result.bindings as Record<string, unknown>).model_id
  const loadPatterns = model.load_patterns as Array<Record<string, unknown>>
  loadPatterns[0].id = (result.bindings as Record<string, unknown>).load_pattern_id
  Object.assign(result.bindings as Record<string, unknown>, await nativeFrameModelIdentity(model))
  return new TextEncoder().encode(canonicalNativeJson(model))
}

function bundleManifest(
  model: Uint8Array,
  result: Record<string, unknown>,
  report: Record<string, unknown>,
  html: Uint8Array,
) {
  const resultBody = bytes(result)
  const reportBody = bytes(report)
  return {
    schema_version: 'structural-native-linear-frame3d-workbench-bundle.v1',
    status: 'complete',
    artifacts: {
      model_ir: { path: 'model-ir.json', media_type: 'application/json', content_hash: bytesHash(model), byte_length: model.byteLength },
      result_ir: { path: 'result-ir.json', media_type: 'application/json', content_hash: bytesHash(resultBody), byte_length: resultBody.byteLength },
      report_ir: { path: 'report-ir.json', media_type: 'application/json', content_hash: bytesHash(reportBody), byte_length: reportBody.byteLength },
      html: { path: 'report.html', media_type: 'text/html', content_hash: bytesHash(html), byte_length: html.byteLength },
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
}

function jobView(
  status: 'queued' | 'running' | 'succeeded' | 'failed',
  manifest: { content_hash: string; byte_length: number } | null = null,
) {
  const revision = status === 'queued' ? 0 : status === 'running' ? 1 : 2
  return {
    schema_version: 'structural-native-linear-frame3d-job-view.v1',
    job_id: 'job_0123456789abcdef0123456789abcdef',
    request_hash: fixedHash('d'),
    model_content_hash: fixedHash('e'),
    revision,
    status,
    created_unix_ms: 1700000000000,
    updated_unix_ms: 1700000000000 + revision,
    bundle_manifest: status === 'succeeded'
      ? { path: 'bundle/manifest.json', ...manifest }
      : null,
    error: status === 'failed'
      ? { code: 'native_analysis_failed', detail: 'Selected load source is unsupported' }
      : null,
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
}

function jobViewV2(
  status: 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled',
  manifest: { content_hash: string; byte_length: number } | null = null,
) {
  const base = jobView(status === 'cancelled' ? 'queued' : status, manifest)
  const revision = status === 'queued' ? 0 : status === 'running' || status === 'cancelled' ? 1 : 2
  return {
    ...base,
    schema_version: 'structural-native-linear-frame3d-job-view.v2',
    revision,
    status,
    updated_unix_ms: 1700000000000 + revision,
    bundle_manifest: status === 'succeeded' ? base.bundle_manifest : null,
    error: status === 'failed' ? base.error : null,
    cancellation: status === 'cancelled'
      ? { code: 'native_worker_cancelled', detail: 'Worker was stopped and reaped by the loopback host' }
      : null,
    service_profile: 'filesystem_append_only_single_host.v2',
    capabilities: {
      process_isolation: false,
      cancellation: true,
      resume: false,
      crash_recovery: false,
      multi_host: false,
    },
    claim_boundary: 'single_host_v2_materialized_view_not_worker_provenance_release_or_recovery_authority',
  }
}

test('Workbench polls the strict job view while the synchronous run request is in flight', async () => {
  const jobId = 'job_0123456789abcdef0123456789abcdef'
  const originalWindow = Object.getOwnPropertyDescriptor(globalThis, 'window')
  const originalFetch = Object.getOwnPropertyDescriptor(globalThis, 'fetch')
  let status: 'queued' | 'running' | 'succeeded' = 'queued'
  let polls = 0
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: {
      location: { href: 'http://127.0.0.1:8787/', origin: 'http://127.0.0.1:8787' },
      setTimeout,
      clearTimeout,
    },
  })
  Object.defineProperty(globalThis, 'fetch', {
    configurable: true,
    value: async (input: URL | RequestInfo, init?: RequestInit) => {
      const url = new URL(String(input))
      if (init?.method === 'POST' && url.pathname === '/api/v1/frame3d/jobs') {
        return Response.json(jobView('queued'))
      }
      if (init?.method === 'POST' && url.pathname.endsWith(`/${jobId}/run`)) {
        status = 'running'
        await new Promise((resolve) => setTimeout(resolve, 260))
        status = 'succeeded'
        return Response.json(jobView('succeeded', { content_hash: fixedHash('a'), byte_length: 1 }))
      }
      if (init?.method === 'GET' && url.pathname.endsWith(`/${jobId}/view.json`)) {
        polls += 1
        if (polls >= 2) status = 'succeeded'
        return Response.json(jobView(status, status === 'succeeded'
          ? { content_hash: fixedHash('a'), byte_length: 1 }
          : null))
      }
      return new Response('not found', { status: 404, headers: { 'Content-Type': 'text/plain' } })
    },
  })
  try {
    const outcome = await submitAndRunNativeFrameJob({
      submissionUrl: '/api/v1/frame3d/jobs',
      jobId,
      modelIrJson: '{"schema_version":"structural-model-ir.v2"}',
      loadSource: { kind: 'pattern', id: 'LC1' },
      resultId: 'result.poll.LC1',
      reportId: 'report.poll.LC1',
    })
    expect(outcome.status).toBe('succeeded')
    expect(outcome.jobId).toBe(jobId)
    expect(polls).toBeGreaterThanOrEqual(2)
  } finally {
    if (originalWindow) Object.defineProperty(globalThis, 'window', originalWindow)
    else Reflect.deleteProperty(globalThis, 'window')
    if (originalFetch) Object.defineProperty(globalThis, 'fetch', originalFetch)
    else Reflect.deleteProperty(globalThis, 'fetch')
  }
})

test('Workbench cancellation posts to the same-origin worker endpoint and preserves Cancelled', async () => {
  const jobId = 'job_0123456789abcdef0123456789abcdef'
  const originalWindow = Object.getOwnPropertyDescriptor(globalThis, 'window')
  const originalFetch = Object.getOwnPropertyDescriptor(globalThis, 'fetch')
  let finishRun: ((response: Response) => void) | undefined
  let queuedReady: (() => void) | undefined
  const queued = new Promise<void>((resolve) => { queuedReady = resolve })
  Object.defineProperty(globalThis, 'window', {
    configurable: true,
    value: {
      location: { href: 'http://127.0.0.1:8787/', origin: 'http://127.0.0.1:8787' },
      setTimeout,
      clearTimeout,
    },
  })
  Object.defineProperty(globalThis, 'fetch', {
    configurable: true,
    value: async (input: URL | RequestInfo, init?: RequestInit) => {
      const url = new URL(String(input))
      if (init?.method === 'POST' && url.pathname === '/api/v1/frame3d/jobs') {
        return Response.json(jobViewV2('queued'))
      }
      if (init?.method === 'POST' && url.pathname.endsWith(`/${jobId}/run`)) {
        return new Promise<Response>((resolve) => { finishRun = resolve })
      }
      if (init?.method === 'POST' && url.pathname.endsWith(`/${jobId}/cancel`)) {
        const response = Response.json(jobViewV2('cancelled'))
        finishRun?.(Response.json(jobViewV2('cancelled')))
        return response
      }
      if (init?.method === 'GET' && url.pathname.endsWith(`/${jobId}/view.json`)) {
        return Response.json(jobViewV2('running'))
      }
      return new Response('not found', { status: 404, headers: { 'Content-Type': 'text/plain' } })
    },
  })
  try {
    const run = submitAndRunNativeFrameJob({
      submissionUrl: '/api/v1/frame3d/jobs',
      jobId,
      modelIrJson: '{"schema_version":"structural-model-ir.v2"}',
      loadSource: { kind: 'pattern', id: 'LC1' },
      resultId: 'result.cancel.LC1',
      reportId: 'report.cancel.LC1',
      onQueued: () => queuedReady?.(),
    })
    await queued
    const cancelled = await cancelNativeFrameJob('/api/v1/frame3d/jobs', jobId)
    expect(cancelled).toMatchObject({
      status: 'cancelled',
      jobId,
      error: { code: 'native_worker_cancelled' },
    })
    await expect(run).resolves.toMatchObject({ status: 'cancelled', jobId })
  } finally {
    if (originalWindow) Object.defineProperty(globalThis, 'window', originalWindow)
    else Reflect.deleteProperty(globalThis, 'window')
    if (originalFetch) Object.defineProperty(globalThis, 'fetch', originalFetch)
    else Reflect.deleteProperty(globalThis, 'fetch')
  }
})

async function withBundle(
  manifest: Record<string, unknown>,
  modelBody: Uint8Array,
  resultBody: Uint8Array,
  reportBody: Uint8Array,
  htmlBody: Uint8Array,
  action: () => Promise<void>,
): Promise<void> {
  const originalFetch = globalThis.fetch
  const bodies = new Map<string, [Uint8Array, string]>([
    [bundleUrl, [bytes(manifest), 'application/json']],
    [new URL('model-ir.json', bundleUrl).toString(), [modelBody, 'application/json']],
    [new URL('result-ir.json', bundleUrl).toString(), [resultBody, 'application/json']],
    [new URL('report-ir.json', bundleUrl).toString(), [reportBody, 'application/json']],
    [new URL('report.html', bundleUrl).toString(), [htmlBody, 'text/html']],
  ])
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    const row = bodies.get(String(input))
    if (!row) return new Response(null, { status: 404 })
    return new Response(row[0], {
      headers: { 'content-type': row[1], 'content-length': String(row[0].byteLength) },
    })
  }) as typeof fetch
  try {
    await action()
  } finally {
    globalThis.fetch = originalFetch
  }
}

async function withArtifacts(
  resultBody: Uint8Array,
  reportBody: Uint8Array | null,
  action: () => Promise<void>,
): Promise<void> {
  const originalFetch = globalThis.fetch
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    const body = String(input) === resultUrl ? resultBody : reportBody
    if (body === null) return new Response(null, { status: 404 })
    return new Response(body, {
      headers: {
        'content-type': 'application/json',
        'content-length': String(body.byteLength),
      },
    })
  }) as typeof fetch
  try {
    await action()
  } finally {
    globalThis.fetch = originalFetch
  }
}

async function withComparison(
  referenceBody: Uint8Array,
  comparisonBody: Uint8Array,
  action: () => Promise<void>,
): Promise<void> {
  const originalFetch = globalThis.fetch
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    const body = String(input) === referenceUrl ? referenceBody
      : String(input) === comparisonUrl ? comparisonBody : null
    if (body === null) return new Response(null, { status: 404 })
    return new Response(body, {
      headers: { 'content-type': 'application/json', 'content-length': String(body.byteLength) },
    })
  }) as typeof fetch
  try {
    await action()
  } finally {
    globalThis.fetch = originalFetch
  }
}

test('native canonical JSON matches the Rust/Python numeric spelling boundary', () => {
  expect(canonicalNativeJson({
    signed_zero: -0,
    integral_float: 1.0,
    small_1e5: 1e-5,
    small_1e4: 1e-4,
    small_1e6: 1e-6,
    fraction: 1.2345678901234567,
    unicode: '구조/α',
    huge_integral_float: 1e20,
  })).toBe('{"fraction":1.2345678901234567,"huge_integral_float":100000000000000000000,"integral_float":1,"signed_zero":0,"small_1e4":0.0001,"small_1e5":1e-05,"small_1e6":1e-06,"unicode":"구조/α"}')
})

test('browser ModelIR identity matches the Rust contract projection', async () => {
  const model = JSON.parse(
    await readFile('native/distribution/frame-alpha-cantilever.model-ir.json', 'utf8'),
  ) as Record<string, unknown>
  await expect(nativeFrameModelIdentity(model)).resolves.toEqual({
    model_content_hash: 'sha256:4cc83ae7f9da3fe1d0ddc59969d1156f83c7bd23aee5df2c4f17437c01569d87',
    model_semantic_hash: 'sha256:3a713f62c057dc4971aa81d2d76132f11eb72061841f76b422eed7121a1c05b1',
    model_provenance_hash: 'sha256:e7e62d36cd4e63648a57ec8f536c4e86c97a0a200d12c0b9e3af87888eadda43',
  })
})

test('browser ModelIR identity rejects schema-invalid nested content before hashing', async () => {
  const model = JSON.parse(
    await readFile('native/distribution/frame-alpha-cantilever.model-ir.json', 'utf8'),
  ) as Record<string, unknown>
  const nodes = model.nodes as Array<Record<string, unknown>>
  nodes[1].coordinates_m = [2.0, 0.0]

  await expect(nativeFrameModelIdentity(model)).rejects.toThrow(
    /ModelIR v2 schema validation failed.*coordinates_m/,
  )
})

test('Workbench provider treats a configured ResultIR/ReportIR pair atomically', async () => {
  const result = resultIr()
  await withArtifacts(bytes(result), null, async () => {
    const loaded = await loadNativeFrameArtifacts(resultUrl, reportUrl)
    expect(loaded).toMatchObject({
      status: 'missing',
      artifactStatus: 'invalid',
      resultIr: null,
      reportIr: null,
      errors: ['native Frame3D ReportIR not found'],
    })
  })

  const reportOnly = await loadNativeFrameArtifacts(undefined, reportUrl)
  expect(reportOnly).toMatchObject({
    status: 'invalid',
    artifactStatus: 'invalid',
    resultIr: null,
    reportIr: null,
  })
})

test('Workbench comparison provider source-replays an atomic ReferenceIR/ComparisonIR pair', async () => {
  const result = resultIr()
  const reference = referenceIr(result)
  const comparison = comparisonIr(result, reference)
  await withComparison(bytes(reference), bytes(comparison), async () => {
    const loaded = await loadNativeFrameComparison(
      result as never,
      referenceUrl,
      comparisonUrl,
    )
    expect(loaded).toMatchObject({ status: 'verified', errors: [] })
    expect(loaded.referenceIr?.units).toEqual({ translation: 'mm', rotation: 'rad', force: 'kN', moment: 'kN*m' })
    expect(loaded.comparisonIr?.summary).toMatchObject({ row_count: 36, failing_row_count: 0, passed: true })
    expect(loaded.comparisonIr?.authority.external_validation).toBe('not_established')
  })
})

test('Workbench comparison provider accepts a replayed failed gate without promoting validation', async () => {
  const result = resultIr()
  const reference = referenceIr(result)
  ;((reference.nodes as Array<Record<string, unknown>>)[1].displacement as number[])[0] = 0.06
  const comparison = comparisonIr(result, reference)
  await withComparison(bytes(reference), bytes(comparison), async () => {
    const loaded = await loadNativeFrameComparison(result as never, referenceUrl, comparisonUrl)
    expect(loaded.status).toBe('verified')
    expect(loaded.comparisonIr?.summary.passed).toBe(false)
    expect(loaded.comparisonIr?.summary.failing_row_count).toBe(1)
    expect(loaded.comparisonIr?.authority.external_validation).toBe('not_established')
  })
})

test('Workbench comparison provider hides both artifacts on transplant, row drift or partial configuration', async () => {
  const result = resultIr()
  const reference = referenceIr(result)
  const comparison = comparisonIr(result, reference)
  ;(comparison.source_result as Record<string, unknown>).result_hash = fixedHash('e')
  const rehashed = { ...comparison, comparison_hash: fixedHash('0') }
  comparison.comparison_hash = hash(rehashed)
  await withComparison(bytes(reference), bytes(comparison), async () => {
    const loaded = await loadNativeFrameComparison(result as never, referenceUrl, comparisonUrl)
    expect(loaded).toMatchObject({ status: 'invalid', referenceIr: null, comparisonIr: null })
    expect(loaded.errors.join(' ')).toMatch(/source result result_hash is invalid/)
  })

  const valid = comparisonIr(result, reference)
  ;(valid.rows as Array<Record<string, unknown>>)[0].passed = false
  const rowDriftBody = { ...valid, comparison_hash: fixedHash('0') }
  valid.comparison_hash = hash(rowDriftBody)
  await withComparison(bytes(reference), bytes(valid), async () => {
    const loaded = await loadNativeFrameComparison(result as never, referenceUrl, comparisonUrl)
    expect(loaded).toMatchObject({ status: 'invalid', referenceIr: null, comparisonIr: null })
    expect(loaded.errors.join(' ')).toMatch(/rows are not the deterministic evaluation/)
  })

  await expect(loadNativeFrameComparison(result as never, referenceUrl, undefined)).resolves.toMatchObject({
    status: 'invalid', referenceIr: null, comparisonIr: null,
  })
})

test('strict native parser rejects duplicate keys including escaped aliases', () => {
  expect(() => parseNativeJsonStrict('{"id":1,"\\u0069d":2}')).toThrow(/duplicate/)
})

test('native job consumer keeps queued, failed and v2 cancelled states non-authoritative', async () => {
  const originalFetch = globalThis.fetch
  let body = bytes(jobView('queued'))
  globalThis.fetch = (async () => new Response(body, {
    headers: { 'content-type': 'application/json', 'content-length': String(body.byteLength) },
  })) as typeof fetch
  try {
    await expect(loadNativeFrameJob(jobUrl)).resolves.toMatchObject({
      status: 'pending', artifactStatus: 'not_configured', resultIr: null, reportIr: null,
    })
    body = bytes(jobView('failed'))
    await expect(loadNativeFrameJob(jobUrl)).resolves.toMatchObject({
      status: 'invalid', artifactStatus: 'invalid', resultIr: null, reportIr: null,
      errors: [expect.stringContaining('native_analysis_failed')],
    })
    body = bytes(jobViewV2('cancelled'))
    await expect(loadNativeFrameJob(jobUrl)).resolves.toMatchObject({
      status: 'invalid', artifactStatus: 'invalid', resultIr: null, reportIr: null,
      errors: [expect.stringContaining('native_worker_cancelled')],
    })
  } finally {
    globalThis.fetch = originalFetch
  }
})

test('native job consumer verifies the terminal manifest hash before loading its bundle', async () => {
  const result = resultIr()
  const modelBody = await boundModelBody(result)
  const resultHashBody = { ...result }
  delete resultHashBody.result_hash
  result.result_hash = hash(resultHashBody)
  const report = reportIr(result)
  const resultBody = bytes(result)
  const reportBody = bytes(report)
  const htmlBody = new TextEncoder().encode('<!doctype html><title>Frame report</title>')
  const manifest = bundleManifest(modelBody, result, report, htmlBody)
  const manifestBody = bytes(manifest)
  const viewBody = bytes(jobView('succeeded', {
    content_hash: bytesHash(manifestBody), byte_length: manifestBody.byteLength,
  }))
  const manifestUrl = new URL('bundle/manifest.json', jobUrl).toString()
  const bodies = new Map<string, [Uint8Array, string]>([
    [jobUrl, [viewBody, 'application/json']],
    [manifestUrl, [manifestBody, 'application/json']],
    [new URL('model-ir.json', manifestUrl).toString(), [modelBody, 'application/json']],
    [new URL('result-ir.json', manifestUrl).toString(), [resultBody, 'application/json']],
    [new URL('report-ir.json', manifestUrl).toString(), [reportBody, 'application/json']],
    [new URL('report.html', manifestUrl).toString(), [htmlBody, 'text/html']],
  ])
  const originalFetch = globalThis.fetch
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    const row = bodies.get(String(input))
    if (!row) return new Response(null, { status: 404 })
    return new Response(row[0], {
      headers: { 'content-type': row[1], 'content-length': String(row[0].byteLength) },
    })
  }) as typeof fetch
  try {
    await expect(loadNativeFrameJob(jobUrl)).resolves.toMatchObject({
      status: 'ready', artifactStatus: 'bundle_verified', errors: [],
    })
    bodies.set(manifestUrl, [bytes({ ...manifest, status: 'tampered' }), 'application/json'])
    await expect(loadNativeFrameJob(jobUrl)).resolves.toMatchObject({
      status: 'invalid', artifactStatus: 'invalid', resultIr: null, reportIr: null,
      errors: ['native Frame3D bundle job manifest hash mismatch'],
    })
  } finally {
    globalThis.fetch = originalFetch
  }
})

test('Workbench provider verifies the exact ResultIR/ReportIR pair and source-bound extrema', async () => {
  const result = resultIr()
  const report = reportIr(result)
  await withArtifacts(bytes(result), bytes(report), async () => {
    const loaded = await loadNativeFrameArtifacts(resultUrl, reportUrl)
    expect(loaded).toMatchObject({
      status: 'ready',
      artifactStatus: 'pair_verified',
      errors: [],
    })
    expect(loaded.resultIr?.authority.release_readiness).toBe('not_authoritative')
    expect(loaded.resultIr?.claim_boundary.independent_recovery_replay).toBe(true)
    expect(loaded.resultIr?.claim_boundary.nodal_load_only).toBe(false)
    expect(loaded.resultIr?.claim_boundary.uniform_member_load_initial_local).toBe(true)
    expect(loaded.resultIr?.claim_boundary.member_end_rotational_release).toBe(true)
    expect(loaded.resultIr?.claim_boundary.rigid_member_end_offset).toBe(true)
    expect(loaded.resultIr?.claim_boundary.self_weight_standard_gravity).toBe(true)
    expect(loaded.resultIr?.claim_boundary.linear_load_combination_superposition).toBe(true)
    expect(loaded.resultIr?.gates.independent_recovery_replay_passed).toBe(true)
    expect(loaded.reportIr?.authority.comparison).toBe('not_evaluated')
    expect(loaded.reportIr?.limitations).toContain('load_scope_nodal_uniform_self_weight_and_nested_linear_combinations')
    expect(loaded.reportIr?.limitations).toContain('no_nonuniform_or_member_point_load')
    expect(loaded.reportIr?.limitations).toContain('offset_scope_finite_global_rigid_end_arms')
    expect(loaded.reportIr?.limitations).toContain('no_translational_release')
    expect(loaded.reportIr?.extrema[2].component).toBe('FX_I')
  })
})

test('Workbench provider verifies one completed CLI bundle before exposing artifacts', async () => {
  const result = resultIr()
  const modelBody = await boundModelBody(result)
  const resultHashBody = { ...result }
  delete resultHashBody.result_hash
  result.result_hash = hash(resultHashBody)
  const report = reportIr(result)
  const resultBody = bytes(result)
  const reportBody = bytes(report)
  const htmlBody = new TextEncoder().encode('<!doctype html>\n<title>Frame report</title>')
  const manifest = bundleManifest(modelBody, result, report, htmlBody)
  await withBundle(manifest, modelBody, resultBody, reportBody, htmlBody, async () => {
    const loaded = await loadNativeFrameBundle(bundleUrl)
    expect(loaded).toMatchObject({ status: 'ready', artifactStatus: 'bundle_verified', errors: [] })
    expect(loaded.resultIr?.result_hash).toBe(result.result_hash)
    expect(loaded.reportIr?.report_hash).toBe(report.report_hash)
    expect(loaded.elementRecovery?.rows[0]).toMatchObject({
      member_id: 'E1', member_index: 0, node_i: 'N1', node_j: 'N2', coordinate_frame: 'member_local',
    })
  })

  const tampered = new Uint8Array([...resultBody, 0x20])
  await withBundle(manifest, modelBody, tampered, reportBody, htmlBody, async () => {
    const loaded = await loadNativeFrameBundle(bundleUrl)
    expect(loaded.status).toBe('invalid')
    expect(loaded.errors).toContain('native Frame3D bundle ResultIR byte length mismatch')
  })

  const tamperedHtml = htmlBody.slice()
  tamperedHtml[tamperedHtml.length - 1] ^= 1
  await withBundle(manifest, modelBody, resultBody, reportBody, tamperedHtml, async () => {
    const loaded = await loadNativeFrameBundle(bundleUrl)
    expect(loaded.status).toBe('invalid')
    expect(loaded.errors).toContain('native Frame3D bundle HTML report hash mismatch')
  })
})

test('Workbench blocks a hash-valid ModelIR and ResultIR with detached member identities', async () => {
  const result = resultIr()
  const originalModelBody = await boundModelBody(result)
  const model = JSON.parse(new TextDecoder().decode(originalModelBody)) as Record<string, unknown>
  const elements = model.elements as Array<Record<string, unknown>>
  elements[0].id = 'E2'
  Object.assign(result.bindings as Record<string, unknown>, await nativeFrameModelIdentity(model))
  const modelBody = new TextEncoder().encode(canonicalNativeJson(model))
  const resultHashBody = { ...result }
  delete resultHashBody.result_hash
  result.result_hash = hash(resultHashBody)
  const report = reportIr(result)
  const resultBody = bytes(result)
  const reportBody = bytes(report)
  const htmlBody = new TextEncoder().encode('<!doctype html><title>Frame report</title>')
  const manifest = bundleManifest(modelBody, result, report, htmlBody)

  await withBundle(manifest, modelBody, resultBody, reportBody, htmlBody, async () => {
    const loaded = await loadNativeFrameBundle(bundleUrl)
    expect(loaded).toMatchObject({
      status: 'invalid', artifactStatus: 'invalid', resultIr: null, reportIr: null,
      errors: [expect.stringContaining('ResultIR is missing a ModelIR member recovery row')],
    })
    expect(loaded.elementRecovery).toBeNull()
  })
})

test('Workbench provider preserves an explicit load-combination source binding', async () => {
  const result = resultIr()
  result.result_id = 'frame-alpha.COMB1'
  const bindings = result.bindings as Record<string, unknown>
  bindings.load_pattern_id = null
  bindings.load_combination_id = 'COMB1'
  const resultBody = { ...result }
  delete resultBody.result_hash
  result.result_hash = hash(resultBody)
  const report = reportIr(result)
  await withArtifacts(bytes(result), bytes(report), async () => {
    const loaded = await loadNativeFrameArtifacts(resultUrl, reportUrl)
    expect(loaded.status).toBe('ready')
    expect(loaded.resultIr?.bindings.load_pattern_id).toBeNull()
    expect(loaded.resultIr?.bindings.load_combination_id).toBe('COMB1')
    expect(loaded.reportIr?.summary.load_pattern_id).toBeNull()
    expect(loaded.reportIr?.summary.load_combination_id).toBe('COMB1')
  })
})

test('Workbench provider fails closed for hash drift and authority promotion', async () => {
  const original = resultIr()
  const stale = structuredClone(original)
  ;((stale.nodes as Array<Record<string, unknown>>)[1].displacement_m_rad as number[])[0] = 0.001
  await withArtifacts(bytes(stale), bytes(reportIr(original)), async () => {
    const loaded = await loadNativeFrameArtifacts(resultUrl, reportUrl)
    expect(loaded.status).toBe('invalid')
    expect(loaded.errors).toContain('ResultIR hash mismatch')
  })

  const promoted = structuredClone(original)
  ;(promoted.authority as Record<string, unknown>).release_readiness = 'bounded_candidate'
  const promotedBody = { ...promoted }
  delete promotedBody.result_hash
  promoted.result_hash = hash(promotedBody)
  await withArtifacts(bytes(promoted), bytes(reportIr(promoted)), async () => {
    const loaded = await loadNativeFrameArtifacts(resultUrl, reportUrl)
    expect(loaded.status).toBe('invalid')
    expect(loaded.errors.join(' ')).toMatch(/release_readiness is invalid/)
  })
})

test('Workbench provider rejects a rehashed failed independent recovery replay gate', async () => {
  const failed = resultIr()
  ;(failed.gates as Record<string, unknown>).member_force_replay_scaled_linf = 2e-9
  const failedBody = { ...failed }
  delete failedBody.result_hash
  failed.result_hash = hash(failedBody)
  await withArtifacts(bytes(failed), bytes(reportIr(failed)), async () => {
    const loaded = await loadNativeFrameArtifacts(resultUrl, reportUrl)
    expect(loaded.status).toBe('invalid')
    expect(loaded.errors.join(' ')).toMatch(/member_force_replay_scaled_linf is invalid/)
  })
})

test('Workbench provider rejects a rehashed ReportIR transplanted to another result identity', async () => {
  const result = resultIr()
  const report = reportIr(result)
  ;(report.source_result as Record<string, unknown>).result_hash = fixedHash('f')
  const reportBody = { ...report }
  delete reportBody.report_hash
  report.report_hash = hash(reportBody)
  await withArtifacts(bytes(result), bytes(report), async () => {
    const loaded = await loadNativeFrameArtifacts(resultUrl, reportUrl)
    expect(loaded.status).toBe('invalid')
    expect(loaded.errors.join(' ')).toMatch(/source result result_hash is invalid/)
  })
})

test('Workbench provider rejects duplicate artifact keys before typed projection', async () => {
  const result = JSON.stringify(resultIr()).replace('{', '{"result_id":"duplicate",')
  const report = reportIr(resultIr())
  await withArtifacts(new TextEncoder().encode(result), bytes(report), async () => {
    const loaded = await loadNativeFrameArtifacts(resultUrl, reportUrl)
    expect(loaded.status).toBe('invalid')
    expect(loaded.errors).toContain('native Frame3D ResultIR contains a duplicate JSON key')
  })
})
