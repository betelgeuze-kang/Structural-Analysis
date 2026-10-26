import { expect, test } from '@playwright/test'
import { createHash } from 'node:crypto'
import {
  BUILDING_LOAD_REVISION_MAX_BYTES, prepareBuildingLoadRevision, openBuildingLoadRevisionDraft,
  serializeBuildingLoadRevisionDraft, getBuildingLoadRevisionEditorView, compileBuildingLoadRevision,
  createBuildingRevisionNodalLoad, type BuildingLoadRevisionDraft,
} from '../../src/workbench-v2/model/buildingLoadRevision'
import { canonicalNativeJson, nativeFrameModelIdentity } from '../../src/workbench-v2/model/nativeFrameProvider'
import { openBuildingMemberReview } from '../../src/workbench-v2/model/buildingMemberReview'
import { buildingFixtureBytes as bytes, buildingMemberFixture } from './buildingMemberFixture'
import { fixtureHash } from './nativeFrameFixture'

const digest = (body: Uint8Array) => `sha256:${createHash('sha256').update(body).digest('hex')}`
const components = { FX: 0, FY: -20, FZ: 30, MX: -40, MY: 50, MZ: -60 }
async function prepared() {
  const fixture = await buildingMemberFixture({ combination: true })
  const draft = await prepareBuildingLoadRevision(fixture.modelBytes, fixture.resultBytes, bytes(fixture.mapping), 'revision.first')
  const view = await getBuildingLoadRevisionEditorView(draft)
  draft.patches = [{ pattern_id: 'LC1', self_weight: [0, 0, -1], nodal_loads: structuredClone(view.patterns[0].nodal_loads) }]
  return { fixture, draft, view }
}
function putArtifact(draft: BuildingLoadRevisionDraft, key: 'model_ir' | 'result_ir' | 'mapping', value: unknown) {
  const body = bytes(value)
  draft.parent[key] = { body_base64: Buffer.from(body).toString('base64'), byte_length: body.length, sha256: digest(body) }
}
async function rebound(fixture: Awaited<ReturnType<typeof buildingMemberFixture>>) {
  const identity = await nativeFrameModelIdentity(fixture.model)
  Object.assign(fixture.result.bindings as Record<string, unknown>, identity)
  const resultBody = { ...fixture.result }; delete resultBody.result_hash
  fixture.result.result_hash = fixtureHash(resultBody)
  Object.assign(fixture.mapping.bindings, identity, { result_hash: fixture.result.result_hash })
  fixture.modelBytes = bytes(fixture.model); fixture.resultBytes = bytes(fixture.result)
  return prepareBuildingLoadRevision(fixture.modelBytes, fixture.resultBytes, bytes(fixture.mapping), 'revision.first')
}

test('load revision changes only declared fields and generated provenance while preserving complete physical inventory', async () => {
  const { fixture, draft, view } = await prepared()
  draft.patches[0].nodal_loads[0].components_si = { ...components }
  const compiled = await compileBuildingLoadRevision(draft)
  const expected = structuredClone(fixture.model)
  expected.load_patterns[0].self_weight = [0, 0, -1]
  expected.load_patterns[0].nodal_loads[0].components_si = components
  expected.provenance = compiled.modelIr.provenance
  expect(compiled.modelIr).toEqual(expected)
  expect(compiled.modelIr.load_combinations).toEqual(fixture.model.load_combinations)
  expect((compiled.modelIr.load_patterns as Array<Record<string, unknown>>)[0].uniform_member_loads).toEqual(fixture.model.load_patterns[0].uniform_member_loads)
  expect(compiled.revisionRecord.unchanged_inventory).toEqual({ storeys: fixture.mapping.storeys, members: fixture.mapping.members })
  expect(compiled.revisionRecord.target).toMatchObject({ model_id: fixture.model.model_id, analysis_status: 'NOT_RUN', review_status: 'NOT_REVIEWED', result: null })
  expect(compiled.revisionRecord.target).not.toHaveProperty('result_hash')
  expect(compiled.revisionRecord.parent).toMatchObject(fixture.mapping.bindings)
  expect(compiled.revisionRecord.source_fingerprint).toBe(view.sourceFingerprint)
  expect(compiled.targetIdentity.model_semantic_hash).not.toBe(view.parentIdentity.model_semantic_hash)
  expect(compiled.revisionRecord.target.model_file_hash).toBe(digest(compiled.modelBytes))
  expect(compiled.modelIr.provenance).toMatchObject({ source_format: 'generated', source_sha256: digest(compiled.recipeBytes), source_units: { length: 'm', force: 'N', mass: 'kg', time: 's', rotation: 'rad' }, unit_scales_to_si: { length_to_m: 1, force_to_n: 1, mass_to_kg: 1, time_to_s: 1, rotation_to_rad: 1 }, extensions: {} })
  expect(JSON.parse(Buffer.from(draft.parent.model_ir.body_base64, 'base64').toString()).provenance).toEqual(fixture.model.provenance)
  await expect(openBuildingMemberReview(compiled.modelBytes, fixture.resultBytes, bytes(fixture.mapping))).rejects.toThrow('content binding')
})

