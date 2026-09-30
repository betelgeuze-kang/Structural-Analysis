import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { createHash } from 'node:crypto'
import { decodeRcFiberPhasePolicy, fields, rawValues, validateRcJobArtifacts } from '../../src/workbench-v2/model/rcJobSchema'

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

for (const value of [1, null, 'true']) {
  test(`RC job rejects a non-boolean reuse setting: ${value}`, async () => {
    const input = fixture()
    const request = JSON.parse(new TextDecoder().decode(input.artifacts.request))
    request.execution_config.reuse_line_search_assembly = value
    input.artifacts.request = new TextEncoder().encode(JSON.stringify(request))
    input.job.request.content_hash = digest(input.artifacts.request)
    input.job.request.byte_length = input.artifacts.request.byteLength
    await expect(validateRcJobArtifacts(input.job, input.artifacts)).rejects.toThrow('execution_reuse_invalid')
  })
}


function originalWorkRaw(raw: string, path: (string | number)[]): string {
  if (!path.length) return raw
  const [key, ...rest] = path
  return originalWorkRaw(typeof key === 'number' ? rawValues(raw)[key] : fields(raw).get(key)!.value, rest)
}
// Preserve every unrelated producer numeric token while forging one work count.
function replaceWorkRaw(raw: string, path: (string | number)[], value: string): string {
  if (!path.length) return value
  const [key, ...rest] = path
  if (typeof key === 'number') {
    const rows = rawValues(raw); rows[key] = replaceWorkRaw(rows[key], rest, value); return `[${rows.join(',')}]`
  }
  const members = fields(raw)
  members.get(key)!.member = `${JSON.stringify(key)}:${replaceWorkRaw(members.get(key)!.value, rest, value)}`
  return `{${[...members.values()].map(row => row.member).join(',')}}`
}
test('v1 rejects rehashed unknown work in a successful last verification receipt', async () => {
  const source = fixture()
  const original = new TextDecoder().decode(source.artifacts.result)
  const tail = JSON.parse(original).receipts.length - 1
  let raw = replaceWorkRaw(original, ['receipts', tail, 'verification_metrics', 'replay_control_work', 'unknown_solver_work_attempt_count'], '1')
  const receipt = fields(originalWorkRaw(raw, ['receipts', tail])); receipt.delete('receipt_hash')
  raw = replaceWorkRaw(raw, ['receipts', tail, 'receipt_hash'], JSON.stringify(digest(`{${[...receipt.values()].map(row => row.member).join(',')}}`)))
  const checkpoint = source.artifacts.checkpoint.slice(), request = source.artifacts.request.slice()
  rebind(source, rehashWrapper(raw))
  const evidence = JSON.parse(new TextDecoder().decode(source.artifacts.evidence))
  evidence.validation_report.receipt_hashes = JSON.parse(raw).receipts.map((row: any) => row.receipt_hash)
  source.artifacts.evidence = new TextEncoder().encode(JSON.stringify(evidence))
  source.job.evidence.content_hash = digest(source.artifacts.evidence)
  source.job.evidence.byte_length = source.artifacts.evidence.byteLength
  expect(source.artifacts.checkpoint).toEqual(checkpoint)
  expect(source.artifacts.request).toEqual(request)
  expect(originalWorkRaw(new TextDecoder().decode(source.artifacts.result), ['api_result'])).toBe(originalWorkRaw(original, ['api_result']))
  await expect(validateRcJobArtifacts(source.job, source.artifacts).then(review => review.summary)).rejects.toThrow('rc_review_work_invalid')
})


