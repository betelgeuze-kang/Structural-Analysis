import type { ReactElement } from 'react'
import type { RunStatus } from '../model/workbenchState'
import type { CaseAnalysis } from '../model/caseSchema'
import { StateChip } from './StateChip'
import { EngineeringValueText } from './EngineeringValueText'

const STAGES: { key: RunStatus; label: string }[] = [
  { key: 'idle', label: 'Idle' },
  { key: 'validating', label: 'Validating' },
  { key: 'running', label: 'Running' },
  { key: 'converged', label: 'Converged' },
]

interface AnalysisRibbonProps {
  runStatus: RunStatus
  analysis?: CaseAnalysis
  convergenceAvailable: boolean
}

export function AnalysisRibbon({ runStatus, analysis, convergenceAvailable }: AnalysisRibbonProps): ReactElement {
  const activeIndex = STAGES.findIndex((s) => s.key === runStatus)
  const failed = runStatus === 'failed'

  return (
    <section className="wb2-panel wb2-ribbon" aria-labelledby="wb2-ribbon-title">
      <h2 id="wb2-ribbon-title" className="wb2-panel__title">Analysis</h2>

      {convergenceAvailable ? (
        <ol className="wb2-ribbon-steps" aria-label="Analysis stages">
          {STAGES.map((stage, index) => {
            const isActive = !failed && activeIndex >= 0 && index <= activeIndex
            const isCurrent = !failed && index === activeIndex
            return (
              <li
                key={stage.key}
                className={`wb2-ribbon-step${isActive ? ' is-active' : ''}${isCurrent ? ' is-current' : ''}`}
                aria-current={isCurrent ? 'step' : undefined}
              >
                <span className="wb2-ribbon-dot" aria-hidden="true" />
                {stage.label}
              </li>
            )
          })}
        </ol>
      ) : (
        <div className="wb2-ribbon-steps">
          <StateChip state="UNAVAILABLE" srLabel="Convergence" />
          <p className="wb2-note">Convergence information is not present in this case; run status is not inferred.</p>
        </div>
      )}

      {failed ? <p className="wb2-note wb2-note--warn">Run did not converge.</p> : null}

      {analysis ? (
        <dl className="wb2-kv wb2-analysis-kv">
          <dt>Type</dt><dd>{analysis.type}</dd>
          <dt>Solver</dt><dd>{analysis.solver}</dd>
          <dt>Load scale</dt><dd><EngineeringValueText value={analysis.loadScale} /></dd>
          <dt>Iterations</dt><dd><EngineeringValueText value={analysis.iterationCount} integer /></dd>
          <dt>Residual tolerance</dt><dd><EngineeringValueText value={analysis.residualTolerance} /></dd>
          <dt>Final normalized residual</dt><dd><EngineeringValueText value={analysis.finalNormalizedResidual} /></dd>
          <dt>Final relative increment</dt><dd><EngineeringValueText value={analysis.finalRelativeIncrement} /></dd>
        </dl>
      ) : null}
    </section>
  )
}
