import exampleModel from '../../../examples/public_rc_fiber_frame_explicit_layers.json'
import { isRcCorotationalRequest, validateRcRequestProfile, type RcObject } from './rcJobSchema'
import { longitudinalSteelArea } from './rcSteelLayers'
import { parseNativeJsonStrict } from './nativeFrameProvider'

export interface RcEditorIssue { path: string; message: string }
export interface RcEditorField { path: string; label: string; kind: 'text' | 'number' | 'list' | 'json'; value: string }
export interface RcEditorRow { path: string; label: string; fields: RcEditorField[] }
export interface RcEditorSection { label: string; path?: string; rows: RcEditorRow[] }
export interface RcEditorResolution { value: RcObject | null; issues: RcEditorIssue[] }
export interface RcEditorPreview {
  nodes: Array<{ id: string; x: number; y: number; support: string[] }>
  members: Array<{ id: string; from: string; to: string }>
  loads: Array<{ node: string; fx: number; fy: number }>
}
const clone = <T,>(value: T): T => JSON.parse(JSON.stringify(value))
const record = (v: unknown): v is RcObject => !!v && typeof v === 'object' && !Array.isArray(v)
const rows = (v: unknown): RcObject[] => Array.isArray(v) ? v.slice(0, 48).filter(record) : []
const id = (v: unknown): v is string => typeof v === 'string' && /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$/.test(v)
const finite = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v)
const numeric = /^[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?$/
const steelFields = ['elastic_modulus_mpa', 'yield_stress_mpa', 'isotropic_hardening_modulus_mpa', 'kinematic_hardening_modulus_mpa', 'yield_tolerance_mpa']
const concreteFields = ['elastic_modulus_mpa', 'tensile_strength_mpa', 'compressive_strength_mpa', 'tensile_softening_rate', 'compressive_softening_rate', 'history_tolerance']
const sectionFields = ['width_m', 'depth_m', 'cover_m', 'concrete_layer_count', 'top_bar_count', 'bottom_bar_count', 'bar_area_m2', 'steel_material', 'concrete_material', 'top_cover_m', 'bottom_cover_m', 'top_bar_area_m2', 'bottom_bar_area_m2', 'intermediate_steel_layers']
const layerFields = ['id', 'y_m', 'bar_count', 'bar_area_m2', 'steel_material', 'circular_integration_points']
const at = (value: RcObject, path: string): any => path.split('/').slice(1).reduce((v, key) => v?.[key], value)
function put(value: RcObject, path: string, item: unknown): void {
  const keys = path.split('/').slice(1), last = keys.pop()!
  const owner = keys.reduce((v, key) => v[key], value)
  owner[last] = item
}

/** Explicitly selected software example. The source declaration is always supplied by the author. */
export function createRcEditorExample(sourceRevision: string): RcObject {
  return {
    schema_version: 'structural-analysis-job-request.v3', operation: 'bounded_rc_fiber_direct_control',
    case_id: 'authored-rc-cantilever', source_revision: sourceRevision,
    model: clone(exampleModel), result_contract: 'bounded-rc-fiber-job-result.v1',
    config: {
      schema_version: 'bounded-rc-fiber-direct-control-request.v1', control_global_dof: 4,
      targets_m: [-1e-6, -2e-6], allow_reversals: false, maximum_reversals: 0, maximum_targets: 255,
      solver_config: {
        newton: { residual_tolerance: 1e-10, increment_tolerance: 1e-12, max_iterations: 25,
          line_search_alphas: [1, 0.5, 0.25, 0.125, 0.0625, 0.03125], matrix_backend: 'numpy_linalg_solve_dense' },
        control_tolerance_m: 1e-12, load_factor_coordinate_scale_m: 1e-3,
      },
    }, execution_config: { chunk_target_count: 1, maximum_api_invocations: 8 },
  }
}

/** Field paths only address fixed schema keys and bounded array indices, never authored object keys. */
export function rcEditorSections(request: RcObject): RcEditorSection[] {
  const field = (path: string, label: string, kind: RcEditorField['kind'] = 'text'): RcEditorField => {
    const value = at(request, path)
    return { path, label, kind, value: kind === 'json' ? JSON.stringify(value) : Array.isArray(value) ? value.join(', ') : String(value ?? '') }
  }
  const f = (path: string, key: string, kind: RcEditorField['kind'] = 'text', label = key) => field(`${path}/${key}`, label, kind)
  const section = (label: string, key: string, build: (r: RcObject, p: string) => RcEditorField[]): RcEditorSection => ({
    label, path: `/model/${key}`, rows: rows(request.model?.[key]).map((r, i) => {
      const path = `/model/${key}/${i}`
      return { path, label: `${label} ${i + 1}`, fields: build(r, path) }
    }),
  })
  const sections = [
    { label: 'Request', rows: [{ path: '', label: 'Request identity', fields: [f('', 'case_id'), f('', 'source_revision')] }] },
    section('Nodes', 'nodes', (_, p) => [f(p, 'id'), ...[0, 1, 2].map((axis) => field(`${p}/coordinates/${axis}`, `${['X', 'Y', 'Z'][axis]} (m)`, 'number'))]),
    section('Members', 'elements', (_, p) => [f(p, 'id'), field(`${p}/nodes/0`, 'Start node'), field(`${p}/nodes/1`, 'End node'), f(p, 'section'), f(p, 'integration_order', 'number')]),
    section('Materials', 'materials', (r, p) => [f(p, 'id'), ...(r.type === 'asymmetric_concrete_damage' ? concreteFields : steelFields).map(k => f(p, k, 'number'))]),
    section('Sections', 'sections', (r, p) => [f(p, 'id'), ...sectionFields.filter(k => Object.prototype.hasOwnProperty.call(r, k)).map(k => f(p, k, k === 'intermediate_steel_layers' ? 'json' : k.endsWith('_material') ? 'text' : 'number'))]),
    section('Supports', 'supports', (_, p) => [f(p, 'node'), f(p, 'dofs', 'list', 'Restrained DOFs (comma separated)')]),
    section('Nodal loads', 'loads', (_, p) => [f(p, 'node'), ...['FX', 'FY', 'FZ', 'MX', 'MY', 'MZ'].map(k => field(`${p}/components/${k}`, `${k} (${k.startsWith('M') ? 'kN m' : 'kN'})`, 'number'))]),
  ]
  rows(request.model?.sections).forEach((r, index) => {
    if (!Array.isArray(r.steel_layers)) return
    const path = `/model/sections/${index}/steel_layers`
    sections.splice(5, 0, { label: `Steel layers · ${r.id}`, path, rows: rows(r.steel_layers).map((layer, i) => ({
      path: `${path}/${i}`, label: `Steel layer ${i + 1}`, fields: layerFields.filter(key => key !== 'circular_integration_points' || Object.prototype.hasOwnProperty.call(layer, key)).map(key => f(`${path}/${i}`, key, ['id', 'steel_material'].includes(key) ? 'text' : 'number')),
    })) })
  })
  const config = request.config
  if (record(config)) {
    const controls = isRcCorotationalRequest(request)
      ? Object.prototype.hasOwnProperty.call(config, 'control_observation')
        ? [f('/config', 'control_observation', 'json')]
        : [f('/config', 'control_node_id'), f('/config', 'control_component')]
      : [f('/config', 'control_global_dof', 'number')]
    sections.push({ label: 'Control', rows: [{ path: '/config', label: 'Control and targets', fields: [
      ...controls, f('/config', 'targets_m', 'list', 'Targets (m, comma separated)'),
      ...(isRcCorotationalRequest(request) ? [f('/config', 'fixed_nodal_loads', 'json')] : []),
    ] }] })
  }
  return sections
}

/** Local authoring checks complement transport admission; the core compiler remains authoritative. */
export function validateRcEditorRequest(request: RcObject): RcEditorIssue[] {
  const issues: RcEditorIssue[] = [], issue = (path: string, message: string) => issues.push({ path, message })
  try { validateRcRequestProfile(request) } catch (error) { issue('/', error instanceof Error ? error.message : 'Request profile is invalid.') }
  const m = request.model
  if (!record(m)) return [...issues, { path: '/model', message: 'A canonical model is required.' }]
  for (const [key, min, max] of [['nodes', 2, 16], ['elements', 1, 15], ['materials', 2, 32], ['sections', 1, 16], ['loads', 1, 48], ['supports', 1, 2]] as const) {
    if (!Array.isArray(m[key]) || m[key].length < min || m[key].length > max || m[key].some((r: unknown) => !record(r))) issue(`/model/${key}`, `Expected ${min}–${max} ${key} rows.`)
  }
  if (m.units?.length !== 'm' || m.units?.force !== 'kN') issue('/model/units', 'Only m and kN are supported.')
  if (JSON.stringify(m.coordinate_system?.axis_order) !== '["X","Y","Z"]' || m.coordinate_system?.up_axis !== 'Z') issue('/model/coordinate_system', 'Only XYZ coordinates with Z up are supported.')
  if (!Array.isArray(m.unsupported_features) || m.unsupported_features.length) issue('/model/unsupported_features', 'Unsupported features cannot be applied.')
  const nodes = rows(m.nodes), members = rows(m.elements), materials = rows(m.materials), sections = rows(m.sections)
  const ids = (collection: RcObject[], key: string): Set<string> => {
    const seen = new Set<string>()
    collection.forEach((r, i) => {
      if (!id(r.id) || seen.has(r.id)) issue(`/model/${key}/${i}/id`, 'Use a unique stable ID (letters, numbers, _ . : -).')
      seen.add(r.id)
    })
    return seen
  }
  const nodeIds = ids(nodes, 'nodes'), materialIds = ids(materials, 'materials'), sectionIds = ids(sections, 'sections')
  ids(members, 'elements')
  const points = new Set<string>(), adjacent = new Map(nodes.map(n => [n.id, new Set<string>()]))
  nodes.forEach((n, i) => {
    if (!Array.isArray(n.coordinates) || n.coordinates.length !== 3 || !n.coordinates.every(finite) || n.coordinates[2] !== 0) issue(`/model/nodes/${i}/coordinates`, 'Three finite coordinates are required; Z must be zero.')
    else {
      const key = JSON.stringify(n.coordinates)
      if (points.has(key)) issue(`/model/nodes/${i}/coordinates`, 'Distinct nodes cannot share coordinates.')
      points.add(key)
    }
  })
  if (nodes.some(n => Array.isArray(n.coordinates) && n.coordinates.every(finite)) && [0, 1].some(axis => {
    const positions = nodes.map(n => n.coordinates?.[axis]).filter(finite)
    return !Number.isFinite(Math.max(...positions) - Math.min(...positions))
  })) issue('/model/nodes', 'Coordinate extent must be finite.')
  members.forEach((e, i) => {
    const p = `/model/elements/${i}`
    if (e.type !== 'stateful_rc_fiber_frame2d') issue(`${p}/type`, 'Only stateful_rc_fiber_frame2d is supported.')
    if (!Array.isArray(e.nodes) || e.nodes.length !== 2 || e.nodes[0] === e.nodes[1] || !e.nodes.every((n: unknown) => nodeIds.has(String(n)))) issue(`${p}/nodes`, 'Reference two distinct declared nodes.')
    else {
      if (adjacent.get(e.nodes[0])?.has(e.nodes[1])) issue(`${p}/nodes`, 'Duplicate member connectivity is unsupported.')
      adjacent.get(e.nodes[0])?.add(e.nodes[1]); adjacent.get(e.nodes[1])?.add(e.nodes[0])
      const a = nodes.find(n => n.id === e.nodes[0])?.coordinates, b = nodes.find(n => n.id === e.nodes[1])?.coordinates
      const length = Array.isArray(a) && Array.isArray(b) ? Math.hypot(a[0] - b[0], a[1] - b[1]) : NaN
      if (!Number.isFinite(length) || length <= Number.EPSILON) issue(`${p}/nodes`, 'Member length must be finite and greater than machine epsilon.')
    }
    if (!sectionIds.has(e.section)) issue(`${p}/section`, 'Reference a declared section.')
    if (![2, 3].includes(e.integration_order)) issue(`${p}/integration_order`, 'Integration order must be 2 or 3.')
  })
  const reached = new Set<string>(), visit = (n: string) => { if (reached.has(n)) return; reached.add(n); adjacent.get(n)?.forEach(visit) }
  if (nodes.length) visit(nodes[0].id)
  const endpoints = nodes.filter(n => adjacent.get(n.id)?.size === 1)
  if (members.length !== nodes.length - 1 || endpoints.length !== 2 || reached.size !== nodes.length || [...adjacent.values()].some(neighbors => neighbors.size > 2)) issue('/model/elements', 'Only one connected, unbranched serial chain is supported.')
  const materialKind = (name: string, kind: string) => materialIds.has(name) && materials.some(mat => mat.id === name && mat.type === kind)
  materials.forEach((r, i) => {
    if (!['bilinear_combined_hardening_steel', 'asymmetric_concrete_damage'].includes(r.type)) issue(`/model/materials/${i}/type`, 'Unsupported RC material type.')
    const fields = r.type === 'asymmetric_concrete_damage' ? concreteFields : steelFields
    if (Object.keys(r).some(k => !['id', 'type', ...fields].includes(k))) issue(`/model/materials/${i}`, 'Unknown material fields require the advanced request editor and core admission.')
    fields.forEach(k => {
      const zeroAllowed = /hardening|tolerance/.test(k)
      if (!finite(r[k]) || (zeroAllowed ? r[k] < 0 : r[k] <= 0)) issue(`/model/materials/${i}/${k}`, `A finite ${zeroAllowed ? 'nonnegative' : 'positive'} value is required.`)
    })
  })
  sections.forEach((s, i) => {
    const p = `/model/sections/${i}`
    if (!['rectangular_rc_fiber_section', 'rectangular_rc_explicit_steel_layers'].includes(s.type)) issue(`${p}/type`, 'Only rectangular RC sections are supported.')
    for (const key of ['width_m', 'depth_m']) if (!finite(s[key]) || s[key] <= 0) issue(`${p}/${key}`, 'A positive section dimension is required.')
    if (!Number.isInteger(s.concrete_layer_count) || s.concrete_layer_count < 2 || s.concrete_layer_count > 32) issue(`${p}/concrete_layer_count`, 'Concrete layer count must be an integer from 2 to 32.')
    if (!materialKind(s.concrete_material, 'asymmetric_concrete_damage')) issue(`${p}/concrete_material`, 'Reference a declared concrete material.')
    if (s.type === 'rectangular_rc_explicit_steel_layers') rows(s.steel_layers).forEach((layer, j) => {
      if (!materialKind(layer.steel_material, 'bilinear_combined_hardening_steel')) issue(`${p}/steel_layers/${j}/steel_material`, 'Reference a declared steel material.')
    })
    else if (!materialKind(s.steel_material, 'bilinear_combined_hardening_steel')) issue(`${p}/steel_material`, 'Reference a declared steel material.')
    try { const area = longitudinalSteelArea(s); if (area >= s.width_m * s.depth_m) throw new Error() } catch { issue(p, 'Check bar counts, areas, ordered layer heights and face-to-bar centroid distances.') }
  })
  const supportNodes = new Set<string>()
  rows(m.supports).forEach((s, i) => {
    if (!nodeIds.has(s.node) || supportNodes.has(s.node)) issue(`/model/supports/${i}/node`, 'Reference a distinct declared support node.')
    supportNodes.add(s.node)
    if (!Array.isArray(s.dofs) || !s.dofs.length || new Set(s.dofs).size !== s.dofs.length || s.dofs.some((d: unknown) => !['UX', 'UY', 'RZ'].includes(String(d)))) issue(`/model/supports/${i}/dofs`, 'Use distinct UX, UY or RZ restraints.')
  })
  const c = request.config
  const pin = request.schema_version === 'structural-analysis-job-request.v4' || c?.experimental_pin_roller_beam === true
  const guide = request.schema_version === 'structural-analysis-job-request.v5' || c?.experimental_fixed_guided_axial === true
  const restraint = (support: RcObject) => Array.isArray(support.dofs) ? [...support.dofs].sort().join(',') : ''
  if (!pin && !guide && (rows(m.supports).length !== 1 || !endpoints.some(n => n.id === rows(m.supports)[0]?.node) || restraint(rows(m.supports)[0] ?? {}) !== 'RZ,UX,UY')) issue('/model/supports', 'The cantilever endpoint must restrain exactly UX, UY and RZ.')
  if (pin && (rows(m.supports).length !== 2 || !rows(m.supports).some(s => restraint(s) === 'UX,UY') || !rows(m.supports).some(s => restraint(s) === 'UY'))) issue('/model/supports', 'Pin/roller requires one UX/UY pin and one UY roller at distinct nodes.')
  if (pin && (nodes.some(n => n.coordinates?.[1] !== nodes[0]?.coordinates?.[1]) || new Set(nodes.map(n => n.coordinates?.[0])).size !== nodes.length)) issue('/model/nodes', 'The pin/roller profile requires distinct horizontal stations.')
  if (pin || guide) {
    const axes = [0, 1].filter(axis => new Set(nodes.map(n => n.coordinates?.[axis])).size > 1)
    const axis = pin ? 0 : axes.length === 1 ? axes[0] : -1
    const ordered = [...nodes].sort((a, b) => a.coordinates?.[axis] - b.coordinates?.[axis])
    if (axis < 0 || new Set(nodes.map(n => n.coordinates?.[axis])).size !== nodes.length || ordered.slice(1).some((n, i) => !adjacent.get(ordered[i].id)?.has(n.id))) issue('/model/elements', 'This support profile requires a straight axis-aligned chain connected in station order.')
    if (guide && (rows(m.supports).length !== 2 || rows(m.supports).some(s => !endpoints.some(n => n.id === s.node)) || !rows(m.supports).some(s => restraint(s) === 'RZ,UX,UY') || !rows(m.supports).some(s => restraint(s) === (axis === 0 ? 'RZ,UY' : 'RZ,UX')))) issue('/model/supports', 'Fixed/guided requires one fixed endpoint and a transverse/RZ guide at the other endpoint.')
  }
  const loaded = new Set<string>()
  rows(m.loads).forEach((l, i) => {
    if (!nodeIds.has(l.node)) issue(`/model/loads/${i}/node`, 'Reference a declared node.')
    if (loaded.has(l.node)) issue(`/model/loads/${i}/node`, 'Use one proportional load row per node.')
    loaded.add(l.node)
    if (!guide && supportNodes.has(l.node)) issue(`/model/loads/${i}/node`, 'Loads directly on this profile’s supports are unsupported.')
    if (!record(l.components) || !['FX', 'FY', 'FZ', 'MX', 'MY', 'MZ'].every(k => finite(l.components[k])) || ['FZ', 'MX', 'MY'].some(k => l.components[k] !== 0)) issue(`/model/loads/${i}/components`, 'Finite planar FX/FY/MZ loads are required; FZ/MX/MY must be zero.')
    else if (!['FX', 'FY', 'MZ'].some(k => l.components[k] !== 0)) issue(`/model/loads/${i}/components`, 'Each load row requires a nonzero planar component.')
  })
  return issues
}

/** Never coerce empty input, Infinity or malformed lists to physical defaults. */
export function resolveRcEditorDraft(request: RcObject, edits: Record<string, string>): RcEditorResolution {
  const value = clone(request), issues: RcEditorIssue[] = []
  const fields = new Map(rcEditorSections(request).flatMap(s => s.rows.flatMap(r => r.fields)).map(f => [f.path, f]))
  for (const [path, raw] of Object.entries(edits)) {
    const field = fields.get(path)
    if (!field) { issues.push({ path, message: 'This field is not editable in this profile.' }); continue }
    try {
      let parsed: unknown = raw
      if (field.kind === 'number') {
        if (!numeric.test(raw.trim()) || !Number.isFinite(Number(raw))) throw new Error('Enter a finite number; blank values are not zero.')
        parsed = Number(raw)
      } else if (field.kind === 'list') {
        const values = raw.split(',').map(v => v.trim())
        if (!values.length || values.some(v => !v)) throw new Error('Enter a nonempty comma-separated list.')
        if (path === '/config/targets_m') {
          if (values.some(v => !numeric.test(v) || !Number.isFinite(Number(v)))) throw new Error('Every target must be a finite number.')
          parsed = values.map(Number)
        } else parsed = values
      } else if (field.kind === 'json') parsed = parseNativeJsonStrict(raw)
      put(value, path, parsed)
    } catch (error) { issues.push({ path, message: error instanceof Error ? error.message : 'Invalid field.' }) }
  }
  if (issues.length) return { value: null, issues }
  return { value, issues: validateRcEditorRequest(value) }
}

/** Geometry is derived only from the exact parsed draft, without a solver or fabricated response. */
export function rcEditorPreview(request: RcObject): RcEditorPreview | null {
  const m = request.model
  if (!record(m) || !Array.isArray(m.nodes) || m.nodes.length < 2 || m.nodes.length > 16 || m.nodes.some((n: unknown) => !record(n) || !id(n.id) || !Array.isArray(n.coordinates) || n.coordinates.length !== 3 || !n.coordinates.every(finite))) return null
  const nodes = rows(m.nodes), ids = new Set(nodes.map(n => n.id))
  if (ids.size !== nodes.length) return null
  if ([0, 1].some(axis => !Number.isFinite(Math.max(...nodes.map(n => n.coordinates[axis])) - Math.min(...nodes.map(n => n.coordinates[axis]))))) return null
  return { nodes: nodes.map(n => ({ id: n.id, x: n.coordinates[0], y: n.coordinates[1], support: rows(m.supports).filter(s => s.node === n.id).flatMap(s => Array.isArray(s.dofs) ? s.dofs.filter((d: unknown) => typeof d === 'string') : []) })),
    members: rows(m.elements).filter(e => Array.isArray(e.nodes) && e.nodes.length === 2 && e.nodes.every((n: unknown) => ids.has(String(n)))).map(e => ({ id: String(e.id), from: e.nodes[0], to: e.nodes[1] })),
    loads: rows(m.loads).filter(l => ids.has(l.node) && finite(l.components?.FX) && finite(l.components?.FY)).map(l => ({ node: l.node, fx: l.components.FX, fy: l.components.FY })),
  }
}

/** Explicit row copy/removal never rewrites references or repairs the model silently. */
export function changeRcEditorRows(request: RcObject, path: string, action: 'copy' | 'remove', index: number): RcObject {
  if (!/^\/model\/(nodes|elements|materials|sections|loads|supports)$|^\/model\/sections\/\d+\/steel_layers$/.test(path)) throw new Error('rc_editor_row_path_invalid')
  const result = clone(request), collection = at(result, path)
  if (!Array.isArray(collection) || !Number.isInteger(index) || index < 0 || index >= collection.length || collection.length > 48) throw new Error('rc_editor_row_invalid')
  if (action === 'remove') {
    // Legacy fixed-chord control is an index, so shifting an earlier node would
    // silently control another physical node while preserving the same number.
    if (path === '/model/nodes' && Number.isInteger(result.config?.control_global_dof) && index <= Math.floor(result.config.control_global_dof / 3)) throw new Error('rc_editor_indexed_control_would_move')
    collection.splice(index, 1)
  }
  else {
    if (collection.length >= (path === '/model/nodes' ? 16 : path === '/model/elements' ? 15 : 48)) throw new Error('rc_editor_row_limit')
    const copied = clone(collection[index])
    if (Object.prototype.hasOwnProperty.call(copied, 'id')) copied.id = ''
    collection.splice(path === '/model/nodes' ? collection.length : index + 1, 0, copied)
  }
  return result
}
