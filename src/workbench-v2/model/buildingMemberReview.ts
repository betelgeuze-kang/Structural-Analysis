import {
  canonicalNativeJson,
  parseNativeJsonStrict,
  parseSavedNativeFramePair,
  type SavedNativeFramePair,
} from './nativeFrameProvider'
import { sha256Bytes, sha256Hex } from './checksum'

export const BUILDING_MEMBER_MODEL_MAX_BYTES = 2 * 1024 * 1024
export const BUILDING_MEMBER_RESULT_MAX_BYTES = 2 * 1024 * 1024
export const BUILDING_MEMBER_MAPPING_MAX_BYTES = 1024 * 1024
const ID = /^[A-Za-z][A-Za-z0-9_.:-]{0,127}$/
const HASH = /^sha256:[0-9a-f]{64}$/
const MAX_ROWS = 4096

export interface BuildingMemberBindings {
  model_id: string
  model_content_hash: string
  model_semantic_hash: string
  model_provenance_hash: string
  result_id: string
  result_hash: string
}
export interface BuildingStorey { storey_id: string; label: string; elevation_m: number }
export interface BuildingMemberSegment {
  segment_id: string
  element_id: string
  member_start: number
  member_end: number
  orientation: 'i_to_j' | 'j_to_i'
}
export interface BuildingReviewLocation { location_id: string; element_id: string; end: 'i' | 'j' }
export interface BuildingPhysicalMember {
  member_id: string
  label: string
  storey_id: string
  segments: BuildingMemberSegment[]
  review_locations: BuildingReviewLocation[]
}
export interface BuildingMemberMapping {
  schema_version: 'structural-building-member-mapping.v1'
  mapping_id: string
  bindings: BuildingMemberBindings
  storeys: BuildingStorey[]
  members: BuildingPhysicalMember[]
}
export interface BuildingMemberReviewRow {
  element_id: string
  member_index: number
  model_element_row_index: number
  recovery_row_index: number
  result_member_row_index: number
  end: 'i' | 'j'
  node_id: string
  coordinate_frame: 'member_local'
  force_n_nm: [number, number, number, number, number, number]
  component_names: ['FX', 'FY', 'FZ', 'MX', 'MY', 'MZ']
  component_units: ['N', 'N', 'N', 'N*m', 'N*m', 'N*m']
  physical_member_id: string | null
  storey_id: string | null
  member_station: number | null
  orientation: 'i_to_j' | 'j_to_i' | null
  review_location_id: string | null
  mapping_status: 'MAPPED' | 'UNMAPPED'
  review_status: 'NOT_REVIEWED'
}
export interface BuildingMemberReview {
  schema_version: 'structural-building-member-review.v1'
  mapping_id: string
  mapping_hash: string
  source: BuildingMemberBindings & {
    model_file_hash: string
    result_file_hash: string
    mapping_file_hash: string
    load_pattern_id: string | null
    load_combination_id: string | null
    unit_profile: 'node_m_rad_force_n_nm_member_local_n_nm.v1'
  }
  storeys: BuildingStorey[]
  physical_members: Array<BuildingPhysicalMember & {
    mapping_status: 'MAPPED' | 'PARTIAL' | 'UNMAPPED'
    coverage_status: 'COMPLETE' | 'INCOMPLETE' | 'UNMAPPED'
    coverage_gaps: Array<{ start: number; end: number }>
    review_status: 'NOT_REVIEWED'
  }>
  rows: BuildingMemberReviewRow[]
  counts: {
    storeys: number
    physical_members: number
    mapped_elements: number
    unmapped_elements: number
    review_locations: number
    endpoint_rows: number
  }
  authority: 'operator_asserted_mapping_read_only'
  claim_boundary: 'saved_bounded_native_endpoint_results_only_not_interior_forces_physical_alignment_design_code_check_or_engineering_acceptance'
}

