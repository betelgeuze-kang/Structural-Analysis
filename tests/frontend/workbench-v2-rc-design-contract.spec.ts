import { fields, rawValues, rcControlHasPreload } from '../../src/workbench-v2/model/rcJobSchema'
import { pinRollerDesignBytes, pinRollerDesignRead, type PinRollerStudy } from './rcPinRollerDesignFixture'
import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { rcDesignBlockedStep, validateRcDesignStudy, validateRcStudyControl, validateRcTwoFixedStudyProfile, validateRcPinRollerStudyModel, rcStudyCompilerProfile } from '../../src/workbench-v2/model/rcControlDesignSchema'
import { portalDesignBytes, portalDesignRead } from './rcPortalDesignFixture'
const root = 'tests/frontend/fixtures/rc-control-design/'
const original = readFileSync(`${root}comparison.json`)
const hash = (s: string | Uint8Array) => `sha256:${createHash('sha256').update(s).digest('hex')}`
const read = async (path: string) => new Uint8Array(readFileSync(`${root}${path}`))
const constantRoot = 'tests/frontend/fixtures/rc-control-design-constant/'
const constantOriginal = readFileSync(`${constantRoot}comparison.json`)
const constantRead = async (path: string) => new Uint8Array(readFileSync(`${constantRoot}${path}`))
const portalRoot = 'examples/research/rc_internal_portal_20mm/'
const portalModel = JSON.parse(readFileSync(`${portalRoot}original-model.json`, 'utf8'))
const portalRequest = JSON.parse(readFileSync(`${portalRoot}experimental-two-fixed-endpoints-request.json`, 'utf8'))
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
test('experimental two-fixed study admits only an explicitly marked v3 request', () => {
  expect(() => validateRcStudyControl(portalRequest)).not.toThrow()
  expect(() => validateRcStudyControl({ ...portalRequest, experimental_two_fixed_endpoints: false })).toThrow('study_two_fixed_opt_in_invalid')
  expect(() => validateRcStudyControl({ ...portalRequest, experimental_two_fixed_endpoints: undefined })).toThrow('study_two_fixed_opt_in_invalid')
  expect(() => validateRcStudyControl({ ...portalRequest, schema_version: 'bounded-rc-fiber-direct-control-request.v2' })).toThrow('study_two_fixed_opt_in_invalid')
  expect(() => validateRcStudyControl({ ...portalRequest, constant_nodal_loads: [] })).toThrow('study_constant_loads_invalid')
  const withoutPreload = { ...portalRequest }
  delete withoutPreload.constant_nodal_loads
  expect(() => validateRcStudyControl(withoutPreload)).not.toThrow()
})
test('two-fixed study binds original endpoint supports and every support reaction', () => {
  const reactions = portalModel.supports.flatMap((support: any) => ['UX', 'UY', 'RZ'].map((dof) => ({ node_id: support.node, dof })))
  const histories = [{ support_reactions: reactions }, { support_reactions: [...reactions].reverse() }]
  expect(() => validateRcTwoFixedStudyProfile(portalModel, histories, portalRequest.constant_nodal_loads)).not.toThrow()
  expect(() => validateRcTwoFixedStudyProfile(portalModel, [histories[0], { support_reactions: reactions.slice(1) }])).toThrow('study_two_fixed_reactions_invalid')
  expect(() => validateRcTwoFixedStudyProfile(portalModel, histories, [{ node_id: portalModel.supports[0].node }])).toThrow('study_two_fixed_preload_support_invalid')
  const interiorSupport = structuredClone(portalModel)
  interiorSupport.supports[1].node = 'N3'
  expect(() => validateRcTwoFixedStudyProfile(interiorSupport, histories)).toThrow('study_two_fixed_support_invalid')
})
test('producer-derived two-fixed portal study retains three fresh-verified designs, quantities and common prices', async () => {
  const review = await validateRcDesignStudy(portalDesignBytes('comparison.json'), portalDesignRead)
  expect(review.report.control_request.schema_version).toBe('bounded-rc-fiber-direct-control-request.v3')
  expect(review.report.control_request.experimental_two_fixed_endpoints).toBe(true)
  expect(review.report.verified_count).toBe(3)
  expect(review.report.selected_candidate_id).toBe('narrower-036')
  expect(review.report.rows.map((row: any) => row.status)).toEqual(['verified', 'verified', 'verified'])
  for (const row of review.report.rows) {
    expect(row.performance.accepted_epoch_count).toBe(4)
    expect(row.quantities.members).toHaveLength(3)
    expect(row.invocations.map((invocation: any) => invocation.work.attempted_step_count)).toEqual([4, 4])
  }
})
function rehashNamed(raw: string, key: string): string {
  const pattern = new RegExp(`,"${key}":"sha256:[a-f0-9]{64}"`)
  const without = raw.replace(pattern, '')
  expect(without).not.toBe(raw)
  return raw.replace(pattern, `,"${key}":"${hash(without)}"`)
}
async function validateAlteredPortalResult(changedResult: string) {
  const originalResult = new TextDecoder().decode(portalDesignBytes('baseline/result.json'))
  const resultHashes = [hash(portalDesignBytes('baseline/result.json')), hash(changedResult)]
  const verifiedHash = JSON.parse(changedResult).result_hash
  const originalVerification = new TextDecoder().decode(portalDesignBytes('baseline/verification.json'))
  const changedVerification = originalVerification.replace(JSON.parse(originalResult).result_hash, verifiedHash)
  expect(changedVerification).not.toBe(originalVerification)
  let report = new TextDecoder().decode(portalDesignBytes('comparison.json'))
  report = report.replace(resultHashes[0], resultHashes[1])
    .replace(hash(portalDesignBytes('baseline/verification.json')), hash(changedVerification))
  const changedReport = new TextEncoder().encode(rehashNamed(report, 'report_hash'))
  return validateRcDesignStudy(changedReport, async path => path === 'baseline/result.json'
    ? new TextEncoder().encode(changedResult)
    : path === 'baseline/verification.json' ? new TextEncoder().encode(changedVerification) : portalDesignRead(path))
}
test('two-fixed study rejects a self-hashed but wrong compiler profile', async () => {
  const originalResult = new TextDecoder().decode(portalDesignBytes('baseline/result.json'))
  const profile = 'planar_serial_two_fixed_endpoints_explicit_rectangular_rc_direct_control.v1'
  expect(originalResult).toContain(profile)
  const changed = rehashNamed(originalResult.replace(profile, profile.replace('.v1', '.v0')), 'result_hash')
  await expect(validateAlteredPortalResult(changed)).rejects.toThrow('study_request_binding_invalid')
})
test('two-fixed study rejects a self-hashed result that drops the explicit opt-in', async () => {
  const originalResult = new TextDecoder().decode(portalDesignBytes('baseline/result.json'))
  const originalFlag = '"experimental_two_fixed_endpoints":true'
  expect(originalResult).toContain(originalFlag)
  const changed = rehashNamed(originalResult.replace(originalFlag, '"experimental_two_fixed_endpoints":null'), 'result_hash')
  await expect(validateAlteredPortalResult(changed)).rejects.toThrow('study_two_fixed_request_invalid')
})
test('two-fixed study rejects a self-hashed result that changes one constant preload', async () => {
  const originalResult = new TextDecoder().decode(portalDesignBytes('baseline/result.json'))
  const originalLoad = '"constant_nodal_loads":[{"FX_kN":0.0,"FY_kN":-25.0,"MZ_kNm":0.0,"node_id":"N3"}'
  expect(originalResult).toContain(originalLoad)
  const changed = rehashNamed(originalResult.replace(originalLoad, originalLoad.replace('-25.0', '-26.0')), 'result_hash')
  await expect(validateAlteredPortalResult(changed)).rejects.toThrow('study_request_binding_invalid')
})
test('two-fixed study rejects a self-hashed accepted row with a missing base reaction', async () => {
  const originalResult = new TextDecoder().decode(portalDesignBytes('baseline/result.json'))
  const historyAt = originalResult.indexOf('"response_history":')
  const reactionAt = originalResult.indexOf('"support_reactions":[', historyAt)
  const nodeAt = originalResult.indexOf('"node_id":"N2"', reactionAt)
  expect(historyAt).toBeGreaterThanOrEqual(0)
  expect(reactionAt).toBeGreaterThan(historyAt)
  expect(nodeAt).toBeGreaterThan(reactionAt)
  const changed = rehashNamed(originalResult.slice(0, nodeAt) + '"node_id":"N3"' + originalResult.slice(nodeAt + '"node_id":"N2"'.length), 'result_hash')
  await expect(validateAlteredPortalResult(changed)).rejects.toThrow('study_two_fixed_reactions_invalid')
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
test('RC study rejects a rehashed member estimate that disagrees with the common price table', async () => {
  const originalRow = '"concrete":60.0,"longitudinal_rebar":48.6072,"member_id":"M1"'
  expect(original.toString()).toContain(originalRow)
  const changed = original.toString().replace(originalRow, '"concrete":61.0,"longitudinal_rebar":48.6072,"member_id":"M1"')
  await expect(validateRcDesignStudy(rehash(changed), read)).rejects.toThrow('study_member_estimate_invalid')
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

// Exact authored producer originals; prices are regression inputs, not quotes.
const pinRaw = (path: string, study: PinRollerStudy = 'no-preload') => new TextDecoder().decode(pinRollerDesignBytes(path, study))
const pinModel = JSON.parse(pinRaw('baseline/model.json'))
const pinConfig = JSON.parse(pinRaw('comparison.json')).control_request
function pinUpdate(raw: string, path: (string | number)[], replacement: string): string {
  if (!path.length) return replacement
  const [key, ...rest] = path
  if (typeof key === 'number') {
    const items = rawValues(raw)
    expect(items[key]).toBeDefined()
    items[key] = pinUpdate(items[key], rest, replacement)
    return `[${items.join(',')}]`
  }
  const item = fields(raw).get(key)
  expect(item).toBeDefined()
  return raw.replace(item!.member, `${JSON.stringify(key)}:${pinUpdate(item!.value, rest, replacement)}`)
}
function pinSelfHash(raw: string, key: string): string {
  const items = fields(raw)
  expect(items.delete(key)).toBe(true)
  return pinUpdate(raw, [key], JSON.stringify(hash(`{${[...items.values()].map(item => item.member).join(',')}}`)))
}
async function pinAlteredResult(transform: (raw: string) => string, study: PinRollerStudy = 'no-preload') {
  const result = pinSelfHash(transform(pinRaw('baseline/result.json', study)), 'result_hash')
  const verification = pinUpdate(pinRaw('baseline/verification.json', study), ['verified_result_hash'], JSON.stringify(JSON.parse(result).result_hash))
  let report = pinRaw('comparison.json', study)
  for (const [role, raw] of [['result', result], ['verification', verification]]) {
    report = pinUpdate(report, ['rows', 0, 'artifacts', role, 'sha256'], JSON.stringify(hash(raw)))
    report = pinUpdate(report, ['rows', 0, 'artifacts', role, 'byte_length'], String(new TextEncoder().encode(raw).byteLength))
  }
  return validateRcDesignStudy(new TextEncoder().encode(pinSelfHash(report, 'report_hash')), async path => path === 'baseline/result.json'
    ? new TextEncoder().encode(result) : path === 'baseline/verification.json' ? new TextEncoder().encode(verification) : pinRollerDesignBytes(path, study))
}
for (const study of ['no-preload', 'preload'] as const) {
  test(`pin/roller ${study} study preserves actual fresh references, full quantities, prices and work`, async () => {
    const review = await validateRcDesignStudy(pinRollerDesignBytes('comparison.json', study), pinRollerDesignRead(study))
    expect(review.report.status).toBe('complete')
    expect(review.report.verified_count).toBe(2)
    expect(review.report.selected_candidate_id).toBe('narrower')
    expect(review.report.control_request).toMatchObject({ schema_version: 'bounded-rc-fiber-direct-control-request.v4', experimental_pin_roller_beam: true, control_global_dof: 10 })
    expect(rcStudyCompilerProfile(review.report.control_request)).toBe('planar_serial_horizontal_pin_roller_beam_explicit_rectangular_rc_direct_control.v1')
    expect(rcControlHasPreload(review.report.control_request)).toBe(study === 'preload')
    for (const row of review.report.rows) {
      expect(row.status).toBe('verified')
      expect(row.full_reference_verification_pass).toBe(true)
      expect(row.performance.accepted_epoch_count).toBe(study === 'preload' ? 3 : 2)
      expect(row.invocations.map((i: any) => [i.status, i.work.attempted_step_count, i.unknown_execution_work])).toEqual([
        ['returned', study === 'preload' ? 3 : 2, false], ['returned', study === 'preload' ? 3 : 2, false],
      ])
      expect(row.quantities.members).toHaveLength(6)
      expect(row.quantities.members.reduce((sum: number, m: any) => sum + m.length_m, 0)).toBeCloseTo(1.9, 14)
      expect(row.quantities.totals.longitudinal_rebar_mass_kg).toBe(46.17684)
      const api = JSON.parse(pinRaw(`${row.candidate_id}/result.json`, study))
      expect(api.control).toMatchObject({ global_dof: 10, node_id: 'N4', component: 'UY', unit: 'm' })
      const history = study === 'preload' ? [api.preload_response, ...api.response_history] : api.response_history
      for (const entry of history) expect(entry.support_reactions.map((r: any) => [r.node_id, r.dof, r.unit])).toEqual([
        ['N2', 'UX', 'N'], ['N2', 'UY', 'N'], ['N6', 'UY', 'N'],
      ])
    }
    expect(review.report.rows[0].quantities.totals.gross_concrete_volume_m3).toBeCloseTo(.456, 14)
    expect(review.report.rows[1].quantities.totals.gross_concrete_volume_m3).toBe(.4104)
    expect(review.report.rows[1].scoped_estimate_reduction).toBeCloseTo(4.56, 14)
    expect(review.report.claims.confirmed_currency_savings).toBe(false)
    expect(review.report.claims.independent_physical_validation).toBe(false)
  })
}
for (const study of ['fixed-control', 'support-preload'] as const) {
  test(`pin/roller review preserves actual ${study} producer failure without acceptance`, async () => {
    const review = await validateRcDesignStudy(pinRollerDesignBytes('comparison.json', study), pinRollerDesignRead(study))
    expect(review.report.status).toBe('incomplete')
    expect(review.report.verified_count).toBe(0)
    expect(review.report.selected_candidate_id).toBeNull()
    expect(review.report.rows).toHaveLength(2)
    for (const row of review.report.rows) {
      expect(row.status).toBe('execution_error')
      expect(row.full_reference_verification_pass).toBe(false)
      expect(row.selection_eligible).toBe(false)
      expect(row.performance).toBeNull()
      expect(row.quantities.members).toHaveLength(6)
      expect(row.invocations).toHaveLength(1)
      expect(row.invocations[0]).toMatchObject({ status: 'raised', unknown_execution_work: true, work: null })
      expect(row.failure).toBeTruthy()
    }
  })
}
test('pin/roller direct study opt-in is exact, exclusive and keeps preload optional', () => {
  expect(() => validateRcStudyControl(pinConfig)).not.toThrow()
  for (const value of [undefined, false, 1, 'true']) expect(() => validateRcStudyControl({ ...pinConfig, experimental_pin_roller_beam: value })).toThrow('study_pin_roller_opt_in_invalid')
  expect(() => validateRcStudyControl({ ...pinConfig, experimental_two_fixed_endpoints: true })).toThrow()
  expect(() => validateRcStudyControl({ ...pinConfig, schema_version: 'bounded-rc-fiber-direct-control-request.v1' })).toThrow('study_pin_roller_opt_in_invalid')
  for (const value of [[], [{ node_id: 'N4', FX_kN: 0, FY_kN: NaN, MZ_kNm: 0 }]]) {
    expect(() => validateRcStudyControl({ ...pinConfig, constant_nodal_loads: value })).toThrow('study_constant_loads_invalid')
  }
})
test('pin/roller model contract matches supported overhang and either pin/roller ordering', () => {
  expect(() => validateRcPinRollerStudyModel(pinModel, pinConfig)).not.toThrow()
  const swapped = structuredClone(pinModel)
  swapped.supports.reverse()
  expect(() => validateRcPinRollerStudyModel(swapped, pinConfig)).not.toThrow()
  const reversedRoles = structuredClone(pinModel)
  reversedRoles.supports[0].dofs = ['UY']; reversedRoles.supports[1].dofs = ['UY', 'UX']
  expect(() => validateRcPinRollerStudyModel(reversedRoles, pinConfig)).not.toThrow()
  expect(() => validateRcPinRollerStudyModel(pinModel, { ...pinConfig, control_global_dof: 1 })).not.toThrow()
})
for (const [label, mutation, error] of [
  ['support DOFs', (m: any) => { m.supports[1].dofs = ['UX', 'UY'] }, 'study_pin_roller_support_invalid'],
  ['nonhorizontal Y', (m: any) => { m.nodes[0].coordinates[1] = .01 }, 'study_pin_roller_geometry_invalid'],
  ['out of plane Z', (m: any) => { m.nodes[0].coordinates[2] = .01 }, 'study_pin_roller_geometry_invalid'],
  ['duplicate X', (m: any) => { m.nodes[0].coordinates[0] = m.nodes[1].coordinates[0] }, 'study_pin_roller_geometry_invalid'],
  ['folded member chain', (m: any) => { m.elements[0].nodes = ['N1', 'N3'] }, 'study_pin_roller_geometry_invalid'],
  ['load at a support', (m: any) => { m.loads[0].node = 'N2' }, 'study_pin_roller_load_invalid'],
] as const) {
  test(`pin/roller verified model rejects ${label}`, () => {
    const model = structuredClone(pinModel); mutation(model)
    expect(() => validateRcPinRollerStudyModel(model, pinConfig)).toThrow(error)
  })
}
for (const dof of [4, 16, 11, 99]) test(`pin/roller verified model rejects invalid or restrained control DOF ${dof}`, () => {
  expect(() => validateRcPinRollerStudyModel(pinModel, { ...pinConfig, control_global_dof: dof })).toThrow('study_pin_roller_control_invalid')
})
for (const node_id of ['N2', 'missing']) test(`pin/roller verified model rejects preload at ${node_id}`, () => {
  expect(() => validateRcPinRollerStudyModel(pinModel, { ...pinConfig, constant_nodal_loads: [{ node_id, FX_kN: 0, FY_kN: -.01, MZ_kNm: 0 }] })).toThrow('study_pin_roller_preload_support_invalid')
})
for (const [label, path, replacement, error] of [
  ['compiler profile', ['model', 'compiler_profile'], '"planar_serial_cantilever_explicit_rectangular_rc.v1"', 'study_request_binding_invalid'],
  ['missing result opt-in', ['request', 'experimental_pin_roller_beam'], 'null', 'study_pin_roller_request_invalid'],
  ['false result opt-in', ['request', 'experimental_pin_roller_beam'], 'false', 'study_pin_roller_request_invalid'],
  ['wrong control node', ['control', 'node_id'], '"N3"', 'study_pin_roller_control_binding_invalid'],
  ['wrong control component', ['control', 'component'], '"UX"', 'study_pin_roller_control_binding_invalid'],
] as const) {
  test(`pin/roller rejects self-hashed ${label} with exact original artifact digests`, async () => {
    await expect(pinAlteredResult(raw => pinUpdate(raw, [...path], replacement))).rejects.toThrow(error)
  })
}
for (const study of ['no-preload', 'preload'] as const) {
  for (const mode of ['missing', 'extra', 'reordered', 'wrong-identity'] as const) {
    test(`pin/roller ${study} rejects self-hashed ${mode} reaction rows`, async () => {
      await expect(pinAlteredResult(raw => {
        const path: (string | number)[] = study === 'preload' ? ['preload_response', 'support_reactions'] : ['response_history', 0, 'support_reactions']
        let reactionRaw = raw
        for (const key of path) reactionRaw = typeof key === 'number' ? rawValues(reactionRaw)[key] : fields(reactionRaw).get(key)!.value
        const rows = rawValues(reactionRaw)
        const changed = mode === 'missing' ? rows.slice(1) : mode === 'extra' ? [...rows, rows[0]] : mode === 'reordered' ? [...rows].reverse()
          : [pinUpdate(rows[0], ['node_id'], '"N3"'), ...rows.slice(1)]
        return pinUpdate(raw, path, `[${changed.join(',')}]`)
      }, study)).rejects.toThrow('pin_roller_reaction_invalid')
    })
  }
}
test('pin/roller direct preload result binds the exact constant loads', async () => {
  await expect(pinAlteredResult(raw => pinUpdate(raw, ['request', 'constant_nodal_loads', 0, 'FY_kN'], '-0.02'), 'preload')).rejects.toThrow('study_request_binding_invalid')
})
test('pin/roller study rejects a self-hashed quantity that differs from model geometry', async () => {
  let report = pinRaw('comparison.json')
  let quantity = fields(rawValues(fields(report).get('rows')!.value)[0]).get('quantities')!.value
  quantity = pinSelfHash(pinUpdate(quantity, ['members', 0, 'gross_concrete_volume_m3'], '0.099'), 'quantity_hash')
  report = pinUpdate(report, ['rows', 0, 'quantities'], quantity)
  await expect(validateRcDesignStudy(new TextEncoder().encode(pinSelfHash(report, 'report_hash')), pinRollerDesignRead())).rejects.toThrow('study_member_quantity_invalid')
})
test('pin/roller study rejects member prices that differ from the common price table', async () => {
  const report = pinUpdate(pinRaw('comparison.json'), ['rows', 0, 'material_estimate', 'members', 0, 'concrete'], '999')
  await expect(validateRcDesignStudy(new TextEncoder().encode(pinSelfHash(report, 'report_hash')), pinRollerDesignRead())).rejects.toThrow('study_member_estimate_invalid')
})