test('reopen verifies raw bytes and deterministically derives identical target, recipe and record', async () => {
  const { fixture, draft } = await prepared()
  const serialized = serializeBuildingLoadRevisionDraft(draft)
  const restored = await openBuildingLoadRevisionDraft(serialized)
  const [first, next] = await Promise.all([compileBuildingLoadRevision(draft), compileBuildingLoadRevision(restored)])
  expect(next).toEqual(first)
  expect(Buffer.from(restored.parent.model_ir.body_base64, 'base64')).toEqual(Buffer.from(fixture.modelBytes))
  expect(Buffer.from(restored.parent.result_ir.body_base64, 'base64')).toEqual(Buffer.from(fixture.resultBytes))
  expect(Buffer.from(restored.parent.mapping.body_base64, 'base64')).toEqual(Buffer.from(bytes(fixture.mapping)))
  const recipe = JSON.parse(new TextDecoder().decode(next.recipeBytes))
  expect(recipe.parent).toMatchObject({ ...fixture.mapping.bindings, model_file_hash: digest(fixture.modelBytes), result_file_hash: digest(fixture.resultBytes), mapping_file_hash: digest(bytes(fixture.mapping)) })
  expect(canonicalNativeJson(recipe)).not.toContain(next.targetIdentity.model_content_hash)
})

test('distinct loads at the same node remain separate signed rows; zero components stay explicit', async () => {
  const { draft } = await prepared()
  draft.patches[0].nodal_loads.push(createBuildingRevisionNodalLoad(draft.revision_id, 'added.load', 9, 'N2', components))
  const compiled = await compileBuildingLoadRevision(draft)
  const pattern = (compiled.modelIr.load_patterns as Array<{ nodal_loads: unknown[] }>)[0]
  expect(pattern.nodal_loads).toHaveLength(draft.patches[0].nodal_loads.length)
  expect(pattern.nodal_loads.at(-1)).toEqual({ id: 'added.load', index: 9, node_id: 'N2', components_si: components, source_id: 'generated:building-load-revision:revision.first:added.load', extensions: {} })
  expect((pattern.nodal_loads.at(-1) as { components_si: typeof components }).components_si.FX).toBe(0)
})

test('surviving row metadata and non-dense indices are preserved after deleting another row', async () => {
  const { fixture } = await prepared()
  fixture.model.load_patterns[0].nodal_loads.push({ ...structuredClone(fixture.model.load_patterns[0].nodal_loads[0]), id: 'SURVIVOR', index: 7, source_id: 'original:seven', extensions: { 'test:retained': true } })
  const draft = await rebound(fixture)
  const survivor = structuredClone(fixture.model.load_patterns[0].nodal_loads[1])
  draft.patches = [{ pattern_id: 'LC1', self_weight: [0, 0, 0], nodal_loads: [survivor] }]
  const compiled = await compileBuildingLoadRevision(draft)
  expect((compiled.modelIr.load_patterns as Array<{ nodal_loads: unknown[] }>)[0].nodal_loads).toEqual([survivor])
})

