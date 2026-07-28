import type { ReactElement } from 'react'
import type { RunStatus } from '../model/workbenchState'
import {
  evidenceField,
  formatEvidence,
  type CaseAnalysis,
} from '../model/caseSchema'
import { StateChip } from './StateChip'

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

function fmt(value: number): string {
  if (value !== 0 && (Math.abs(value) < 1e-3 || Math.abs(value) >= 1e6)) return value.toExponential(3)
  return Number.isInteger(value) ? String(value) : value.toFixed(4).replace(/0+$/, '').replace(/\.$/, '')
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
          <dt>Type</dt><dd>{formatEvidence(analysis.type)}</dd>
          <dt>Solver</dt><dd>{formatEvidence(analysis.solver)}</dd>
          <dt>Load scale</dt><dd>{formatEvidence(analysis.loadScale, fmt)}</dd>
          <dt>Iterations</dt><dd>{formatEvidence(analysis.iterationCount, String)}</dd>
          <dt>Residual tolerance</dt><dd>{formatEvidence(analysis.residualTolerance, fmt)}</dd>
          <dt>Final normalized residual</dt><dd>{formatEvidence(analysis.finalNormalizedResidual, fmt)}</dd>
          <dt>Final relative increment</dt><dd>{formatEvidence(analysis.finalRelativeIncrement, fmt)}</dd>
          <dt>Characteristic length</dt><dd>
            {formatEvidence(
              evidenceField(analysis.equationScaling, (value) => value.characteristicLength),
              fmt,
            )}
          </dd>
          <dt>Scaled residual</dt><dd>
            {formatEvidence(
              evidenceField(analysis.equationScaling, (value) => value.dimensionlessScaledResidual),
              fmt,
            )}
          </dd>
          <dt>Scaled increment</dt><dd>
            {formatEvidence(
              evidenceField(analysis.equationScaling, (value) => value.dimensionlessScaledIncrement),
              fmt,
            )}
          </dd>
          <dt>Scaled condition</dt><dd>
            {formatEvidence(
              evidenceField(analysis.equationScaling, (value) => value.scaledConditionNumber),
              fmt,
            )}
          </dd>
          <dt>Scaling hash</dt><dd className="wb2-mono">
            {formatEvidence(
              evidenceField(analysis.equationScaling, (value) => value.scalingHash),
              (value) => value.slice(0, 19),
            )}
          </dd>
        </dl>
      ) : null}
    </section>
  )
}