const phasePolicy = () => ({
  schema_version: 'bounded-rc-fiber-phase-execution-policy.v1',
  analysis_timeout_ms: 60000, verification_timeout_ms: 120000, termination_grace_ms: 1000,
})
function rehashPolicyRaw(raw: string, key: string): string {
  const members = fields(raw); members.delete(key)
  return replaceWorkRaw(raw, [key], JSON.stringify(digest(`{${[...members.values()].map(row => row.member).join(',')}}`)))
}
function policyRequestRaw(source: ReturnType<typeof fixture>, policyRaw: string): string {
  const raw = new TextDecoder().decode(source.artifacts.request)
  const execution = fields(fields(raw).get('execution_config')!.value)
  execution.set('phase_execution_policy', { member: `"phase_execution_policy":${policyRaw}`, value: policyRaw })
  return replaceWorkRaw(raw, ['execution_config'], `{${[...execution].sort(([a], [b]) => a.localeCompare(b)).map(([, row]) => row.member).join(',')}}`)
}
function bindPolicyRequest(source: ReturnType<typeof fixture>, raw: string): void {
  source.artifacts.request = new TextEncoder().encode(raw)
  source.job.request.content_hash = digest(source.artifacts.request)
  source.job.request.byte_length = source.artifacts.request.byteLength
}
// Synthetic transport rebindings retain every API/native byte; they do not
// attest that a timed worker ran or grant physics/performance authority.
function bindAcceptedPolicyFixture(source: ReturnType<typeof fixture>, policy: ReturnType<typeof phasePolicy>): void {
  const policyRaw = JSON.stringify(Object.fromEntries(Object.entries(policy).sort(([a], [b]) => a.localeCompare(b))))
  bindPolicyRequest(source, policyRequestRaw(source, policyRaw))
  const requestHash = source.job.request.content_hash
  const resumeHash = digest(JSON.stringify({ profile: 'bounded_rc_fiber_durable_chunk_execution.v1', request_hash: requestHash }))
  source.job.resume_contract_hash = resumeHash
  let resultRaw = new TextDecoder().decode(source.artifacts.result)
  resultRaw = replaceWorkRaw(resultRaw, ['request_hash'], JSON.stringify(requestHash))
  resultRaw = replaceWorkRaw(resultRaw, ['resume_contract_hash'], JSON.stringify(resumeHash))
  const receipts = rawValues(fields(resultRaw).get('receipts')!.value).map(raw =>
    rehashPolicyRaw(replaceWorkRaw(raw, ['job_request_hash'], JSON.stringify(requestHash)), 'receipt_hash'))
  resultRaw = replaceWorkRaw(resultRaw, ['receipts'], `[${receipts.join(',')}]`)
  let checkpointRaw = new TextDecoder().decode(source.artifacts.checkpoint)
  const prefixCount = JSON.parse(checkpointRaw).receipts.length
  checkpointRaw = replaceWorkRaw(checkpointRaw, ['request_hash'], JSON.stringify(requestHash))
  checkpointRaw = replaceWorkRaw(checkpointRaw, ['resume_contract_hash'], JSON.stringify(resumeHash))
  checkpointRaw = replaceWorkRaw(checkpointRaw, ['receipts'], `[${receipts.slice(0, prefixCount).join(',')}]`)
  source.artifacts.checkpoint = new TextEncoder().encode(rehashPolicyRaw(checkpointRaw, 'checkpoint_hash'))
  source.job.checkpoint.content_hash = digest(source.artifacts.checkpoint)
  source.job.checkpoint.byte_length = source.artifacts.checkpoint.byteLength
  rebind(source, rehashPolicyRaw(resultRaw, 'result_hash'))
  let evidenceRaw = new TextDecoder().decode(source.artifacts.evidence)
  evidenceRaw = replaceWorkRaw(evidenceRaw, ['request_hash'], JSON.stringify(requestHash))
  evidenceRaw = replaceWorkRaw(evidenceRaw, ['checkpoint_hash'], JSON.stringify(source.job.checkpoint.content_hash))
  evidenceRaw = replaceWorkRaw(evidenceRaw, ['validation_report', 'request_hash'], JSON.stringify(requestHash))
  evidenceRaw = replaceWorkRaw(evidenceRaw, ['validation_report', 'receipt_hashes'], JSON.stringify(receipts.map(raw => JSON.parse(raw).receipt_hash)))
  source.artifacts.evidence = new TextEncoder().encode(evidenceRaw)
  source.job.evidence.content_hash = digest(source.artifacts.evidence)
  source.job.evidence.byte_length = source.artifacts.evidence.byteLength
}

