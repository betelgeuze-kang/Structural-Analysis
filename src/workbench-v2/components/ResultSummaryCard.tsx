import type { ReactElement } from 'react'
import { isAvailableValue, type WorkbenchCaseV2 } from '../model/caseSchema'
import { BooleanEvidenceValueText, EngineeringValueText } from './EngineeringValueText'

interface ResultSummaryCardProps {
  caseV2: WorkbenchCaseV2
  convergenceAvailable: boolean
}

type Verdict = 'converged' | 'failed' | 'unavailable' | 'invalid' | 'unsupported'

/**
 * Single-glance result card. Explicit execution failure remains visible even
 * though numerical convergence is unavailable. Numerical convergence is shown
 * only from the explicit converged evidence and is never inferred from residual
 * history, tolerance comparison, or job completion.
 */
export function ResultSummaryCard({ caseV2, convergenceAvailable }: ResultSummaryCardProps): ReactElement {
  const analysis = caseV2.analysis
  const executionFailed = analysis?.status === 'failed'
  const verdict: Verdict = !analysis
    ? 'unavailable'
    : executionFailed
      ? 'failed'
      : !convergenceAvailable || !isAvailableValue(analysis.converged)
        ? analysis.converged.status
        : analysis.converged.value
          ? 'converged'
          : 'failed'

  const verdictLabel =
    verdict === 'converged'
      ? 'Converged'
      : verdict === 'failed'
        ? executionFailed
          ? 'Analysis failed'
          : 'Did not converge'
        : `Convergence ${verdict}`
  const chipClass =
    verdict === 'converged'
      ? 'wb2-chip--live'
      : verdict === 'failed' || verdict === 'invalid'
        ? 'wb2-chip--blocked'
        : 'wb2-chip--unavailable'

  const withinTolerance =
    analysis != null
    && isAvailableValue(analysis.finalNormalizedResidual)
    && isAvailableValue(analysis.residualTolerance)
      ? analysis.finalNormalizedResidual.value <= analysis.residualTolerance.value
      : null

  return (
    <section className="wb2-panel wb2-result-card" aria-labelledby="wb2-result-title" data-result-verdict={verdict}>
      <h2 id="wb2-result-title" className="wb2-panel__title">Result summary</h2>

      <div className="wb2-result-head">
        <span className={`wb2-chip ${chipClass}`} data-result-chip>{verdictLabel}</span>
        {executionFailed ? (
          <span className="wb2-result-sub">
            Execution failed; numerical convergence is unavailable and is not inferred.
          </span>
        ) : verdict !== 'converged' && verdict !== 'failed' ? (
          <span className="wb2-result-sub">
            {analysis
              ? 'Convergence status is unavailable — it is not inferred from the attached values.'
              : 'No analysis attached — status is not inferred.'}
          </span>
        ) : (
          <span className="wb2-result-sub">
            {analysis!.type} · {analysis!.solver}
          </span>
        )}
      </div>

      {analysis ? (
        <dl className="wb2-result-metrics">
          <div className="wb2-result-metric">
            <dt>Converged</dt>
            <dd><BooleanEvidenceValueText value={analysis.converged} /></dd>
          </div>
          <div className="wb2-result-metric">
            <dt>Final residual</dt>
            <dd className="wb2-mono"><EngineeringValueText value={analysis.finalNormalizedResidual} /></dd>
          </div>
          <div className="wb2-result-metric">
            <dt>Tolerance</dt>
            <dd className="wb2-mono"><EngineeringValueText value={analysis.residualTolerance} /></dd>
          </div>
          <div className="wb2-result-metric">
            <dt>Iterations</dt>
            <dd className="wb2-mono"><EngineeringValueText value={analysis.iterationCount} integer /></dd>
          </div>
          <div className="wb2-result-metric">
            <dt>Load scale</dt>
            <dd className="wb2-mono"><EngineeringValueText value={analysis.loadScale} /></dd>
          </div>
        </dl>
      ) : (
        <p className="wb2-unavailable" data-wb2-unavailable>
          Convergence information is not present in this case.
        </p>
      )}

      {analysis ? (
        <p
          className={`wb2-result-tol${withinTolerance === true ? ' is-ok' : withinTolerance === false ? ' is-no' : ''}`}
          data-result-within-tol={withinTolerance == null ? 'unavailable' : String(withinTolerance)}
        >
          {withinTolerance == null
            ? 'Tolerance comparison is unavailable unless both values are available.'
            : withinTolerance
              ? 'Final residual is at or below the requested tolerance.'
              : 'Final residual is above the requested tolerance.'}
        </p>
      ) : null}
    </section>
  )
}
