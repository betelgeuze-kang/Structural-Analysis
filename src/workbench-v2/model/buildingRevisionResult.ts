import {
  BUILDING_LOAD_REVISION_MAX_BYTES, compileBuildingLoadRevision, openBuildingLoadRevisionDraft,
  type BuildingLoadRevisionDraft, type BuildingLoadRevisionRecord, type BuildingRevisionArtifact,
} from './buildingLoadRevision'
import {
  BUILDING_MEMBER_MAPPING_MAX_BYTES, BUILDING_MEMBER_RESULT_MAX_BYTES, openBuildingMemberReview,
  type BuildingMemberBindings, type BuildingMemberMapping, type BuildingMemberReview,
} from './buildingMemberReview'
import { canonicalNativeJson, parseNativeJsonStrict } from './nativeFrameProvider'
import { sha256Bytes } from './checksum'

export const BUILDING_REVISION_RESULT_MAX_BYTES = 16 * 1024 * 1024
const HASH = /^sha256:[0-9a-f]{64}$/
const ID = /^[A-Za-z][A-Za-z0-9_.:-]{0,127}$/
export type BuildingRevisionLoadSource = { kind: 'load_pattern' | 'load_combination'; id: string }
export interface BuildingRevisionResultAttachment {
  schema_version: 'structural-building-revision-result-attachment.v1'
  draft: BuildingRevisionArtifact
  result_ir: BuildingRevisionArtifact
  selected_load_source: BuildingRevisionLoadSource
}
export interface BuildingRevisionResultLineage {
  schema_version: 'structural-building-revision-result-lineage.v1'
  revision_id: string
  draft_file_hash: string
  attachment_file_hash: string
  edit_recipe_hash: string
  unchanged_inventory_hash: string
  parent: BuildingLoadRevisionRecord['parent']
  parent_load_source: BuildingRevisionLoadSource
  target: BuildingMemberBindings & { model_file_hash: string; result_file_hash: string; mapping_file_hash: string }
  selected_load_source: BuildingRevisionLoadSource
  compilation_analysis_status: 'NOT_RUN'
  attachment_status: 'STORED_RESULT_FILE_CONSISTENT'
  result_origin: 'UNVERIFIED'
  execution_status: 'NOT_VERIFIED'
  review_status: 'NOT_REVIEWED'
  comparison_status: 'NOT_COMPUTED'
  authority: 'saved_result_attachment_read_only'
  claim_boundary: 'file_integrity_and_exact_target_binding_only_not_execution_parent_comparison_design_code_check_or_engineering_acceptance'
}
export interface BuildingRevisionResultSession {
  draft: BuildingLoadRevisionDraft
  compiled: Awaited<ReturnType<typeof compileBuildingLoadRevision>>
  mapping: BuildingMemberMapping
  review: BuildingMemberReview
  lineage: BuildingRevisionResultLineage
  draftBytes: Uint8Array
  resultBytes: Uint8Array
  targetModelBytes: Uint8Array
  mappingBytes: Uint8Array
  reviewBytes: Uint8Array
  lineageBytes: Uint8Array
  attachmentBytes: Uint8Array
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
function limited(bytes: Uint8Array, maximum: number, label: string): void {
  if (!bytes.byteLength || bytes.byteLength > maximum) throw new Error(`${label} file size is invalid`)
}
function json(bytes: Uint8Array, maximum: number, label: string): unknown {
  limited(bytes, maximum, label)
  if (bytes[0] === 0xef && bytes[1] === 0xbb && bytes[2] === 0xbf) throw new Error(`${label} UTF-8 BOM is unsupported`)
  return parseNativeJsonStrict(new TextDecoder('utf-8', { fatal: true }).decode(bytes))
}
function bytes(value: unknown): Uint8Array { return new TextEncoder().encode(canonicalNativeJson(value)) }
async function hash(value: Uint8Array): Promise<string> {
  const digest = await sha256Bytes(value)
  if (digest === null) throw new Error('Result attachment integrity is unavailable')
  return digest
}
function base64(value: Uint8Array): string {
  let binary = ''
  for (let index = 0; index < value.length; index += 32768) binary += String.fromCharCode(...value.subarray(index, index + 32768))
  return btoa(binary)
}
async function artifact(value: Uint8Array): Promise<BuildingRevisionArtifact> {
  return { body_base64: base64(value), byte_length: value.byteLength, sha256: await hash(value) }
}
function artifactBytes(value: unknown, maximum: number, label: string): { bytes: Uint8Array; sha256: string } {
  const row = exact(value, ['body_base64', 'byte_length', 'sha256'], `${label} artifact`)
  if (!Number.isSafeInteger(row.byte_length) || (row.byte_length as number) < 1 || (row.byte_length as number) > maximum) throw new Error(`${label} artifact size is invalid`)
  if (typeof row.sha256 !== 'string' || !HASH.test(row.sha256)) throw new Error(`${label} artifact hash is invalid`)
  if (typeof row.body_base64 !== 'string' || row.body_base64.length !== 4 * Math.ceil((row.byte_length as number) / 3)
    || !/^[A-Za-z0-9+/]*={0,2}$/.test(row.body_base64)) throw new Error(`${label} artifact base64 is invalid`)
  const binary = atob(row.body_base64)
  const decoded = Uint8Array.from(binary, char => char.charCodeAt(0))
  if (decoded.byteLength !== row.byte_length || base64(decoded) !== row.body_base64) throw new Error(`${label} artifact base64 is noncanonical`)
  return { bytes: decoded, sha256: row.sha256 }
}
function selectedSource(value: unknown): BuildingRevisionLoadSource {
  const row = exact(value, ['kind', 'id'], 'Selected load source')
  if ((row.kind !== 'load_pattern' && row.kind !== 'load_combination') || typeof row.id !== 'string' || !ID.test(row.id)) throw new Error('Selected load source is invalid')
  return { kind: row.kind, id: row.id }
}
function source(pattern: string | null, combination: string | null): BuildingRevisionLoadSource {
  // The existing pair admission verifies that exactly one valid source exists in this model.
  return pattern !== null ? { kind: 'load_pattern', id: pattern } : { kind: 'load_combination', id: combination! }
}

/** Attach saved bytes to a deterministically compiled draft; no solver or service is invoked.
 * The original draft continues to describe an unexecuted edit. File consistency never
 * establishes who produced a result, that its computation ran, or engineering acceptance.
 */
export async function attachBuildingRevisionResult(draftBytes: Uint8Array, resultBytes: Uint8Array, expectedLoadSource: BuildingRevisionLoadSource): Promise<BuildingRevisionResultSession> {
  // Check both lengths before copying either buffer. Uint8Array owns Buffer subclasses too.
  limited(draftBytes, BUILDING_LOAD_REVISION_MAX_BYTES, 'Revision draft')
  limited(resultBytes, BUILDING_MEMBER_RESULT_MAX_BYTES, 'ResultIR')
  const selected = selectedSource(expectedLoadSource)
  draftBytes = new Uint8Array(draftBytes)
  resultBytes = new Uint8Array(resultBytes)
  return admit(draftBytes, resultBytes, selected)
}

async function admit(draftBytes: Uint8Array, resultBytes: Uint8Array, selected: BuildingRevisionLoadSource, originalAttachmentBytes?: Uint8Array): Promise<BuildingRevisionResultSession> {
  const draft = await openBuildingLoadRevisionDraft(draftBytes)
  const compiled = await compileBuildingLoadRevision(draft)
  const parentMapping = object(json(Uint8Array.from(atob(draft.parent.mapping.body_base64), char => char.charCodeAt(0)), BUILDING_MEMBER_MAPPING_MAX_BYTES, 'Parent mapping'), 'Parent mapping') as unknown as BuildingMemberMapping
  const incoming = object(json(resultBytes, BUILDING_MEMBER_RESULT_MAX_BYTES, 'ResultIR'), 'ResultIR')
  // Rebuild only from the target identity and the validated original inventory. These
  // fields gain no authority until openBuildingMemberReview admits the complete pair.
  const mapping: BuildingMemberMapping = {
    schema_version: 'structural-building-member-mapping.v1', mapping_id: parentMapping.mapping_id,
    bindings: {
      model_id: compiled.revisionRecord.target.model_id, ...compiled.targetIdentity,
      result_id: incoming.result_id as string, result_hash: incoming.result_hash as string,
    },
    storeys: structuredClone(compiled.revisionRecord.unchanged_inventory.storeys),
    members: structuredClone(compiled.revisionRecord.unchanged_inventory.members),
  }
  const mappingBytes = bytes(mapping)
  const review = await openBuildingMemberReview(compiled.modelBytes, resultBytes, mappingBytes)
  const actualSource = source(review.source.load_pattern_id, review.source.load_combination_id)
  if (actualSource.kind !== selected.kind || actualSource.id !== selected.id) throw new Error('ResultIR selected load source differs from the explicitly selected target load source')
  // Parent review supplies the original load source independently of the new result.
  const parentResult = object(json(Uint8Array.from(atob(draft.parent.result_ir.body_base64), char => char.charCodeAt(0)), BUILDING_MEMBER_RESULT_MAX_BYTES, 'Parent ResultIR'), 'Parent ResultIR')
  const parentBindings = object(parentResult.bindings, 'Parent bindings')
  const attachment: BuildingRevisionResultAttachment = {
    schema_version: 'structural-building-revision-result-attachment.v1',
    draft: await artifact(draftBytes), result_ir: await artifact(resultBytes), selected_load_source: selected,
  }
  const attachmentBytes = originalAttachmentBytes ?? bytes(attachment)
  limited(attachmentBytes, BUILDING_REVISION_RESULT_MAX_BYTES, 'Result attachment')
  const lineage: BuildingRevisionResultLineage = {
    schema_version: 'structural-building-revision-result-lineage.v1', revision_id: draft.revision_id,
    draft_file_hash: attachment.draft.sha256, attachment_file_hash: await hash(attachmentBytes),
    edit_recipe_hash: compiled.revisionRecord.edit_recipe_hash,
    unchanged_inventory_hash: compiled.revisionRecord.unchanged_inventory_hash,
    parent: structuredClone(compiled.revisionRecord.parent),
    parent_load_source: source(parentBindings.load_pattern_id as string | null, parentBindings.load_combination_id as string | null),
    target: {
      model_id: review.source.model_id, model_content_hash: review.source.model_content_hash,
      model_semantic_hash: review.source.model_semantic_hash, model_provenance_hash: review.source.model_provenance_hash,
      result_id: review.source.result_id, result_hash: review.source.result_hash,
      model_file_hash: review.source.model_file_hash, result_file_hash: review.source.result_file_hash, mapping_file_hash: review.source.mapping_file_hash,
    },
    selected_load_source: { ...selected },
    compilation_analysis_status: 'NOT_RUN', attachment_status: 'STORED_RESULT_FILE_CONSISTENT',
    result_origin: 'UNVERIFIED', execution_status: 'NOT_VERIFIED', review_status: 'NOT_REVIEWED', comparison_status: 'NOT_COMPUTED',
    authority: 'saved_result_attachment_read_only',
    claim_boundary: 'file_integrity_and_exact_target_binding_only_not_execution_parent_comparison_design_code_check_or_engineering_acceptance',
  }
  return {
    draft, compiled, mapping, review, lineage, draftBytes, resultBytes,
    targetModelBytes: new Uint8Array(compiled.modelBytes), mappingBytes,
    reviewBytes: bytes(review), lineageBytes: bytes(lineage), attachmentBytes,
  }
}

/** A reopened file contains raw inputs only. Every derived model, mapping, review,
 * record, load source, and identity is recomputed and admitted atomically.
 */
export async function openBuildingRevisionResultAttachment(input: Uint8Array): Promise<BuildingRevisionResultSession> {
  limited(input, BUILDING_REVISION_RESULT_MAX_BYTES, 'Result attachment')
  const snapshot = new Uint8Array(input)
  const root = exact(json(snapshot, BUILDING_REVISION_RESULT_MAX_BYTES, 'Result attachment'), ['schema_version', 'draft', 'result_ir', 'selected_load_source'], 'Result attachment')
  if (root.schema_version !== 'structural-building-revision-result-attachment.v1') throw new Error('Result attachment schema is unsupported')
  const selected = selectedSource(root.selected_load_source)
  const draft = artifactBytes(root.draft, BUILDING_LOAD_REVISION_MAX_BYTES, 'Revision draft')
  const result = artifactBytes(root.result_ir, BUILDING_MEMBER_RESULT_MAX_BYTES, 'ResultIR')
  const [draftHash, resultHash] = await Promise.all([hash(draft.bytes), hash(result.bytes)])
  if (draftHash !== draft.sha256 || resultHash !== result.sha256) throw new Error('Result attachment artifact hash mismatch')
  return admit(draft.bytes, result.bytes, selected, snapshot)
}
