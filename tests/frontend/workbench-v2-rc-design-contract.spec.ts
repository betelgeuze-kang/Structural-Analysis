import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { rcDesignBlockedStep, validateRcDesignStudy } from '../../src/workbench-v2/model/rcControlDesignSchema'
const root = 'tests/frontend/fixtures/rc-control-design/'
const original = readFileSync(`${root}comparison.json`)
const hash = (s: string | Uint8Array) => `sha256:${createHash('sha256').update(s).digest('hex')}`
const read = async (path: string) => new Uint8Array(readFileSync(`${root}${path}`))
const constantRoot = 'tests/frontend/fixtures/rc-control-design-constant/'
const constantOriginal = readFileSync(`${constantRoot}comparison.json`)
const constantRead = async (path: string) => new Uint8Array(readFileSync(`${constantRoot}${path}`))
// Synthetic diagnostic parsing cases; numerical evidence is recorded separately.
const failedStep = () => ({ schema_version: 'bounded-rc-fiber-direct-control-result.v1', status: 'blocked',
  path: { accepted_target_prefix_m: [-.001], attempts: [{ committed: false, target_control_displacement_m: -.002,
    rollback_exact: true, parent_checkpoint_immutable: true, parent_checkpoint_hash: `sha256:${'a'.repeat(64)}`,
    accepted_checkpoint_hash: `sha256:${'a'.repeat(64)}`, solver_work: { detail: 'line_search_failed_to_reduce_residual' } }] } })
