import type { ReactElement } from 'react'
import { DECISION_CLASS, DECISION_LABELS, normalizeDecision } from '../format'

export function DecisionPill({ decision }: { decision: string | null }): ReactElement {
  const key = normalizeDecision(decision)
  if (!key) {
    return (
      <span className="ec-pill ec-pill--unavailable" data-ec-decision="unavailable">
        Evidence unavailable
      </span>
    )
  }
  return (
    <span className={`ec-pill ${DECISION_CLASS[key]}`} data-ec-decision={key}>
      {DECISION_LABELS[key]}
    </span>
  )
}
