import {
  BUILDING_MEMBER_MODEL_MAX_BYTES, BUILDING_MEMBER_RESULT_MAX_BYTES, BUILDING_MEMBER_MAPPING_MAX_BYTES,
  openBuildingMemberReview, type BuildingMemberBindings, type BuildingMemberMapping,
} from './buildingMemberReview'
import { canonicalNativeJson, nativeFrameModelIdentity, parseNativeJsonStrict, type NativeFrameModelIdentity } from './nativeFrameProvider'
import { sha256Bytes, sha256Hex } from './checksum'

export const BUILDING_LOAD_REVISION_MAX_BYTES = 8 * 1024 * 1024
const ID = /^[A-Za-z][A-Za-z0-9_.:-]{0,127}$/
const HASH = /^sha256:[0-9a-f]{64}$/
const MAX_ROWS = 4096
const COMPONENTS = ['FX', 'FY', 'FZ', 'MX', 'MY', 'MZ'] as const
export type BuildingLoadComponents = Record<typeof COMPONENTS[number], number>
export interface BuildingNodalLoad {
  id: string; index: number; node_id: string; components_si: BuildingLoadComponents
  source_id: string | null; extensions: Record<string, unknown>
}
export interface BuildingLoadPatternPatch {
  pattern_id: string
  self_weight: [number, number, number]
  nodal_loads: BuildingNodalLoad[]
}
export interface BuildingRevisionArtifact { body_base64: string; byte_length: number; sha256: string }
export interface BuildingLoadRevisionDraft {
  schema_version: 'structural-building-load-revision-draft.v1'
  revision_id: string
  parent: { model_ir: BuildingRevisionArtifact; result_ir: BuildingRevisionArtifact; mapping: BuildingRevisionArtifact }
  patches: BuildingLoadPatternPatch[]
}
export interface BuildingLoadRevisionEditorView {
  sourceFingerprint: string
  parentIdentity: BuildingMemberBindings
  nodes: Array<{ id: string }>
  patterns: Array<{ id: string; index: number; self_weight: [number, number, number]; nodal_loads: BuildingNodalLoad[] }>
}
export interface BuildingLoadRevisionRecord {
  schema_version: 'structural-building-load-revision-record.v1'
  revision_id: string
  source_fingerprint: string
  edit_recipe_hash: string
  parent: BuildingMemberBindings & { model_file_hash: string; result_file_hash: string; mapping_file_hash: string }
  unchanged_inventory: { storeys: BuildingMemberMapping['storeys']; members: BuildingMemberMapping['members'] }
  unchanged_inventory_hash: string
  target: NativeFrameModelIdentity & { model_id: string; model_file_hash: string; analysis_status: 'NOT_RUN'; review_status: 'NOT_REVIEWED'; result: null }
  authority: 'operator_authored_load_revision_only'
  claim_boundary: 'load_edit_and_identity_only_not_native_semantic_acceptance_analysis_mass_source_design_code_check_or_engineering_acceptance'
}