function diagnosticBytes(value: object): Uint8Array {
  const without = JSON.stringify(value)
  return new TextEncoder().encode(JSON.stringify({ ...value, result_hash: hash(without) }))
}
test('RC failure inspection retains target, recorded reason and rollback without promotion', async () => {
  expect(await rcDesignBlockedStep(diagnosticBytes(failedStep()))).toEqual({ reason: 'line_search_failed_to_reduce_residual', target_m: -.002,
    accepted_targets: 1, rollback_exact: true, parent_immutable: true })
  expect(await rcDesignBlockedStep(await read('baseline/result.json'))).toBeNull()
})
test('RC failure inspection rejects original tampering and contradictory rollback', async () => {
  const bytes = diagnosticBytes(failedStep())
  await expect(rcDesignBlockedStep(new TextEncoder().encode(new TextDecoder().decode(bytes).replace('residual', 'corrupt')))).rejects.toThrow()
  const value = failedStep()
  value.path.attempts[0].accepted_checkpoint_hash = `sha256:${'b'.repeat(64)}`
  await expect(rcDesignBlockedStep(diagnosticBytes(value))).rejects.toThrow('study_failure_rollback_mismatch')
})
test('RC failure inspection does not turn unavailable or mistyped flags into success', async () => {
  const value = failedStep()
  value.path.attempts[0].rollback_exact = false
  expect((await rcDesignBlockedStep(diagnosticBytes(value)))!.rollback_exact).toBe(false)
  ;(value.path.attempts[0] as any).rollback_exact = 'true'
  await expect(rcDesignBlockedStep(diagnosticBytes(value))).rejects.toThrow('study_failure_step_invalid')
})
function rehash(raw: string): Uint8Array {
  const key = /,"report_hash":"sha256:[a-f0-9]{64}"/
  const without = raw.replace(key, '')
  return new TextEncoder().encode(raw.replace(key, `,"report_hash":"${hash(without)}"`))
}
test('RC study validates original constant preload and complete per-design work', async () => {
  const review = await validateRcDesignStudy(constantOriginal, constantRead)
  expect(review.report.verified_count).toBe(2)
  expect(review.report.control_request.constant_nodal_loads).toEqual([{ node_id: 'N2', FX_kN: -600, FY_kN: 0, MZ_kNm: 0 }])
  for (const row of review.report.rows) {
    expect(row.performance.accepted_epoch_count).toBe(4)
    expect(row.invocations.map((i: any) => i.work.attempted_step_count)).toEqual([4, 4])
  }
})
test('RC study rejects rehashed omission of preload from performance count', async () => {
  const changed = constantOriginal.toString().replace('"accepted_epoch_count":4', '"accepted_epoch_count":3')
  expect(changed).not.toBe(constantOriginal.toString())
  await expect(validateRcDesignStudy(rehash(changed), constantRead)).rejects.toThrow('study_performance_invalid')
})
test('RC study validates original full references, physical changes, quantity and price selection', async () => {
  const review = await validateRcDesignStudy(original, read)
  expect(review.report.verified_count).toBe(2)
  expect(review.report.candidate_denominator).toBe(3)
  expect(review.report.selected_candidate_id).toBe('baseline')
  expect(review.models.wider.sections[0].width_m).toBe(.5)
  expect(review.report.rows[2].status).toBe('invalid_candidate')
})
for (const role of ['model', 'result', 'checkpoint', 'verification', 'analysis_started', 'analysis_outcome', 'verification_started', 'verification_outcome']) {
  test(`RC study rejects changed original ${role}`, async () => {
    const report = JSON.parse(original.toString())
    const target = report.rows[0].artifacts[role].path
    await expect(validateRcDesignStudy(original, async path => path === target ? new Uint8Array(Buffer.concat([await read(path), Buffer.from(' ')])) : read(path))).rejects.toThrow()
  })
}
for (const [label, from, to] of [
  ['performance', '"accepted_epoch_count":3', '"accepted_epoch_count":4'],
  ['quantity delta', '"scoped_estimate_reduction":-21.0', '"scoped_estimate_reduction":-22.0'],
  ['selected candidate', '"selected_candidate_id":"baseline"', '"selected_candidate_id":"wider"'],
  ['authority', '"design_authority":false', '"design_authority":true'],
  ['byte path', 'baseline/result.json', '../result.json'],
  ['unknown work', '"unknown_execution_work":false', '"unknown_execution_work":true'],
]) {
  test(`RC study rejects rehashed ${label}`, async () => {
    expect(original.toString()).toContain(from)
    const changed = original.toString().replace(from, to)
    await expect(validateRcDesignStudy(rehash(changed), read)).rejects.toThrow()
  })
}
test('RC study refuses duplicate keys and oversized artifact budgets before artifact reads', async () => {
  let calls = 0
  await expect(validateRcDesignStudy(new TextEncoder().encode(original.toString().replace('{', '{"schema_version":"duplicate",')), async path => { calls++; return read(path) })).rejects.toThrow()
  expect(calls).toBe(0)
  await expect(validateRcDesignStudy(rehash(original.toString().replace(/"byte_length":\d+/, '"byte_length":999999999')), async path => { calls++; return read(path) })).rejects.toThrow()
  expect(calls).toBe(0)
})
for (const name of ['unpriced', 'strict']) {
  test(`RC study retains verification but blocks selection for ${name}`, async () => {
    const review = await validateRcDesignStudy(readFileSync(`${root}${name}.json`), read)
    expect(review.report.verified_count).toBe(2)
    expect(review.report.selected_candidate_id).toBeNull()
    expect(review.report.selection_status).toBe(name === 'unpriced' ? 'prices_unavailable' : 'no_verified_feasible_candidate')
  })
}
test('RC study preserves quantities and unknown verification work for a failed alternative', async () => {
  const review = await validateRcDesignStudy(readFileSync(`${root}failed.json`), path => read(path === 'wider/verification-outcome.json' ? 'synthetic-failed-verification-outcome.json' : path))
  expect(review.report.verified_count).toBe(1)
  expect(review.report.rows[1].quantities.totals.gross_concrete_volume_m3).toBeCloseTo(1.05)
  expect(review.report.rows[1].invocations[1]).toMatchObject({ status: 'raised', work: null, unknown_execution_work: true })
  expect(review.report.rows[1].selection_eligible).toBe(false)
})

test('RC study rejects unknown reuse profiles before trusting result files', async () => {
  const changed = original.toString().replace('{', '{"line_search_assembly_reuse":"unknown",')
  await expect(validateRcDesignStudy(rehash(changed), read)).rejects.toThrow('study_reuse_profile_invalid')
})
