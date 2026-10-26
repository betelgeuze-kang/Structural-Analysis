import { expect, test } from '@playwright/test'
import { createHash } from 'node:crypto'
import {
  BUILDING_REVISION_RESULT_MAX_BYTES, attachBuildingRevisionResult, openBuildingRevisionResultAttachment,
} from '../../src/workbench-v2/model/buildingRevisionResult'
import { BUILDING_LOAD_REVISION_MAX_BYTES, serializeBuildingLoadRevisionDraft } from '../../src/workbench-v2/model/buildingLoadRevision'
import { BUILDING_MEMBER_RESULT_MAX_BYTES, openBuildingMemberReview } from '../../src/workbench-v2/model/buildingMemberReview'
import { buildingFixtureBytes as bytes } from './buildingMemberFixture'
import { buildingRevisionResultFixture } from './buildingRevisionResultFixture'
import { fixtureHash } from './nativeFrameFixture'

const digest = (value: Uint8Array) => `sha256:${createHash('sha256').update(value).digest('hex')}`
const combo = { kind: 'load_combination' as const, id: 'COMB1' }
const pattern = { kind: 'load_pattern' as const, id: 'LC1' }
const parsed = (value: Uint8Array) => JSON.parse(new TextDecoder().decode(value))
function rehash<T extends { result_hash: string }>(value: T): T {
  const body = { ...value }; delete (body as Partial<T>).result_hash
  value.result_hash = fixtureHash(body)
  return value
}
function putArtifact(root: Record<string, unknown>, key: string, value: Uint8Array) {
  root[key] = { body_base64: Buffer.from(value).toString('base64'), byte_length: value.byteLength, sha256: digest(value) }
}

test('exact compiled target attaches signed endpoint rows and unchanged physical inventory without promoting execution or review', async () => {
  const f = await buildingRevisionResultFixture()
  const parentBytes = Buffer.from(f.fixture.resultBytes)
  const session = await attachBuildingRevisionResult(f.draftBytes, f.resultBytes, combo)
  expect(session.compiled).toEqual(f.compiled)
  expect(session.compiled.revisionRecord.target).toMatchObject({ analysis_status: 'NOT_RUN', review_status: 'NOT_REVIEWED', result: null })
  expect(session.mapping.storeys).toEqual(f.fixture.mapping.storeys)
  expect(session.mapping.members).toEqual(f.fixture.mapping.members)
  expect(session.mapping.bindings).toEqual({
    model_id: String(f.compiled.modelIr.model_id), ...f.compiled.targetIdentity, result_id: f.result.result_id, result_hash: f.result.result_hash,
  })
  expect(session.review.physical_members.find(row => row.member_id === 'PHYSICAL_C12')).toMatchObject({ mapping_status: 'UNMAPPED', review_status: 'NOT_REVIEWED' })
  const junction = session.review.rows.filter(row => row.member_station === 0.5)
  expect(junction).toHaveLength(2)
  expect(junction.map(row => row.force_n_nm)).toEqual([f.result.members[0].end_j_force_n_nm, f.result.members[1].end_j_force_n_nm])
  expect(junction.map(row => row.result_member_row_index)).toEqual([0, 1])
  expect(junction.map(row => row.node_id)).toEqual(['N2', 'N2'])
  expect(session.review.rows.every(row => row.coordinate_frame === 'member_local' && row.review_status === 'NOT_REVIEWED')).toBe(true)
  expect(session.lineage).toMatchObject({
    parent_load_source: { kind: 'load_combination', id: 'COMB1' }, selected_load_source: { kind: 'load_combination', id: 'COMB1' },
    compilation_analysis_status: 'NOT_RUN', attachment_status: 'STORED_RESULT_FILE_CONSISTENT', result_origin: 'UNVERIFIED',
    execution_status: 'NOT_VERIFIED', review_status: 'NOT_REVIEWED', comparison_status: 'NOT_COMPUTED',
  })
  expect(session.lineage.target.result_file_hash).toBe(digest(f.resultBytes))
  expect(session.lineage.parent.result_hash).toBe(f.fixture.result.result_hash)
  expect(Buffer.from(f.fixture.resultBytes)).toEqual(parentBytes)
  expect(f.draft.parent.result_ir.body_base64).toBe(parentBytes.toString('base64'))
})

