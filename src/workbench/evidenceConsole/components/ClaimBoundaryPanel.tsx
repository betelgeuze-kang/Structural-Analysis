import type { ReactElement } from 'react'
import type { ReadinessState } from '../types'
import { hasValue } from '../format'

export function ClaimBoundaryPanel({ readiness }: { readiness: ReadinessState }): ReactElement {
  return (
    <section className="ec-panel ec-claim-panel" aria-label="Claim boundary">
      <div className="ec-readiness-head">
        <h2 className="ec-readiness-title">Claim boundary</h2>
        <span className="ec-demo-badge" role="img" aria-label="Demo prototype — not validated evidence">
          Demo prototype
        </span>
      </div>
      {hasValue(readiness.claimBoundary) ? (
        <p className="ec-claim-text">{readiness.claimBoundary}</p>
      ) : (
        <p className="ec-claim-text">
          Claim boundary text could not be read from the readiness evidence. This surface remains a DEMO prototype and
          is not validated evidence.
        </p>
      )}
    </section>
  )
}
