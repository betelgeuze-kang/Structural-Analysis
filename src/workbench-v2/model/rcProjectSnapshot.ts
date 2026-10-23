import type { RcProjectFile, RcProjectJobRef } from './rcProjectFile'

const reference = (value: RcProjectJobRef | null): RcProjectJobRef | null => value ? { jobId: value.jobId, requestHash: value.requestHash } : null

/** Snapshot only exportable authoring custody. Large immutable request strings
 * are shared; mutable outer wrappers and job references are copied.
 */
export function snapshotRcProject(project: RcProjectFile): RcProjectFile {
  return {
    schema: project.schema, scope: { ...project.scope }, draft: project.draft,
    submission: project.submission ? { serialized: project.submission.serialized, idempotencyKey: project.submission.idempotencyKey, job: reference(project.submission.job) } : null,
    selectedJob: reference(project.selectedJob),
    changedRun: project.changedRun ? { original: reference(project.changedRun.original)!, child: reference(project.changedRun.child) } : null,
    scenarios: project.scenarios.map(row => ({ intent: { id: row.intent.id, name: row.intent.name, serialized: row.intent.serialized, idempotencyKey: row.intent.idempotencyKey }, attempted: row.attempted, job: reference(row.job) })),
    baselineId: project.baselineId, variantId: project.variantId,
  }
}
function sameRef(a: RcProjectJobRef | null, b: RcProjectJobRef | null): boolean {
  return a === null || b === null ? a === b : a.jobId === b.jobId && a.requestHash === b.requestHash
}

/** Exact structural equality, without JSON parsing, serialization or encoding.
 * Poll status/results are deliberately absent from the portable file contract.
 */
export function sameRcProject(a: RcProjectFile, b: RcProjectFile): boolean {
  return a.schema === b.schema && a.scope.collectionUrl === b.scope.collectionUrl && a.scope.tenantId === b.scope.tenantId
    && a.draft === b.draft && sameRef(a.selectedJob, b.selectedJob)
    && (a.submission === null || b.submission === null ? a.submission === b.submission
      : a.submission.serialized === b.submission.serialized && a.submission.idempotencyKey === b.submission.idempotencyKey && sameRef(a.submission.job, b.submission.job))
    && (a.changedRun === null || b.changedRun === null ? a.changedRun === b.changedRun
      : sameRef(a.changedRun.original, b.changedRun.original) && sameRef(a.changedRun.child, b.changedRun.child))
    && a.baselineId === b.baselineId && a.variantId === b.variantId && a.scenarios.length === b.scenarios.length
    && a.scenarios.every((row, index) => {
      const other = b.scenarios[index]
      return row.intent.id === other.intent.id && row.intent.name === other.intent.name && row.intent.serialized === other.intent.serialized
        && row.intent.idempotencyKey === other.intent.idempotencyKey && row.attempted === other.attempted && sameRef(row.job, other.job)
    })
}

/** An initial session has no export baseline. Scope alone is not authored work. */
export function emptyRcProject(project: RcProjectFile): boolean {
  return project.draft === '' && project.submission === null && project.selectedJob === null && project.changedRun === null
    && project.scenarios.length === 0 && project.baselineId === null && project.variantId === null
}