type Row = Record<string, unknown>
function object(value: unknown, label: string): Row {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error(`${label} must be an object`)
  return value as Row
}
function exact(value: unknown, keys: string[], label: string): Row {
  const row = object(value, label)
  if (Object.keys(row).length !== keys.length || keys.some(key => !Object.prototype.hasOwnProperty.call(row, key))) throw new Error(`${label} fields are invalid`)
  return row
}
function id(value: unknown, label: string): asserts value is string {
  if (typeof value !== 'string' || !ID.test(value)) throw new Error(`${label} is invalid`)
}
function rows(value: unknown, label: string, maximum = MAX_ROWS): unknown[] {
  if (!Array.isArray(value) || value.length > maximum) throw new Error(`${label} row count is invalid`)
  return value
}
function finite(value: unknown, label: string): asserts value is number {
  if (typeof value !== 'number' || !Number.isFinite(value)) throw new Error(`${label} must be finite`)
}
function vector(value: unknown, label: string): asserts value is [number, number, number] {
  if (!Array.isArray(value) || value.length !== 3) throw new Error(`${label} requires three components`)
  value.forEach(component => finite(component, label))
}
function unique(value: unknown, seen: Set<string | number>, label: string): void {
  if (typeof value !== 'string' && typeof value !== 'number') throw new Error(`${label} is invalid`)
  if (seen.has(value)) throw new Error(`${label} is duplicated`)
  seen.add(value)
}
function index(value: unknown): asserts value is number {
  if (!Number.isSafeInteger(value) || (value as number) < 0) throw new Error('Nodal load index is invalid')
}
function json(bytes: Uint8Array, maximum: number, label: string): unknown {
  if (!bytes.byteLength || bytes.byteLength > maximum) throw new Error(`${label} file size is invalid`)
  if (bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf) throw new Error(`${label} UTF-8 BOM is unsupported`)
  return parseNativeJsonStrict(new TextDecoder('utf-8', { fatal: true }).decode(bytes))
}
async function hashBytes(bytes: Uint8Array): Promise<string> {
  const hash = await sha256Bytes(bytes)
  if (hash === null) throw new Error('Revision integrity is unavailable')
  return hash
}
async function hashJson(value: unknown): Promise<string> {
  const hash = await sha256Hex(canonicalNativeJson(value))
  if (hash === null) throw new Error('Revision integrity is unavailable')
  return hash
}
function base64(bytes: Uint8Array): string {
  let binary = ''
  for (let offset = 0; offset < bytes.length; offset += 32768) binary += String.fromCharCode(...bytes.subarray(offset, offset + 32768))
  return btoa(binary)
}
function artifactBytes(value: unknown, maximum: number, label: string): Uint8Array {
  const row = exact(value, ['body_base64', 'byte_length', 'sha256'], `${label} artifact`)
  if (!Number.isSafeInteger(row.byte_length) || (row.byte_length as number) < 1 || (row.byte_length as number) > maximum) throw new Error(`${label} artifact size is invalid`)
  if (typeof row.sha256 !== 'string' || !HASH.test(row.sha256)) throw new Error(`${label} artifact hash is invalid`)
  if (typeof row.body_base64 !== 'string' || row.body_base64.length !== 4 * Math.ceil((row.byte_length as number) / 3)
    || !/^[A-Za-z0-9+/]*={0,2}$/.test(row.body_base64)) throw new Error(`${label} artifact base64 is invalid`)
  const binary = atob(row.body_base64)
  const bytes = Uint8Array.from(binary, char => char.charCodeAt(0))
  if (bytes.byteLength !== row.byte_length || base64(bytes) !== row.body_base64) throw new Error(`${label} artifact base64 is noncanonical`)
  return bytes
}
async function artifact(bytes: Uint8Array): Promise<BuildingRevisionArtifact> {
  return { body_base64: base64(bytes), byte_length: bytes.byteLength, sha256: await hashBytes(bytes) }
}

/** Creates explicit new-row provenance; surviving rows keep their original metadata. */
export function createBuildingRevisionNodalLoad(
  revisionId: string, loadId: string, rowIndex: number, nodeId: string, components: BuildingLoadComponents,
): BuildingNodalLoad {
  id(revisionId, 'Revision ID'); id(loadId, 'Load ID'); id(nodeId, 'Node ID'); index(rowIndex)
  const copied = exact(components, [...COMPONENTS], 'Nodal components')
  COMPONENTS.forEach(key => finite(copied[key], key))
  return { id: loadId, index: rowIndex, node_id: nodeId, components_si: { ...components }, source_id: `generated:building-load-revision:${revisionId}:${loadId}`, extensions: {} }
}