test('empty nodal replacement removes nodal loads while retained uniform loads remain exact', async () => {
  const { fixture, draft } = await prepared()
  draft.patches[0].nodal_loads = []; draft.patches[0].self_weight = [0, 0, 0]
  const compiled = await compileBuildingLoadRevision(draft)
  const pattern = (compiled.modelIr.load_patterns as Array<Record<string, unknown>>)[0]
  expect(pattern.nodal_loads).toEqual([])
  expect(pattern.uniform_member_loads).toEqual(fixture.model.load_patterns[0].uniform_member_loads)
})

for (const scenario of [
  { name: 'unknown pattern', edit: (d: BuildingLoadRevisionDraft) => { d.patches[0].pattern_id = 'MISSING' } },
  { name: 'duplicate patch', edit: (d: BuildingLoadRevisionDraft) => { d.patches.push(structuredClone(d.patches[0])) } },
  { name: 'missing component', edit: (d: BuildingLoadRevisionDraft) => { delete (d.patches[0].nodal_loads[0].components_si as Partial<typeof components>).FX } },
  { name: 'nonfinite component', edit: (d: BuildingLoadRevisionDraft) => { d.patches[0].nodal_loads[0].components_si.FX = Infinity } },
  { name: 'dangling node', edit: (d: BuildingLoadRevisionDraft) => { d.patches[0].nodal_loads[0].node_id = 'MISSING' } },
  { name: 'duplicate load ID', edit: (d: BuildingLoadRevisionDraft) => { d.patches[0].nodal_loads.push(structuredClone(d.patches[0].nodal_loads[0])) } },
  { name: 'surviving row index rewrite', edit: (d: BuildingLoadRevisionDraft) => { d.patches[0].nodal_loads[0].index = 11 } },
  { name: 'surviving source rewrite', edit: (d: BuildingLoadRevisionDraft) => { d.patches[0].nodal_loads[0].source_id = 'invented' } },
  { name: 'surviving extensions rewrite', edit: (d: BuildingLoadRevisionDraft) => { d.patches[0].nodal_loads[0].extensions = { invented: true } } },
  { name: 'new row missing generated metadata', edit: (d: BuildingLoadRevisionDraft) => { d.patches[0].nodal_loads[0].id = 'invented' } },
  { name: 'new row reuses parent index', edit: (d: BuildingLoadRevisionDraft) => { d.patches[0].nodal_loads = [createBuildingRevisionNodalLoad(d.revision_id, 'invented', d.patches[0].nodal_loads[0].index, 'N2', components)] } },
  { name: 'load row count', edit: (d: BuildingLoadRevisionDraft) => { d.patches[0].nodal_loads = Array.from({ length: 4097 }, () => structuredClone(d.patches[0].nodal_loads[0])) } },
]) test(`revision rejects ${scenario.name}`, async () => {
  const { draft } = await prepared(); scenario.edit(draft)
  await expect(compileBuildingLoadRevision(draft)).rejects.toThrow()
})

