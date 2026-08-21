import { sha256Hex } from './checksum'
import {
  canonicalNativeJson,
  parseNativeJsonStrict,
  type NativeFrame3dResultIr,
} from './nativeFrameProvider'

type SixVector = [number, number, number, number, number, number]
type Quantity = 'displacement' | 'reaction' | 'member_end_force'

export type NativeFrameComparisonLoadStatus =
  | 'unconfigured'
  | 'loading'
  | 'verified'
  | 'integrity_unavailable'
  | 'missing'
  | 'invalid'
  | 'error'

export interface ExternalLinearFrame3dReferenceV1 {
  schema_version: 'structural-external-linear-frame3d-reference.v1'
  reference_id: string
  source: {
    tool: 'sap2000' | 'midas_gen' | 'opensees' | 'calculix' | 'synthetic_fixture'
    version: string
    origin: 'operator_attached_external' | 'synthetic_contract_fixture'
    export_sha256: string
  }
  bindings: {
    model_content_hash: string
    load_pattern_id: string | null
    load_combination_id: string | null
  }
  axes: {
    node_displacement: 'global_ux_uy_uz_rx_ry_rz'
    node_reaction: 'global_fx_fy_fz_mx_my_mz'
    member_end_force: 'member_local_fx_fy_fz_mx_my_mz_i_then_j'
    sign_convention: 'native_result_ir_compatible'
  }
  units: {
    translation: 'm' | 'mm'
    rotation: 'rad'
    force: 'N' | 'kN'
    moment: 'N*m' | 'kN*m'
  }
  nodes: Array<{ node_id: string; displacement: SixVector; reaction: SixVector }>
  members: Array<{ member_id: string; end_i_force: SixVector; end_j_force: SixVector }>
  claim_boundary: 'operator_declared_mapping_and_units_not_independent_validation_or_release_authority'
}

export interface LinearFrame3dComparisonRowV1 {
  quantity: Quantity
  entity_id: string
  component: string
  unit: 'm' | 'rad' | 'N' | 'N*m'
  native_value: number
  reference_value: number
  absolute_difference: number
  scaled_difference: number
  tolerance: 0.005 | 0.01
  passed: boolean
}

export interface LinearFrame3dComparisonFamilyV1 {
  quantity: Quantity
  row_count: number
  failing_row_count: number
  max_scaled_difference: number
  tolerance: 0.005 | 0.01
  worst_entity_id: string
  worst_component: string
  passed: boolean
}

export interface LinearFrame3dComparisonIrV1 {
  schema_version: 'structural-native-linear-frame3d-comparison-ir.v1'
  comparison_id: string
  comparison_hash: string
  comparison_kind: 'bounded_native_to_external_linear_frame3d'
  source_result: {
    schema_version: 'structural-native-linear-frame3d-result-ir.v1'
    result_id: string
    result_hash: string
    model_content_hash: string
  }
  source_reference: {
    schema_version: 'structural-external-linear-frame3d-reference.v1'
    reference_id: string
    reference_hash: string
    tool: ExternalLinearFrame3dReferenceV1['source']['tool']
    version: string
    origin: ExternalLinearFrame3dReferenceV1['source']['origin']
    export_sha256: string
  }
  tolerance_profile: typeof TOLERANCE_PROFILE
  summary: {
    row_count: number
    failing_row_count: number
    passed: boolean
    families: LinearFrame3dComparisonFamilyV1[]
  }
  rows: LinearFrame3dComparisonRowV1[]
  authority: typeof COMPARISON_AUTHORITY
  claim_boundary: typeof COMPARISON_CLAIM_BOUNDARY
}

export interface NativeFrameComparisonLoadResult {
  status: NativeFrameComparisonLoadStatus
  referenceIr: ExternalLinearFrame3dReferenceV1 | null
  comparisonIr: LinearFrame3dComparisonIrV1 | null
  errors: string[]
}

