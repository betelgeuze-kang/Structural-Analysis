import { test, expect } from '@playwright/test'
import { admitRcReviewArtifacts, RC_REVIEW_TOTAL_BYTES } from '../../src/workbench-v2/model/rcJobReviewBudget'
import { loadRcJobReview } from '../../src/workbench-v2/model/rcJobReview'
import type { WorkbenchJobView } from '../../src/workbench-v2/model/jobSchema'
import type { JobReadTransport } from '../../src/workbench-v2/model/jobTransport'
import { rcWorkflowMessage } from '../../src/workbench-v2/components/RcJobWorkflowPanel'
const MiB = 1024 * 1024
const job = (lengths: Record<string, number>) => Object.fromEntries(Object.entries(lengths).map(([role, byte_length]) => [role, { byte_length, media_type: 'application/json' }])) as unknown as WorkbenchJobView

for (const limit of [0, -1, 1.5, NaN, Infinity, 128 * MiB + 1, '134217728', null]) {
  test(`rejects invalid host budget ${String(limit)} before fetching`, async () => {
    let calls = 0
    const transport = { get: async () => { calls++; return new Response('') } } as unknown as JobReadTransport
    await expect(loadRcJobReview(job({ result: 1 }), transport, undefined, limit as number)).rejects.toThrow('rc_review_budget_invalid')
    expect(calls).toBe(0)
  })
}

test('default rejects the actual source-informed result before any artifact fetch', async () => {
  let calls = 0
  const transport = { get: async () => { calls++; return new Response('') } } as unknown as JobReadTransport
  await expect(loadRcJobReview(job({ request: 4996, checkpoint: 158953, result: 117689201, evidence: 2314 }), transport)).rejects.toThrow('rc_result_too_large')
  expect(calls).toBe(0)
})

test('explicit host budget admits larger result but still checks HTTP failure', async () => {
  let calls = 0
  const transport = { get: async () => { calls++; return new Response('', { status: 503 }) } } as unknown as JobReadTransport
  await expect(loadRcJobReview(job({ result: 117689201 }), transport, undefined, 128 * MiB)).rejects.toThrow('rc_result_HTTP_503')
  expect(calls).toBe(1)
})

test('aggregate budget is preserved and checked before fetching', async () => {
  expect(admitRcReviewArtifacts(job({ checkpoint: 96 * MiB, result: 128 * MiB }), 128 * MiB).result).toBe(128 * MiB)
  expect(RC_REVIEW_TOTAL_BYTES).toBe(224 * MiB)
  let calls = 0
  const transport = { get: async () => { calls++; return new Response('') } } as unknown as JobReadTransport
  await expect(loadRcJobReview(job({ checkpoint: 96 * MiB, result: 128 * MiB, evidence: 1 }), transport, undefined, 128 * MiB)).rejects.toThrow('rc_artifacts_too_large')
  expect(calls).toBe(0)
})

test('large host budget cannot relax other role limits or declared byte lengths', () => {
  expect(() => admitRcReviewArtifacts(job({ request: 16 * MiB + 1 }), 128 * MiB)).toThrow('rc_request_too_large')
  expect(() => admitRcReviewArtifacts(job({ checkpoint: 128 * MiB + 1 }), 128 * MiB)).toThrow('rc_checkpoint_too_large')
  expect(() => admitRcReviewArtifacts(job({ evidence: 16 * MiB + 1 }), 128 * MiB)).toThrow('rc_evidence_too_large')
  for (const n of [0, -1, 1.5, NaN, Infinity]) expect(() => admitRcReviewArtifacts(job({ result: n }))).toThrow('rc_review_length_invalid')
})

test('host can lower its budget and the workflow explains a capacity rejection', () => {
  expect(admitRcReviewArtifacts(job({ result: 1 }), 1).result).toBe(1)
  expect(() => admitRcReviewArtifacts(job({ result: 2 }), 1)).toThrow('rc_result_too_large')
  expect(rcWorkflowMessage(new Error('rc_result_too_large'))).toContain('review size limit')
  expect(rcWorkflowMessage(new Error('rc_review_budget_invalid'))).toContain('administrator')
})
