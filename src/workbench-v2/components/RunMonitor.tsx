import type { ReactElement } from 'react'
import {
  evidenceValue,
  formatEvidence,
  type CaseAnalysis,
  type EvidenceValue,
  type ResidualStep,
} from '../model/caseSchema'
import type { RunStatus } from '../model/workbenchState'
import { StateChip } from './StateChip'

interface RunMonitorProps {
  runStatus: RunStatus
  analysis?: CaseAnalysis
  residualHistory: EvidenceValue<ResidualStep[]>
  convergenceAvailable: boolean
}

function fmt(value: number): string {
  if (value !== 0 && (Math.abs(value) < 1e-3 || Math.abs(value) >= 1e6)) return value.toExponential(3)
  return Number.isInteger(value) ? String(value) : value.toFixed(4).replace(/0+$/, '').replace(/\.$/, '')
}

const STATUS_LABEL: Record<RunStatus, string> = {
  idle: 'Idle',
  validating: 'Validating',
  running: 'Running',
  converged: 'Converged',
  failed: 'Did not converge',
}

/**
 * Run Monitor. Shows live-style progress derived only from the attached
 * analysis: recorded iterations vs. the iteration count, the latest residual,
 * and how it stands against tolerance. When convergence information is absent,
 * the whole panel reports UNAVAILABLE and infers nothing.
 */
export function RunMonitor({ runStatus, analysis, residualHistory, convergenceAvailable }: RunMonitorProps): ReactElement {
  if (!convergenceAvailable || !analysis) {
    return (
      <section className="wb2-panel" aria-labelledby="wb2-run-title" data-run-monitor="unavailable">
        <h2 id="wb2-run-title" className="wb2-panel__title">Run Monitor</h2>
        <div className="wb2-run-head">
          <StateChip state="UNAVAILABLE" srLabel="Run status" />
        </div>
        <p className="wb2-unavailable" data-wb2-unavailable>
          No convergence information is attached to this case; run progress is not inferred.
        </p>
      </section>
    )
  }

  const history = evidenceValue(residualHistory)
  const recorded = history?.length ?? null
  const total = evidenceValue(analysis.iterationCount)
  const pct =
    recorded != null && total != null && total > 0
      ? Math.min(100, Math.round((recorded / total) * 100))
      : 0
  const latest = history?.length ? history[history.length - 1] : null
  const finalResidual = evidenceValue(analysis.finalNormalizedResidual)
  const residualTolerance = evidenceValue(analysis.residualTolerance)
  const withinTolerance =
    finalResidual != null && residualTolerance != null
      ? finalResidual <= residualTolerance
      : null
  const statusState = runStatus === 'converged' ? 'LIVE' : runStatus === 'failed' ? 'BLOCKED' : 'UNAVAILABLE'

  return (
    <section className="wb2-panel" aria-labelledby="wb2-run-title" data-run-monitor={runStatus}>
      <h2 id="wb2-run-title" className="wb2-panel__title">Run Monitor</h2>

      <div className="wb2-run-head">
        <StateChip state={statusState} srLabel="Run status" />
        <span className="wb2-run-status-label" data-run-status>{STATUS_LABEL[runStatus]}</span>
      </div>

      <div
        className="wb2-run-progress"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={total ?? 1}
        aria-valuenow={recorded ?? undefined}
        aria-label="Recorded iterations"
        data-run-progress={pct}
      >
        <div className="wb2-run-progress__bar" style={{ width: `${pct}%` }} />
      </div>
      <p className="wb2-run-progress__caption">
        {formatEvidence(residualHistory, (rows) => String(rows.length))} of{' '}
        {formatEvidence(analysis.iterationCount, String)} iteration(s) recorded · load scale{' '}
        {formatEvidence(analysis.loadScale, fmt)}
      </p>

      <dl className="wb2-kv">
        <dt>Latest residual</dt><dd className="wb2-mono">
          {latest
            ? formatEvidence(latest.residual, fmt)
            : formatEvidence(residualHistory, () => 'NO RECORDED ITERATION')}
        </dd>
        <dt>Final residual</dt><dd className="wb2-mono">{formatEvidence(analysis.finalNormalizedResidual, fmt)}</dd>
        <dt>Tolerance</dt><dd className="wb2-mono">{formatEvidence(analysis.residualTolerance, fmt)}</dd>
        <dt>Final rel. increment</dt><dd className="wb2-mono">{formatEvidence(analysis.finalRelativeIncrement, fmt)}</dd>
      </dl>

      <p
        className={`wb2-result-tol${withinTolerance == null ? '' : withinTolerance ? ' is-ok' : ' is-no'}`}
        data-run-within-tol={withinTolerance == null ? 'unavailable' : String(withinTolerance)}
      >
        {withinTolerance == null
          ? 'Tolerance comparison is UNAVAILABLE because one or both required values are not available.'
          : withinTolerance
          ? 'Final residual is at or below tolerance.'
          : 'Final residual is above tolerance — run is not converged.'}
      </p>
    </section>
  )
}