test('draft and imported claims reject unknown fields, duplicate keys, malformed UTF-8/BOM, hash/length/base64/version tamper and size overflow', async () => {
  const { draft } = await prepared()
  const text = new TextDecoder().decode(serializeBuildingLoadRevisionDraft(draft))
  for (const invalid of [
    text.replace('"revision_id":', '"revision_id":"duplicate","revision_id":'),
    text.replace('"revision_id":', '"target":{"analysis_status":"SUCCEEDED"},"revision_id":'),
    text.replace('structural-building-load-revision-draft.v1', 'structural-building-load-revision-draft.v9'),
  ]) await expect(openBuildingLoadRevisionDraft(new TextEncoder().encode(invalid))).rejects.toThrow()
  for (const key of ['model_ir', 'result_ir', 'mapping'] as const) {
    const changed = structuredClone(draft); changed.parent[key].sha256 = `sha256:${'1'.repeat(64)}`
    await expect(openBuildingLoadRevisionDraft(bytes(changed))).rejects.toThrow('hash mismatch')
    changed.parent[key].byte_length += 1
    await expect(openBuildingLoadRevisionDraft(bytes(changed))).rejects.toThrow()
  }
  const invalidBase64 = structuredClone(draft); invalidBase64.parent.mapping.body_base64 = '!'.repeat(invalidBase64.parent.mapping.body_base64.length)
  await expect(openBuildingLoadRevisionDraft(bytes(invalidBase64))).rejects.toThrow('base64')
  await expect(openBuildingLoadRevisionDraft(new Uint8Array([0xff]))).rejects.toThrow()
  await expect(openBuildingLoadRevisionDraft(new Uint8Array([0xef, 0xbb, 0xbf, ...serializeBuildingLoadRevisionDraft(draft)]))).rejects.toThrow('BOM')
  await expect(openBuildingLoadRevisionDraft(new Uint8Array(BUILDING_LOAD_REVISION_MAX_BYTES + 1))).rejects.toThrow('size')
  const oversizeArtifact = structuredClone(draft); oversizeArtifact.parent.model_ir.byte_length = 2 * 1024 * 1024 + 1
  await expect(openBuildingLoadRevisionDraft(bytes(oversizeArtifact))).rejects.toThrow('size')
})

test('rewriting a parent artifact and its raw hash cannot bypass the saved source binding', async () => {
  const { fixture, draft } = await prepared()
  fixture.model.load_patterns[0].self_weight = [1, 0, 0]
  putArtifact(draft, 'model_ir', fixture.model)
  await expect(openBuildingLoadRevisionDraft(bytes(draft))).rejects.toThrow('content binding')
})

for (const kind of ['dangling uniform member', 'dangling combination', 'combination cycle', 'combination overflow', 'expanded terms'] as const) test(`preserved load structure rejects ${kind}`, async () => {
  const { fixture } = await prepared()
  if (kind === 'dangling uniform member') fixture.model.load_patterns[0].uniform_member_loads[0].member_id = 'MISSING'
  if (kind === 'dangling combination') fixture.model.load_combinations[0].terms[0].ref_id = 'MISSING'
  if (kind === 'combination cycle') fixture.model.load_combinations[0].terms = [{ ref_kind: 'load_combination', ref_id: 'COMB1', factor: 1 }]
  if (kind === 'combination overflow') fixture.model.load_combinations[0].terms = [{ ref_kind: 'load_pattern', ref_id: 'LC1', factor: 1e308 }, { ref_kind: 'load_pattern', ref_id: 'LC1', factor: 1e308 }]
  if (kind === 'expanded terms') fixture.model.load_combinations[0].terms = Array.from({ length: 4097 }, () => ({ ref_kind: 'load_pattern', ref_id: 'LC1', factor: 1 }))
  const draft = await rebound(fixture)
  await expect(compileBuildingLoadRevision(draft)).rejects.toThrow()
})

test('source bytes and draft objects are captured before asynchronous integrity work', async () => {
  const fixture = await buildingMemberFixture()
  const model = Buffer.from(fixture.modelBytes), result = Buffer.from(fixture.resultBytes), mapping = Buffer.from(bytes(fixture.mapping))
  const originalModel = Buffer.from(model), originalResult = Buffer.from(result), originalMapping = Buffer.from(mapping)
  const pending = prepareBuildingLoadRevision(model, result, mapping, 'revision.snapshot')
  model.fill(0); result.fill(0); mapping.fill(0)
  const draft = await pending
  expect(Buffer.from(draft.parent.model_ir.body_base64, 'base64')).toEqual(originalModel)
  expect(Buffer.from(draft.parent.result_ir.body_base64, 'base64')).toEqual(originalResult)
  expect(Buffer.from(draft.parent.mapping.body_base64, 'base64')).toEqual(originalMapping)
  const compiledPending = compileBuildingLoadRevision(draft)
  draft.revision_id = 'revision.later'; draft.parent.model_ir.sha256 = `sha256:${'f'.repeat(64)}`
  expect((await compiledPending).revisionRecord.revision_id).toBe('revision.snapshot')
})

