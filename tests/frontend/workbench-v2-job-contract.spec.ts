import { expect, test } from '@playwright/test'
import { createHash } from 'node:crypto'
import { loadWorkbenchJob } from '../../src/workbench-v2/model/jobProvider'
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

test('job success is publication state and carries no inferred convergence field', () => {
  const succeeded = {
    ...queuedJob(),
    status: 'succeeded',
    revision: 2,
    attempt: 1,
    progress: { completed_steps: 4, total_steps: 4 },
    result: { role: 'result', content_hash: hash, byte_length: 10, media_type: 'application/json' },
    evidence: { role: 'evidence', content_hash: hash, byte_length: 10, media_type: 'application/json' },
  }
  const validation = validateWorkbenchJobView(succeeded)
  expect(validation.ok).toBe(true)
  expect(validation.value).not.toHaveProperty('converged')
})

test('Workbench never accepts a lease token in the tenant projection', () => {
  expect(validateWorkbenchJobView({ ...queuedJob(), lease_token: 'secret' }).ok).toBe(false)
})

function digest(bytes: Uint8Array): string {
  return `sha256:${createHash('sha256').update(bytes).digest('hex')}`
}

function canonical(value: unknown): string {
  const sort = (item: unknown): unknown => {
    if (Array.isArray(item)) return item.map(sort)
    if (item && typeof item === 'object') {
      return Object.keys(item as Record<string, unknown>)
        .sort()
        .reduce<Record<string, unknown>>((acc, key) => {
          acc[key] = sort((item as Record<string, unknown>)[key])
          return acc
        }, {})
    }
    return item
  }
  return JSON.stringify(sort(value))
}

function canonicalHash(value: unknown): string {
  return digest(new TextEncoder().encode(canonical(value)))
}

function publishedResult(): Record<string, unknown> {
  const authorityAxes = {
    convergence: 'inherited_bounded_candidate',
    displacement: 'exact_bounded_candidate',
    reaction: 'exact_bounded_candidate',
    member_force: 'exact_bounded_candidate',
    member_features: 'not_supported',
    section_resultant: 'exact_bounded_candidate',
    fiber_result: 'exact_bounded_candidate',
    fallback: 'not_used',
    external_vv: 'not_attached',
    engineering_design: 'not_authoritative',
    release_readiness: 'not_authoritative',
  }
  const descriptorNames = [
    'node_translation_m', 'node_rotation_rad', 'reaction_force_n', 'reaction_moment_nm',
    'member_force_n', 'member_moment_nm', 'section_axial_force_n', 'section_moment_nm',
    'section_strain', 'section_curvature_per_m', 'fiber_strain', 'fiber_stress_pa',
    'member_node_indices', 'section_offsets', 'section_xi', 'fiber_offsets', 'fiber_y_m', 'fiber_area_m2',
  ]
  const descriptors = descriptorNames.map((name, index) => ({
    name,
    dtype: name.includes('indices') || name.includes('offsets') ? '<i8' : '<f8',
    shape: [index < 4 ? 4 : 3],
    unit: '1',
    quantity_ids: [],
    order_scope: index < 4 ? 'node' : index < 8 ? 'member' : index < 12 ? 'section' : 'fiber',
    authority_role: index < 12 ? 'output' : 'mapping',
    order_hash: hash,
    data_hash: hash,
    content_hash: hash,
  }))
  const irBody = {
    schema_version: 'corotational-fiber-frame2d-engineering-result-ir.v1',
    engineering_result_id: 'engineering.portal.test',
    result_kind: 'corotational_portal_reaction_member_section_fiber',
    recovery_profile: 'exact_terminal_parent_corotational_section_global_replay.v1',
    authority_profile: 'exact_bounded_portal_engineering_candidate.v1',
    compiler_hash: hash,
    source_adapter_hash: hash,
    model_content_hash: hash,
    problem_contract_hash: hash,
    terminal_checkpoint_hash: hash,
    terminal_assembly_hash: hash,
    quantity_catalog_hash: hash,
    load_factor: 1,
    counts: { node: 4, member: 3, section: 3, fiber: 6 },
    member_ids: ['M1', 'M2', 'M3'],
    metrics: { terminal_assembly_replay_exact: true },
    authority_axes: authorityAxes,
    limitations: ['external_level2_not_attached'],
    array_bundle_hash: canonicalHash(descriptors),
    array_descriptors: descriptors,
  }
  const engineeringResultIr = {
    ...irBody,
    engineering_result_hash: canonicalHash(irBody),
  }
  const resultBody = {
    schema_version: 'unified-nonlinear-frame-result.v1',
    status: 'ready',
    contract_pass: true,
    profile: 'corotational_one_bay_portal.v1',
    source_result_hash: engineeringResultIr.engineering_result_hash,
    contract_bindings: {
      engineering_result_hash: engineeringResultIr.engineering_result_hash,
      engineering_array_bundle_hash: engineeringResultIr.array_bundle_hash,
      quantity_catalog_hash: engineeringResultIr.quantity_catalog_hash,
    },
    authority: authorityAxes,
    engineering_result_ir: engineeringResultIr,
    // Legacy top-level engineering arrays may coexist for API compatibility,
    // but Workbench must not expose them through its durable-job projection.
    node_displacements: [{ node_id: 'legacy-must-not-be-consumed' }],
  }
  return { ...resultBody, result_hash: canonicalHash(resultBody) }
}