const REFERENCE_SCHEMA = 'structural-external-linear-frame3d-reference.v1'
const COMPARISON_SCHEMA = 'structural-native-linear-frame3d-comparison-ir.v1'
const ZERO_HASH = `sha256:${'0'.repeat(64)}`
const HASH = /^sha256:[0-9a-f]{64}$/
const STABLE_ID = /^[A-Za-z][A-Za-z0-9_.:-]{0,127}$/
const JSON_CONTENT_TYPE = /^application\/(?:json|[a-z0-9.+-]+\+json)\b/i
const MAX_BYTES = 2 * 1024 * 1024
const DISPLACEMENT_COMPONENTS = ['UX', 'UY', 'UZ', 'RX', 'RY', 'RZ'] as const
const FORCE_COMPONENTS = ['FX', 'FY', 'FZ', 'MX', 'MY', 'MZ'] as const
const TOLERANCE_PROFILE = {
  profile: 'frame_alpha_cross_code.v1',
  scaled_difference: 'abs(native-reference)/max(abs(native),abs(reference),absolute_floor)',
  displacement_relative: 0.005,
  reaction_relative: 0.005,
  member_end_force_relative: 0.01,
  translation_rotation_absolute_floor: 1e-12,
  force_moment_absolute_floor: 1e-6,
} as const
const COMPARISON_AUTHORITY = {
  source_result: 'bounded_candidate',
  reference_input: 'operator_declared_or_synthetic_fixture',
  comparison: 'bounded_cross_code_evaluation',
  external_validation: 'not_established',
  engineering_design: 'not_authoritative',
  release_readiness: 'not_authoritative',
} as const
const COMPARISON_CLAIM_BOUNDARY =
  'strict_mapping_unit_normalization_and_tolerance_evaluation_not_external_validation_design_or_release_authority' as const

class ComparisonArtifactError extends Error {
  constructor(readonly kind: 'missing' | 'invalid' | 'error', message: string) {
    super(message)
  }
}

/** Load and atomically replay a ReferenceIR/ComparisonIR pair against one verified ResultIR. */
export async function loadNativeFrameComparison(
  result: NativeFrame3dResultIr | null,
  referenceUrl: string | undefined,
  comparisonUrl: string | undefined,
  signal?: AbortSignal,
): Promise<NativeFrameComparisonLoadResult> {
  if (!referenceUrl && !comparisonUrl) return empty('unconfigured')
  if (!referenceUrl || !comparisonUrl) {
    return empty('invalid', 'native Frame3D ReferenceIR and ComparisonIR URLs must be configured together')
  }
  if (!result) return empty('invalid', 'native Frame3D comparison requires a verified ResultIR')
  try {
    const [referenceValue, comparisonValue] = await Promise.all([
      fetchStrictJson(referenceUrl, 'native Frame3D ReferenceIR', signal),
      fetchStrictJson(comparisonUrl, 'native Frame3D ComparisonIR', signal),
    ])
    const reference = validateReference(referenceValue, result)
    const referenceHash = await sha256Hex(canonicalNativeJson(reference))
    const comparison = validateComparison(comparisonValue, result, reference, referenceHash)
    const body = { ...comparison, comparison_hash: ZERO_HASH }
    const comparisonHash = await sha256Hex(canonicalNativeJson(body))
    if (comparisonHash !== null && comparisonHash !== comparison.comparison_hash) {
      throw new Error('ComparisonIR hash mismatch')
    }
    if (referenceHash !== null && comparison.source_reference.reference_hash !== referenceHash) {
      throw new Error('ComparisonIR reference hash binding is invalid')
    }
    if (referenceHash === null || comparisonHash === null) {
      return empty('integrity_unavailable', 'native Frame3D comparison integrity is unavailable')
    }
    return { status: 'verified', referenceIr: reference, comparisonIr: comparison, errors: [] }
  } catch (error: unknown) {
    if ((error as Error)?.name === 'AbortError') return empty('unconfigured')
    const failure = error instanceof ComparisonArtifactError
      ? error
      : new ComparisonArtifactError('invalid', String((error as Error)?.message ?? error))
    return empty(failure.kind, failure.message)
  }
}