function exact(value: unknown, keys: string[], label: string): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)
    || Object.keys(value).length !== keys.length || keys.some((key) => !Object.prototype.hasOwnProperty.call(value, key))) {
    throw new Error(`${label} fields are invalid`)
  }
  return value as Record<string, unknown>
}
function id(value: unknown, label: string): asserts value is string {
  if (typeof value !== 'string' || !ID.test(value)) throw new Error(`${label} is invalid`)
}
function text(value: unknown, label: string): asserts value is string {
  if (typeof value !== 'string' || value.length < 1 || value.length > 200 || /[\u0000-\u001f\u007f]/.test(value)) {
    throw new Error(`${label} is invalid`)
  }
}
function list(value: unknown, label: string): unknown[] {
  if (!Array.isArray(value) || value.length > MAX_ROWS) throw new Error(`${label} size is invalid`)
  return value
}
function unique(value: string, seen: Set<string>, label: string): void {
  if (seen.has(value)) throw new Error(`${label} is duplicated`)
  seen.add(value)
}
function bindings(source: SavedNativeFramePair): BuildingMemberBindings {
  const result = source.resultIr
  return {
    model_id: result.bindings.model_id,
    model_content_hash: result.bindings.model_content_hash,
    model_semantic_hash: result.bindings.model_semantic_hash,
    model_provenance_hash: result.bindings.model_provenance_hash,
    result_id: result.result_id,
    result_hash: result.result_hash,
  }
}

/** No member or storey is inferred from geometry, names, or analysis element IDs. */
export async function createBuildingMemberMappingTemplate(
  modelBytes: Uint8Array,
  resultBytes: Uint8Array,
): Promise<BuildingMemberMapping> {
  const source = await parseSavedNativeFramePair(modelBytes, resultBytes)
  return {
    schema_version: 'structural-building-member-mapping.v1',
    mapping_id: 'building.mapping',
    bindings: bindings(source),
    storeys: [],
    members: [],
  }
}

