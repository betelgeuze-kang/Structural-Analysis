import { expect, test } from '@playwright/test'
import { validateRcControlSearch } from '../../src/workbench-v2/model/rcControlSearchSchema'
import { portalCandidateBytes, portalCandidateRead } from './rcPortalCandidateFixture'

test('two-fixed portal search reviews frozen learned and price schedules against later full pool', async () => {
  const review = await validateRcControlSearch(portalCandidateBytes('result.json'), portalCandidateRead)
  expect(review.plan.control_request.experimental_two_fixed_endpoints).toBe(true)
  expect(review.plan.control_request.targets_m).toEqual([-0.01, -0.02, 0.01])
  expect(review.plan.control_request.constant_nodal_loads).toHaveLength(2)
  expect(review.plan.pool.map((row: any) => row.candidate_id)).toEqual(['baseline', 'narrower-036', 'wider-050'])
  expect(review.plan.plans.price_order).toEqual(review.plan.plans.learned_order)
  expect(review.report.historical_training_cost.sample_count).toBe(3)
  expect(review.report.claims.net_savings_proved).toBe(false)
  expect(review.costOptimality.pool_minimum_feasible_candidate_ids).toEqual(['narrower-036'])
  for (const name of ['price_order', 'learned_order']) {
    expect(review.report.arms[name].selected_candidate_id).toBe('narrower-036')
    expect(review.report.arms[name].execution_work.api_invocation_count).toBe(4)
    expect(review.report.candidate_coverage_audit.arms[name].missed_feasible_candidate_ids).toEqual(['wider-050'])
    expect(review.costOptimality.arms[name].selected_minus_pool_minimum_estimate).toBe(0)
    for (const row of review.designs[name].report.rows) expect(row.full_reference_verification_pass).toBe(true)
  }
  expect(review.report.oracle.execution_work.api_invocation_count).toBe(6)
  expect(review.designs.exhaustive_oracle.report.rows).toHaveLength(3)
  expect(review.designs.learned_order.models['narrower-036'].sections[0].width_m).toBe(0.36)
})

for (const path of ['policy.json', 'pool/wider-050.json', 'learned_order/narrower-036/result.json']) {
  test(`two-fixed portal search rejects changed original bytes ${path}`, async () => {
    await expect(validateRcControlSearch(portalCandidateBytes('result.json'), async candidate =>
      candidate === path
        ? path === 'policy.json'
          ? new TextEncoder().encode(new TextDecoder().decode(portalCandidateBytes(candidate)).replace('"schema_version":"', '"schema_version":"tampered-'))
          : Uint8Array.from(Buffer.concat([Buffer.from(portalCandidateBytes(candidate)), Buffer.from(' ')]))
        : portalCandidateRead(candidate),
    )).rejects.toThrow()
  })
}
