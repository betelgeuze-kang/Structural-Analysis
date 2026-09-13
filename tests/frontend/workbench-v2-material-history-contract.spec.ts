import { expect, test } from '@playwright/test'
import { createHash } from 'node:crypto'
import { DesignComparisonPanel } from '../../src/workbench-v2/components/DesignComparisonPanel'
import { loadDesignComparison } from '../../src/workbench-v2/model/designComparisonProvider'
import { validateDesignComparisonManifest, validateDesignComparisonReport } from '../../src/workbench-v2/model/designComparisonSchema'
import { designHash } from './designComparisonFixture'
import { designMaterialHistoryComparisonFixture, removeVerifiedMaterialHistory } from './designMaterialHistoryComparisonFixture'

function manifest(report: Record<string, any>) {
  const bytes = Buffer.from(JSON.stringify(report))
  return validateDesignComparisonManifest({ schema_version: 'rc-fiber-design-comparison-bundle.v1', source_revision: 'a'.repeat(40), report_file: 'comparison.json', report_byte_length: bytes.length, report_sha256: `sha256:${createHash('sha256').update(bytes).digest('hex')}`, report_hash: report.report_hash, experiment_identity_hash: report.experiment_identity_hash })
}
const validate = (report: Record<string, any>) => validateDesignComparisonReport(report, manifest(report))

test('material memory limits block a terminal and response-history passing candidate', () => {
  const report = designMaterialHistoryComparisonFixture(); const checked = validate(report)
  expect(checked).toBe(report)
  expect(checked.rows.every(row => row.terminal_limit_status === 'pass' && row.history_limit_status === 'pass')).toBe(true)
  expect(checked.rows[1].material_history_limit_status).toBe('fail')
  expect(checked.rows[1].performance?.history_maximum_steel_accumulated_plastic_strain).toBe(0.003)
  expect(checked.selection.candidate_id).toBe('baseline'); expect(checked.selection.eligible_count).toBe(1)
})

for (const index of [0, 1]) test(`unavailable material memory at row ${index} retains verified terminal and history values`, () => {
  const report = designMaterialHistoryComparisonFixture(); const before = structuredClone(report.rows[index])
  removeVerifiedMaterialHistory(report, index)
  const checked = validate(report); const row = checked.rows[index]
  expect(row.result).toEqual(before.result); expect(row.quantities).toEqual(before.quantities)
  expect(row.response_history).toEqual(before.response_history)
  expect(row.performance?.terminal_maximum_translation_m).toBe(before.performance.terminal_maximum_translation_m)
  expect(row.performance?.history_maximum_translation_m).toBe(before.performance.history_maximum_translation_m)
  expect(row.performance?.history_maximum_steel_accumulated_plastic_strain).toBeUndefined()
  expect(row.material_history_limit_status).toBe('unavailable')
  expect(checked.selection.candidate_id).toBe(index === 0 ? null : 'baseline')
})

test('zero material limits are valid and remain an explicit failed screen', () => {
  const report = designMaterialHistoryComparisonFixture()
  Object.keys(report.identity.material_history_limits).forEach(key => { report.identity.material_history_limits[key] = 0 })
  report.rows.forEach((row: any) => { row.material_history_limit_status = 'fail'; row.violated_material_history_limits = ['history_maximum_steel_accumulated_plastic_strain', 'history_maximum_concrete_tensile_damage', 'history_maximum_concrete_compressive_damage'] })
  Object.assign(report.selection, { candidate_id: null, eligible_count: 0, reason: 'reference_or_limits_or_prices_unavailable_or_no_candidate_passes' })
  expect(validate(report).selection.candidate_id).toBeNull()
})

