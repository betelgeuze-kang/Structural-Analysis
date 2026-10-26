import { expect, test } from '@playwright/test'
import { createHash } from 'node:crypto'
import {
  BUILDING_MEMBER_MAPPING_MAX_BYTES,
  createBuildingMemberMappingTemplate,
  openBuildingMemberReview,
} from '../../src/workbench-v2/model/buildingMemberReview'
import { parseSavedNativeFramePair } from '../../src/workbench-v2/model/nativeFrameProvider'
import { buildingFixtureBytes as bytes, buildingMemberFixture } from './buildingMemberFixture'

test('explicit one-to-many member mapping preserves native signs, both junction sides, row identities, and source hashes', async () => {
  const f = await buildingMemberFixture()
  const review = await openBuildingMemberReview(f.modelBytes, f.resultBytes, bytes(f.mapping))
  expect(review.rows).toHaveLength(4)
  expect(review.rows.map((row) => row.member_station)).toEqual([0, 0.5, 1, 0.5])
  expect(review.rows.map((row) => [row.model_element_row_index, row.member_index, row.recovery_row_index, row.result_member_row_index]))
    .toEqual([[1, 7, 1, 0], [1, 7, 1, 0], [0, 2, 0, 1], [0, 2, 0, 1]])
  expect(review.rows[2]).toMatchObject({ end: 'i', node_id: 'N3', orientation: 'j_to_i', force_n_nm: [-31, 32, -33, 34, -35, 36] })
  expect(review.rows.filter((row) => row.member_station === 0.5).map((row) => row.force_n_nm))
    .toEqual([[21, -22, 23, -24, 25, -26], [41, -42, 43, -44, 45, -46]])
  expect(review.rows.every((row) => row.review_status === 'NOT_REVIEWED')).toBe(true)
  expect(review.physical_members[0]).toMatchObject({ mapping_status: 'MAPPED', coverage_status: 'COMPLETE', coverage_gaps: [], review_status: 'NOT_REVIEWED' })
  expect(review.source).toMatchObject({ ...f.mapping.bindings, load_pattern_id: 'LC1', load_combination_id: null })
  expect(review.source.model_file_hash).toBe(`sha256:${createHash('sha256').update(f.modelBytes).digest('hex')}`)
  expect(review.rows[0].component_units).toEqual(['N', 'N', 'N', 'N*m', 'N*m', 'N*m'])
  expect(JSON.parse(JSON.stringify(review))).toEqual(review)
})

test('an empty template guesses no physical identities and retains every source endpoint as UNMAPPED', async () => {
  const f = await buildingMemberFixture()
  const template = await createBuildingMemberMappingTemplate(f.modelBytes, f.resultBytes)
  expect(template.storeys).toEqual([])
  expect(template.members).toEqual([])
  const review = await openBuildingMemberReview(f.modelBytes, f.resultBytes, bytes(template))
  expect(review.counts).toMatchObject({ physical_members: 0, mapped_elements: 0, unmapped_elements: 2, endpoint_rows: 4 })
  expect(review.rows.every((row) => row.mapping_status === 'UNMAPPED' && row.member_station === null)).toBe(true)
})

test('incomplete and empty physical members stay visible with exact gaps and NOT_REVIEWED', async () => {
  const f = await buildingMemberFixture()
  f.mapping.members[0].segments[0].member_start = 0.6
  f.mapping.members[0].segments[1].member_start = 0.1
  f.mapping.members[0].segments[0].member_end = 0.9
  f.mapping.members.push({ member_id: 'PHYSICAL_C12', label: 'Column C12', storey_id: 'STOREY_1', segments: [], review_locations: [] })
  const review = await openBuildingMemberReview(f.modelBytes, f.resultBytes, bytes(f.mapping))
  expect(review.physical_members[0]).toMatchObject({ mapping_status: 'PARTIAL', coverage_status: 'INCOMPLETE', coverage_gaps: [{ start: 0, end: 0.1 }, { start: 0.5, end: 0.6 }, { start: 0.9, end: 1 }], review_status: 'NOT_REVIEWED' })
  expect(review.physical_members[1]).toMatchObject({ mapping_status: 'UNMAPPED', coverage_status: 'UNMAPPED', coverage_gaps: [{ start: 0, end: 1 }] })
})