function validateMapping(value: unknown, source: SavedNativeFramePair): BuildingMemberMapping {
  const root = exact(value, ['schema_version', 'mapping_id', 'bindings', 'storeys', 'members'], 'Mapping')
  if (root.schema_version !== 'structural-building-member-mapping.v1') throw new Error('Mapping schema is unsupported')
  id(root.mapping_id, 'Mapping ID')
  const expected = bindings(source)
  const bound = exact(root.bindings, Object.keys(expected), 'Mapping bindings')
  for (const [key, expectedValue] of Object.entries(expected)) {
    if (key.endsWith('_hash') && (typeof bound[key] !== 'string' || !HASH.test(bound[key] as string))) {
      throw new Error(`Mapping ${key} is invalid`)
    }
    if (bound[key] !== expectedValue) throw new Error(`Mapping ${key} binding differs from the saved source`)
  }
  const storeys = new Set<string>()
  for (const value of list(root.storeys, 'Storeys')) {
    const row = exact(value, ['storey_id', 'label', 'elevation_m'], 'Storey')
    id(row.storey_id, 'Storey ID')
    unique(row.storey_id, storeys, 'Storey ID')
    text(row.label, 'Storey label')
    if (typeof row.elevation_m !== 'number' || !Number.isFinite(row.elevation_m)) throw new Error('Storey elevation is invalid')
  }
  const recovered = new Map(source.elementRecovery.rows.map((row) => [row.member_id, row]))
  const memberIds = new Set<string>()
  const segmentIds = new Set<string>()
  const elementIds = new Set<string>()
  const locationIds = new Set<string>()
  let segmentCount = 0
  let locationCount = 0
  for (const value of list(root.members, 'Physical members')) {
    const member = exact(value, ['member_id', 'label', 'storey_id', 'segments', 'review_locations'], 'Physical member')
    id(member.member_id, 'Physical member ID')
    unique(member.member_id, memberIds, 'Physical member ID')
    text(member.label, 'Physical member label')
    id(member.storey_id, 'Physical member storey ID')
    if (!storeys.has(member.storey_id)) throw new Error('Physical member storey is not declared')
    const localElements = new Set<string>()
    const segments = list(member.segments, 'Segments').map((value) => {
      const segment = exact(value, ['segment_id', 'element_id', 'member_start', 'member_end', 'orientation'], 'Segment')
      id(segment.segment_id, 'Segment ID')
      id(segment.element_id, 'Segment element ID')
      unique(segment.segment_id, segmentIds, 'Segment ID')
      unique(segment.element_id, elementIds, 'Mapped element ID')
      localElements.add(segment.element_id)
      if (!recovered.has(segment.element_id)) throw new Error('Mapped element is absent from the saved source')
      if (typeof segment.member_start !== 'number' || typeof segment.member_end !== 'number'
        || !Number.isFinite(segment.member_start) || !Number.isFinite(segment.member_end)
        || segment.member_start < 0 || segment.member_end > 1 || segment.member_start >= segment.member_end) {
        throw new Error('Member segment interval must increase within [0, 1]')
      }
      if (segment.orientation !== 'i_to_j' && segment.orientation !== 'j_to_i') throw new Error('Segment orientation is invalid')
      return segment as unknown as BuildingMemberSegment
    })
    segmentCount += segments.length
    if (segmentCount > MAX_ROWS) throw new Error('Total segment count is invalid')
    const ordered = [...segments].sort((a, b) => a.member_start - b.member_start)
    for (let index = 1; index < ordered.length; index += 1) {
      const previous = ordered[index - 1]
      const current = ordered[index]
      if (previous.member_end > current.member_start) throw new Error('Member segments overlap')
      if (previous.member_end < current.member_start) continue
      const previousRow = recovered.get(previous.element_id)!
      const currentRow = recovered.get(current.element_id)!
      const previousEnd = previous.orientation === 'i_to_j' ? previousRow.node_j : previousRow.node_i
      const currentStart = current.orientation === 'i_to_j' ? currentRow.node_i : currentRow.node_j
      if (previousEnd !== currentStart) throw new Error('Member segments are not connected in the declared orientation')
    }
    const selectedEnds = new Set<string>()
    const locations = list(member.review_locations, 'Review locations')
    locationCount += locations.length
    if (locationCount > MAX_ROWS) throw new Error('Total review location count is invalid')
    for (const value of locations) {
      const location = exact(value, ['location_id', 'element_id', 'end'], 'Review location')
      id(location.location_id, 'Review location ID')
      unique(location.location_id, locationIds, 'Review location ID')
      id(location.element_id, 'Review element ID')
      if (!localElements.has(location.element_id)) throw new Error('Review location element is absent from its physical member')
      if (location.end !== 'i' && location.end !== 'j') throw new Error('Review location must select an existing native i or j end')
      unique(`${location.element_id}/${location.end}`, selectedEnds, 'Review endpoint')
    }
  }
  return value as BuildingMemberMapping
}

function coverageGaps(segments: BuildingMemberSegment[]): Array<{ start: number; end: number }> {
  const gaps: Array<{ start: number; end: number }> = []
  let position = 0
  for (const segment of [...segments].sort((a, b) => a.member_start - b.member_start)) {
    if (position < segment.member_start) gaps.push({ start: position, end: segment.member_start })
    position = segment.member_end
  }
  if (position < 1) gaps.push({ start: position, end: 1 })
  return gaps
}

/** Map all saved native endpoint rows. The authored direction locates endpoints only;
 * native axes and signs remain unchanged. Shared stations retain both native sides.
 */