test('editor views are independent snapshots and source fingerprints bind exact raw parent bytes', async () => {
  const { fixture, draft, view } = await prepared()
  view.patterns[0].nodal_loads[0].components_si.FX = 999
  view.nodes[0].id = 'changed'
  const next = await getBuildingLoadRevisionEditorView(draft)
  expect(next.patterns[0].nodal_loads[0].components_si.FX).not.toBe(999)
  expect(next.nodes[0].id).toBe('N1')
  const prettyModel = new TextEncoder().encode(JSON.stringify(fixture.model, null, 2))
  const pretty = await prepareBuildingLoadRevision(prettyModel, fixture.resultBytes, bytes(fixture.mapping), draft.revision_id)
  const prettyView = await getBuildingLoadRevisionEditorView(pretty)
  expect(prettyView.parentIdentity).toEqual(next.parentIdentity)
  expect(prettyView.sourceFingerprint).not.toBe(next.sourceFingerprint)
})

test('an entirely zero edit stays reopenable for repair but cannot export a target model', async () => {
  const { fixture } = await prepared()
  delete fixture.model.load_patterns[0].uniform_member_loads
  const draft = await rebound(fixture)
  draft.patches = [{ pattern_id: 'LC1', self_weight: [0, 0, 0], nodal_loads: [] }]
  const reopened = await openBuildingLoadRevisionDraft(serializeBuildingLoadRevisionDraft(draft))
  expect(reopened.patches).toEqual(draft.patches)
  await expect(compileBuildingLoadRevision(reopened)).rejects.toThrow('nonzero')
})

test('global nested load identities follow ModelIR semantics while different IDs at one node remain allowed', async () => {
  const { fixture } = await prepared()
  fixture.model.load_patterns.push({ ...structuredClone(fixture.model.load_patterns[0]), id: 'OTHER', index: 1, uniform_member_loads: [] })
  const draft = await rebound(fixture)
  await expect(compileBuildingLoadRevision(draft)).rejects.toThrow('Nested load ID is duplicated')
})

test('finite individual nodal values cannot overflow their accumulated node component', async () => {
  const { draft } = await prepared()
  draft.patches[0].nodal_loads[0].components_si.FX = 1e308
  draft.patches[0].nodal_loads.push(createBuildingRevisionNodalLoad(draft.revision_id, 'second.huge', 12, draft.patches[0].nodal_loads[0].node_id, { FX: 1e308, FY: 0, FZ: 0, MX: 0, MY: 0, MZ: 0 }))
  await expect(compileBuildingLoadRevision(draft)).rejects.toThrow('Accumulated nodal component')
})

test('near-limit parent artifact reopens without recursive base64-regex failure and larger bytes fail admission', async () => {
  const fixture = await buildingMemberFixture()
  const maximum = 2 * 1024 * 1024
  const padded = new Uint8Array(maximum)
  padded.fill(32); padded.set(fixture.modelBytes)
  const draft = await prepareBuildingLoadRevision(padded, fixture.resultBytes, bytes(fixture.mapping), 'revision.large.artifact')
  expect(draft.parent.model_ir.byte_length).toBe(maximum)
  expect((await openBuildingLoadRevisionDraft(serializeBuildingLoadRevisionDraft(draft))).parent.model_ir).toEqual(draft.parent.model_ir)
  await expect(prepareBuildingLoadRevision(new Uint8Array(maximum + 1), fixture.resultBytes, bytes(fixture.mapping), 'revision.too.large')).rejects.toThrow('size')
})
