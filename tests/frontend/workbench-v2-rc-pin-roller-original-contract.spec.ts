import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { gunzipSync } from 'node:zlib'
import { reviewRcPinRollerOriginals, type RcPinRollerOriginals } from '../../src/workbench-v2/model/rcPinRollerOriginal'

const directory = 'tests/frontend/fixtures/rc-pin-roller-original/'
function originals(): RcPinRollerOriginals {
  return {
    model: readFileSync(`${directory}model.json`), request: readFileSync(`${directory}request.json`),
    result: gunzipSync(readFileSync(`${directory}result.json.gz`)), checkpoint: readFileSync(`${directory}checkpoint.json`),
    verification: readFileSync(`${directory}verify-report.json`),
  }
}
function preloadOriginals(): RcPinRollerOriginals {
  const prefix = 'tests/frontend/fixtures/rc-pin-roller-preload/'
  return {
    model: readFileSync(`${prefix}model.json`), request: readFileSync(`${prefix}request.json`),
    result: gunzipSync(readFileSync(`${prefix}result.json.gz`)), checkpoint: readFileSync(`${prefix}checkpoint.json`),
    verification: readFileSync(`${prefix}verify-report.json`),
  }
}
function changed(role: keyof RcPinRollerOriginals, edit: (doc: any) => void): RcPinRollerOriginals {
  const files = originals(), doc = JSON.parse(Buffer.from(files[role]).toString())
  edit(doc); files[role] = Buffer.from(JSON.stringify(doc))
  return files
}
test('v4 original reviewer checks byte-bound CLI verify receipt and pin/roller rows', async () => {
  const review = await reviewRcPinRollerOriginals(originals())
  expect(review.status).toBe('ready')
  expect([review.pin, review.roller]).toEqual(['N2', 'N6'])
  expect(review.history).toHaveLength(1)
  expect(review.verificationWork.attempted_step_count).toBe(1)
})
test('v4 original reviewer rejects run report and changed originals', async () => {
  const files = originals()
  files.verification = readFileSync(`${directory}run-report.json`)
  await expect(reviewRcPinRollerOriginals(files)).rejects.toThrow()
  const tampered = originals()
  tampered.model = Buffer.concat([tampered.model, Buffer.from(' ')])
  await expect(reviewRcPinRollerOriginals(tampered)).rejects.toThrow()
  await expect(reviewRcPinRollerOriginals(changed('request', request => { request.experimental_pin_roller_beam = false }))).rejects.toThrow()
})
test('v4 original reviewer requires full typed first-run request and no restart input', async () => {
  await expect(reviewRcPinRollerOriginals(changed('request', request => { delete request.solver_config })))
    .rejects.toThrow('rc_pin_roller_full_typed_v4_request_required')
  const files = originals()
  files.verification = readFileSync(`${directory}verify-report-extra-restart.json`)
  await expect(reviewRcPinRollerOriginals(files)).rejects.toThrow('rc_pin_roller_verify_report_invalid')
})
test('v4 original reviewer checks the accepted preload reaction row too', async () => {
  const review = await reviewRcPinRollerOriginals(preloadOriginals())
  expect(review.preload?.support_reactions.map((row: any) => [row.node_id, row.dof])).toEqual([
    ['N2', 'UX'], ['N2', 'UY'], ['N6', 'UY'],
  ])
  expect(review.history).toHaveLength(1)
  const malformed = preloadOriginals(), prefix = 'tests/frontend/fixtures/rc-pin-roller-preload/'
  malformed.result = gunzipSync(readFileSync(`${prefix}invalid-preload-result.json.gz`))
  malformed.verification = readFileSync(`${prefix}invalid-preload-verify-report.json`)
  await expect(reviewRcPinRollerOriginals(malformed)).rejects.toThrow('rc_pin_roller_preload_reaction_count_invalid')
})
test('v4 original reviewer rejects missing, extra and reordered reaction rows', async () => {
  for (const edit of [
    (reactions: any[]) => reactions.pop(),
    (reactions: any[]) => reactions.push({ ...reactions[0], dof: 'RZ' }),
    (reactions: any[]) => reactions.reverse(),
  ]) {
    const files = changed('result', result => edit(result.response_history[0].support_reactions))
    await expect(reviewRcPinRollerOriginals(files)).rejects.toThrow()
  }
})
test('v4 original reviewer binds result request policy, control node and full checkpoint scope', async () => {
  for (const [name, code] of [
    ['request-bounds', 'rc_pin_roller_result_source_invalid'],
    ['control', 'rc_pin_roller_result_source_invalid'],
    ['scope', 'rc_pin_roller_checkpoint_scope_mismatch'],
  ] as const) {
    const files = originals()
    files.result = gunzipSync(readFileSync(`${directory}invalid-${name}-result.json.gz`))
    files.verification = readFileSync(`${directory}invalid-${name}-verify-report.json`)
    await expect(reviewRcPinRollerOriginals(files)).rejects.toThrow(code)
  }
})
