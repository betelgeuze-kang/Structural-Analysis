import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { validateRcDesignStudy } from '../../src/workbench-v2/model/rcControlDesignSchema'
const root = 'tests/frontend/fixtures/rc-control-design/'
const original = readFileSync(`${root}comparison.json`)
const hash = (s: string | Uint8Array) => `sha256:${createHash('sha256').update(s).digest('hex')}`
const read = async (path: string) => new Uint8Array(readFileSync(`${root}${path}`))
const constantRoot = 'tests/frontend/fixtures/rc-control-design-constant/'
const constantOriginal = readFileSync(`${constantRoot}comparison.json`)
const constantRead = async (path: string) => new Uint8Array(readFileSync(`${constantRoot}${path}`))
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
