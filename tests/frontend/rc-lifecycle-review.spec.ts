import { test, expect } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import { readFileSync, writeFileSync, mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { validateRcJobArtifacts, validateRcRequestProfile, validateRcDeclaredInitialTrials, fields } from '../../src/workbench-v2/model/rcJobSchema'
import { validateRcQuantityReport } from '../../src/workbench-v2/model/rcQuantityReportSchema'
import { sha256Hex } from '../../src/workbench-v2/model/checksum'

for (const { profile, isolated, prescribed, search, secant } of [
  { profile: 'legacy', isolated: false, prescribed: false, search: false, secant: false },
  { profile: 'explicit-layers', isolated: false, prescribed: false, search: false, secant: false },
  { profile: 'explicit-layers', isolated: true, prescribed: false, search: false, secant: false },
  { profile: 'explicit-layers', isolated: true, prescribed: true, search: false, secant: false },
  { profile: 'explicit-layers', isolated: true, prescribed: false, search: true, secant: false },
  { profile: 'explicit-layers', isolated: true, prescribed: false, search: true, secant: true },
] as const) {
test.describe(`Narrow RC ${profile} ${isolated ? 'isolated' : 'inline'} ${secant ? 'secant' : search ? 'search' : prescribed ? 'prescribed' : 'accepted'} reviewer with freshly computed artifacts`, () => {
  test.describe.configure({ mode: 'serial', timeout: 120000 })
  let temporary: string, snapshot: any, reviewed: Awaited<ReturnType<typeof validateRcJobArtifacts>>
  const bytes = (value: string) => new Uint8Array(Buffer.from(value, 'base64'))
  test.beforeAll(async () => {
    temporary = mkdtempSync(path.join(tmpdir(), 'rc-review-contract-'))
    const output = path.join(temporary, 'review.json')
    const authored = JSON.parse(execFileSync('python', ['-c',
      `import sys; sys.path.insert(0, 'tests/frontend'); from rc_lifecycle_http_fixture import ${profile === 'legacy' ? 'authored_request' : 'authored_explicit_layers_request as authored_request'}, canonical; print(canonical(authored_request()).decode())`], { encoding: 'utf8' }))
    if (isolated) authored.execution_config.phase_execution_policy = {
      schema_version: 'bounded-rc-fiber-phase-execution-policy.v1',
      analysis_timeout_ms: 30000, verification_timeout_ms: 30000, termination_grace_ms: 100,
    }
    if (prescribed) authored.config.solver_config.initial_trial_policy = 'prescribed_control'
    if (search) authored.config.solver_config.initial_trial_policy = secant ? 'accepted_then_prescribed_then_secant' : 'accepted_then_prescribed'
    const requestFile = path.join(temporary, 'browser-request.json')
    // The exact browser JSON.stringify boundary converts Python 1.0 to JSON 1.
    writeFileSync(requestFile, JSON.stringify(authored))
    execFileSync('python', ['tests/frontend/rc_lifecycle_review_snapshot.py', '--output', output, '--request-file', requestFile], { timeout: 100000, stdio: 'pipe' })
    snapshot = JSON.parse(readFileSync(output, 'utf8'))
    reviewed = await validateRcJobArtifacts(snapshot.job, Object.fromEntries(
      Object.entries(snapshot.artifacts).map(([role, value]: [string, any]) => [role, bytes(value.base64)])), 'a')
  })
  test.afterAll(() => { if (temporary) rmSync(temporary, { recursive: true, force: true }) })

  test('verifies original execution, unknown reservation and two price-only revisions', async () => {
    expect(snapshot.original_request_representation_retained).toBe(true)
    expect(reviewed.summary.targets).toEqual([-1e-6, -2e-6])
    expect(reviewed.summary.unknownWork).toBe(true)
    expect(reviewed.summary.reservedInvocations).toBe(5)
    expect(snapshot.reports.map((row: any) => row.reference.revision)).toEqual([1, 2])
    const reports = await Promise.all(snapshot.reports.map((row: any) =>
      validateRcQuantityReport(bytes(row.base64), reviewed.quantitySource, row.reference)))
    expect(reports[0].bindings).toEqual(reports[1].bindings)
    expect(reports[0].quantities).toEqual(reports[1].quantities)
    expect(reports[0].declared_prices).not.toEqual(reports[1].declared_prices)
    if (profile === 'explicit-layers') expect(reports[0].quantities.totals.longitudinal_rebar_mass_kg).toBeCloseTo(28.26, 10)
  })

  test('rejects unsupported request extensions before submission', () => {
    const original = JSON.parse(Buffer.from(snapshot.artifacts.request.base64, 'base64').toString())
    expect(() => validateRcRequestProfile(original)).not.toThrow()
    for (const mutate of [
      (r: any) => { r.config.solver_config.newton.terminal_polishing = false },
      (r: any) => { r.config.solver_config.initial_trial_policy = 'automatic_retry' },
      (r: any) => { r.config.constant_nodal_loads = [] },
      (r: any) => { r.config.schema_version = 'bounded-rc-fiber-direct-control-request.v4' },
      (r: any) => { r.config.experimental_two_fixed_endpoints = true },
      (r: any) => { r.execution_config.reuse_line_search_assembly = false },
      (r: any) => { r.execution_config.phase_execution_policy = {} },
    ]) {
      const request = structuredClone(original); mutate(request)
      expect(() => validateRcRequestProfile(request)).toThrow()
    }
  })

  if (search) test('rejects altered trial work and parent bindings without trusting summary totals', () => {
    const result = JSON.parse(Buffer.from(snapshot.artifacts.result.base64, 'base64').toString())
    const request = JSON.parse(Buffer.from(snapshot.artifacts.request.base64, 'base64').toString())
    expect(() => validateRcDeclaredInitialTrials(result.api_result, request.config)).not.toThrow()
    for (const mutate of [
      (step: any) => { step.initial_trial_search.trials[0].work.known_linear_solve_count += 1 },
      (step: any) => { step.initial_trial_search.trials[0].parent_checkpoint_hash = 'sha256:' + '0'.repeat(64) },
      (step: any) => { step.initial_trial_search.maximum_trials = secant ? 2 : 3 },
      (step: any) => { step.initial_trial_search.trials[0].solver.metrics.linear_solve_count += 1 },
    ]) {
      const api = structuredClone(result.api_result)
      mutate([...api.path.replay_attempts, ...api.path.attempts][0].step)
      expect(() => validateRcDeclaredInitialTrials(api, request.config)).toThrow(/initial_trial_/)
    }
  })

  test('fails closed for changed original bytes and cross-tenant report source', async () => {
    const artifacts = Object.fromEntries(Object.entries(snapshot.artifacts).map(([role, value]: [string, any]) => [role, bytes(value.base64)]))
    artifacts.result[artifacts.result.length - 1] ^= 1
    await expect(validateRcJobArtifacts(snapshot.job, artifacts, 'a')).rejects.toThrow('byte_hash_mismatch')
    await expect(validateRcQuantityReport(bytes(snapshot.reports[1].base64), { ...reviewed.quantitySource, tenantId: 'b' }, snapshot.reports[1].reference)).rejects.toThrow()
  })

  test('rederives declared price totals even when a forged report is self-hashed', async () => {
    const raw = Buffer.from(snapshot.reports[1].base64, 'base64').toString()
    const members = fields(raw), estimate = fields(members.get('material_estimate')!.value)
    estimate.set('total', { member: '"total":999999', value: '999999' })
    const estimateRaw = `{${[...estimate.values()].map(row => row.member).join(',')}}`
    members.set('material_estimate', { member: `"material_estimate":${estimateRaw}`, value: estimateRaw })
    members.delete('report_hash')
    const hash = await sha256Hex(`{${[...members.values()].map(row => row.member).join(',')}}`)
    members.set('report_hash', { member: `"report_hash":${JSON.stringify(hash)}`, value: JSON.stringify(hash) })
    const forged = new TextEncoder().encode(`{${[...members].sort(([a], [b]) => a < b ? -1 : 1).map(([,row])=>row.member).join(',')}}`)
    await expect(validateRcQuantityReport(forged, reviewed.quantitySource)).rejects.toThrow('study_estimate_invalid')
  })
})

}


test.describe('Third-seed trace auditor with fresh numerical projection', () => {
  test.describe.configure({ mode: 'serial', timeout: 300000 })
  let temporary: string, packet: any
  test.beforeAll(() => {
    temporary = mkdtempSync(path.join(tmpdir(), 'rc-secant-trace-'))
    const output = path.join(temporary, 'trace.json')
    execFileSync('python', ['tests/frontend/rc_lifecycle_review_snapshot.py', '--secant-trace', '--output', output],
      { timeout: 295000, stdio: 'pipe' })
    packet = JSON.parse(readFileSync(output, 'utf8'))
  })
  test.afterAll(() => { if (temporary) rmSync(temporary, { recursive: true, force: true }) })
  test('recomputes the actual third initial vector and all rejected-trial work', () => {
    expect(packet.scope).toContain('not a complete product artifact')
    expect(packet.api.path.attempts.at(-1).step.initial_trial_search.trials).toHaveLength(3)
    expect(() => validateRcDeclaredInitialTrials(packet.api, packet.config)).not.toThrow()
    expect(Object.keys(packet.api.path.metrics).sort())
      .toEqual(['prefix_replay_work', 'suffix_work', 'total_work'])
    const generation = packet.fixture_generation
    console.log(JSON.stringify({
      evidence: 'bounded_real_third_seed_fixture_work',
      probes: generation.probes.map((probe: any) => ({
        target_m: probe.target_control_displacement_m,
        committed: probe.committed,
        trials: probe.solver_work.declared_initial_trial_attempt_count,
        linear_solves: probe.solver_work.linear_solve_count,
      })),
      generation_work: generation.total_work,
      selected_path_work: packet.api.metrics.control_work,
    }))
    expect(generation.scope).toContain('not specimen calibration')
    expect(generation.probes.length).toBeGreaterThan(0)
    expect(generation.probes.length).toBeLessThanOrEqual(generation.candidate_targets_m.length)
    expect(generation.probes.map((probe: any) => probe.target_control_displacement_m))
      .toEqual(generation.candidate_targets_m.slice(0, generation.probes.length))
    const probeSolves = generation.probes.reduce((sum: number, probe: any) =>
      sum + probe.solver_work.linear_solve_count, 0)
    expect(generation.total_work.known_linear_solve_count)
      .toBe(generation.prefix_work.known_linear_solve_count + probeSolves)
    expect(generation.total_work.attempted_step_count)
      .toBe(generation.prefix_work.attempted_step_count + generation.probes.length)
    expect(generation.total_work.unknown_solver_work_attempt_count).toBe(0)
    expect(generation.probes.at(-1).committed).toBe(true)
    expect(generation.probes.at(-1).solver_work.declared_initial_trial_attempt_count).toBe(3)
  })
  test('rejects changed predecessor, ratio, seed, iteration start, order and work', () => {
    for (const mutate of [
      (step: any) => { step.initial_trial_search.secant_predecessor_hash = null },
      (step: any) => { step.initial_trial_search.trials[2].prediction.previous_checkpoint_hash = 'sha256:' + '0'.repeat(64) },
      (step: any) => { step.initial_trial_search.trials[2].prediction.ratio += 1 },
      (step: any) => { step.initial_trial_search.trials[2].prediction.initial_coordinates_m[0] += .001 },
      (step: any) => { step.initial_trial_search.trials[2].solver.convergence_history[0].free_displacements_m[0] += .001 },
      (step: any) => { step.initial_trial_search.trials[2].initial_trial_policy = 'prescribed_control' },
      (step: any) => { step.initial_trial_search.trials[2].work.known_linear_solve_count += 1 },
      (step: any) => { step.initial_trial_search.maximum_trials = 4 },
    ]) {
      const api = structuredClone(packet.api)
      mutate(api.path.attempts.at(-1).step)
      expect(() => validateRcDeclaredInitialTrials(api, packet.config)).toThrow(/initial_trial_/)
    }
  })
})
