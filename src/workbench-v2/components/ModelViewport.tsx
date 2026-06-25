import type { ReactElement } from 'react'
import type { MemberRef } from '../model/caseSchema'

interface ModelViewportProps {
  members: MemberRef[]
  selectedMemberId: string | null
  onSelectMember: (memberId: string) => void
}

export function ModelViewport({ members, selectedMemberId, onSelectMember }: ModelViewportProps): ReactElement {
  return (
    <section className="wb2-panel wb2-viewport" aria-labelledby="wb2-viewport-title">
      <h2 id="wb2-viewport-title" className="wb2-panel__title">Model viewport</h2>
      <div className="wb2-viewport-canvas" role="img" aria-label="Model preview placeholder">
        <span className="wb2-viewport-hint">3D preview placeholder</span>
        {selectedMemberId ? (
          <span className="wb2-viewport-selected">Selected: {selectedMemberId}</span>
        ) : null}
      </div>
      {members.length ? (
        <ul className="wb2-member-list" aria-label="Members">
          {members.map((member) => (
            <li key={member.id}>
              <button
                type="button"
                className={`wb2-member-btn${member.id === selectedMemberId ? ' is-active' : ''}`}
                aria-pressed={member.id === selectedMemberId}
                onClick={() => onSelectMember(member.id)}
              >
                {member.label ?? member.id}
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="wb2-unavailable" data-wb2-unavailable>No members in this dataset.</p>
      )}
    </section>
  )
}