export async function openBuildingMemberReview(
  modelBytes: Uint8Array,
  resultBytes: Uint8Array,
  mappingBytes: Uint8Array,
): Promise<BuildingMemberReview> {
  if (mappingBytes.byteLength === 0 || mappingBytes.byteLength > BUILDING_MEMBER_MAPPING_MAX_BYTES) {
    throw new Error('Mapping file size is invalid')
  }
  mappingBytes = new Uint8Array(mappingBytes)
  if (mappingBytes[0] === 0xef && mappingBytes[1] === 0xbb && mappingBytes[2] === 0xbf) throw new Error('Mapping UTF-8 BOM is not supported')
  const mappingValue = parseNativeJsonStrict(new TextDecoder('utf-8', { fatal: true }).decode(mappingBytes))
  const source = await parseSavedNativeFramePair(modelBytes, resultBytes)
  const mapping = validateMapping(mappingValue, source)
  const [mappingHash, mappingFileHash] = await Promise.all([
    sha256Hex(canonicalNativeJson(mapping)), sha256Bytes(mappingBytes),
  ])
  if (mappingHash === null || mappingFileHash === null) throw new Error('Mapping integrity is unavailable')
  const ownership = new Map<string, { member: BuildingPhysicalMember; segment: BuildingMemberSegment }>()
  const locations = new Map<string, string>()
  for (const member of mapping.members) {
    for (const segment of member.segments) ownership.set(segment.element_id, { member, segment })
    for (const location of member.review_locations) locations.set(`${location.element_id}/${location.end}`, location.location_id)
  }
  const recovery = new Map(source.elementRecovery.rows.map((row, index) => [row.member_id, { row, index }]))
  const rows: BuildingMemberReviewRow[] = []
  source.resultIr.members.forEach((resultRow, resultIndex) => {
    const recovered = recovery.get(resultRow.member_id)!
    const element = recovered.row
    const owner = ownership.get(element.member_id)
    for (const end of ['i', 'j'] as const) {
      const start = owner && ((end === 'i') === (owner.segment.orientation === 'i_to_j'))
      rows.push({
        element_id: element.member_id,
        member_index: element.member_index,
        model_element_row_index: source.modelElementRowIndices[element.member_id],
        recovery_row_index: recovered.index,
        result_member_row_index: resultIndex,
        end,
        node_id: end === 'i' ? element.node_i : element.node_j,
        coordinate_frame: 'member_local',
        force_n_nm: [...(end === 'i' ? resultRow.end_i_force_n_nm : resultRow.end_j_force_n_nm)],
        component_names: ['FX', 'FY', 'FZ', 'MX', 'MY', 'MZ'],
        component_units: ['N', 'N', 'N', 'N*m', 'N*m', 'N*m'],
        physical_member_id: owner?.member.member_id ?? null,
        storey_id: owner?.member.storey_id ?? null,
        member_station: owner ? (start ? owner.segment.member_start : owner.segment.member_end) : null,
        orientation: owner?.segment.orientation ?? null,
        review_location_id: locations.get(`${element.member_id}/${end}`) ?? null,
        mapping_status: owner ? 'MAPPED' : 'UNMAPPED',
        review_status: 'NOT_REVIEWED',
      })
    }
  })
  return {
    schema_version: 'structural-building-member-review.v1',
    mapping_id: mapping.mapping_id,
    mapping_hash: mappingHash,
    source: {
      ...bindings(source),
      model_file_hash: source.modelFileHash,
      result_file_hash: source.resultFileHash,
      mapping_file_hash: mappingFileHash,
      load_pattern_id: source.resultIr.bindings.load_pattern_id,
      load_combination_id: source.resultIr.bindings.load_combination_id,
      unit_profile: source.resultIr.solver.unit_profile,
    },
    storeys: mapping.storeys,
    physical_members: mapping.members.map((member) => {
      const gaps = coverageGaps(member.segments)
      return {
        ...member,
        mapping_status: member.segments.length ? (gaps.length ? 'PARTIAL' : 'MAPPED') : 'UNMAPPED',
        coverage_status: member.segments.length ? (gaps.length ? 'INCOMPLETE' : 'COMPLETE') : 'UNMAPPED',
        coverage_gaps: gaps,
        review_status: 'NOT_REVIEWED',
      }
    }),
    rows,
    counts: {
      storeys: mapping.storeys.length,
      physical_members: mapping.members.length,
      mapped_elements: ownership.size,
      unmapped_elements: source.resultIr.members.length - ownership.size,
      review_locations: locations.size,
      endpoint_rows: rows.length,
    },
    authority: 'operator_asserted_mapping_read_only',
    claim_boundary: 'saved_bounded_native_endpoint_results_only_not_interior_forces_physical_alignment_design_code_check_or_engineering_acceptance',
  }
}
