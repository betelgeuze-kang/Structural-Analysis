import type { ReactElement } from 'react'
import {
  isAvailableValue,
  type CaseAnalysis,
  type EngineeringValue,
  type ResidualStep,
} from '../model/caseSchema'
import type { RunStatus } from '../model/workbenchState'
import { BooleanEvidenceValueText, EngineeringValueText } from './EngineeringValueText'
import { StateChip } from './StateChip'

interface RunMonitorProps {
  runStatus: RunStatus
  analysis?: CaseAnalysis
  residualHistory: ResidualStep[]
  convergenceAvailable: boolean
}

const STATUS_LABEL: Record<RunStatus, string> = {
  idle: 'Idle',
  validating: 'Validating',
  running: 'Running',
  converged: 'Converged',
  not_converged: 'Did not converge',
  failed: 'Did not converge',
  blocked: 'Blocked',
  not_run: 'Not run',
}

/**
 * Run Monitor. Shows live-style progress derived only from the attached
 * analysis: recorded iterations vs. the iteration count, the latest residual,
 * and how it stands against tolerance. When convergence information is absent,
 * the whole panel reports UNAVAILABLE and infers nothing.
 */
export function RunMonitor({ runStatus, analysis, residualHistory, convergenceAvailable }: RunMonitorProps): ReactElement {
  if (!analysis) {
    return (
      <section className="wb2-panel" aria-labelledby="wb2-run-title" data-run-monitor="unavailable">
        <h2 id="wb2-run-title" className="wb2-panel__title">Run Monitor</h2>
        <div className="wb2-run-head">
          <StateChip state="UNAVAILABLE" srLabel="Run status" />
        </div>
        <p className="wb2-unavailable" data-wb2-unavailable>
          No analysis is attached to this case; run progress is not inferred.
        </p>
      </section>
    )
  }

  const usableSteps = residualHistory.filter(
    (step) => isAvailableValue(step.iteration) && isAvailableValue(step.residual),
  )
  const recorded = usableSteps.length
  const total = isAvailableValue(analysis.iterationCount) ? analysis.iterationCount.value : null
  const pct = total != null && total > 0 ? Math.min(100, Math.round((recorded / total) * 100)) : 0
  const latestResidual: EngineeringValue = usableSteps.length
    ? usableSteps[usableSteps.length - 1].residual
    : { status: 'unavailable' }
  const withinTolerance =
    isAvailableValue(analysis.finalNormalizedResidual) && isAvailableValue(analysis.residualTolerance)
      ? analysis.finalNormalizedResidual.value <= analysis.residualTolerance.value
      : null
  const statusState = runStatus === 'converged'
    ? 'LIVE'
    : runStatus === 'failed' || runStatus === 'not_converged' || runStatus === 'blocked'
      ? 'BLOCKED'
      : 'UNAVAILABLE'

  return (
    <section className="wb2-panel" aria-labelledby="wb2-run-title" data-run-monitor={runStatus}>
      <h2 id="wb2-run-title" className="wb2-panel__title">Run Monitor</h2>

      <div className="wb2-run-head">
        <StateChip state={statusState} srLabel="Run status" />
        <span className="wb2-run-status-label" data-run-status>{STATUS_LABEL[runStatus]}</span>
      </div>

      {total != null ? (
        <div
          className="wb2-run-progress"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={Math.max(total, recorded)}
          aria-valuenow={recorded}
          aria-label="Recorded iterations"
          data-run-progress={pct}
        >
          <div className="wb2-run-progress__bar" style={{ width: `${pct}%` }} />
        </div>
      ) : null}
      <p className="wb2-run-progress__caption">
        {recorded} recorded of <EngineeringValueText value={analysis.iterationCount} integer /> iteration(s) · load scale{' '}
        <EngineeringValueText value={analysis.loadScale} />
      </p>

      <dl className="wb2-kv">
        <dt>Converged</dt><dd><BooleanEvidenceValueText value={analysis.converged} /></dd>
        <dt>Latest residual</dt><dd className="wb2-mono"><EngineeringValueText value={latestResidual} /></dd>
        <dt>Final residual</dt><dd className="wb2-mono"><EngineeringValueText value={analysis.finalNormalizedResidual} /></dd>
        <dt>Tolerance</dt><dd className="wb2-mono"><EngineeringValueText value={analysis.residualTolerance} /></dd>
        <dt>Final rel. increment</dt><dd className="wb2-mono"><EngineeringValueText value={analysis.finalRelativeIncrement} /></dd>
      </dl>

      {!convergenceAvailable ? (
        <p className="wb2-unavailable" data-wb2-unavailable>
          Convergence is not available for status {analysis.status}; it is not inferred from progress or job completion.
        </p>
      ) : null}

      <p
        className={`wb2-result-tol${withinTolerance === true ? ' is-ok' : withinTolerance === false ? ' is-no' : ''}`}
        data-run-within-tol={withinTolerance == null ? 'unavailable' : String(withinTolerance)}
      >
        {withinTolerance == null
          ? 'Tolerance comparison is unavailable unless both values are available.'
          : withinTolerance
            ? 'Final residual is at or below tolerance.'
            : 'Final residual is above tolerance — run is not converged.'}
      </p>
    </section>
  )
}