test('partial overall mapping and unselected endpoints preserve all source rows', async () => {
  const f = await buildingMemberFixture()
  f.mapping.members[0].segments.shift()
  f.mapping.members[0].review_locations = []
  const review = await openBuildingMemberReview(f.modelBytes, f.resultBytes, bytes(f.mapping))
  expect(review.counts).toMatchObject({ mapped_elements: 1, unmapped_elements: 1, review_locations: 0, endpoint_rows: 4 })
  expect(review.rows.slice(2).map((row) => row.mapping_status)).toEqual(['UNMAPPED', 'UNMAPPED'])
  expect(review.rows.every((row) => row.review_location_id === null && row.review_status === 'NOT_REVIEWED')).toBe(true)
})

test('explicit remesh bindings preserve physical member ID while old source bindings fail closed', async () => {
  const old = await buildingMemberFixture()
  const next = await buildingMemberFixture({ remesh: true })
  await expect(openBuildingMemberReview(next.modelBytes, next.resultBytes, bytes(old.mapping))).rejects.toThrow('binding differs')
  const review = await openBuildingMemberReview(next.modelBytes, next.resultBytes, bytes(next.mapping))
  expect(review.physical_members[0].member_id).toBe(old.mapping.members[0].member_id)
  expect(review.rows.map((row) => row.element_id)).toEqual(['REMESH_A', 'REMESH_A', 'REMESH_B', 'REMESH_B', 'REMESH_C', 'REMESH_C'])
  expect(review.physical_members[0]).toMatchObject({ coverage_status: 'COMPLETE', coverage_gaps: [] })
})

test('saved source load combination identity is retained without merging or component envelopes', async () => {
  const f = await buildingMemberFixture({ combination: true })
  const review = await openBuildingMemberReview(f.modelBytes, f.resultBytes, bytes(f.mapping))
  expect(review.source).toMatchObject({ load_pattern_id: null, load_combination_id: 'COMB1' })
  expect(review.rows[0].force_n_nm).toEqual([-11, 12, -13, 14, -15, 16])
})

for (const scenario of [
  { name: 'overlap', alter: (f: Awaited<ReturnType<typeof buildingMemberFixture>>) => { f.mapping.members[0].segments[0].member_start = 0.49 }, error: 'overlap' },
  { name: 'tiny positive overlap', alter: (f: Awaited<ReturnType<typeof buildingMemberFixture>>) => { f.mapping.members[0].segments[0].member_start = 0.5 - Number.EPSILON }, error: 'overlap' },
  { name: 'contiguous reversed connectivity', alter: (f: Awaited<ReturnType<typeof buildingMemberFixture>>) => { f.mapping.members[0].segments[0].orientation = 'i_to_j' }, error: 'not connected' },
  { name: 'duplicate element ownership', alter: (f: Awaited<ReturnType<typeof buildingMemberFixture>>) => { f.mapping.members.push({ ...structuredClone(f.mapping.members[0]), member_id: 'PHYSICAL_OTHER', segments: [{ ...f.mapping.members[0].segments[0], segment_id: 'OTHER_SEG' }], review_locations: [] }) }, error: 'Mapped element ID is duplicated' },
  { name: 'dangling storey', alter: (f: Awaited<ReturnType<typeof buildingMemberFixture>>) => { f.mapping.members[0].storey_id = 'MISSING' }, error: 'storey is not declared' },
  { name: 'dangling element', alter: (f: Awaited<ReturnType<typeof buildingMemberFixture>>) => { f.mapping.members[0].segments[0].element_id = 'MISSING' }, error: 'absent from the saved source' },
  { name: 'interior review location', alter: (f: Awaited<ReturnType<typeof buildingMemberFixture>>) => { Object.assign(f.mapping.members[0].review_locations[0], { end: 'interior' }) }, error: 'existing native i or j end' },
  { name: 'duplicate review endpoint', alter: (f: Awaited<ReturnType<typeof buildingMemberFixture>>) => { f.mapping.members[0].review_locations.push({ ...f.mapping.members[0].review_locations[0], location_id: 'OTHER_LOCATION' }) }, error: 'Review endpoint is duplicated' },
  { name: 'stale provenance', alter: (f: Awaited<ReturnType<typeof buildingMemberFixture>>) => { f.mapping.bindings.model_provenance_hash = `sha256:${'a'.repeat(64)}` }, error: 'binding differs' },
]) {
  test(`mapping rejects ${scenario.name}`, async () => {
    const f = await buildingMemberFixture()
    scenario.alter(f)
    await expect(openBuildingMemberReview(f.modelBytes, f.resultBytes, bytes(f.mapping))).rejects.toThrow(scenario.error)
  })
}

