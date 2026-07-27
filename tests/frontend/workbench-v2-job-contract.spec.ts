import { expect, test } from '@playwright/test'
import { createHash } from 'node:crypto'
import { loadWorkbenchJob, normalizeResultSummary } from '../../src/workbench-v2/model/jobProvider'
import { validateWorkbenchJobView } from '../../src/workbench-v2/model/jobSchema'

const hash = `sha256:${'1'.repeat(64)}`

function queuedJob(): Record<string, unknown> {
  return {
    schema_version: 'structural-analysis-job-view.v1',
    service_profile: 'sqlite_wal_content_addressed_single_host.v1',
    job_id: `job_${'a'.repeat(32)}`,
    status: 'queued',
    revision: 0,
    attempt: 0,
    progress: { completed_steps: 0, total_steps: 4 },
    created_at: '2026-07-22T00:00:00.000000Z',
    updated_at: '2026-07-22T00:00:00.000000Z',
    lease_expires_at: null,
    error_code: null,
    can_resume: false,
    request: { role: 'request', content_hash: hash, byte_length: 100, media_type: 'application/json' },
    checkpoint: null,
    result: null,
    evidence: null,
    resume_contract_hash: null,
    solver_truth_owner: 'structural_analysis_core',
    result_authority: 'referenced_result_and_evidence_contracts_only',
    claim_boundary: 'orchestration only',
    terminal_event_hash: hash,
  }
}

test('Workbench accepts the exact read-only queued job projection', () => {
  const validation = validateWorkbenchJobView(queuedJob())
  expect(validation.ok).toBe(true)
  expect(validation.value?.status).toBe('queued')
})

test('Workbench rejects premature result publication and hidden fields', () => {
  const premature = queuedJob()
  premature.result = { role: 'result', content_hash: hash, byte_length: 10, media_type: 'application/json' }
  premature.evidence = { role: 'evidence', content_hash: hash, byte_length: 10, media_type: 'application/json' }
  expect(validateWorkbenchJobView(premature).errors).toContain('non-succeeded job exposes published artifacts')

  const hiddenTruth = { ...queuedJob(), converged: true }
  expect(validateWorkbenchJobView(hiddenTruth)).toMatchObject({ ok: false, value: null })
})

test('Workbench requires an atomic result and evidence pair for success', () => {
  const succeeded = {
    ...queuedJob(),
    status: 'succeeded',
    revision: 2,
    attempt: 1,
    progress: { completed_steps: 4, total_steps: 4 },
    result: { role: 'result', content_hash: hash, byte_length: 10, media_type: 'application/json' },
    evidence: { role: 'evidence', content_hash: hash, byte_length: 10, media_type: 'application/json' },
  }
  expect(validateWorkbenchJobView(succeeded).ok).toBe(true)
  expect(validateWorkbenchJobView({ ...succeeded, evidence: null }).ok).toBe(false)
})

test('Workbench never accepts a lease token in the tenant projection', () => {
  expect(validateWorkbenchJobView({ ...queuedJob(), lease_token: 'secret' }).ok).toBe(false)
})

function digest(bytes: Uint8Array): string {
  return `sha256:${createHash('sha256').update(bytes).digest('hex')}`
}

