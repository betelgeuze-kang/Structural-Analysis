import type { WorkbenchJobView } from './jobSchema'
import { JobArtifactError } from './jobTransport'

const MiB = 1024 * 1024
export const RC_REVIEW_DEFAULT_RESULT_BYTES = 64 * MiB
export const RC_REVIEW_MAX_RESULT_BYTES = 128 * MiB
// Preserve the aggregate of the original role limits, even with a larger result.
export const RC_REVIEW_TOTAL_BYTES = 224 * MiB

/** Trusted host policy only; never derived from a job, media type or URL. */
export function admitRcReviewArtifacts(job: WorkbenchJobView, resultMaximum = RC_REVIEW_DEFAULT_RESULT_BYTES) {
  if (!Number.isSafeInteger(resultMaximum) || resultMaximum <= 0 || resultMaximum > RC_REVIEW_MAX_RESULT_BYTES) {
    throw new JobArtifactError('rc_review_budget_invalid')
  }
  const limits = { request: 16 * MiB, checkpoint: 128 * MiB, result: resultMaximum, evidence: 16 * MiB }
  let total = 0
  for (const role of ['request', 'checkpoint', 'result', 'evidence'] as const) {
    const reference = job[role]
    if (!reference) continue
    if (!Number.isSafeInteger(reference.byte_length) || reference.byte_length <= 0) throw new JobArtifactError('rc_review_length_invalid')
    if (reference.byte_length > limits[role]) throw new JobArtifactError(`rc_${role}_too_large`)
    total += reference.byte_length
    if (total > RC_REVIEW_TOTAL_BYTES) throw new JobArtifactError('rc_artifacts_too_large')
  }
  return limits
}