function validateNodalLoads(value: unknown, nodeIds: Set<string>, label: string): BuildingNodalLoad[] {
  const indices = new Set<string | number>()
  const ids = new Set<string | number>()
  return rows(value, label).map(value => {
    const row = exact(value, ['id', 'index', 'node_id', 'components_si', 'source_id', 'extensions'], label)
    id(row.id, 'Nodal load ID'); unique(row.id, ids, 'Nodal load ID')
    index(row.index); unique(row.index, indices, 'Nodal load index')
    id(row.node_id, 'Nodal load node ID')
    if (!nodeIds.has(row.node_id)) throw new Error('Nodal load node is absent from the parent model')
    const components = exact(row.components_si, [...COMPONENTS], 'Nodal components')
    COMPONENTS.forEach(key => finite(components[key], `Nodal ${key}`))
    if (row.source_id !== null && (typeof row.source_id !== 'string' || row.source_id.length > 4096)) throw new Error('Nodal source_id is invalid')
    object(row.extensions, 'Nodal extensions')
    return row as unknown as BuildingNodalLoad
  })
}

/** Checks load references and finite combination arithmetic, not complete native/model semantics. */
function validateLoads(model: Row): void {
  const nodeIds = new Set(rows(model.nodes, 'Nodes').map(value => String(object(value, 'Node').id)))
  const elementIds = new Set(rows(model.elements, 'Elements').map(value => String(object(value, 'Element').id)))
  const patterns = new Map<string, Row>()
  const allLoadIds = new Set<string | number>()
  let nestedRows = 0
  for (const value of rows(model.load_patterns, 'Load patterns', 256)) {
    const pattern = object(value, 'Load pattern')
    id(pattern.id, 'Pattern ID')
    if (patterns.has(pattern.id)) throw new Error('Pattern ID is duplicated')
    patterns.set(pattern.id, pattern)
    if (pattern.analysis_type !== 'linear_static') throw new Error('Only existing linear_static patterns can be revised')
    vector(pattern.self_weight, 'Self-weight multiplier')
    const nodal = validateNodalLoads(pattern.nodal_loads, nodeIds, 'Nodal loads')
    const sums = new Map<string, number[]>()
    let nonzero = pattern.self_weight.some(value => value !== 0)
    for (const load of nodal) {
      unique(load.id, allLoadIds, 'Nested load ID')
      const sum = sums.get(load.node_id) ?? [0, 0, 0, 0, 0, 0]
      COMPONENTS.forEach((key, index) => { sum[index] += load.components_si[key]; finite(sum[index], 'Accumulated nodal component') })
      sums.set(load.node_id, sum)
      nonzero ||= COMPONENTS.some(key => load.components_si[key] !== 0)
    }
    const uniform = rows(pattern.uniform_member_loads ?? [], 'Uniform member loads', 128)
    nestedRows += nodal.length + uniform.length
    if (nestedRows > MAX_ROWS) throw new Error('Total load row count is invalid')
    const uniformIndices = new Set<string | number>()
    for (const value of uniform) {
      const load = object(value, 'Uniform member load')
      id(load.id, 'Uniform load ID'); unique(load.id, allLoadIds, 'Nested load ID')
      index(load.index); unique(load.index, uniformIndices, 'Uniform load index')
      if (!elementIds.has(String(load.member_id))) throw new Error('Preserved uniform load member is absent from the parent model')
      const components = object(load.components_si, 'Uniform load components')
      const values = ['QX', 'QY', 'QZ'].map(key => { finite(components[key], key); return components[key] as number })
      if (values.every(value => value === 0)) throw new Error('Preserved uniform load row is entirely zero')
      nonzero = true
    }
    if (!nonzero) throw new Error('Each load pattern must retain at least one nonzero load')
  }
  const combinations = new Map<string, Row>()
  for (const value of rows(model.load_combinations, 'Combinations', 256)) {
    const row = object(value, 'Combination'); id(row.id, 'Combination ID')
    if (combinations.has(row.id)) throw new Error('Combination ID is duplicated')
    combinations.set(row.id, row)
  }
  for (const selected of combinations.keys()) {
    let expanded = 0
    const factors = new Map<string, number>()
    function visit(combinationId: string, factor: number, path: Set<string>): void {
      if (path.has(combinationId)) throw new Error('Preserved load combination cycle is invalid')
      const combination = combinations.get(combinationId)
      if (!combination) throw new Error('Preserved load combination reference is absent')
      path.add(combinationId)
      const terms = rows(combination.terms, 'Combination terms')
      if (!terms.length) throw new Error('Combination terms are empty')
      for (const value of terms) {
        if (++expanded > MAX_ROWS) throw new Error('Expanded combination term count exceeds 4096')
        const term = object(value, 'Combination term')
        finite(term.factor, 'Combination factor')
        const product = factor * term.factor
        finite(product, 'Combined factor product')
        id(term.ref_id, 'Combination reference')
        if (term.ref_kind === 'load_pattern') {
          if (!patterns.has(term.ref_id)) throw new Error('Preserved load pattern reference is absent')
          const sum = (factors.get(term.ref_id) ?? 0) + product
          finite(sum, 'Accumulated combination factor'); factors.set(term.ref_id, sum)
        } else if (term.ref_kind === 'load_combination') visit(term.ref_id, product, path)
        else throw new Error('Combination reference kind is invalid')
      }
      path.delete(combinationId)
    }
    visit(selected, 1, new Set())
  }
}

