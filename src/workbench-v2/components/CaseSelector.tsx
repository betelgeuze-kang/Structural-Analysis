import type { ReactElement } from 'react'
import { demoCases, type DemoCaseId } from '../model/demoCases'

interface CaseSelectorProps {
  selectedId: DemoCaseId
  onSelect: (id: DemoCaseId) => void
}

/**
 * Demo-only case picker. Lets a reviewer move between the converged, failed,
 * and convergence-unavailable sample results so each honest UI state can be
 * inspected. Only rendered while the demo provider is active.
 */
export function CaseSelector({ selectedId, onSelect }: CaseSelectorProps): ReactElement {
  const active = demoCases.find((c) => c.id === selectedId) ?? demoCases[0]
  return (
    <section className="wb2-panel" aria-labelledby="wb2-caseselect-title" data-wb2-case-selector>
      <h2 id="wb2-caseselect-title" className="wb2-panel__title">Demo case</h2>
      <div className="wb2-case-tabs" role="group" aria-label="Demo case">
        {demoCases.map((c) => (
          <button
            key={c.id}
            type="button"
            className={`wb2-case-tab${c.id === selectedId ? ' is-active' : ''}`}
            aria-pressed={c.id === selectedId}
            data-wb2-case={c.id}
            onClick={() => onSelect(c.id)}
          >
            {c.label}
          </button>
        ))}
      </div>
      <p className="wb2-note" data-wb2-case-desc>{active.description}</p>
    </section>
  )
}
