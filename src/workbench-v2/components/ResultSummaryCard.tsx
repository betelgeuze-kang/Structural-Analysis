import type { ReactElement } from 'react'
import type { WorkbenchCaseV2 } from '../model/caseSchema'

interface ResultSummaryCardProps {
  caseV2: WorkbenchCaseV2
  convergenceAvailable: boolean
}

type Verdict = 'converged' | 'failed' | 'unavailable'

function fmt(value: number): string {
  if (value !== 0 && (Math.abs(value) < 1e-3 || Math.abs(value) >= 1e6)) return value.toExponential(3)
  return Number.isInteger(value) ? String(value) : value.toFixed(4).replace(/0+$/, '').replace(/\.$/, '')
}

/**
 * Single-glance result card. The verdict is derived only from explicit analysis
 * data: converged true/false from the case, or UNAVAILABLE when convergence
 * information is absent. Nothing is inferred from residual history length.
 */
export function ResultSummaryCard({ caseV2, convergenceAvailable }: ResultSummaryCardProps): ReactElement {
  const analysis = caseV2.analysis
  const verdict: Verdict = !convergenceAvailable || !analysis ? 'unavailable' : analysis.converged ? 'converged' : 'failed'

  const verdictLabel =
    verdict === 'converged' ? 'Converged' : verdict === 'failed' ? 'Did not converge' : 'Convergence unavailable'
  const chipClass =
    verdict === 'converged' ? 'wb2-chip--live' : verdict === 'failed' ? 'wb2-chip--blocked' : 'wb2-chip--unavailable'

  const withinTolerance =
    analysis != null ? analysis.finalNormalizedResidual <= analysis.residualTolerance : null

  return (
    <section className="wb2-panel wb2-result-card" aria-labelledby="wb2-result-title" data-result-verdict={verdict}>
      <h2 id="wb2-result-title" className="wb2-panel__title">Result summary</h2>

      <div className="wb2-result-head">
        <span className={`wb2-chip ${chipClass}`} data-result-chip>{verdictLabel}</span>
        {verdict === 'unavailable' ? (
          <span className="wb2-result-sub">No analysis attached — status is not inferred.</span>
        ) : (
          <span className="wb2-result-sub">
            {analysis!.type} · {analysis!.solver}
          </span>
        )}
      </div>

      {analysis ? (
        <dl className="wb2-result-metrics">
          <div className="wb2-result-metric">
            <dt>Final residual</dt>
            <dd className="wb2-mono">{fmt(analysis.finalNormalizedResidual)}</dd>
          </div>
          <div className="wb2-result-metric">
            <dt>Tolerance</dt>
            <dd className="wb2-mono">{fmt(analysis.residualTolerance)}</dd>
          </div>
          <div className="wb2-result-metric">
            <dt>Iterations</dt>
            <dd className="wb2-mono">{analysis.iterationCount}</dd>
          </div>
          <div className="wb2-result-metric">
            <dt>Load scale</dt>
            <dd className="wb2-mono">{fmt(analysis.loadScale)}</dd>
          </div>
        </dl>
      ) : (
        <p className="wb2-unavailable" data-wb2-unavailable>
          Convergence information is not present in this case.
        </p>
      )}

      {analysis ? (
        <p className={`wb2-result-tol${withinTolerance ? ' is-ok' : ' is-no'}`} data-result-within-tol={String(withinTolerance)}>
          {withinTolerance
            ? 'Final residual is at or below the requested tolerance.'
            : 'Final residual is above the requested tolerance.'}
        </p>
      ) : null}
    </section>
  )
}