function snapshot(value: unknown): BuildingLoadRevisionDraft {
  const bytes = serializeBuildingLoadRevisionDraft(value as BuildingLoadRevisionDraft)
  return json(bytes, BUILDING_LOAD_REVISION_MAX_BYTES, 'Revision draft') as BuildingLoadRevisionDraft
}
async function admit(input: BuildingLoadRevisionDraft) {
  // Own the complete JSON snapshot before any asynchronous hashing/admission.
  const draft = snapshot(input)
  const root = exact(draft, ['schema_version', 'revision_id', 'parent', 'patches'], 'Revision draft')
  if (root.schema_version !== 'structural-building-load-revision-draft.v1') throw new Error('Revision draft schema is unsupported')
  id(root.revision_id, 'Revision ID')
  const parent = exact(root.parent, ['model_ir', 'result_ir', 'mapping'], 'Parent artifacts')
  const modelBytes = artifactBytes(parent.model_ir, BUILDING_MEMBER_MODEL_MAX_BYTES, 'ModelIR')
  const resultBytes = artifactBytes(parent.result_ir, BUILDING_MEMBER_RESULT_MAX_BYTES, 'ResultIR')
  const mappingBytes = artifactBytes(parent.mapping, BUILDING_MEMBER_MAPPING_MAX_BYTES, 'Mapping')
  const model = object(json(modelBytes, BUILDING_MEMBER_MODEL_MAX_BYTES, 'ModelIR'), 'ModelIR')
  const mapping = json(mappingBytes, BUILDING_MEMBER_MAPPING_MAX_BYTES, 'Mapping') as BuildingMemberMapping
  const review = await openBuildingMemberReview(modelBytes, resultBytes, mappingBytes)
  for (const [name, actual] of [['model_ir', review.source.model_file_hash], ['result_ir', review.source.result_file_hash], ['mapping', review.source.mapping_file_hash]] as const) {
    if (draft.parent[name].sha256 !== actual) throw new Error(`Parent ${name} artifact hash mismatch`)
  }
  const nodeIds = new Set(rows(model.nodes, 'Nodes').map(value => String(object(value, 'Node').id)))
  const patterns = rows(model.load_patterns, 'Load patterns', 256).map(value => object(value, 'Pattern'))
  const patchIds = new Set<string | number>()
  for (const value of rows(root.patches, 'Patches', 256)) {
    const patch = exact(value, ['pattern_id', 'self_weight', 'nodal_loads'], 'Pattern patch')
    id(patch.pattern_id, 'Patch pattern ID'); unique(patch.pattern_id, patchIds, 'Patch pattern ID')
    const parentPatterns = patterns.filter(pattern => pattern.id === patch.pattern_id)
    if (parentPatterns.length !== 1 || parentPatterns[0].analysis_type !== 'linear_static') throw new Error('Patch must select one existing linear_static pattern')
    vector(patch.self_weight, 'Self-weight multiplier')
    const loads = validateNodalLoads(patch.nodal_loads, nodeIds, 'Patch nodal loads')
    const oldLoads = rows(parentPatterns[0].nodal_loads, 'Parent nodal loads').map(value => object(value, 'Parent nodal load'))
    for (const load of loads) {
      const old = oldLoads.find(row => row.id === load.id)
      if (old) {
        for (const key of ['index', 'source_id', 'extensions'] as const) if (canonicalNativeJson(load[key]) !== canonicalNativeJson(old[key])) throw new Error(`Surviving nodal load ${key} must be preserved`)
      } else {
        if (load.source_id !== `generated:building-load-revision:${draft.revision_id}:${load.id}` || Object.keys(load.extensions).length) throw new Error('New nodal load requires explicit generated source metadata')
        if (oldLoads.some(row => row.index === load.index)) throw new Error('New nodal load index is already used by a parent row')
      }
    }
  }
  const sourceFingerprint = await hashJson({ model_ir: review.source.model_file_hash, result_ir: review.source.result_file_hash, mapping: review.source.mapping_file_hash })
  const parentIdentity: BuildingMemberBindings = {
    model_id: review.source.model_id, model_content_hash: review.source.model_content_hash,
    model_semantic_hash: review.source.model_semantic_hash, model_provenance_hash: review.source.model_provenance_hash,
    result_id: review.source.result_id, result_hash: review.source.result_hash,
  }
  return { draft, model, mapping, review, sourceFingerprint, parentIdentity }
}