for (const [field, maximum] of [
  ['analysis_timeout_ms', 3600000], ['verification_timeout_ms', 3600000], ['termination_grace_ms', 5000],
] as const) {
  test(`RC phase policy keeps authored ${field} inclusive bounds and frozen values`, () => {
    for (const value of [1, maximum]) {
      const payload = { ...phasePolicy(), [field]: value }
      const decoded = decodeRcFiberPhasePolicy(JSON.stringify(payload))
      payload[field] = maximum + 1
      expect(decoded[field]).toBe(value)
      expect(Object.isFrozen(decoded)).toBe(true)
      expect(() => { (decoded as any)[field] = maximum + 1 }).toThrow(TypeError)
      expect(Object.keys(decoded).sort()).toEqual(['analysis_timeout_ms', 'termination_grace_ms', 'verification_timeout_ms'])
    }
  })
  for (const [label, value] of [['boolean', true], ['string', '1'], ['null', null], ['zero', 0], ['negative', -1], ['fraction', 1.5], ['above maximum', maximum + 1]] as const) {
    test(`RC reader rejects ${field} ${label} before artifact publication`, async () => {
      const source = fixture()
      bindPolicyRequest(source, policyRequestRaw(source, JSON.stringify({ ...phasePolicy(), [field]: value })))
      await expect(validateRcJobArtifacts(source.job, source.artifacts)).rejects.toThrow('phase_execution_policy_invalid')
    })
  }
  test(`RC reader rejects a missing authored ${field}`, async () => {
    const source = fixture(), policy: Record<string, any> = phasePolicy()
    delete policy[field]
    bindPolicyRequest(source, policyRequestRaw(source, JSON.stringify(policy)))
    await expect(validateRcJobArtifacts(source.job, source.artifacts)).rejects.toThrow('phase_execution_policy_invalid')
  })
}
for (const [name, value] of [
  ['null', null], ['array', []], ['boolean', false], ['string', 'policy'], ['empty', {}],
  ['version', { ...phasePolicy(), schema_version: 'bounded-rc-fiber-phase-execution-policy.v2' }],
  ['extra', { ...phasePolicy(), memory_limit_bytes: 1 }],
] as const) {
  test(`RC reader rejects policy ${name} without widening summary`, async () => {
    const source = fixture()
    bindPolicyRequest(source, policyRequestRaw(source, JSON.stringify(value)))
    await expect(validateRcJobArtifacts(source.job, source.artifacts)).rejects.toThrow()
  })
}
for (const token of ['1.0', '1e0', '1E+0', 'true', 'null', 'NaN', 'Infinity']) {
  test(`RC reader rejects original analysis_timeout_ms token ${token}`, async () => {
    const source = fixture()
    const raw = JSON.stringify({ ...phasePolicy(), analysis_timeout_ms: 1 }).replace('"analysis_timeout_ms":1', `"analysis_timeout_ms":${token}`)
    bindPolicyRequest(source, policyRequestRaw(source, raw))
    await expect(validateRcJobArtifacts(source.job, source.artifacts)).rejects.toThrow()
  })
}
test('RC reader rejects duplicate policy keys despite matching transport hash', async () => {
  const source = fixture()
  const raw = JSON.stringify(phasePolicy()).replace('"analysis_timeout_ms":', '"analysis_timeout_ms":1,"analysis_timeout_ms":')
  bindPolicyRequest(source, policyRequestRaw(source, raw))
  await expect(validateRcJobArtifacts(source.job, source.artifacts)).rejects.toThrow('duplicate')
})
for (const [name, policy] of [
  ['minimum', { ...phasePolicy(), analysis_timeout_ms: 1, verification_timeout_ms: 1, termination_grace_ms: 1 }],
  ['maximum', { ...phasePolicy(), analysis_timeout_ms: 3600000, verification_timeout_ms: 3600000, termination_grace_ms: 5000 }],
] as const) {
  test(`RC reader accepts hash-bound authored policy ${name} preserving native results and summary shape`, async () => {
    const source = fixture(), legacy = fixture()
    const legacyReview = await validateRcJobArtifacts(legacy.job, legacy.artifacts)
    const originalApi = originalWorkRaw(new TextDecoder().decode(source.artifacts.result), ['api_result'])
    const originalCheckpoint = JSON.parse(new TextDecoder().decode(source.artifacts.checkpoint)).terminal_checkpoint_artifact_base64
    const oldRequestHash = source.job.request.content_hash, oldResumeHash = source.job.resume_contract_hash
    bindAcceptedPolicyFixture(source, policy)
    const review = await validateRcJobArtifacts(source.job, source.artifacts)
    expect(source.job.request.content_hash).not.toBe(oldRequestHash)
    expect(source.job.resume_contract_hash).not.toBe(oldResumeHash)
    expect(originalWorkRaw(new TextDecoder().decode(source.artifacts.result), ['api_result'])).toBe(originalApi)
    expect(JSON.parse(new TextDecoder().decode(source.artifacts.checkpoint)).terminal_checkpoint_artifact_base64).toBe(originalCheckpoint)
    expect(review.terminalBytes).toEqual(legacyReview.terminalBytes)
    expect(review.history).toEqual(legacyReview.history)
    expect(Object.keys(review.summary).sort()).toEqual(Object.keys(legacyReview.summary).sort())
    expect(review.summary).toEqual({ ...legacyReview.summary, resultHash: JSON.parse(new TextDecoder().decode(source.artifacts.result)).result_hash })
    expect(review.summary).not.toHaveProperty('phase_execution_policy')
  })
}
test('RC policy rebind cannot hide changed original request bounds', async () => {
  const source = fixture()
  bindAcceptedPolicyFixture(source, phasePolicy())
  const changed = JSON.parse(new TextDecoder().decode(source.artifacts.request))
  changed.execution_config.phase_execution_policy.analysis_timeout_ms += 1
  bindPolicyRequest(source, policyRequestRaw(source, JSON.stringify(changed.execution_config.phase_execution_policy)))
  await expect(validateRcJobArtifacts(source.job, source.artifacts)).rejects.toThrow('result_binding_invalid')
})
