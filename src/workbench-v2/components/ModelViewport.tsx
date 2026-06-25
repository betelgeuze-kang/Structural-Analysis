import type { ReactElement } from 'react'
import type { CaseModel } from '../model/caseSchema'

interface ModelViewportProps {
  model: CaseModel
  selectedMemberId: string | null
}

export function ModelViewport({ model, selectedMemberId }: ModelViewportProps): ReactElement {
  return (
    <section className="wb2-panel wb2-viewport" aria-labelledby="wb2-viewport-title">
      <h2 id="wb2-viewport-title" className="wb2-panel__title">Model viewport</h2>
      <div className="wb2-viewport-canvas" role="img" aria-label="Model preview placeholder">
        <span className="wb2-viewport-hint">3D preview placeholder</span>
        <span className="wb2-viewport-meta">
          {model.nodeCount.toLocaleString()} nodes · {model.elementCount.toLocaleString()} elements · {model.dofCount.toLocaleString()} DOF
        </span>
        <span className="wb2-viewport-selected">
          {selectedMemberId ? `Selected: ${selectedMemberId}` : 'No member selected'}
        </span>
      </div>
      <p className="wb2-note">A real 3D viewer is bridged in a later step; selection will sync here.</p>
    </section>
  )
}
