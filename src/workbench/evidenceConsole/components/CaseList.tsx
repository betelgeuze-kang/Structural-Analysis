import { useRef, type KeyboardEvent, type ReactElement } from 'react'
import type { EvidenceCase } from '../types'
import { decisionAnnouncement, hasValue } from '../format'
import { DecisionPill } from './DecisionPill'

interface CaseListProps {
  cases: EvidenceCase[]
  activeId: string | null
  onSelect: (id: string) => void
}

export function CaseList({ cases, activeId, onSelect }: CaseListProps): ReactElement {
  const buttonRefs = useRef<Map<string, HTMLButtonElement>>(new Map())

  function handleKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number): void {
    let target: number | null = null
    switch (event.key) {
      case 'ArrowDown':
      case 'ArrowRight':
        target = (index + 1) % cases.length
        break
      case 'ArrowUp':
      case 'ArrowLeft':
        target = (index - 1 + cases.length) % cases.length
        break
      case 'Home':
        target = 0
        break
      case 'End':
        target = cases.length - 1
        break
      default:
        return
    }
    event.preventDefault()
    const targetId = cases[target].id
    onSelect(targetId)
    buttonRefs.current.get(targetId)?.focus()
  }

  return (
    <nav className="ec-panel" aria-labelledby="ec-react-case-list-title">
      <h2 id="ec-react-case-list-title">Case list</h2>
      <ul className="ec-case-list" aria-label="Evidence cases">
        {cases.map((caseItem, index) => {
          const isActive = caseItem.id === activeId
          const displayName = hasValue(caseItem.name) ? (caseItem.name as string) : caseItem.id
          return (
            <li key={caseItem.id} role="none">
              <button
                type="button"
                ref={(node) => {
                  if (node) buttonRefs.current.set(caseItem.id, node)
                  else buttonRefs.current.delete(caseItem.id)
                }}
                className={`ec-case-btn${isActive ? ' is-active' : ''}`}
                data-ec-case-id={caseItem.id}
                tabIndex={isActive ? 0 : -1}
                aria-current={isActive ? 'true' : 'false'}
                aria-label={`${displayName}. Reviewer decision: ${decisionAnnouncement(caseItem.reviewer_decision)}.`}
                onClick={() => onSelect(caseItem.id)}
                onKeyDown={(event) => handleKeyDown(event, index)}
              >
                <span className="ec-case-name">{displayName}</span>
                <span className="ec-case-meta" aria-hidden="true">
                  <DecisionPill decision={caseItem.reviewer_decision} />
                  {hasValue(caseItem.structure_family) ? <span>{caseItem.structure_family}</span> : null}
                </span>
              </button>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}
