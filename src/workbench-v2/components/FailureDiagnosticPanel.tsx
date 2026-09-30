import type { ReactElement } from 'react'
import type { FailureDiagnosticReview } from '../model/failureDiagnostic'

export function FailureDiagnosticPanel({ review }: { review: FailureDiagnosticReview }): ReactElement {
  const path = review.observed
  function download(bytes: Uint8Array, name: string): void {
    const url = URL.createObjectURL(new Blob([new Uint8Array(bytes).buffer], { type: 'application/json' }))
    const link = document.createElement('a')
    link.href = url; link.download = name; link.click()
    setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  return <section aria-label="Failed attempt diagnostics" data-failure-diagnostic="verified">
    <h3>Failed attempt {review.attempt}</h3>
    <p>Stored failure diagnostics only. No accepted numerical or engineering result is available.</p>
    <dl className="wb2-kv">
      <dt>Attempted steps</dt><dd data-failure-attempted>{path?.attempted ?? 'unavailable'}</dd>
      <dt>Committed steps before failure</dt><dd data-failure-committed>{path?.committed ?? 'unavailable'}</dd>
      <dt>Replayed prefix steps</dt><dd>{path?.replayed ?? 'unavailable'}</dd>
      <dt>Newly attempted steps</dt><dd>{path?.newlyAttempted ?? 'unavailable'}</dd>
      <dt>Recorded history rows</dt><dd data-failure-history-rows>{path?.historyRows ?? 'unavailable'}</dd>
      <dt>Source revision</dt><dd style={{ overflowWrap: 'anywhere' }}>{review.sourceRevision ?? 'unavailable in this request'}</dd>
      <dt>Model identity check</dt><dd>{review.modelIdentityVerification === 'service_normalized_model_ir' ? 'Normalized by the service' : 'Original neutral model bytes checked in browser'}</dd>
    </dl>
    <p data-failure-cost-scope>History rows do not count all solves or line searches. Total API work is unverified.</p>
    {path ? <ol aria-label="Observed failed load path">
      {path.steps.map((step, index) => <li key={index} data-failure-step>
        Step {index + 1} · load factor {step.target} · {step.committed ? 'committed' : 'failed'} · {step.historyRows} history rows.
        {' '}Reason: <span style={{ overflowWrap: 'anywhere' }}>{step.reason ?? 'unavailable'}</span>.
        {!step.committed ? <span data-failure-rollback> Rollback: {step.rollbackExact ? 'exact' : 'not exact'}.</span> : null}
      </li>)}
    </ol> : <p data-failure-work-unavailable>The source contains no observed path. This does not mean zero work.</p>}
    <button type="button" className="wb2-btn" onClick={() => download(review.diagnosticBytes, `failure-attempt-${review.attempt}.json`)}>Download original diagnostic</button>
    <button type="button" className="wb2-btn" onClick={() => download(review.resultBytes, `failure-result-${review.attempt}.json`)}>Download original failed result</button>
  </section>
}
