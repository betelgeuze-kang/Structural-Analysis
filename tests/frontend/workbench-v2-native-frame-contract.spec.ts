import { expect, test } from '@playwright/test'
import { createHash } from 'node:crypto'
import {
  canonicalNativeJson,
  loadNativeFrameBundle,
  loadNativeFrameArtifacts,
  parseNativeJsonStrict,
} from '../../src/workbench-v2/model/nativeFrameProvider'
import {
  artifactBytes as bytes,
  fixedHash,
  fixtureHash as hash,
  nativeFrameReportFixture as reportIr,
  nativeFrameResultFixture as resultIr,
} from './nativeFrameFixture'

const resultUrl = 'https://example.test/evidence/native-frame-result.json'
const reportUrl = 'https://example.test/evidence/native-frame-report.json'
const bundleUrl = 'https://example.test/evidence/frame-bundle/manifest.json'

function bytesHash(value: Uint8Array): string {
  return `sha256:${createHash('sha256').update(value).digest('hex')}`
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

test('strict native parser rejects duplicate keys including escaped aliases', () => {
  expect(() => parseNativeJsonStrict('{"id":1,"\\u0069d":2}')).toThrow(/duplicate/)
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
  const modelBody = new TextEncoder().encode('{"model_id":"frame-alpha"}')
  ;(result.bindings as Record<string, unknown>).model_content_hash = bytesHash(modelBody)
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
