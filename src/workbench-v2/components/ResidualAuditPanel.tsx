import type { ReactElement } from 'react'

interface ResidualAuditPanelProps {
  residualHistory: number[]
  sourceLabel: string
}

export function ResidualAuditPanel({ residualHistory, sourceLabel }: ResidualAuditPanelProps): ReactElement {
  return (
    <section className="wb2-panel" aria-labelledby="wb2-residual-title">
      <h2 id="wb2-residual-title" className="wb2-panel__title">Residual audit</h2>
      {residualHistory.length ? (
        <>
          <ol className="wb2-residual-list">
            {residualHistory.map((value, index) => (
              <li key={index}>
                <span className="wb2-residual-step">#{index + 1}</span>
                <span className="wb2-residual-value">{value.toExponential(3)}</span>
              </li>
            ))}
          </ol>
          <p className="wb2-provenance" data-wb2-provenance>Source: {sourceLabel}</p>
        </>
      ) : (
        <p className="wb2-unavailable" data-wb2-unavailable>
          No residual history attached. Convergence cannot be shown for this dataset.
        </p>
      )}
    </section>
  )
}
