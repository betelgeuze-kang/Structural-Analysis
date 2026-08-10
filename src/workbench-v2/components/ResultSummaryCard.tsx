import type { ReactElement } from 'react'
import { isAvailableValue, type WorkbenchCaseV2 } from '../model/caseSchema'
import { deriveResultVerdict } from '../model/workbenchState'
import { BooleanEvidenceValueText, EngineeringValueText } from './EngineeringValueText'

interface ResultSummaryCardProps {
  caseV2: WorkbenchCaseV2
  convergenceAvailable: boolean
}

/**
 * Single-glance result card. Explicit execution failure, execution blocking,
 * and completed numerical non-convergence remain distinct. Numerical
 * convergence is shown only from explicit evidence and is never inferred from
 * residual history, tolerance comparison, or job completion.
 */
export function ResultSummaryCard({ caseV2, convergenceAvailable }: ResultSummaryCardProps): ReactElement {
  const analysis = caseV2.analysis
  const verdict = deriveResultVerdict(caseV2, convergenceAvailable)

  const verdictLabel =
    verdict === 'converged'
      ? 'Converged'
      : verdict === 'not_converged'
        ? 'Did not converge'
        : verdict === 'failed'
          ? 'Analysis failed'
          : verdict === 'blocked'
            ? 'Analysis blocked'
            : `Convergence ${verdict}`
  const chipClass =
    verdict === 'converged'
      ? 'wb2-chip--live'
      : verdict === 'failed' || verdict === 'not_converged' || verdict === 'blocked' || verdict === 'invalid'
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
        {verdict === 'failed' ? (
          <span className="wb2-result-sub">
            Execution failed; numerical convergence is unavailable and is not inferred.
          </span>
        ) : verdict === 'blocked' ? (
          <span className="wb2-result-sub">
            Execution was blocked before a numerical convergence outcome.
          </span>
        ) : analysis && (verdict === 'converged' || verdict === 'not_converged') ? (
          <span className="wb2-result-sub">
            {analysis.type} · {analysis.solver}
          </span>
        ) : (
          <span className="wb2-result-sub">
            {analysis
              ? 'Convergence status is unavailable — it is not inferred from the attached values.'
              : 'No analysis attached — status is not inferred.'}
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