for (const [name, mutate] of [
  ['scope downgrade', (r: any) => { r.schema_version = r.identity.schema_version = 'public-rc-fiber-design-comparison.v2' }],
  ['missing response scope', (r: any) => { delete r.identity.history_limits }],
  ['missing material scope', (r: any) => { delete r.identity.material_history_limits }],
  ['unknown limit', (r: any) => { r.identity.material_history_limits.maximum_yielding = 1 }],
  ['boolean limit', (r: any) => { r.identity.material_history_limits.maximum_steel_accumulated_plastic_strain = false }],
  ['negative limit', (r: any) => { r.identity.material_history_limits.maximum_steel_accumulated_plastic_strain = -1 }],
  ['nonfinite limit', (r: any) => { r.identity.material_history_limits.maximum_steel_accumulated_plastic_strain = Infinity }],
  ['damage limit above one', (r: any) => { r.identity.material_history_limits.maximum_concrete_compressive_damage = 1.01 }],
  ['missing material verification', (r: any) => { delete r.rows[1].full_material_history_verification_pass }],
  ['boolean substituted verification', (r: any) => { r.rows[1].full_material_history_verification_pass = 1 }],
  ['missing sidecar', (r: any) => { r.rows[1].constitutive_history = null }],
  ['unknown sidecar field', (r: any) => { r.rows[1].constitutive_history.extra = false }],
  ['wrong result', (r: any) => { r.rows[1].constitutive_history.bindings.source_result_hash = designHash('0') }],
  ['wrong model', (r: any) => { r.rows[1].constitutive_history.bindings.canonical_model_checksum = designHash('0') }],
  ['wrong input', (r: any) => { r.rows[1].constitutive_history.bindings.input_checksum = designHash('0') }],
  ['wrong problem', (r: any) => { r.rows[1].constitutive_history.bindings.problem_contract_hash = designHash('0') }],
  ['wrong checkpoint', (r: any) => { r.rows[1].constitutive_history.bindings.checkpoint_artifact_hash = designHash('0') }],
  ['wrong checkpoint size', (r: any) => { r.rows[1].constitutive_history.bindings.checkpoint_artifact_byte_length++ }],
  ['wrong response history', (r: any) => { r.rows[1].constitutive_history.bindings.response_history_report_hash = designHash('0') }],
  ['wrong engineering history', (r: any) => { r.rows[1].constitutive_history.bindings.engineering_history_hash = designHash('0') }],
  ['missing genesis', (r: any) => { r.rows[1].constitutive_history.states.shift() }],
  ['duplicate epoch', (r: any) => { r.rows[1].constitutive_history.states[1].epoch = 2 }],
  ['wrong load factor', (r: any) => { r.rows[1].constitutive_history.states[1].load_factor = 0.75 }],
  ['wrong accepted parent', (r: any) => { r.rows[1].constitutive_history.states[2].parent_checkpoint_state_hash = designHash('f') }],
  ['detached recovery', (r: any) => { r.rows[1].constitutive_history.states[1].engineering_recovery_hash = designHash('f') }],
  ['density sum substituted as total energy', (r: any) => { r.rows[1].constitutive_history.states[1].total_dissipated_energy_mj = 0.425 }],
  ['invented genesis recovery', (r: any) => { r.rows[1].constitutive_history.states[0].engineering_recovery_hash = designHash('f') }],
  ['invented genesis zero energy', (r: any) => { r.rows[1].constitutive_history.states[0].total_dissipated_energy_mj = 0 }],
  ['wrong material population', (r: any) => { r.rows[1].constitutive_history.states[1].materials.steel.point_count = 2 }],
  ['missing native field', (r: any) => { delete r.rows[1].constitutive_history.states[1].materials.steel.fields.backstress_mpa }],
  ['unknown native field', (r: any) => { r.rows[1].constitutive_history.states[1].materials.steel.fields.currently_yielded = true }],
  ['boolean native value', (r: any) => { r.rows[1].constitutive_history.states[1].materials.steel.fields.accumulated_plastic_strain.maximum = true }],
  ['inverted extrema', (r: any) => { r.rows[1].constitutive_history.states[1].materials.steel.fields.accumulated_plastic_strain.minimum = 100 }],
  ['density interpreted as total', (r: any) => { r.rows[1].constitutive_history.states[1].materials.steel.fields.dissipated_energy_density_mj_per_m3.unit = 'MJ' }],
  ['invalid count', (r: any) => { r.rows[1].constitutive_history.states[1].materials.steel.fields.plastic_strain.positive_value_point_count = 2 }],
  ['boolean count', (r: any) => { r.rows[1].constitutive_history.states[1].materials.steel.fields.plastic_strain.changed_from_parent_point_count = true }],
  ['change count mismatch', (r: any) => { r.rows[1].constitutive_history.states[1].materials.steel.fields.plastic_strain.changed_from_parent_point_count = 0 }],
  ['claimed memory decrease', (r: any) => { r.rows[1].constitutive_history.states[1].materials.steel.fields.accumulated_plastic_strain.increased_from_parent_point_count = 0; r.rows[1].constitutive_history.states[1].materials.steel.fields.accumulated_plastic_strain.decreased_from_parent_point_count = 1 }],
  ['genesis transition count', (r: any) => { r.rows[1].constitutive_history.states[0].materials.steel.fields.plastic_strain.changed_from_parent_point_count = 0 }],
  ['detached density summary', (r: any) => { const s = r.rows[1].constitutive_history.states[1].materials.steel.fields.dissipated_energy_density_mj_per_m3; s.minimum = s.maximum = s.maximum_absolute = 999 }],
  ['wrong displayed maximum', (r: any) => { r.rows[1].performance.history_maximum_steel_accumulated_plastic_strain = 0 }],
  ['missing material violation', (r: any) => { r.rows[1].violated_material_history_limits = [] }],
  ['false pass', (r: any) => { r.rows[1].material_history_limit_status = 'pass' }],
  ['false safe selection', (r: any) => { r.selection.candidate_id = 'narrow'; r.selection.eligible_count = 2 }],
  ['current-yield claim', (r: any) => { r.claims.material_memory_is_current_yield_event = true }],
  ['independent material authority', (r: any) => { r.rows[1].constitutive_history.claim_boundary.independent_physical_validation = true }],
] as const) test(`material history rejects ${name}`, () => {
  const report = designMaterialHistoryComparisonFixture(); mutate(report)
  expect(() => validate(report)).toThrow()
})