function validateReference(
  value: unknown,
  result: NativeFrame3dResultIr,
): ExternalLinearFrame3dReferenceV1 {
  const root = exactRecord(value, 'ReferenceIR', [
    'schema_version', 'reference_id', 'source', 'bindings', 'axes', 'units', 'nodes', 'members',
    'claim_boundary',
  ])
  exact(root.schema_version, REFERENCE_SCHEMA, 'ReferenceIR schema')
  id(root.reference_id, 'ReferenceIR reference_id')
  const source = exactRecord(root.source, 'ReferenceIR source', ['tool', 'version', 'origin', 'export_sha256'])
  if (!['sap2000', 'midas_gen', 'opensees', 'calculix', 'synthetic_fixture'].includes(String(source.tool))) {
    throw new Error('ReferenceIR source tool is invalid')
  }
  const external = ['sap2000', 'midas_gen', 'opensees', 'calculix'].includes(String(source.tool))
  exact(source.origin, external ? 'operator_attached_external' : 'synthetic_contract_fixture', 'ReferenceIR source origin')
  if (typeof source.version !== 'string' || source.version.trim().length === 0
    || [...source.version].length > 128
    || [...source.version].some((character) => /\p{Cc}/u.test(character))) {
    throw new Error('ReferenceIR source version is invalid')
  }
  hash(source.export_sha256, 'ReferenceIR export hash')
  requireExactRecord(root.bindings, 'ReferenceIR bindings', {
    model_content_hash: result.bindings.model_content_hash,
    load_pattern_id: result.bindings.load_pattern_id,
    load_combination_id: result.bindings.load_combination_id,
  })
  requireExactRecord(root.axes, 'ReferenceIR axes', {
    node_displacement: 'global_ux_uy_uz_rx_ry_rz',
    node_reaction: 'global_fx_fy_fz_mx_my_mz',
    member_end_force: 'member_local_fx_fy_fz_mx_my_mz_i_then_j',
    sign_convention: 'native_result_ir_compatible',
  })
  const units = exactRecord(root.units, 'ReferenceIR units', ['translation', 'rotation', 'force', 'moment'])
  oneOf(units.translation, ['m', 'mm'], 'ReferenceIR translation unit')
  exact(units.rotation, 'rad', 'ReferenceIR rotation unit')
  oneOf(units.force, ['N', 'kN'], 'ReferenceIR force unit')
  oneOf(units.moment, ['N*m', 'kN*m'], 'ReferenceIR moment unit')
  validateReferenceRows(root.nodes, result.nodes.map((row) => row.node_id), 'node')
  validateReferenceRows(root.members, result.members.map((row) => row.member_id), 'member')
  exact(
    root.claim_boundary,
    'operator_declared_mapping_and_units_not_independent_validation_or_release_authority',
    'ReferenceIR claim boundary',
  )
  return root as unknown as ExternalLinearFrame3dReferenceV1
}

function validateReferenceRows(
  value: unknown,
  expectedIds: string[],
  kind: 'node' | 'member',
): void {
  if (!Array.isArray(value) || value.length !== expectedIds.length) {
    throw new Error(`ReferenceIR ${kind} coverage is invalid`)
  }
  const found = new Set<string>()
  for (const item of value) {
    const keys = kind === 'node'
      ? ['node_id', 'displacement', 'reaction']
      : ['member_id', 'end_i_force', 'end_j_force']
    const row = exactRecord(item, `ReferenceIR ${kind}`, keys)
    const key = kind === 'node' ? 'node_id' : 'member_id'
    id(row[key], `ReferenceIR ${key}`)
    const rowId = row[key] as string
    if (found.has(rowId) || !expectedIds.includes(rowId)) throw new Error(`ReferenceIR ${kind} identity is invalid`)
    found.add(rowId)
    for (const vector of keys.slice(1)) sixFinite(row[vector], `ReferenceIR ${kind} ${vector}`)
  }
  if (expectedIds.some((rowId) => !found.has(rowId))) throw new Error(`ReferenceIR ${kind} coverage is invalid`)
}

