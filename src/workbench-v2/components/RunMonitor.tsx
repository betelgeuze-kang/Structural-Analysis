import type { ReactElement } from 'react'
import type { CaseAnalysis, ResidualStep } from '../model/caseSchema'
import type { RunStatus } from '../model/workbenchState'
import { StateChip } from './StateChip'

interface RunMonitorProps {
  runStatus: RunStatus
  analysis?: CaseAnalysis
  residualHistory: ResidualStep[]
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

  const recorded = residualHistory.length
  const total = Math.max(analysis.iterationCount, recorded)
  const pct = total > 0 ? Math.min(100, Math.round((recorded / total) * 100)) : 0
  const latest = recorded ? residualHistory[recorded - 1] : null
  const withinTolerance = analysis.finalNormalizedResidual <= analysis.residualTolerance
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
        aria-valuemax={total}
        aria-valuenow={recorded}
        aria-label="Recorded iterations"
        data-run-progress={pct}
      >
        <div className="wb2-run-progress__bar" style={{ width: `${pct}%` }} />
      </div>
      <p className="wb2-run-progress__caption">
        {recorded} of {total} iteration(s) recorded · load scale {fmt(analysis.loadScale)}
      </p>

      <dl className="wb2-kv">
        <dt>Latest residual</dt><dd className="wb2-mono">{latest ? fmt(latest.residual) : 'n/a'}</dd>
        <dt>Final residual</dt><dd className="wb2-mono">{fmt(analysis.finalNormalizedResidual)}</dd>
        <dt>Tolerance</dt><dd className="wb2-mono">{fmt(analysis.residualTolerance)}</dd>
        <dt>Final rel. increment</dt><dd className="wb2-mono">{fmt(analysis.finalRelativeIncrement)}</dd>
      </dl>

      <p className={`wb2-result-tol${withinTolerance ? ' is-ok' : ' is-no'}`} data-run-within-tol={String(withinTolerance)}>
        {withinTolerance
          ? 'Final residual is at or below tolerance.'
          : 'Final residual is above tolerance — run is not converged.'}
      </p>
    </section>
  )
}