export async function prepareBuildingLoadRevision(modelBytes: Uint8Array, resultBytes: Uint8Array, mappingBytes: Uint8Array, revisionId: string): Promise<BuildingLoadRevisionDraft> {
  id(revisionId, 'Revision ID')
  if (!modelBytes.length || modelBytes.length > BUILDING_MEMBER_MODEL_MAX_BYTES || !resultBytes.length || resultBytes.length > BUILDING_MEMBER_RESULT_MAX_BYTES || !mappingBytes.length || mappingBytes.length > BUILDING_MEMBER_MAPPING_MAX_BYTES) throw new Error('Parent file size is invalid')
  // Uint8Array construction copies Buffer subclasses too; slice() would not.
  modelBytes = new Uint8Array(modelBytes); resultBytes = new Uint8Array(resultBytes); mappingBytes = new Uint8Array(mappingBytes)
  await openBuildingMemberReview(modelBytes, resultBytes, mappingBytes)
  const draft: BuildingLoadRevisionDraft = {
    schema_version: 'structural-building-load-revision-draft.v1', revision_id: revisionId,
    parent: { model_ir: await artifact(modelBytes), result_ir: await artifact(resultBytes), mapping: await artifact(mappingBytes) }, patches: [],
  }
  await admit(draft)
  return draft
}

/** Serialization preserves an unfinished patch draft; compilation is a separate explicit check. */
export function serializeBuildingLoadRevisionDraft(draft: BuildingLoadRevisionDraft): Uint8Array {
  const bytes = new TextEncoder().encode(canonicalNativeJson(draft))
  if (!bytes.length || bytes.length > BUILDING_LOAD_REVISION_MAX_BYTES) throw new Error('Revision draft file size is invalid')
  return bytes
}
export async function openBuildingLoadRevisionDraft(bytes: Uint8Array): Promise<BuildingLoadRevisionDraft> {
  if (!bytes.byteLength || bytes.byteLength > BUILDING_LOAD_REVISION_MAX_BYTES) throw new Error('Revision draft file size is invalid')
  bytes = new Uint8Array(bytes)
  const draft = json(bytes, BUILDING_LOAD_REVISION_MAX_BYTES, 'Revision draft') as BuildingLoadRevisionDraft
  return (await admit(draft)).draft
}
export const openBuildingLoadRevision = openBuildingLoadRevisionDraft
export const serializeBuildingLoadRevision = serializeBuildingLoadRevisionDraft