function validateComparison(
  value: unknown,
  result: NativeFrame3dResultIr,
  reference: ExternalLinearFrame3dReferenceV1,
  referenceHash: string | null,
): LinearFrame3dComparisonIrV1 {
  const root = exactRecord(value, 'ComparisonIR', [
    'schema_version', 'comparison_id', 'comparison_hash', 'comparison_kind', 'source_result',
    'source_reference', 'tolerance_profile', 'summary', 'rows', 'authority', 'claim_boundary',
  ])
  exact(root.schema_version, COMPARISON_SCHEMA, 'ComparisonIR schema')
  id(root.comparison_id, 'ComparisonIR comparison_id')
  hash(root.comparison_hash, 'ComparisonIR comparison_hash')
  exact(root.comparison_kind, 'bounded_native_to_external_linear_frame3d', 'ComparisonIR kind')
  requireExactRecord(root.source_result, 'ComparisonIR source result', {
    schema_version: result.schema_version,
    result_id: result.result_id,
    result_hash: result.result_hash,
    model_content_hash: result.bindings.model_content_hash,
  })
  const sourceReference = exactRecord(root.source_reference, 'ComparisonIR source reference', [
    'schema_version', 'reference_id', 'reference_hash', 'tool', 'version', 'origin', 'export_sha256',
  ])
  requireExactRecord(sourceReference, 'ComparisonIR source reference', {
    schema_version: reference.schema_version,
    reference_id: reference.reference_id,
    reference_hash: sourceReference.reference_hash,
    tool: reference.source.tool,
    version: reference.source.version,
    origin: reference.source.origin,
    export_sha256: reference.source.export_sha256,
  })
  hash(sourceReference.reference_hash, 'ComparisonIR reference hash')
  if (referenceHash !== null) exact(sourceReference.reference_hash, referenceHash, 'ComparisonIR reference hash binding')
  requireExactRecord(root.tolerance_profile, 'ComparisonIR tolerance profile', TOLERANCE_PROFILE)
  requireExactRecord(root.authority, 'ComparisonIR authority', COMPARISON_AUTHORITY)
  exact(root.claim_boundary, COMPARISON_CLAIM_BOUNDARY, 'ComparisonIR claim boundary')
  const expectedRows = buildRows(result, reference)
  if (canonicalNativeJson(root.rows) !== canonicalNativeJson(expectedRows)) {
    throw new Error('ComparisonIR rows are not the deterministic evaluation of ResultIR and ReferenceIR')
  }
  const expectedSummary = summarize(expectedRows)
  if (canonicalNativeJson(root.summary) !== canonicalNativeJson(expectedSummary)) {
    throw new Error('ComparisonIR summary is inconsistent')
  }
  return root as unknown as LinearFrame3dComparisonIrV1
}

function buildRows(
  result: NativeFrame3dResultIr,
  reference: ExternalLinearFrame3dReferenceV1,
): LinearFrame3dComparisonRowV1[] {
  const nodes = new Map(reference.nodes.map((row) => [row.node_id, row]))
  const members = new Map(reference.members.map((row) => [row.member_id, row]))
  const rows: LinearFrame3dComparisonRowV1[] = []
  for (const node of result.nodes) {
    const target = nodes.get(node.node_id)
    if (!target) throw new Error('ReferenceIR node coverage is invalid')
    DISPLACEMENT_COMPONENTS.forEach((component, index) => {
      const scale = index < 3 && reference.units.translation === 'mm' ? 1e-3 : 1
      rows.push(row('displacement', node.node_id, component, index < 3 ? 'm' : 'rad',
        node.displacement_m_rad[index], target.displacement[index] * scale))
    })
    FORCE_COMPONENTS.forEach((component, index) => {
      const scale = index < 3
        ? reference.units.force === 'kN' ? 1e3 : 1
        : reference.units.moment === 'kN*m' ? 1e3 : 1
      rows.push(row('reaction', node.node_id, component, index < 3 ? 'N' : 'N*m',
        node.reaction_n_nm[index], target.reaction[index] * scale))
    })
  }
  for (const member of result.members) {
    const target = members.get(member.member_id)
    if (!target) throw new Error('ReferenceIR member coverage is invalid')
    for (const [end, nativeValues, referenceValues] of [
      ['I', member.end_i_force_n_nm, target.end_i_force],
      ['J', member.end_j_force_n_nm, target.end_j_force],
    ] as const) {
      FORCE_COMPONENTS.forEach((component, index) => {
        const scale = index < 3
          ? reference.units.force === 'kN' ? 1e3 : 1
          : reference.units.moment === 'kN*m' ? 1e3 : 1
        rows.push(row('member_end_force', member.member_id, `${component}_${end}`,
          index < 3 ? 'N' : 'N*m', nativeValues[index], referenceValues[index] * scale))
      })
    }
  }
  return rows
}

function row(
  quantity: Quantity,
  entityId: string,
  component: string,
  unit: LinearFrame3dComparisonRowV1['unit'],
  nativeValue: number,
  referenceValue: number,
): LinearFrame3dComparisonRowV1 {
  const tolerance = quantity === 'member_end_force' ? 0.01 : 0.005
  const floor = quantity === 'displacement' ? 1e-12 : 1e-6
  const absoluteDifference = Math.abs(nativeValue - referenceValue)
  const scaledDifference = absoluteDifference / Math.max(Math.abs(nativeValue), Math.abs(referenceValue), floor)
  return {
    quantity, entity_id: entityId, component, unit, native_value: nativeValue,
    reference_value: referenceValue, absolute_difference: absoluteDifference,
    scaled_difference: scaledDifference, tolerance, passed: scaledDifference <= tolerance,
  }
}