function completionEvidence(
  result: Record<string, unknown>,
  resultArtifactHash: string,
): Record<string, unknown> {
  return {
    schema_version: 'structural-analysis-job-completion-evidence.v1',
    job_id: `job_${'a'.repeat(32)}`,
    request_hash: hash,
    checkpoint_hash: null,
    result_artifact_hash: resultArtifactHash,
    validator_id: 'structural_analysis.api.nonlinear_frame.validate_nonlinear_frame_result',
    contract_pass: true,
    solver_truth_owner: 'structural_analysis_core',
    validation_report: {
      schema_version: 'unified-nonlinear-frame-validation-report.v1',
      status: 'ready',
      contract_pass: true,
      result_hash: result.result_hash,
      profile: result.profile,
      exact_engineering_recovery: true,
      exact_checkpoint_chain_replay: true,
      checkpoint_available: true,
      unsupported_feature_count: 0,
      fallback_count: 0,
      regularization_count: 0,
    },
  }
}

test('Workbench verifies a succeeded result/evidence pair before display', async () => {
  const encoder = new TextEncoder()
  const result = publishedResult()
  const resultBytes = encoder.encode(JSON.stringify(result))
  const resultHash = digest(resultBytes)
  const evidenceBytes = encoder.encode(JSON.stringify(completionEvidence(result, resultHash)))
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
    expect(loaded.engineeringResultIr?.engineering_result_hash).toBe(result.source_result_hash)
    expect('node_displacements' in loaded).toBe(false)
  } finally {
    globalThis.fetch = originalFetch
  }
})

test('Workbench blocks a tampered published result', async () => {
  const encoder = new TextEncoder()
  const result = publishedResult()
  const declaredResult = encoder.encode(JSON.stringify(result))
  const tamperedResult = encoder.encode(JSON.stringify({ ...result, changed: true }))
  const resultHash = digest(declaredResult)
  const evidenceBytes = encoder.encode(JSON.stringify(completionEvidence(result, resultHash)))
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

test('Workbench blocks a hash-valid result with a detached ResultIR mismatch', async () => {
  const encoder = new TextEncoder()
  const payload = publishedResult()
  payload.source_result_hash = `sha256:${'2'.repeat(64)}`
  const resultBody = { ...payload }
  delete resultBody.result_hash
  payload.result_hash = canonicalHash(resultBody)
  const resultBytes = encoder.encode(JSON.stringify(payload))
  const resultHash = digest(resultBytes)
  const evidenceBytes = encoder.encode(JSON.stringify(completionEvidence(payload, resultHash)))
  const succeeded = {
    ...queuedJob(), status: 'succeeded', revision: 2, attempt: 1,
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
    expect(loaded.status).toBe('invalid')
    expect(loaded.errors).toContain('published engineering ResultIR binding is invalid')
  } finally {
    globalThis.fetch = originalFetch
  }
})

test('Workbench blocks a hash-valid pair when the core validation report is detached', async () => {
  const encoder = new TextEncoder()
  const result = publishedResult()
  const resultBytes = encoder.encode(JSON.stringify(result))
  const resultHash = digest(resultBytes)
  const evidence = completionEvidence(result, resultHash)
  ;(evidence.validation_report as Record<string, unknown>).result_hash = `sha256:${'9'.repeat(64)}`
  const evidenceBytes = encoder.encode(JSON.stringify(evidence))
  const succeeded = {
    ...queuedJob(), status: 'succeeded', revision: 2, attempt: 1,
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
    expect(loaded.status).toBe('invalid')
    expect(loaded.errors).toContain('published completion evidence binding is invalid')
  } finally {
    globalThis.fetch = originalFetch
  }
})
