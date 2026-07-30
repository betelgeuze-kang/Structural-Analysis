import type { ReactElement } from 'react'
import {
  type CaseAnalysis,
  type EngineeringValue,
  type TextValue,
} from '../model/caseSchema'
import { EngineeringValueText } from './EngineeringValueText'

interface EquationScalingPanelProps {
  analysis?: CaseAnalysis
}

function ExplicitText({ value }: { value: TextValue }): ReactElement {
  if (value.status === 'available') {
    return (
      <span className="wb2-engineering-value" data-engineering-value-state="available">
        {value.value}
      </span>
    )
  }
  return (
    <span
      className={`wb2-engineering-value wb2-engineering-value--${value.status}`}
      data-engineering-value-state={value.status}
      title={value.status === 'unavailable' ? 'Evidence is unavailable' : value.reason}
    >
      {value.status.toUpperCase()}
    </span>
  )
}

const NUMERIC_ROWS: Array<{
  key: keyof Omit<CaseAnalysis['equationScaling6DOF'], 'scaling_hash'>
  label: string
}> = [
  { key: 'reference_force', label: 'Reference force' },
  { key: 'characteristic_length', label: 'Characteristic length' },
  { key: 'translation_residual_norm', label: 'Translation residual norm' },
  { key: 'rotation_residual_norm', label: 'Rotation residual norm' },
  { key: 'scaled_residual_norm', label: 'Scaled residual norm' },
  { key: 'translation_increment_norm', label: 'Translation increment norm' },
  { key: 'rotation_increment_norm', label: 'Rotation increment norm' },
  { key: 'scaled_increment_norm', label: 'Scaled increment norm' },
  { key: 'scaled_tangent_condition', label: 'Scaled tangent condition' },
]

/** Exposes the shared solver scaling receipt without filling absent values. */
export function EquationScalingPanel({ analysis }: EquationScalingPanelProps): ReactElement {
  if (!analysis) {
    return (
      <section className="wb2-panel" data-equation-scaling-6dof="unavailable">
        <h2 className="wb2-panel__title">6DOF equation scaling</h2>
        <p className="wb2-unavailable" data-wb2-unavailable>No analysis scaling receipt is attached.</p>
      </section>
    )
  }
  const scaling = analysis.equationScaling6DOF
  return (
    <section className="wb2-panel" data-equation-scaling-6dof>
      <h2 className="wb2-panel__title">6DOF equation scaling</h2>
      <dl className="wb2-kv">
        {NUMERIC_ROWS.map((row) => (
          <div key={row.key}>
            <dt>{row.label}</dt>
            <dd className="wb2-mono">
              <EngineeringValueText value={scaling[row.key] as EngineeringValue} />
            </dd>
          </div>
        ))}
        <div>
          <dt>Scaling hash</dt>
          <dd className="wb2-mono"><ExplicitText value={scaling.scaling_hash} /></dd>
        </div>
      </dl>
    </section>
  )
}
