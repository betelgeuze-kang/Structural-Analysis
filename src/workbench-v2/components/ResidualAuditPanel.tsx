import type { ReactElement } from 'react'
import type { ResidualStep } from '../model/caseSchema'

function fmt(value: number): string {
  if (value !== 0 && (Math.abs(value) < 1e-3 || Math.abs(value) >= 1e6)) return value.toExponential(3)
  return Number.isInteger(value) ? String(value) : value.toFixed(4).replace(/0+$/, '').replace(/\.$/, '')
}

interface ResidualAuditPanelProps {
  residualHistory: ResidualStep[]
  sourceLabel: string
}

export function ResidualAuditPanel({ residualHistory, sourceLabel }: ResidualAuditPanelProps): ReactElement {
  return (
    <section className="wb2-panel" aria-labelledby="wb2-residual-title">
      <h2 id="wb2-residual-title" className="wb2-panel__title">Residual audit</h2>
      {residualHistory.length ? (
        <>
          <div className="wb2-table-scroll" role="region" aria-label="Residual history table" tabIndex={0}>
            <table className="wb2-table">
              <thead>
                <tr>
                  <th className="wb2-num">Iter</th>
                  <th className="wb2-num">Residual</th>
                  <th className="wb2-num">Rel. increment</th>
                  <th className="wb2-num">Alpha</th>
                </tr>
              </thead>
              <tbody>
                {residualHistory.map((step) => (
                  <tr key={step.iteration}>
                    <td className="wb2-num">{step.iteration}</td>
                    <td className="wb2-num">{fmt(step.residual)}</td>
                    <td className="wb2-num">{fmt(step.relativeIncrement)}</td>
                    <td className="wb2-num">{fmt(step.alpha)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="wb2-provenance" data-wb2-provenance>Source: {sourceLabel}</p>
        </>
      ) : (
        <p className="wb2-unavailable" data-wb2-unavailable>
          No residual history attached. Convergence trace cannot be shown for this case.
        </p>
      )}
    </section>
  )
}
