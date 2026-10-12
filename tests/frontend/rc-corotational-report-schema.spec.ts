import { test, expect } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import { mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { sha256Hex } from '../../src/workbench-v2/model/checksum'
import { fields, rawValues, validateRcRequestProfile } from '../../src/workbench-v2/model/rcJobSchema'
import {
  parseRcCorotationalReport, RC_COROTATIONAL_REPORT_MAX_BYTES,
  type RcCorotationalReportExpected,
} from '../../src/workbench-v2/model/rcCorotationalReportSchema'

/** Replace one original token; preserve every other Python numeric spelling. */
function replace(raw: string, route: (string | number)[], replacement: string): string {
  if (!route.length) return replacement
  const [key, ...rest] = route
  if (typeof key === 'number') {
    const values = rawValues(raw)
    values[key] = replace(values[key], rest, replacement)
    return `[${values.join(',')}]`
  }
  const members = fields(raw), previous = members.get(key)
  if (!previous && rest.length) throw new Error('test_mutation_path_invalid')
  const value = replace(previous?.value ?? '', rest, replacement)
  members.set(key, { member: `${JSON.stringify(key)}:${value}`, value })
  return `{${[...members].sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0).map(([, row]) => row.member).join(',')}}`
}

async function rehash(raw: string): Promise<Uint8Array> {
  const members = fields(raw)
  members.delete('report_hash')
  const digest = await sha256Hex(`{${[...members.values()].map(row => row.member).join(',')}}`)
  if (!digest) throw new Error('test_hash_unavailable')
  members.set('report_hash', { member: `"report_hash":${JSON.stringify(digest)}`, value: JSON.stringify(digest) })
  return new TextEncoder().encode(`{${[...members].sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0).map(([, row]) => row.member).join(',')}}`)
}

for (const profile of ['v6', 'v7'] as const) {
  test.describe(`Strict saved corotational nodal report ${profile}`, () => {
    test.describe.configure({ mode: 'serial', timeout: 300000 })
    let temporary: string | undefined, snapshot: any, raw: string, expected: RcCorotationalReportExpected
    test.beforeAll(() => {
      const retained = process.env.RC_COROTATIONAL_REPORT_FIXTURE_DIR
      const directory = retained ?? (temporary = mkdtempSync(path.join(tmpdir(), 'rc-coro-schema-')))
      const output = path.join(directory, `${profile}-review-snapshot.json`)
      if (!retained) execFileSync('python3', [
        'tests/frontend/rc_corotational_review_snapshot.py', '--output', output, '--profile', profile,
      ], { timeout: 290000, stdio: 'pipe' })
      snapshot = JSON.parse(readFileSync(output, 'utf8'))
      raw = Buffer.from(snapshot.report.body_base64, 'base64').toString('utf8')
      expected = { job: snapshot.job, tenantId: snapshot.tenant_id, request: snapshot.request }
    })
    test.afterAll(() => { if (temporary) rmSync(temporary, { recursive: true, force: true }) })
    const parse = (input = raw, bindings = expected) => parseRcCorotationalReport(new TextEncoder().encode(input), bindings)
    const rejects = async (route: (string | number)[], token: string) => {
      await expect(parseRcCorotationalReport(await rehash(replace(raw, route, token)), expected))
        .rejects.toThrow(/^rc_corotational_report_[a-z_]+$/)
    }

    test('accepts original Python bytes and keeps attempt, target and accepted-state counts distinct', async () => {
      const report = await parse()
      expect(report.responses).toHaveLength(4)
      expect(report.progress.authored_targets).toEqual({ completed: 3, total: 3 })
      expect(report.progress.control_solver_attempts).toEqual({ completed: 3, maximum: 255 })
      expect(report.execution.budget).toEqual({ maximum_attempts: 6, reserved_attempts: 5, remaining_attempts: 1 })
      expect(report.execution.pending_ordinals).toEqual([3])
      expect(report.execution.unknown_execution_work).toBe(true)
      expect(report.responses[0].phase).toBe('preload')
      expect(report.responses.some(row => row.load_factor < 0)).toBe(true)
      expect(report.responses.some(row => row.load_factor > 0)).toBe(true)
      expect(report.structural_authority).toEqual({
        experimental_corotational_rc_control: true, trusted_worker_verification_attestation: true,
        service_numerical_verification_performed: false, independent_execution_authentication: false,
        independent_physical_validation: false, design_authority: false, release_approved: false,
        production_promotion_eligible: false,
      })
      expect(report.derivation.fresh_analysis_invocations).toBe(0)
    })

    test('accepts a synthetic subdivision within tolerance of a single authored goal', async () => {
      // Shape-only regression based on retained tokens: it grants no service,
      // execution or physical authenticity to this deliberately edited document.
      const original = JSON.parse(raw), goal = original.declarations.targets_m[0]
      const nearGoal = goal + original.declarations.config.config.control_tolerance_m / 2
      const nodeIndex = expected.request.model && (expected.request.model as any).nodes
        .findIndex((node: any) => node.id === original.declarations.control.node_id)
      const component = original.declarations.control.component === 'UX' ? 0 : 1
      const rows = rawValues(fields(raw).get('responses')!.value)
      const insertedHash = `"sha256:${'d'.repeat(64)}"`
      let subdivision = replace(rows[1], ['checkpoint_hash'], insertedHash)
      subdivision = replace(subdivision, ['control_displacement_m'], JSON.stringify(nearGoal))
      subdivision = replace(subdivision, ['nodes', nodeIndex as number, 'displacements_m_rad', component], JSON.stringify(nearGoal))
      let terminal = replace(rows[1], ['state_index'], '2')
      terminal = replace(terminal, ['parent_checkpoint_hash'], insertedHash)
      let edited = replace(raw, ['responses'], `[${rows[0]},${subdivision},${terminal}]`)
      edited = replace(edited, ['progress', 'accepted_response_states'], '3')
      edited = replace(edited, ['progress', 'authored_targets', 'completed'], '1')
      edited = replace(edited, ['progress', 'authored_targets', 'total'], '1')
      edited = replace(edited, ['declarations', 'targets_m'], JSON.stringify([goal]))
      edited = replace(edited, ['declarations', 'config', 'targets_m'], JSON.stringify([goal]))
      const request = structuredClone(expected.request)
      ;(request.config as any).targets_m = [goal]
      const parsed = await parseRcCorotationalReport(await rehash(edited), { ...expected, request })
      expect(parsed.responses).toHaveLength(3)
      expect(parsed.progress.authored_targets).toEqual({ completed: 1, total: 1 })
    })

    test('admits the distinct original corotational request profile and case-insensitive axes', () => {
      expect(() => validateRcRequestProfile(expected.request)).not.toThrow()
      const lowerAxes = structuredClone(expected.request) as any
      lowerAxes.model.coordinate_system = { axis_order: ['x', 'y', 'z'], up_axis: 'z' }
      expect(() => validateRcRequestProfile(lowerAxes)).not.toThrow()
    })

    test('rejects incompatible execution policy, restrained control, units and duplicate fixed load requests', () => {
      for (const mutate of [
        (request: any) => { if (profile === 'v7') delete request.execution_config.phase_execution_policy
          else request.execution_config.phase_execution_policy = { schema_version: 'bounded-rc-corotational-phase-execution-policy.v1', analysis_timeout_ms: 60000, verification_timeout_ms: 60000, termination_grace_ms: 500 } },
        (request: any) => { request.config.control_component = 'RZ' },
        (request: any) => { request.config.control_node_id = request.model.supports[0].node; request.config.control_component = request.model.supports[0].dofs.find((dof: string) => ['UX', 'UY'].includes(dof)) },
        (request: any) => { request.config.control_node_id = 'unknown-node' },
        (request: any) => { request.model.units.length = 'mm' },
        (request: any) => { request.model.units.force = 'N' },
        (request: any) => { request.config.fixed_nodal_loads.push([...request.config.fixed_nodal_loads[0]]) },
        (request: any) => { request.config.config.matrix_backend = 'scipy_sparse_spsolve_cpu' },
      ]) {
        const request = structuredClone(expected.request)
        mutate(request)
        expect(() => validateRcRequestProfile(request)).toThrow(/^rc_review_/)
      }
      if (profile === 'v7') for (const mutate of [
        (policy: any) => { policy.schema_version = 'bounded-rc-fiber-phase-execution-policy.v1' },
        (policy: any) => { policy.analysis_timeout_ms = 0 },
        (policy: any) => { policy.verification_timeout_ms = 3600001 },
        (policy: any) => { policy.termination_grace_ms = 5001 },
        (policy: any) => { policy.extra = false },
      ]) {
        const request = structuredClone(expected.request) as any
        mutate(request.execution_config.phase_execution_policy)
        expect(() => validateRcRequestProfile(request)).toThrow(/^rc_review_/)
      }
    })

    test('rejects coherent self-hashed changes to original identity and artifact references', async () => {
      for (const [route, token] of [
        [['bindings', 'tenant_id'], '"other"'],
        [['bindings', 'job_id'], '"job_00000000000000000000000000000000"'],
        [['bindings', 'completed_job_revision'], '999'],
        [['bindings', 'terminal_event_hash'], `"sha256:${'0'.repeat(64)}"`],
        [['bindings', 'original_artifacts', 'request', 'content_hash'], `"sha256:${'0'.repeat(64)}"`],
        [['bindings', 'original_artifacts', 'result', 'byte_length'], '1'],
        [['bindings', 'original_artifacts', 'checkpoint'], 'null'],
        [['bindings', 'resume_contract_hash'], `"sha256:${'0'.repeat(64)}"`],
        [['bindings', 'source_revision'], `"${'0'.repeat(40)}"`],
      ] as [(string | number)[], string][]) await rejects(route, token)
      await expect(parse(raw, { ...expected, tenantId: 'other' })).rejects.toThrow('source_binding_invalid')
      await expect(parse(raw, { ...expected, job: { ...expected.job, schema_version: 'structural-analysis-job-view.v1' } }))
        .rejects.toThrow('job_invalid')
    })

    test('rejects changes to every retained declaration without reconstructing numerical JSON', async () => {
      for (const [route, token] of [
        [['declarations', 'control', 'component'], '"UX"'],
        [['declarations', 'targets_m', 0], '123.0'],
        [['declarations', 'fixed_nodal_loads'], '[]'],
        [['declarations', 'reference_loads'], '[]'],
        [['declarations', 'supports'], '[]'],
        [['declarations', 'model_units', 'force'], '"N"'],
        [['declarations', 'coordinate_system', 'up_axis'], '"Y"'],
        [['declarations', 'model_metadata'], '{}'],
        [['declarations', 'config', 'maximum_attempt_count'], '256'],
        [['declarations', 'execution_config', 'maximum_api_invocations'], '7'],
      ] as [(string | number)[], string][]) await rejects(route, token)
    })

    test('rejects extra fiber/J1–J5 data and any physical, design or release authority promotion', async () => {
      for (const key of ['service_numerical_verification_performed', 'independent_execution_authentication',
        'independent_physical_validation', 'design_authority', 'release_approved', 'production_promotion_eligible']) {
        await rejects(['structural_authority', key], 'true')
      }
      for (const key of ['experimental_corotational_rc_control', 'trusted_worker_verification_attestation']) {
        await rejects(['structural_authority', key], 'false')
      }
      await rejects(['structural_authority', 'public_j1_j5_authority'], 'false')
      await rejects(['responses', 1, 'fiber_results'], '[]')
      await rejects(['responses', 1, 'member_end_forces'], '[]')
      await rejects(['derivation', 'fresh_analysis_invocations'], '1')
      await rejects(['claim_boundary'], '"design approved"')
    })

    test('rejects state/target confusion, response chain defects and incorrect nodal vectors', async () => {
      for (const [route, token] of [
        [['progress', 'accepted_response_states'], '3'],
        [['progress', 'authored_targets', 'completed'], '4'],
        [['progress', 'control_solver_attempts', 'maximum'], '3'],
        [['responses', 1, 'state_index'], '0'],
        [['responses', 1, 'phase'], '"preload"'],
        [['responses', 1, 'parent_checkpoint_hash'], `"sha256:${'0'.repeat(64)}"`],
        [['responses', 0, 'load_factor'], '1.0'],
        [['responses', 1, 'nodes', 0, 'node_id'], '"different-node"'],
        [['responses', 1, 'nodes', 0, 'displacements_m_rad'], '[0.0,0.0]'],
        [['responses', 1, 'nodes', 2, 'reactions_kn_knm', 0], '1.0'],
        [['responses', 1, 'nodes', 2, 'external_loads_kn_knm', 1], '12345.0'],
        [['responses', 1, 'control_displacement_m'], '999.0'],
      ] as [(string | number)[], string][]) await rejects(route, token)
    })

    test('derives immutable chunk hashes even when both retained declarations change together', async () => {
      const forged = `"sha256:${'0'.repeat(64)}"`
      let edited = replace(raw, ['execution', 'invocations', 0, 'chunk_request_hash'], forged)
      if (profile === 'v7') edited = replace(edited, ['execution', 'invocations', 0, 'phase_supervision', 'chunk_request_hash'], forged)
      await expect(parseRcCorotationalReport(await rehash(edited), expected)).rejects.toThrow('chunk_hash_invalid')
    })

    test('retains a synthetic recorded failure as spent unknown work, including unavailable child CPU', async () => {
      // Shape-only projection of the missing ordinal; the service's authenticated
      // report digest remains the separate authority for any real report reopen.
      const executionRaw = fields(raw).get('execution')!.value
      const invocations = rawValues(fields(executionRaw).get('invocations')!.value)
      const failedHash = `"sha256:${'e'.repeat(64)}"`
      let raised = replace(invocations[2], ['ordinal'], '3')
      raised = replace(raised, ['content_hash'], failedHash)
      raised = replace(raised, ['status'], '"raised"')
      raised = replace(raised, ['work'], 'null')
      raised = replace(raised, ['unavailable_execution_work'], 'true')
      raised = replace(raised, ['timing'], `{"process_cpu_ns":${profile === 'v7' ? 'null' : '123'},"wall_ns":123}`)
      if (profile === 'v7') {
        raised = replace(raised, ['phase_supervision', 'status'], '"unaccounted"')
        raised = replace(raised, ['phase_supervision', 'supervisor'], '{"scope":"parent phase failure; child CPU unavailable","wall_ns":123}')
        raised = replace(raised, ['phase_supervision', 'cleanup'], '{"reap_completed":false}')
      }
      let edited = replace(raw, ['execution', 'invocations'], `[${[...invocations.slice(0, 2), raised, ...invocations.slice(2)].join(',')}]`)
      edited = replace(edited, ['execution', 'recorded_invocation_count'], '5')
      edited = replace(edited, ['execution', 'pending_ordinals'], '[]')
      edited = replace(edited, ['bindings', 'invocation_artifact_hashes', '3'], failedHash)
      const parsed = await parseRcCorotationalReport(await rehash(edited), expected)
      expect(parsed.execution.budget.reserved_attempts).toBe(5)
      expect(parsed.execution.unknown_execution_work).toBe(true)
      expect(parsed.execution.invocations[2].work).toBeNull()
      expect(parsed.execution.invocations[2].timing.process_cpu_ns).toBe(profile === 'v7' ? null : 123)
      if (profile === 'v7') expect(parsed.execution.invocations[2].phase_supervision?.cleanup).toEqual({ reap_completed: false })
    })

    test('rejects refunded reservations, hidden pending work, changed totals and invocation identities', async () => {
      for (const [route, token] of [
        [['execution', 'unit'], '"control_solver_attempts"'],
        [['execution', 'budget', 'reserved_attempts'], '4'],
        [['execution', 'budget', 'remaining_attempts'], '2'],
        [['execution', 'recorded_invocation_count'], '3'],
        [['execution', 'pending_ordinals'], '[]'],
        [['execution', 'unknown_execution_work'], 'false'],
        [['execution', 'known_work', 'control_solver_calls'], '999'],
        [['execution', 'invocations', 0, 'ordinal'], '3'],
        [['execution', 'invocations', 0, 'completed_after'], '1'],
        [['execution', 'invocations', 0, 'job_request_hash'], `"sha256:${'0'.repeat(64)}"`],
        [['execution', 'invocations', 0, 'work'], 'null'],
        [['execution', 'invocations', 0, 'status'], '"raised"'],
      ] as [(string | number)[], string][]) await rejects(route, token)
    })

    test('rejects duplicate keys, invalid UTF-8, non-finite values and non-integer counter tokens safely', async () => {
      await expect(parse(`{"schema_version":"duplicate",${raw.slice(1)}`)).rejects.toThrow('rc_corotational_report_invalid')
      await expect(parseRcCorotationalReport(new Uint8Array([0xc3, 0x28]), expected)).rejects.toThrow('rc_corotational_report_invalid')
      await expect(parse(`\uFEFF${raw}`)).rejects.toThrow('encoding_invalid')
      await rejects(['responses', 1, 'load_factor'], '1e999')
      await rejects(['progress', 'accepted_response_states'], '4.0')
      await rejects(['execution', 'recorded_invocation_count'], '4e0')
      await rejects(['derivation', 'fresh_analysis_invocations'], '0.0')
      await rejects(['claim_boundary'], '"\\ud800"')
      await rejects(['execution', 'invocations', 0, 'timing', 'wall_ns'], '9007199254740993')
      await rejects(['progress', 'authored_targets', 'completed'], 'true')
      await expect(parse(replace(raw, ['responses', 1, 'load_factor'], '0.5'))).rejects.toThrow('rc_corotational_report_invalid')
      await expect(parseRcCorotationalReport(new Uint8Array(0), expected)).rejects.toThrow('size_invalid')
      await expect(parseRcCorotationalReport(new Uint8Array(RC_COROTATIONAL_REPORT_MAX_BYTES + 1), expected)).rejects.toThrow('size_invalid')
    })

    if (profile === 'v7') test('rejects changed supervision policy, span, phase, cleanup and raw integer declarations', async () => {
      for (const [route, token] of [
        [['execution', 'invocations', 0, 'phase_supervision'], 'null'],
        [['execution', 'invocations', 0, 'phase_supervision', 'policy', 'analysis_timeout_ms'], '1'],
        [['execution', 'invocations', 0, 'phase_supervision', 'planned_after'], '1'],
        [['execution', 'invocations', 0, 'phase_supervision', 'phase'], '"verification"'],
        [['execution', 'invocations', 0, 'phase_supervision', 'cleanup'], '{"unreaped":true}'],
        [['execution', 'invocations', 0, 'phase_supervision', 'supervisor', 'direct_child_reaped'], 'false'],
        [['execution', 'invocations', 0, 'phase_supervision', 'supervisor', 'child_returncode'], '0.0'],
      ] as [(string | number)[], string][]) await rejects(route, token)
    })
  })
}
