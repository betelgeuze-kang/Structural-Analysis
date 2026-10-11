import { test, expect } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import { readFileSync, writeFileSync, mkdtempSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { validateRcJobArtifacts, validateRcRequestProfile, validateRcAcceptedHistory, fields } from '../../src/workbench-v2/model/rcJobSchema'
import { validateRcQuantityReport } from '../../src/workbench-v2/model/rcQuantityReportSchema'
import { sha256Hex } from '../../src/workbench-v2/model/checksum'

test.describe('Explicit fixed-guided axial RC reviewer with freshly computed artifacts', () => {
  test.describe.configure({ mode: 'serial', timeout: 120000 })
  let temporary: string, snapshot: any, reviewed: Awaited<ReturnType<typeof validateRcJobArtifacts>>
  const bytes = (value: string) => new Uint8Array(Buffer.from(value, 'base64'))
  test.beforeAll(async () => {
    temporary = mkdtempSync(path.join(tmpdir(), 'rc-review-contract-'))
    const output = path.join(temporary, 'review.json')
    const authored = JSON.parse(execFileSync('python3', ['tests/frontend/rc_fixed_guided_request.py'], { encoding: 'utf8' }))
    const requestFile = path.join(temporary, 'browser-request.json')
    // The exact browser JSON.stringify boundary converts Python 1.0 to JSON 1.
    writeFileSync(requestFile, JSON.stringify(authored))
    execFileSync('python3', ['tests/frontend/rc_lifecycle_review_snapshot.py', '--output', output, '--request-file', requestFile], { timeout: 100000, stdio: 'pipe' })
    snapshot = JSON.parse(readFileSync(output, 'utf8'))
    reviewed = await validateRcJobArtifacts(snapshot.job, Object.fromEntries(
      Object.entries(snapshot.artifacts).map(([role, value]: [string, any]) => [role, bytes(value.base64)])), 'a')
  })
  test.afterAll(() => { if (temporary) rmSync(temporary, { recursive: true, force: true }) })

  test('verifies original execution, unknown reservation and two price-only revisions', async () => {
    expect(snapshot.original_request_representation_retained).toBe(true)
    expect(reviewed.summary.fixedGuided).toEqual({ fixed: 'N1', guided: 'N2', axial: 'UY' })
    expect(reviewed.summary.pinRoller).toBeUndefined()
    expect(reviewed.summary.targets).toEqual([-1e-6, -2e-6])
    expect(reviewed.summary.unknownWork).toBe(true)
    expect(reviewed.summary.reservedInvocations).toBe(5)
    expect(snapshot.reports.map((row: any) => row.reference.revision)).toEqual([1, 2])
    const reports = await Promise.all(snapshot.reports.map((row: any) =>
      validateRcQuantityReport(bytes(row.base64), reviewed.quantitySource, row.reference)))
    expect(reports[0].bindings).toEqual(reports[1].bindings)
    expect(reports[0].quantities).toEqual(reports[1].quantities)
    expect(reports[0].declared_prices).not.toEqual(reports[1].declared_prices)
  })

  test('rejects unsupported request extensions before submission', () => {
    const original = JSON.parse(Buffer.from(snapshot.artifacts.request.base64, 'base64').toString())
    expect(() => validateRcRequestProfile(original)).not.toThrow()
    for (const mutate of [
      (r: any) => { r.config.solver_config.newton.terminal_polishing = false },
      (r: any) => { r.config.constant_nodal_loads = [] },
      (r: any) => { r.config.schema_version = 'bounded-rc-fiber-direct-control-request.v1' },
      (r: any) => { r.schema_version = 'structural-analysis-job-request.v3' },
      (r: any) => { r.config.experimental_fixed_guided_axial = false },
      (r: any) => { r.config.experimental_pin_roller_beam = true },
      (r: any) => { r.model.supports[1].dofs = ['UY', 'RZ'] },
      (r: any) => { r.model.supports[1].node = 'N1' },
      (r: any) => { r.model.nodes[1].coordinates[0] = 0.1 },
      (r: any) => { r.execution_config.reuse_line_search_assembly = false },
      (r: any) => { r.execution_config.phase_execution_policy = {} },
    ]) {
      const request = structuredClone(original); mutate(request)
      expect(() => validateRcRequestProfile(request)).toThrow()
    }
  })

  test('binds all five restrained components and excludes the axial guide reaction', () => {
    const request = JSON.parse(Buffer.from(snapshot.artifacts.request.base64, 'base64').toString())
    const result = JSON.parse(Buffer.from(snapshot.artifacts.result.base64, 'base64').toString())
    const native = JSON.parse(Buffer.from(result.terminal_checkpoint_artifact_base64, 'base64').toString())
    expect(() => validateRcAcceptedHistory(result.api_result, native, request.model, request.config)).not.toThrow()
    for (const mutate of [
      (api: any) => { api.response_history[0].support_reactions.pop() },
      (api: any) => { api.response_history[0].support_reactions[3].dof = 'UY' },
      (api: any) => { api.response_history[0].node_displacements[1].RZ_rad = 0.001 },
    ]) {
      const changed = structuredClone(result.api_result); mutate(changed)
      expect(() => validateRcAcceptedHistory(changed, native, request.model, request.config)).toThrow()
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