export async function getBuildingLoadRevisionEditorView(draft: BuildingLoadRevisionDraft): Promise<BuildingLoadRevisionEditorView> {
  const admitted = await admit(draft)
  const model = admitted.model
  return {
    sourceFingerprint: admitted.sourceFingerprint, parentIdentity: admitted.parentIdentity,
    nodes: rows(model.nodes, 'Nodes').map(value => ({ id: String(object(value, 'Node').id) })),
    patterns: rows(model.load_patterns, 'Patterns', 256).map(value => {
      const row = object(value, 'Pattern')
      return { id: String(row.id), index: row.index as number, self_weight: row.self_weight as [number, number, number], nodal_loads: row.nodal_loads as BuildingNodalLoad[] }
    }),
  }
}

export async function compileBuildingLoadRevision(draft: BuildingLoadRevisionDraft) {
  const admitted = await admit(draft)
  const { model, mapping, parentIdentity, sourceFingerprint } = admitted
  const patches = admitted.draft.patches
  model.load_patterns = rows(model.load_patterns, 'Patterns').map(value => {
    const pattern = object(value, 'Pattern')
    const patch = patches.find(patch => patch.pattern_id === pattern.id)
    return patch ? { ...pattern, self_weight: patch.self_weight, nodal_loads: patch.nodal_loads } : pattern
  })
  validateLoads(model)
  const recipe = {
    schema_version: 'structural-building-load-edit-recipe.v1', revision_id: admitted.draft.revision_id,
    parent: { ...parentIdentity, model_file_hash: admitted.review.source.model_file_hash, result_file_hash: admitted.review.source.result_file_hash, mapping_file_hash: admitted.review.source.mapping_file_hash },
    patches,
    edited_fields: ['load_patterns[].self_weight', 'load_patterns[].nodal_loads'],
    units: { force: 'N', moment: 'N*m', self_weight: 'dimensionless_global_standard_gravity_multipliers' },
  }
  const recipeBytes = new TextEncoder().encode(canonicalNativeJson(recipe))
  const recipeHash = await hashBytes(recipeBytes)
  model.provenance = {
    source_format: 'generated', source_ref: `building-load-revision:${admitted.draft.revision_id}`, source_sha256: recipeHash,
    normalizer_id: 'building.load.revision', normalizer_version: '1',
    source_units: { length: 'm', force: 'N', mass: 'kg', time: 's', rotation: 'rad' },
    unit_scales_to_si: { length_to_m: 1, force_to_n: 1, mass_to_kg: 1, time_to_s: 1, rotation_to_rad: 1 },
    extensions: {},
  }
  const targetIdentity = await nativeFrameModelIdentity(model)
  const modelBytes = new TextEncoder().encode(canonicalNativeJson(model))
  if (modelBytes.length > BUILDING_MEMBER_MODEL_MAX_BYTES) throw new Error('Derived ModelIR file size is invalid')
  const inventory = { storeys: mapping.storeys, members: mapping.members }
  const revisionRecord: BuildingLoadRevisionRecord = {
    schema_version: 'structural-building-load-revision-record.v1', revision_id: admitted.draft.revision_id,
    source_fingerprint: sourceFingerprint, edit_recipe_hash: recipeHash, parent: recipe.parent,
    unchanged_inventory: inventory, unchanged_inventory_hash: await hashJson(inventory),
    target: { model_id: String(model.model_id), ...targetIdentity, model_file_hash: await hashBytes(modelBytes), analysis_status: 'NOT_RUN', review_status: 'NOT_REVIEWED', result: null },
    authority: 'operator_authored_load_revision_only',
    claim_boundary: 'load_edit_and_identity_only_not_native_semantic_acceptance_analysis_mass_source_design_code_check_or_engineering_acceptance',
  }
  return { modelIr: model, modelBytes, targetIdentity, recipeBytes, revisionRecord }
}
