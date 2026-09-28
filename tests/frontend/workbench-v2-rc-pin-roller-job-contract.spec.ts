import { expect, test } from '@playwright/test'
import { createHash } from 'node:crypto'
import { readFileSync } from 'node:fs'
import { fields, rawValues, validateRcAcceptedHistory, validateRcJobArtifacts } from '../../src/workbench-v2/model/rcJobSchema'

const directory = 'tests/frontend/fixtures/rc-pin-roller-durable-job/'
function fixture() {
  return {
    job: JSON.parse(readFileSync(`${directory}job.json`, 'utf8')),
    artifacts: Object.fromEntries(['request', 'checkpoint', 'result', 'evidence'].map(role =>
      [role, new Uint8Array(readFileSync(`${directory}${role}.json`))])),
  }
}
const digest = (raw: string | Uint8Array) => `sha256:${createHash('sha256').update(raw).digest('hex')}`
function at(raw: string, path: (string | number)[]): string {
  if (!path.length) return raw
  const [key, ...rest] = path
  return at(typeof key === 'number' ? rawValues(raw)[key] : fields(raw).get(key)!.value, rest)
}
// Preserve producer numeric tokens (including 1.0) when testing rehashed forgeries.
function replace(raw: string, path: (string | number)[], value: string): string {
  if (!path.length) return value
  const [key, ...rest] = path
  if (typeof key === 'number') {
    const rows = rawValues(raw); rows[key] = replace(rows[key], rest, value); return `[${rows.join(',')}]`
  }
  const members = fields(raw)
  members.get(key)!.member = `${JSON.stringify(key)}:${replace(members.get(key)!.value, rest, value)}`
  return `{${[...members.values()].map(row => row.member).join(',')}}`
}
function rehash(raw: string, path: (string | number)[], key: string): string {
  const members = fields(at(raw, path)); members.delete(key)
  return replace(raw, [...path, key], JSON.stringify(digest(`{${[...members.values()].map(row => row.member).join(',')}}`)))
}
function bind(source: ReturnType<typeof fixture>, raw: string): void {
  raw = rehash(raw, [], 'result_hash')
  source.artifacts.result = new TextEncoder().encode(raw)
  source.job.result.content_hash = digest(raw)
  source.job.result.byte_length = source.artifacts.result.byteLength
  const evidence = JSON.parse(new TextDecoder().decode(source.artifacts.evidence))
  evidence.result_artifact_hash = source.job.result.content_hash
  const result = JSON.parse(raw)
  evidence.validation_report.result_hash = result.result_hash
  evidence.validation_report.receipt_hashes = result.receipts.map((receipt: any) => receipt.receipt_hash)
  source.artifacts.evidence = new TextEncoder().encode(JSON.stringify(evidence))
  source.job.evidence.content_hash = digest(source.artifacts.evidence)
  source.job.evidence.byte_length = source.artifacts.evidence.byteLength
}

test('v4 saved pin/roller job reviews both restart-bound targets without promoting authority', async () => {
  const source = fixture()
  const review = await validateRcJobArtifacts(source.job, source.artifacts)
  expect(review.summary).toMatchObject({
    pinRoller: { pin: 'N2', roller: 'N6' }, hasPreload: false, targets: [-1e-6, -2e-6],
  })
  expect(review.history.map(row => row.support_reactions.map((r: any) => [r.node_id, r.dof]))).toEqual([
    [['N2', 'UX'], ['N2', 'UY'], ['N6', 'UY']],
    [['N2', 'UX'], ['N2', 'UY'], ['N6', 'UY']],
  ])
  const result = JSON.parse(new TextDecoder().decode(source.artifacts.result))
  const checkpointed = JSON.parse(readFileSync(`${directory}checkpointed-job.json`, 'utf8'))
  expect(checkpointed).toMatchObject({ status: 'checkpointed', can_resume: true })
  expect(checkpointed.checkpoint.content_hash).toBe(source.job.checkpoint.content_hash)
  expect(result.receipts[1].api_request.restart_input_sha256).toBe(result.receipts[0].checkpoint_sha256)
  expect(source.job.checkpoint.content_hash).toBe(digest(source.artifacts.checkpoint))
})

test('v4 review requires explicit true opt-in in the saved request', async () => {
  const source = fixture()
  const request = JSON.parse(new TextDecoder().decode(source.artifacts.request))
  request.config.experimental_pin_roller_beam = false
  source.artifacts.request = new TextEncoder().encode(JSON.stringify(request))
  source.job.request.content_hash = digest(source.artifacts.request)
  source.job.request.byte_length = source.artifacts.request.byteLength
  await expect(validateRcJobArtifacts(source.job, source.artifacts)).rejects.toThrow('rc_review_pin_roller_opt_in_invalid')
})

test('v4 review rejects a forged compiler profile with refreshed outer hashes', async () => {
  const source = fixture()
  let raw = new TextDecoder().decode(source.artifacts.result)
  raw = replace(raw, ['api_result', 'model', 'compiler_profile'], JSON.stringify('planar_serial_cantilever_explicit_rectangular_rc.v1'))
  raw = rehash(raw, ['api_result'], 'result_hash')
  bind(source, raw)
  await expect(validateRcJobArtifacts(source.job, source.artifacts)).rejects.toThrow('rc_review_model_binding_invalid')
})

test('v4 review rejects a forged opt-in in an earlier restart receipt', async () => {
  const source = fixture()
  let raw = new TextDecoder().decode(source.artifacts.result)
  raw = replace(raw, ['receipts', 0, 'api_request', 'experimental_pin_roller_beam'], 'false')
  raw = rehash(raw, ['receipts', 0], 'receipt_hash')
  bind(source, raw)
  await expect(validateRcJobArtifacts(source.job, source.artifacts)).rejects.toThrow('rc_review_receipt_binding_invalid')
})

test('v4 history rejects altered support roles, reaction rows, and restrained displacement', () => {
  const source = fixture()
  const request = JSON.parse(new TextDecoder().decode(source.artifacts.request))
  const result = JSON.parse(new TextDecoder().decode(source.artifacts.result))
  const native = JSON.parse(Buffer.from(result.terminal_checkpoint_artifact_base64, 'base64').toString())
  const check = (api: any, model: any) => validateRcAcceptedHistory(api, native, model, request.config)
  expect(check(result.api_result, request.model)).toHaveLength(2)
  const wrongModel = structuredClone(request.model)
  wrongModel.supports[1].dofs = ['UX', 'UY']
  expect(() => check(result.api_result, wrongModel)).toThrow('rc_review_pin_roller_support_invalid')
  for (const mutate of [
    (api: any) => api.response_history[0].support_reactions.reverse(),
    (api: any) => api.response_history[0].support_reactions.pop(),
    (api: any) => api.response_history[0].support_reactions.push(api.response_history[0].support_reactions[0]),
  ]) {
    const api = structuredClone(result.api_result); mutate(api)
    expect(() => check(api, request.model)).toThrow('rc_review_pin_roller_reaction_invalid')
  }
  const displaced = structuredClone(result.api_result)
  displaced.response_history[0].node_displacements.find((node: any) => node.node_id === 'N6').UY_m = 1e-9
  expect(() => check(displaced, request.model)).toThrow('rc_review_pin_roller_restrained_displacement_invalid')
})