test('standalone attachment retains exact input bytes and recomputes every derived output on reopen', async () => {
  const f = await buildingRevisionResultFixture({ combination: false })
  const draftRaw = new TextEncoder().encode(` \n${new TextDecoder().decode(f.draftBytes)}\n`)
  const resultRaw = new TextEncoder().encode(`\n${new TextDecoder().decode(f.resultBytes)} `)
  const session = await attachBuildingRevisionResult(draftRaw, resultRaw, pattern)
  const root = parsed(session.attachmentBytes)
  expect(Object.keys(root).sort()).toEqual(['draft', 'result_ir', 'schema_version', 'selected_load_source'])
  expect(Buffer.from(root.draft.body_base64, 'base64')).toEqual(Buffer.from(draftRaw))
  expect(Buffer.from(root.result_ir.body_base64, 'base64')).toEqual(Buffer.from(resultRaw))
  const reopened = await openBuildingRevisionResultAttachment(session.attachmentBytes)
  for (const key of ['draftBytes', 'resultBytes', 'targetModelBytes', 'mappingBytes', 'reviewBytes', 'lineageBytes', 'attachmentBytes'] as const) expect(reopened[key]).toEqual(session[key])
  expect(reopened.lineage.selected_load_source).toEqual({ kind: 'load_pattern', id: 'LC1' })
  expect(reopened.lineage.draft_file_hash).toBe(digest(draftRaw))
  expect(reopened.lineage.attachment_file_hash).toBe(digest(session.attachmentBytes))
  expect(await openBuildingMemberReview(reopened.targetModelBytes, reopened.resultBytes, reopened.mappingBytes)).toEqual(reopened.review)
  expect(parsed(reopened.reviewBytes)).toEqual(reopened.review)
  expect(parsed(reopened.lineageBytes)).toEqual(reopened.lineage)
  session.mapping.members[0].label = 'later mutation'
  session.review.rows[0].force_n_nm[0] = 999
  session.lineage.target.result_hash = 'forged'
  expect((await openBuildingRevisionResultAttachment(session.attachmentBytes)).review).toEqual(reopened.review)
})

test('a reused result ID is accepted only with a distinct exact-target content identity', async () => {
  const f = await buildingRevisionResultFixture()
  f.result.result_id = String(f.fixture.result.result_id)
  rehash(f.result)
  expect(f.result.result_hash).not.toBe(f.fixture.result.result_hash)
  const session = await attachBuildingRevisionResult(f.draftBytes, bytes(f.result), combo)
  expect(session.lineage.target.result_id).toBe(session.lineage.parent.result_id)
  expect(session.lineage.target.result_hash).not.toBe(session.lineage.parent.result_hash)
  await expect(attachBuildingRevisionResult(f.draftBytes, f.fixture.resultBytes, combo)).rejects.toThrow('binding')
})

test('a different valid selected load source stays explicit without creating a parent comparison', async () => {
  const f = await buildingRevisionResultFixture()
  const result = rehash({ ...f.result, bindings: { ...f.result.bindings, load_pattern_id: 'LC1', load_combination_id: null } })
  const session = await attachBuildingRevisionResult(f.draftBytes, bytes(result), pattern)
  expect(session.lineage.parent_load_source).toEqual({ kind: 'load_combination', id: 'COMB1' })
  expect(session.lineage.selected_load_source).toEqual({ kind: 'load_pattern', id: 'LC1' })
  expect(session.review.source.load_pattern_id).toBe('LC1')
  expect(session.review.source.load_combination_id).toBeNull()
  expect(session.lineage.comparison_status).toBe('NOT_COMPUTED')
})

for (const field of ['model_id', 'model_content_hash', 'model_semantic_hash', 'model_provenance_hash'] as const) test(`self-consistent result with wrong ${field} cannot attach`, async () => {
  const f = await buildingRevisionResultFixture()
  const result = structuredClone(f.result)
  result.bindings[field] = field === 'model_id' ? 'another.model' : `sha256:${'e'.repeat(64)}`
  rehash(result)
  await expect(attachBuildingRevisionResult(f.draftBytes, bytes(result), combo)).rejects.toThrow('binding')
})