test('strict mapping admission rejects duplicate/unknown fields, versions, UTF-8, BOM, nonfinite stations and oversize', async () => {
  const f = await buildingMemberFixture()
  const valid = new TextDecoder().decode(bytes(f.mapping))
  for (const invalid of [
    valid.replace('"mapping_id":', '"mapping_id":"duplicate","mapping_id":'),
    valid.replace('"mapping_id":', '"unknown":true,"mapping_id":'),
    valid.replace('structural-building-member-mapping.v1', 'structural-building-member-mapping.v9'),
    valid.replace('"member_start":0.5', '"member_start":1e999'),
  ]) await expect(openBuildingMemberReview(f.modelBytes, f.resultBytes, new TextEncoder().encode(invalid))).rejects.toThrow()
  await expect(openBuildingMemberReview(f.modelBytes, f.resultBytes, new Uint8Array([0xff]))).rejects.toThrow()
  await expect(openBuildingMemberReview(f.modelBytes, f.resultBytes, new Uint8Array([0xef, 0xbb, 0xbf, ...bytes(f.mapping)]))).rejects.toThrow('BOM')
  await expect(openBuildingMemberReview(f.modelBytes, f.resultBytes, new Uint8Array(BUILDING_MEMBER_MAPPING_MAX_BYTES + 1))).rejects.toThrow('size')
})

test('local pair rejects tampered ResultIR, stale model content, invalid source UTF-8 and missing Web Crypto', async () => {
  const f = await buildingMemberFixture()
  const tampered = structuredClone(f.result)
  ;(tampered.members as Array<{ end_i_force_n_nm: number[] }>)[0].end_i_force_n_nm[0] = 999
  await expect(parseSavedNativeFramePair(f.modelBytes, bytes(tampered))).rejects.toThrow('ResultIR hash mismatch')
  const changed = structuredClone(f.model)
  changed.elements[0].index = 3
  await expect(parseSavedNativeFramePair(bytes(changed), f.resultBytes)).rejects.toThrow('content binding')
  await expect(parseSavedNativeFramePair(new Uint8Array([0xff]), f.resultBytes)).rejects.toThrow()
  const cryptoDescriptor = Object.getOwnPropertyDescriptor(globalThis, 'crypto')
  Object.defineProperty(globalThis, 'crypto', { configurable: true, value: undefined })
  try {
    await expect(parseSavedNativeFramePair(f.modelBytes, f.resultBytes)).rejects.toThrow('integrity is unavailable')
  } finally {
    if (cryptoDescriptor) Object.defineProperty(globalThis, 'crypto', cryptoDescriptor)
    else Reflect.deleteProperty(globalThis, 'crypto')
  }
})

test('raw file hashes distinguish noncanonical input bytes without changing admitted semantic identity', async () => {
  const f = await buildingMemberFixture()
  const prettyModel = new TextEncoder().encode(JSON.stringify(f.model, null, 2))
  const prettyResult = new TextEncoder().encode(JSON.stringify(f.result, null, 2))
  const compact = await openBuildingMemberReview(f.modelBytes, f.resultBytes, bytes(f.mapping))
  const pretty = await openBuildingMemberReview(prettyModel, prettyResult, bytes(f.mapping))
  expect(pretty.source.model_content_hash).toBe(compact.source.model_content_hash)
  expect(pretty.source.result_hash).toBe(compact.source.result_hash)
  expect(pretty.source.model_file_hash).not.toBe(compact.source.model_file_hash)
  expect(pretty.source.result_file_hash).not.toBe(compact.source.result_file_hash)
})

test('caller buffer reuse during asynchronous integrity checks cannot split decoded values from file hashes', async () => {
  for (const bufferSubclass of [false, true]) {
    const f = await buildingMemberFixture()
    const modelBytes = bufferSubclass ? Buffer.from(f.modelBytes) : f.modelBytes
    const resultBytes = bufferSubclass ? Buffer.from(f.resultBytes) : f.resultBytes
    const mappingBytes = bufferSubclass ? Buffer.from(bytes(f.mapping)) : bytes(f.mapping)
    const modelHash = `sha256:${createHash('sha256').update(modelBytes).digest('hex')}`
    const resultHash = `sha256:${createHash('sha256').update(resultBytes).digest('hex')}`
    const mappingHash = `sha256:${createHash('sha256').update(mappingBytes).digest('hex')}`
    const pending = openBuildingMemberReview(modelBytes, resultBytes, mappingBytes)
    modelBytes.fill(0)
    resultBytes.fill(0)
    mappingBytes.fill(0)
    const review = await pending
    expect(review.source).toMatchObject({ model_file_hash: modelHash, result_file_hash: resultHash, mapping_file_hash: mappingHash })
    expect(review.physical_members[0].member_id).toBe('PHYSICAL_B7')
  }
})
