import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { validateRcJobArtifacts } from '../../src/workbench-v2/model/rcJobSchema'

const directory = 'tests/frontend/fixtures/rc-fiber-durable-job/'
function fixture() {
  return {
    job: JSON.parse(readFileSync(`${directory}job.json`, 'utf8')),
    artifacts: Object.fromEntries(['request', 'checkpoint', 'result', 'evidence'].map((role) => [
      role, new Uint8Array(readFileSync(`${directory}${role}.json`)),
    ])),
  }
}
test('RC review binds retained Python bytes, full history and native checkpoint', async () => {
  const { job, artifacts } = fixture()
  const review = await validateRcJobArtifacts(job, artifacts)
  expect(review.summary.targets).toEqual([-1e-6, -2e-6, -1.5e-6])
  expect(review.summary).toMatchObject({ reservedInvocations: 6, confirmedInvocations: 6, knownCoreCalls: 12, knownNewtonIterations: 24, unknownWork: false })
  expect(review.history.map((row) => row.epoch)).toEqual([1, 2, 3])
  expect(review.history[2].fiber_results).toHaveLength(84)
})

function digest(bytes: Uint8Array | string): string { return `sha256:${createHash('sha256').update(bytes).digest('hex')}` }
function rebind(source: ReturnType<typeof fixture>, resultRaw: string): void {
  source.artifacts.result = new TextEncoder().encode(resultRaw)
  source.job.result.content_hash = digest(source.artifacts.result)
  source.job.result.byte_length = source.artifacts.result.byteLength
  const evidence = JSON.parse(new TextDecoder().decode(source.artifacts.evidence))
  evidence.result_artifact_hash = source.job.result.content_hash
  evidence.validation_report.result_hash = JSON.parse(resultRaw).result_hash
  source.artifacts.evidence = new TextEncoder().encode(JSON.stringify(evidence))
  source.job.evidence.content_hash = digest(source.artifacts.evidence)
  source.job.evidence.byte_length = source.artifacts.evidence.byteLength
}
function rehashWrapper(raw: string): string {
  // Root result_hash is the last such field in compact, key-sorted producer JSON.
  const start = raw.lastIndexOf(',"result_hash":')
  const end = raw.indexOf(',', start + 1)
  const unsigned = raw.slice(0, start) + raw.slice(end)
  return raw.slice(0, start) + `,"result_hash":"${digest(unsigned)}"` + raw.slice(end)
}
for (const role of ['request', 'checkpoint', 'result', 'evidence']) {
  test(`RC review rejects altered original ${role} bytes`, async () => {
    const source = fixture()
    source.artifacts[role][20] ^= 1
    await expect(validateRcJobArtifacts(source.job, source.artifacts)).rejects.toThrow('rc_review_byte_hash_mismatch')
  })
}
test('RC review rejects changed physical values even with a refreshed outer wrapper and transport', async () => {
  const source = fixture()
  const raw = new TextDecoder().decode(source.artifacts.result)
  const changed = raw.replace('"stress_MPa":', '"stress_MPa":9,"discarded_stress_MPa":')
  expect(changed).not.toBe(raw)
  rebind(source, rehashWrapper(changed))
  await expect(validateRcJobArtifacts(source.job, source.artifacts)).rejects.toThrow('rc_review_logical_hash_mismatch')
})
test('RC review rejects a rehashed wrapper authority promotion', async () => {
  const source = fixture()
  const raw = new TextDecoder().decode(source.artifacts.result)
  // Last occurrence is the wrapper authority, after the cumulative API object.
  const key = '"service_numerical_verification_performed":false'
  const offset = raw.lastIndexOf(key)
  rebind(source, rehashWrapper(raw.slice(0, offset) + raw.slice(offset).replace(key, '"service_numerical_verification_performed":true')))
  await expect(validateRcJobArtifacts(source.job, source.artifacts)).rejects.toThrow('rc_review_result_binding_invalid')
})
test('RC review rejects duplicate JSON keys despite refreshed transport references', async () => {
  const source = fixture()
  const raw = new TextDecoder().decode(source.artifacts.result)
  rebind(source, raw.replace('"case_id":', '"case_id":"duplicate","case_id":'))
  await expect(validateRcJobArtifacts(source.job, source.artifacts)).rejects.toThrow('duplicate')
})
test('RC review keeps unconfirmed reservations as unknown work', async () => {
  const source = fixture()
  const raw = new TextDecoder().decode(source.artifacts.result)
    .replace('"remaining_attempts":10,"reserved_attempts":6', '"remaining_attempts":9,"reserved_attempts":7')
  rebind(source, rehashWrapper(raw))
  const evidence = JSON.parse(new TextDecoder().decode(source.artifacts.evidence))
  evidence.validation_report.execution_budget = { maximum_attempts: 16, remaining_attempts: 9, reserved_attempts: 7 }
  source.artifacts.evidence = new TextEncoder().encode(JSON.stringify(evidence))
  source.job.evidence.content_hash = digest(source.artifacts.evidence)
  source.job.evidence.byte_length = source.artifacts.evidence.byteLength
  const { summary } = await validateRcJobArtifacts(source.job, source.artifacts)
  expect(summary).toMatchObject({ reservedInvocations: 7, confirmedInvocations: 6, unknownWork: true, knownCoreCalls: 12 })
})