for (const scenario of ['unknown pattern', 'unknown combination', 'both sources', 'no source', 'wrong schema', 'wrong result hash', 'missing member', 'wrong tuple', 'imported authority'] as const) test(`invalid native result rejects ${scenario}`, async () => {
  const f = await buildingRevisionResultFixture()
  const result = structuredClone(f.result)
  if (scenario === 'unknown pattern') { result.bindings.load_pattern_id = 'MISSING'; result.bindings.load_combination_id = null }
  if (scenario === 'unknown combination') result.bindings.load_combination_id = 'MISSING'
  if (scenario === 'both sources') result.bindings.load_pattern_id = 'LC1'
  if (scenario === 'no source') { result.bindings.load_pattern_id = null; result.bindings.load_combination_id = null }
  if (scenario === 'wrong schema') result.schema_version = 'forged.v1'
  if (scenario === 'missing member') result.members.pop()
  if (scenario === 'wrong tuple') result.members[0].end_i_force_n_nm.pop()
  if (scenario === 'imported authority') result.authority.engineering_design = 'authoritative'
  rehash(result)
  if (scenario === 'wrong result hash') result.result_hash = `sha256:${'f'.repeat(64)}`
  await expect(attachBuildingRevisionResult(f.draftBytes, bytes(result), combo)).rejects.toThrow()
})

test('target revision/provenance change rejects a result bound to a different compiled draft', async () => {
  const f = await buildingRevisionResultFixture()
  f.draft.revision_id = 'another.revision'
  await expect(attachBuildingRevisionResult(serializeBuildingLoadRevisionDraft(f.draft), f.resultBytes, combo)).rejects.toThrow('binding')
  f.draft.revision_id = 'synthetic.load.revision'
  f.draft.patches[0].self_weight[0] = 1
  await expect(attachBuildingRevisionResult(serializeBuildingLoadRevisionDraft(f.draft), f.resultBytes, combo)).rejects.toThrow('binding')
})

test('partial and unmapped physical members survive the attachment without invented interpolation or review', async () => {
  const f = await buildingRevisionResultFixture()
  const mapping = structuredClone(f.fixture.mapping)
  mapping.members[0].segments[0].member_start = 0.75
  mapping.members[0].segments[1].member_end = 0.25
  const body = bytes(mapping)
  f.draft.parent.mapping = { body_base64: Buffer.from(body).toString('base64'), byte_length: body.byteLength, sha256: digest(body) }
  // Recompile the changed inventory's edit provenance before authoring its target binding.
  const { compileBuildingLoadRevision } = await import('../../src/workbench-v2/model/buildingLoadRevision')
  const compiled = await compileBuildingLoadRevision(f.draft)
  Object.assign(f.result.bindings, compiled.targetIdentity)
  rehash(f.result)
  const session = await attachBuildingRevisionResult(serializeBuildingLoadRevisionDraft(f.draft), bytes(f.result), combo)
  expect(session.mapping.members).toEqual(mapping.members)
  expect(session.review.physical_members[0]).toMatchObject({ coverage_status: 'INCOMPLETE', coverage_gaps: [{ start: 0.25, end: 0.75 }], review_status: 'NOT_REVIEWED' })
  expect(session.review.physical_members[1].mapping_status).toBe('UNMAPPED')
  expect(session.review.rows).toHaveLength(4)
})

test('attachment rejects unknown derived claims, duplicate keys, malformed UTF-8, BOM, and unsupported versions', async () => {
  const f = await buildingRevisionResultFixture()
  const session = await attachBuildingRevisionResult(f.draftBytes, f.resultBytes, combo)
  const text = new TextDecoder().decode(session.attachmentBytes)
  for (const invalid of [
    text.replace('"schema_version":', '"review":{"status":"PASSED"},"schema_version":'),
    text.replace('"schema_version":', '"schema_version":"duplicate","schema_version":'),
    text.replace('structural-building-revision-result-attachment.v1', 'structural-building-revision-result-attachment.v2'),
  ]) await expect(openBuildingRevisionResultAttachment(new TextEncoder().encode(invalid))).rejects.toThrow()
  await expect(openBuildingRevisionResultAttachment(new Uint8Array([0xff]))).rejects.toThrow()
  await expect(openBuildingRevisionResultAttachment(new Uint8Array([0xef, 0xbb, 0xbf, ...session.attachmentBytes]))).rejects.toThrow('BOM')
  for (const inner of ['draft', 'result_ir'] as const) {
    const root = parsed(session.attachmentBytes)
    const original = Buffer.from(root[inner].body_base64, 'base64')
    putArtifact(root, inner, new Uint8Array([0xef, 0xbb, 0xbf, ...original]))
    await expect(openBuildingRevisionResultAttachment(bytes(root))).rejects.toThrow('BOM')
  }
})