test('material panel renders explicit limits and signed memory semantics without a browser', () => {
  const raw = designMaterialHistoryComparisonFixture(); const report = validate(raw)
  // Playwright's TSX transform emits element descriptors. Walk these pure
  // components without a DOM, browser, devserver, or application bootstrap.
  function inspect(node: any): { text: string; props: Record<string, any>[] } {
    if (node === null || node === undefined || typeof node === 'boolean') return { text: '', props: [] }
    if (typeof node === 'string' || typeof node === 'number') return { text: String(node), props: [] }
    if (Array.isArray(node)) return node.map(inspect).reduce((a, b) => ({ text: a.text + b.text, props: [...a.props, ...b.props] }), { text: '', props: [] })
    if (typeof node.type === 'function') return inspect(node.type(node.props))
    const children = inspect(node.props?.children)
    return { text: children.text, props: [node.props ?? {}, ...children.props] }
  }
  const tree = inspect(DesignComparisonPanel({ load: { status: 'verified', errors: [], bundle: { report, manifest: manifest(raw), manifestUrl: 'https://example.test/manifest.json', reportUrl: 'https://example.test/comparison.json' } } }))
  expect(tree.props.some(props => 'data-design-material-history-scope' in props)).toBe(true)
  expect(tree.text).toContain('not a current yielding event')
  expect(tree.text).toContain('material memory verified / fail')
  expect(tree.props.filter(props => 'data-design-material-limit' in props)).toHaveLength(6)
  expect(tree.props.some(props => props.style?.whiteSpace === 'normal')).toBe(true)
  removeVerifiedMaterialHistory(raw, 1)
  const unavailable = inspect(DesignComparisonPanel({ load: { status: 'verified', errors: [], bundle: { report: validate(raw), manifest: manifest(raw), manifestUrl: '', reportUrl: '' } } }))
  expect(unavailable.text).toContain('material memory UNAVAILABLE')
})

test('material report provider retains the original report and manifest for export', async () => {
  const report = designMaterialHistoryComparisonFixture(); const declared = manifest(report)
  const savedFetch = globalThis.fetch; const descriptor = Object.getOwnPropertyDescriptor(globalThis, 'window')
  Object.defineProperty(globalThis, 'window', { configurable: true, value: { location: { href: 'https://example.test/', origin: 'https://example.test' } } })
  globalThis.fetch = async input => new Response(JSON.stringify(String(input).endsWith('manifest.json') ? declared : report), { headers: { 'content-type': 'application/json' } })
  try {
    const loaded = await loadDesignComparison('https://example.test/manifest.json')
    expect(loaded.errors).toEqual([]); expect(loaded.status).toBe('verified')
    expect(loaded.bundle?.report).toEqual(report); expect(loaded.bundle?.manifest).toEqual(declared)
  } finally { globalThis.fetch = savedFetch; if (descriptor) Object.defineProperty(globalThis, 'window', descriptor); else delete (globalThis as { window?: unknown }).window }
})