test('Workbench verifies a succeeded result/evidence pair before display', async () => {
  const encoder = new TextEncoder()
  const resultBytes = encoder.encode(JSON.stringify({
    schema_version: 'unified-nonlinear-frame-result.v1',
    solver_id: 'public_cpu_corotational_rc_fiber_frame_arc_length_v1',
    configuration: { control_mode: 'arc_length' },
    checkpoint: {
      terminal_load_factor: -2.5,
      terminal_epoch: 7,
      terminal_monitor_displacement_m: -0.03,
    },
    metrics: {
      exact_engineering_recovery: true,
      exact_checkpoint_chain_replay: true,
      fallback_count: 0,
      regularization_count: 0,
      accepted_step_count: 7,
      rejected_step_count: 1,
    },
    authority: { public_api: 'developer_preview_candidate', external_vv: 'not_attached' },
    node_displacements: [{ node_id: 'N1' }, { node_id: 'N2' }],
    support_reactions: [{ node_id: 'N1', dof: 'UY' }],
    member_end_forces: [{ member_id: 'M1' }],
    section_results: [{ member_id: 'M1', section_index: 0 }],
    fiber_results: [{ member_id: 'M1', fiber_index: 0 }],
  }))
  const resultHash = digest(resultBytes)
  const evidenceBytes = encoder.encode(JSON.stringify({
    schema_version: 'structural-analysis-job-completion-evidence.v1',
    job_id: `job_${'a'.repeat(32)}`,
    request_hash: hash,
    checkpoint_hash: null,
    result_artifact_hash: resultHash,
    contract_pass: true,
    solver_truth_owner: 'structural_analysis_core',
  }))
  const succeeded = {
    ...queuedJob(),
    status: 'succeeded', revision: 2, attempt: 1,
    progress: { completed_steps: 4, total_steps: 4 },
    result: { role: 'result', content_hash: resultHash, byte_length: resultBytes.byteLength, media_type: 'application/json' },
    evidence: { role: 'evidence', content_hash: digest(evidenceBytes), byte_length: evidenceBytes.byteLength, media_type: 'application/json' },
  }
  const statusBytes = encoder.encode(JSON.stringify(succeeded))
  const originalFetch = globalThis.fetch
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    const url = String(input)
    const bytes = url.endsWith('/result') ? resultBytes : url.endsWith('/evidence') ? evidenceBytes : statusBytes
    return new Response(bytes, { headers: { 'content-type': 'application/json', 'content-length': String(bytes.byteLength) } })
  }) as typeof fetch
  try {
    const loaded = await loadWorkbenchJob('https://example.test/v1/jobs/job_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa')
    expect(loaded).toMatchObject({ status: 'ready', artifactStatus: 'verified', errors: [] })
    expect(loaded.resultSummary).toMatchObject({
      controlMode: { state: 'available', value: 'arc_length' },
      terminalLoadFactor: { state: 'available', value: -2.5 },
      terminalControlDisplacement: { state: 'available', value: -0.03 },
      acceptedStepCount: { state: 'available', value: 7 },
      nodeDisplacementRows: { state: 'available', value: 2 },
    })
  } finally {
    globalThis.fetch = originalFetch
  }
})

test('Workbench result summary preserves unavailable and invalid engineering states', () => {
  const summary = normalizeResultSummary({
    schema_version: 'unified-nonlinear-frame-result.v1',
    configuration: { control_mode: 'arc_length' },
    checkpoint: { terminal_load_factor: 'not-a-number', terminal_epoch: -1 },
    metrics: { fallback_count: -1, exact_engineering_recovery: 'yes' },
    node_displacements: 'not-an-array',
  })

  expect(summary.terminalLoadFactor.state).toBe('invalid')
  expect(summary.terminalEpoch.state).toBe('invalid')
  expect(summary.fallbackCount.state).toBe('invalid')
  expect(summary.exactEngineeringRecovery.state).toBe('invalid')
  expect(summary.nodeDisplacementRows.state).toBe('invalid')
  expect(summary.terminalControlDisplacement.state).toBe('unavailable')
  expect(summary.supportReactionRows.state).toBe('unavailable')
})

test('Workbench blocks a tampered published result', async () => {
  const encoder = new TextEncoder()
  const declaredResult = encoder.encode(JSON.stringify({ schema_version: 'unified-nonlinear-frame-result.v1' }))
  const tamperedResult = encoder.encode(JSON.stringify({ schema_version: 'unified-nonlinear-frame-result.v1', changed: true }))
  const resultHash = digest(declaredResult)
  const evidenceBytes = encoder.encode(JSON.stringify({
    schema_version: 'structural-analysis-job-completion-evidence.v1',
    job_id: `job_${'a'.repeat(32)}`, request_hash: hash, checkpoint_hash: null,
    result_artifact_hash: resultHash, contract_pass: true,
    solver_truth_owner: 'structural_analysis_core',
  }))
  const succeeded = {
    ...queuedJob(), status: 'succeeded', revision: 2, attempt: 1,
    progress: { completed_steps: 4, total_steps: 4 },
    result: { role: 'result', content_hash: resultHash, byte_length: declaredResult.byteLength, media_type: 'application/json' },
    evidence: { role: 'evidence', content_hash: digest(evidenceBytes), byte_length: evidenceBytes.byteLength, media_type: 'application/json' },
  }
  const statusBytes = encoder.encode(JSON.stringify(succeeded))
  const originalFetch = globalThis.fetch
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    const url = String(input)
    const bytes = url.endsWith('/result') ? tamperedResult : url.endsWith('/evidence') ? evidenceBytes : statusBytes
    return new Response(bytes, { headers: { 'content-type': 'application/json' } })
  }) as typeof fetch
  try {
    const loaded = await loadWorkbenchJob('https://example.test/v1/jobs/job_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa')
    expect(loaded.status).toBe('invalid')
    expect(loaded.artifactStatus).toBe('invalid')
    expect(loaded.errors.join(' ')).toMatch(/result (byte length|sha256) mismatch/)
  } finally {
    globalThis.fetch = originalFetch
  }
})