function summarize(rows: LinearFrame3dComparisonRowV1[]): LinearFrame3dComparisonIrV1['summary'] {
  const families = ([
    ['displacement', 0.005], ['reaction', 0.005], ['member_end_force', 0.01],
  ] as const).map(([quantity, tolerance]) => {
    const selected = rows.filter((item) => item.quantity === quantity)
    let worst = selected[0]
    for (const item of selected.slice(1)) if (item.scaled_difference > worst.scaled_difference) worst = item
    const failing = selected.filter((item) => !item.passed).length
    return {
      quantity, row_count: selected.length, failing_row_count: failing,
      max_scaled_difference: worst.scaled_difference, tolerance,
      worst_entity_id: worst.entity_id, worst_component: worst.component, passed: failing === 0,
    }
  })
  const failing = rows.filter((item) => !item.passed).length
  return { row_count: rows.length, failing_row_count: failing, passed: failing === 0, families }
}

async function fetchStrictJson(url: string, label: string, signal?: AbortSignal): Promise<unknown> {
  const response = await fetch(url, {
    method: 'GET', credentials: 'include', cache: 'no-store', headers: { Accept: 'application/json' }, signal,
  })
  if (response.status === 404) throw new ComparisonArtifactError('missing', `${label} not found`)
  if (!response.ok) throw new ComparisonArtifactError('error', `${label} returned HTTP ${response.status}`)
  if (!JSON_CONTENT_TYPE.test(response.headers.get('content-type') ?? '')) {
    throw new ComparisonArtifactError('invalid', `${label} content type is invalid`)
  }
  const declared = Number(response.headers.get('content-length'))
  if (Number.isFinite(declared) && declared > MAX_BYTES) throw new ComparisonArtifactError('invalid', `${label} exceeds the size limit`)
  const bytes = new Uint8Array(await response.arrayBuffer())
  if (bytes.byteLength > MAX_BYTES) throw new ComparisonArtifactError('invalid', `${label} exceeds the size limit`)
  let text: string
  try {
    text = new TextDecoder('utf-8', { fatal: true }).decode(bytes)
  } catch {
    throw new ComparisonArtifactError('invalid', `${label} is not valid UTF-8`)
  }
  try {
    return parseNativeJsonStrict(text)
  } catch (error: unknown) {
    const duplicate = (error as Error)?.message === 'native_frame_duplicate_json_key'
    throw new ComparisonArtifactError('invalid', duplicate ? `${label} contains a duplicate JSON key` : `${label} JSON is invalid`)
  }
}

function empty(status: NativeFrameComparisonLoadStatus, error?: string): NativeFrameComparisonLoadResult {
  return { status, referenceIr: null, comparisonIr: null, errors: error ? [error] : [] }
}

function exactRecord(value: unknown, label: string, keys: readonly string[]): Record<string, unknown> {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error(`${label} is not an object`)
  const record = value as Record<string, unknown>
  const actual = Object.keys(record).sort()
  const expected = [...keys].sort()
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) {
    throw new Error(`${label} fields are invalid`)
  }
  return record
}

function requireExactRecord(value: unknown, label: string, expected: Record<string, unknown>): void {
  const actual = exactRecord(value, label, Object.keys(expected))
  for (const [key, expectedValue] of Object.entries(expected)) exact(actual[key], expectedValue, `${label} ${key}`)
}

function exact(value: unknown, expected: unknown, label: string): void {
  if (value !== expected) throw new Error(`${label} is invalid`)
}

function oneOf(value: unknown, expected: readonly unknown[], label: string): void {
  if (!expected.includes(value)) throw new Error(`${label} is invalid`)
}

function id(value: unknown, label: string): asserts value is string {
  if (typeof value !== 'string' || !STABLE_ID.test(value)) throw new Error(`${label} is invalid`)
}

function hash(value: unknown, label: string): asserts value is string {
  if (typeof value !== 'string' || !HASH.test(value)) throw new Error(`${label} is invalid`)
}

function sixFinite(value: unknown, label: string): void {
  if (!Array.isArray(value) || value.length !== 6
    || value.some((item) => typeof item !== 'number' || !Number.isFinite(item))) {
    throw new Error(`${label} is invalid`)
  }
}