for (const key of ['draft', 'result_ir'] as const) test(`attachment verifies exact embedded ${key} bytes, canonical base64, length and hash before admission`, async () => {
  const f = await buildingRevisionResultFixture()
  const session = await attachBuildingRevisionResult(f.draftBytes, f.resultBytes, combo)
  for (const change of ['hash', 'length', 'base64', 'unknown field', 'altered bytes'] as const) {
    const root = parsed(session.attachmentBytes)
    if (change === 'hash') root[key].sha256 = `sha256:${'1'.repeat(64)}`
    if (change === 'length') root[key].byte_length += 1
    if (change === 'base64') root[key].body_base64 = '!'.repeat(root[key].body_base64.length)
    if (change === 'unknown field') root[key].trusted = true
    if (change === 'altered bytes') { const body = Buffer.from(root[key].body_base64, 'base64'); body[5] ^= 1; root[key].body_base64 = body.toString('base64') }
    await expect(openBuildingRevisionResultAttachment(bytes(root))).rejects.toThrow()
  }
})

test('all outer and inner file ceilings reject oversized input before admission', async () => {
  const f = await buildingRevisionResultFixture()
  await expect(attachBuildingRevisionResult(new Uint8Array(BUILDING_LOAD_REVISION_MAX_BYTES + 1), f.resultBytes, combo)).rejects.toThrow('size')
  await expect(attachBuildingRevisionResult(f.draftBytes, new Uint8Array(BUILDING_MEMBER_RESULT_MAX_BYTES + 1), combo)).rejects.toThrow('size')
  await expect(openBuildingRevisionResultAttachment(new Uint8Array(BUILDING_REVISION_RESULT_MAX_BYTES + 1))).rejects.toThrow('size')
  const session = await attachBuildingRevisionResult(f.draftBytes, f.resultBytes, combo)
  for (const key of ['draft', 'result_ir'] as const) {
    const root = parsed(session.attachmentBytes)
    root[key].byte_length = (key === 'draft' ? BUILDING_LOAD_REVISION_MAX_BYTES : BUILDING_MEMBER_RESULT_MAX_BYTES) + 1
    await expect(openBuildingRevisionResultAttachment(bytes(root))).rejects.toThrow('size')
  }
})

test('caller buffer reuse after attach or reopen cannot alter the captured session', async () => {
  const f = await buildingRevisionResultFixture()
  const draft = Buffer.from(f.draftBytes), result = Buffer.from(f.resultBytes)
  const pending = attachBuildingRevisionResult(draft, result, combo)
  draft.fill(0); result.fill(0)
  const session = await pending
  expect(session.draftBytes).toEqual(f.draftBytes)
  expect(session.resultBytes).toEqual(f.resultBytes)
  const attachment = Buffer.from(session.attachmentBytes)
  const reopened = openBuildingRevisionResultAttachment(attachment)
  attachment.fill(0)
  expect((await reopened).attachmentBytes).toEqual(session.attachmentBytes)
})

test('explicit target load source rejects another valid result source and mismatched reopened assertions', async () => {
  const f = await buildingRevisionResultFixture()
  await expect(attachBuildingRevisionResult(f.draftBytes, f.resultBytes, pattern)).rejects.toThrow('explicitly selected')
  const session = await attachBuildingRevisionResult(f.draftBytes, f.resultBytes, combo)
  const root = parsed(session.attachmentBytes)
  root.selected_load_source = pattern
  await expect(openBuildingRevisionResultAttachment(bytes(root))).rejects.toThrow('explicitly selected')
})

test('selected load source is strict input and cannot import extra authority or invalid identities', async () => {
  const f = await buildingRevisionResultFixture()
  for (const selected of [undefined, null, {}, { kind: 'load_case', id: 'LC1' }, { kind: 'load_pattern', id: '' }, { ...combo, reviewed: true }]) {
    await expect(attachBuildingRevisionResult(f.draftBytes, f.resultBytes, selected as any)).rejects.toThrow('Selected load source')
  }
  const session = await attachBuildingRevisionResult(f.draftBytes, f.resultBytes, combo)
  const root = parsed(session.attachmentBytes)
  root.selected_load_source = { ...combo, trusted: true }
  await expect(openBuildingRevisionResultAttachment(bytes(root))).rejects.toThrow('Selected load source')
})

test('expected source is captured before asynchronous admission and cannot be retargeted by caller mutation', async () => {
  const f = await buildingRevisionResultFixture()
  const selected = { ...combo }
  const pending = attachBuildingRevisionResult(f.draftBytes, f.resultBytes, selected)
  selected.id = 'MUTATED'
  const session = await pending
  expect(session.lineage.selected_load_source).toEqual(combo)
  expect(parsed(session.attachmentBytes).selected_load_source).toEqual(combo)
})
