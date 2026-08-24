import { expect, test } from '@playwright/test'
import {
  canonicalNativeJson,
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
    expect(loaded.resultIr?.gates.independent_recovery_replay_passed).toBe(true)
    expect(loaded.reportIr?.authority.comparison).toBe('not_evaluated')
    expect(loaded.reportIr?.limitations).toContain('load_scope_nodal_and_uniform_initial_local_force')
    expect(loaded.reportIr?.limitations).toContain('no_nonuniform_or_member_point_load')
    expect(loaded.reportIr?.limitations).toContain('offset_scope_finite_global_rigid_end_arms')
    expect(loaded.reportIr?.limitations).toContain('no_translational_release')
    expect(loaded.reportIr?.extrema[2].component).toBe('FX_I')
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
