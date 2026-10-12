import { test, expect } from '@playwright/test'
import { execFileSync } from 'node:child_process'
import { mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import path from 'node:path'
import { createRequire } from 'node:module'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import ts from 'typescript'
import { sha256Hex } from '../../src/workbench-v2/model/checksum'
import { fields, rawValues, validateRcRequestProfile, type RcLinearPhysicalDisplacementObservation } from '../../src/workbench-v2/model/rcJobSchema'
import { parseRcCorotationalReport, rcCorotationalObservationValue, type RcCorotationalReportExpected, type RcCorotationalReportNode } from '../../src/workbench-v2/model/rcCorotationalReportSchema'

function replace(raw: string, route: (string | number)[], replacement: string): string {
  if (!route.length) return replacement
  const [key, ...rest] = route
  if (typeof key === 'number') {
    const values = rawValues(raw); values[key] = replace(values[key], rest, replacement)
    return `[${values.join(',')}]`
  }
  const members = fields(raw), value = replace(members.get(key)?.value ?? '', rest, replacement)
  members.set(key, { member: `${JSON.stringify(key)}:${value}`, value })
  return `{${[...members].sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0).map(([, row]) => row.member).join(',')}}`
}
async function rehash(raw: string): Promise<Uint8Array> {
  const members = fields(raw); members.delete('report_hash')
  const digest = await sha256Hex(`{${[...members.values()].map(row => row.member).join(',')}}`)
  members.set('report_hash', { member: `"report_hash":${JSON.stringify(digest)}`, value: JSON.stringify(digest) })
  return new TextEncoder().encode(`{${[...members].sort(([a], [b]) => a < b ? -1 : a > b ? 1 : 0).map(([, row]) => row.member).join(',')}}`)
}
const node = (node_id: string, uy: number, rz = 0): RcCorotationalReportNode => ({
  node_id, displacements_m_rad: [0, uy, rz], external_loads_kn_knm: [0, 0, 0], reactions_kn_knm: [0, 0, 0],
})

test.describe('Selected physical displacement observation saved reports', () => {
  test.describe.configure({ mode: 'serial', timeout: 300000 })
  let temporary: string | undefined, raw: string, expected: RcCorotationalReportExpected
  test.beforeAll(() => {
    const retained = process.env.RC_SELECTED_REPORT_SNAPSHOT
    const output = retained ?? path.join(temporary = mkdtempSync(path.join(tmpdir(), 'rc-relative-schema-')), 'selected-v6.json')
    if (!retained) execFileSync('python3', ['tests/frontend/rc_corotational_review_snapshot.py',
      '--profile', 'v6', '--linear-observation', '--output', output], { timeout: 290000, stdio: 'pipe' })
    const snapshot = JSON.parse(readFileSync(output, 'utf8'))
    raw = Buffer.from(snapshot.report.body_base64, 'base64').toString('utf8')
    expected = { job: snapshot.job, tenantId: snapshot.tenant_id, request: snapshot.request }
  })
  test.afterAll(() => { if (temporary) rmSync(temporary, { recursive: true, force: true }) })
  const parse = (text = raw) => parseRcCorotationalReport(new TextEncoder().encode(text), expected)
  const rejects = async (route: (string | number)[], token: string) => {
    await expect(parseRcCorotationalReport(await rehash(replace(raw, route, token)), expected))
      .rejects.toThrow(/^rc_corotational_report_[a-z_]+$/)
  }

  test('reads actual selected report tokens, operator identity and the stored source declaration', async () => {
    expect(() => validateRcRequestProfile(expected.request)).not.toThrow()
    const report = await parse(), control = report.declarations.control
    expect('observation' in control).toBe(true)
    if (!('observation' in control)) throw new Error('selected_control_missing')
    expect(control.finite_rotation_drift).toBe(false)
    expect(control.operator.terms).toContainEqual({ coefficient: -1, coefficient_unit: '1', global_dof: 1 })
    expect(control.operator.terms).toContainEqual({ coefficient: -0.5, coefficient_unit: 'm/rad', global_dof: 2 })
    expect(control.operator.terms).toContainEqual({ coefficient: 1, coefficient_unit: '1', global_dof: 7 })
    expect(control.operator.terms).toHaveLength(control.observation.terms.length)
    expect(report.responses).toHaveLength(4)
    expect(report.bindings.source_revision).toBe(expected.request.source_revision)
    expect(report.structural_authority.independent_physical_validation).toBe(false)
  })

  test('admits bounded physical terms and rejects ambiguous, unknown or fully restrained requests', () => {
    for (const mutate of [
      (c: any) => { c.control_node_id = 'N3' },
      (c: any) => { c.control_observation.schema_version = 'finite-rotation-drift.v1' },
      (c: any) => { c.control_observation.extra = false },
      (c: any) => { c.control_observation.terms[0].coefficient = 0 },
      (c: any) => { c.control_observation.terms[0].coefficient = true },
      (c: any) => { c.control_observation.terms[0].coefficient = Infinity },
      (c: any) => { c.control_observation.terms[0].node_id = 'unknown' },
      (c: any) => { c.control_observation.terms[0].component = 'UZ' },
      (c: any) => { c.control_observation.terms.push({ ...c.control_observation.terms[0] }) },
      (c: any) => { c.control_observation.terms[0].coefficient_unit = 'm/rad' },
      (c: any) => { c.control_observation.terms = c.control_observation.terms.filter((term: any) => term.node_id === 'N1') },
      (c: any) => { c.control_observation.terms = [] },
      (c: any) => { c.control_observation.terms = Array.from({ length: 49 }, () => ({ ...c.control_observation.terms[0] })) },
    ]) {
      const request = structuredClone(expected.request) as any; mutate(request.config)
      expect(() => validateRcRequestProfile(request)).toThrow(/^rc_review_/)
    }
  })

  test('rejects coherent report changes to selected shape, authored binding, normalized terms and hash', async () => {
    for (const [route, token] of [
      [['declarations', 'control', 'finite_rotation_drift'], 'true'],
      [['declarations', 'control', 'definition'], '"finite_rotation_drift"'],
      [['declarations', 'control', 'extra'], 'false'],
      [['declarations', 'control', 'observation', 'terms', 0, 'coefficient'], '2.0'],
      [['declarations', 'control', 'operator', 'terms', 0, 'global_dof'], '0'],
      [['declarations', 'control', 'operator', 'terms', 1, 'coefficient_unit'], '"1"'],
      [['declarations', 'control', 'operator', 'terms', 1, 'coefficient'], '-0.6'],
      [['declarations', 'control', 'observation_hash'], `"sha256:${'0'.repeat(64)}"`],
      [['declarations', 'control'], '{"component":"UY","node_id":"N3","unit":"m"}'],
    ] as [(string | number)[], string][]) await rejects(route, token)
  })

  test('includes support translation and a rotation lever and retains cancellation terms', () => {
    const observation = (expected.request.config as any).control_observation as RcLinearPhysicalDisplacementObservation
    expect(rcCorotationalObservationValue(observation, [node('N1', 0.0625, 0.125), node('N2', 0), node('N3', 0.125)])).toBe(0)
    const cancellation: RcLinearPhysicalDisplacementObservation = { schema_version: 'linear-physical-displacement-observation.v1',
      terms: ['A', 'B', 'C'].map(node_id => ({ node_id, component: 'UY', coefficient: 1 })) }
    expect(rcCorotationalObservationValue(cancellation, [node('A', 1e16), node('B', 1), node('C', -1e16)])).toBe(1)
    expect(() => rcCorotationalObservationValue(cancellation, [node('A', Infinity), node('B', 1), node('C', 0)])).toThrow(/^rc_corotational_report_/)
  })

  test('checks a coupled free rotation observation against accepted nodal values, not one node coordinate', async () => {
    // This coherently edited shape-only document is not an execution or physical
    // attestation. The two-term geometric projection is independently explicit.
    const declaration = { schema_version: 'linear-physical-displacement-observation.v1', terms: [
      { node_id: 'N3', component: 'UY', coefficient: 1 }, { node_id: 'N3', component: 'RZ', coefficient: 0.5 },
    ] }
    const operatorRaw = '{"schema_version":"linear-physical-displacement-observation.v1","terms":[{"coefficient":1.0,"coefficient_unit":"1","global_dof":7},{"coefficient":0.5,"coefficient_unit":"m/rad","global_dof":8}],"unit":"m"}'
    const source = JSON.parse(raw), values = source.responses.map((row: any) => row.nodes[2].displacements_m_rad[1] + 0.5 * row.nodes[2].displacements_m_rad[2])
    let edited = replace(raw, ['declarations', 'control', 'observation'], JSON.stringify(declaration))
    edited = replace(edited, ['declarations', 'control', 'operator'], operatorRaw)
    edited = replace(edited, ['declarations', 'control', 'observation_hash'], JSON.stringify(await sha256Hex(operatorRaw)))
    edited = replace(edited, ['declarations', 'config', 'control_observation'], JSON.stringify(declaration))
    edited = replace(edited, ['declarations', 'targets_m'], JSON.stringify(values.slice(1)))
    edited = replace(edited, ['declarations', 'config', 'targets_m'], JSON.stringify(values.slice(1)))
    for (let i = 0; i < values.length; i++) edited = replace(edited, ['responses', i, 'control_displacement_m'], JSON.stringify(values[i]))
    const request = structuredClone(expected.request) as any
    request.config.control_observation = declaration; request.config.targets_m = values.slice(1)
    const report = await parseRcCorotationalReport(await rehash(edited), { ...expected, request })
    expect(report.responses[1].control_displacement_m).not.toBe(report.responses[1].nodes[2].displacements_m_rad[1])
    edited = replace(edited, ['responses', 1, 'control_displacement_m'], JSON.stringify(source.responses[1].nodes[2].displacements_m_rad[1]))
    await expect(parseRcCorotationalReport(await rehash(edited), { ...expected, request })).rejects.toThrow(/^rc_corotational_report_/)
  })

  test('rejects a control value changed within solver tolerance when its nodal projection is inconsistent', async () => {
    const report = JSON.parse(raw)
    await rejects(['responses', 1, 'control_displacement_m'], JSON.stringify(report.responses[1].control_displacement_m + report.declarations.config.config.control_tolerance_m / 2))
  })

  test('shows engineering movements and units while preserving the legacy control label', async () => {
    const report = await parse()
    // Playwright instruments imported TSX into component metadata. Compile the
    // actual owned component with React's production JSX runtime for this SSR check.
    const filename = path.resolve('src/workbench-v2/components/RcCorotationalReportPanel.tsx')
    const emitted = ts.transpileModule(readFileSync(filename, 'utf8'), { compilerOptions: {
      module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020, jsx: ts.JsxEmit.ReactJSX,
    } }).outputText
    const compiled = { exports: {} as any }
    new Function('require', 'exports', 'module', emitted)(createRequire(filename), compiled.exports, compiled)
    const Description = compiled.exports.RcCorotationalControlDescription
    const selected = renderToStaticMarkup(React.createElement(Description, { control: report.declarations.control }))
    expect(selected).toContain('Weighted displacement observation (m)')
    expect(selected).toContain('N1'); expect(selected).toContain('RZ (rad)'); expect(selected).toContain('-0.5 m/rad')
    expect(selected).not.toContain('global_dof'); expect(selected).not.toContain('observation_hash')
    const legacy = renderToStaticMarkup(React.createElement(Description, { control: { node_id: 'N3', component: 'UY', unit: 'm' } }))
    expect(legacy).toBe('N3 · UY (m)')
  })
})
