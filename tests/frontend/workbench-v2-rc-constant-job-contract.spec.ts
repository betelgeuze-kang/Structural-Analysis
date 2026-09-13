import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { fields, rawValues, validateRcJobArtifacts } from '../../src/workbench-v2/model/rcJobSchema'

const directory = 'tests/frontend/fixtures/rc-fiber-constant-durable-job/'
function fixture() {
  return {
    job: JSON.parse(readFileSync(`${directory}job.json`, 'utf8')),
    artifacts: Object.fromEntries(['request', 'checkpoint', 'result', 'evidence'].map((role) => [
      role, new Uint8Array(readFileSync(`${directory}${role}.json`)),
    ])),
  }
}
test('constant RC review includes preload, all original material states and full costs', async () => {
  const { job, artifacts } = fixture()
  const review = await validateRcJobArtifacts(job, artifacts)
  expect(review.summary).toMatchObject({ hasPreload: true, reservedInvocations: 6, confirmedInvocations: 6,
    knownCoreCalls: 18, knownNewtonIterations: 36, unknownWork: false })
  expect(review.summary.targets).toEqual([-1e-5, -2e-5, 1e-5])
  expect(review.summary.constantLoads).toEqual([{ node_id: 'N2', FX_kN: -600, FY_kN: 0, MZ_kNm: 0 }])
  expect(review.history.map((row) => row.epoch)).toEqual([1, 2, 3, 4])
  expect(review.history[0].load_factor).toBe(0)
  expect(review.history[0].support_reactions[0].value_si).toBeCloseTo(600000, 6)
  const original = JSON.parse(new TextDecoder().decode(artifacts.result))
  expect(review.history).toEqual([original.api_result.preload_response, ...original.api_result.response_history])
  expect(Buffer.from(review.terminalBytes)).toEqual(Buffer.from(original.terminal_checkpoint_artifact_base64, 'base64'))
})
function digest(raw: string | Uint8Array): string { return `sha256:${createHash('sha256').update(raw).digest('hex')}` }
function get(raw: string, path: (string | number)[]): string {
  if (!path.length) return raw
  const [key, ...rest] = path
  return get(typeof key === 'number' ? rawValues(raw)[key] : fields(raw).get(key)!.value, rest)
}
// Preserve original Python numeric spellings while changing one declared field.
function replace(raw: string, path: (string | number)[], value: string): string {
  if (!path.length) return value
  const [key, ...rest] = path
  if (typeof key === 'number') {
    const rows = rawValues(raw); rows[key] = replace(rows[key], rest, value); return `[${rows.join(',')}]`
  }
  const members = fields(raw)
  members.get(key)!.member = `${JSON.stringify(key)}:${replace(members.get(key)!.value, rest, value)}`
  return `{${[...members.values()].map((row) => row.member).join(',')}}`
}
function rehash(raw: string, path: (string | number)[], key: string): string {
  const members = fields(get(raw, path)); members.delete(key)
  const hash = digest(`{${[...members.values()].map((row) => row.member).join(',')}}`)
  return replace(raw, [...path, key], JSON.stringify(hash))
}
function bind(source: ReturnType<typeof fixture>, raw: string): void {
  raw = rehash(raw, ['api_result', 'path'], 'path_hash')
  raw = rehash(raw, ['api_result'], 'result_hash')
  const parsed = JSON.parse(raw), tail = parsed.receipts.length - 1
  const updates: [(string | number)[], unknown][] = [
    [['receipts', tail, 'path_hash'], parsed.api_result.path.path_hash],
    [['receipts', tail, 'result_hash'], parsed.api_result.result_hash],
    [['receipts', tail, 'result_artifact_sha256'], digest(get(raw, ['api_result']))],
    [['receipts', tail, 'validation_report', 'verified_result_hash'], parsed.api_result.result_hash],
  ]
  for (const [path, value] of updates) raw = replace(raw, path, JSON.stringify(value))
  for (let i = 0; i <= tail; i += 1) raw = rehash(raw, ['receipts', i], 'receipt_hash')
  raw = rehash(raw, [], 'result_hash')
  source.artifacts.result = new TextEncoder().encode(raw)
  source.job.result.content_hash = digest(raw); source.job.result.byte_length = source.artifacts.result.byteLength
  const evidence = JSON.parse(new TextDecoder().decode(source.artifacts.evidence)), result = JSON.parse(raw)
  evidence.result_artifact_hash = source.job.result.content_hash
  evidence.validation_report.result_hash = result.result_hash
  evidence.validation_report.receipt_hashes = result.receipts.map((r: any) => r.receipt_hash)
  source.artifacts.evidence = new TextEncoder().encode(JSON.stringify(evidence))
  source.job.evidence.content_hash = digest(source.artifacts.evidence); source.job.evidence.byte_length = source.artifacts.evidence.byteLength
}
for (const [name, path, value, error] of [
  ['preload epoch', ['api_result', 'preload_response', 'epoch'], 0, 'preload_response_invalid'],
  ['preload material ancestry', ['api_result', 'preload_response', 'parent_checkpoint_hash'], `sha256:${'0'.repeat(64)}`, 'preload_response_invalid'],
  ['lateral epoch', ['api_result', 'response_history', 0, 'epoch'], 1, 'epoch_binding_invalid'],
  ['preload work', ['api_result', 'path', 'metrics', 'preload_work', 'known_linear_solve_count'], 99, 'preload_work_invalid'],
  ['preload source', ['api_result', 'path', 'preload_attempts', 0, 'step', 'committed'], false, 'preload_source_invalid'],
  ['receipt preload', ['receipts', 0, 'preload_step_hash'], `sha256:${'0'.repeat(64)}`, 'receipt_preload_invalid'],
] as [string, (string | number)[], unknown, string][]) {
  test(`constant RC rejects rehashed ${name}`, async () => {
    const source = fixture()
    bind(source, replace(new TextDecoder().decode(source.artifacts.result), path, JSON.stringify(value)))
    await expect(validateRcJobArtifacts(source.job, source.artifacts)).rejects.toThrow(`rc_review_${error}`)
  })
}
