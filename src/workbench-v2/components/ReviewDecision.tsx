import { type ReactElement } from 'react'
import type { DataMode } from '../model/workbenchState'
import {
  MAX_REVIEWER_CHARS,
  MAX_REVIEW_COMMENT_CHARS,
  reviewDecisionOptions,
  type ReviewDecisionValue,
  type ReviewDraft,
  type ReviewDraftPersistenceReceipt,
  type ReviewDraftState,
} from '../model/reviewDraft'
import { StateChip } from './StateChip'

interface ReviewDecisionProps {
  dataMode: DataMode
  draftState: ReviewDraftState | null
  onDraftChange: (patch: Partial<ReviewDraft>) => void
}

function persistenceHint(receipt: ReviewDraftPersistenceReceipt): string {
  switch (receipt.displayStatus) {
    case 'Saved locally':
      return 'Stored in this browser only (localStorage) and included in the export. No server save.'
    case 'Session-only':
      return 'Current draft is held in memory and included in the export, but it will not survive a reload.'
    case 'Storage unavailable':
      return 'No persisted draft could be restored. New edits can still be retained for this session.'
    case 'Previous state retained':
      return 'The replacement was rejected; the previous validated draft remains current.'
  }
}

/**
 * Review panel. The automated verdict is always UNAVAILABLE — nothing is
 * inferred. Below it, a reviewer can record a DRAFT decision (pass/review/fail)
 * with a comment. The draft is a human note with explicit local/session
 * persistence status and is included in the export; it is never presented as
 * an automated result.
 */
export function ReviewDecision({ dataMode, draftState, onDraftChange }: ReviewDecisionProps): ReactElement {
  const note =
    dataMode === 'demo'
      ? 'Demo data with no solver evidence — a PASS/REVIEW/FAIL result is never inferred here.'
      : 'No verdict is shown unless it is present in attached evidence; it is never defaulted to PASS.'
  const draft = draftState?.draft ?? null
  const receipt = draftState?.receipt ?? null
  const sourceCommitSha = draft?.sourceCommitSha ?? null

  return (
    <section className="wb2-panel" aria-labelledby="wb2-verdict-title">
      <h2 id="wb2-verdict-title" className="wb2-panel__title">Review decision</h2>

      <div className="wb2-review-auto">
        <span className="wb2-review-auto__label">Automated verdict</span>
        <StateChip state="UNAVAILABLE" srLabel="Automated verdict" />
      </div>
      <p className="wb2-note">{note}</p>

      {sourceCommitSha && draft && receipt ? (
        <div className="wb2-review-draft" data-wb2-review-draft>
          <h3 className="wb2-subhead">Reviewer draft (not an automated verdict)</h3>

          <div className="wb2-review-field">
            <span className="wb2-review-field__label" id="wb2-review-decision-label">Decision</span>
            <div className="wb2-review-decisions" role="radiogroup" aria-labelledby="wb2-review-decision-label">
              {reviewDecisionOptions.map((opt) => (
                <button
                  key={opt.value}
                  type="button"
                  role="radio"
                  aria-checked={draft.decision === opt.value}
                  className={`wb2-review-decision${draft.decision === opt.value ? ' is-active' : ''}`}
                  data-wb2-decision={opt.value}
                  onClick={() => onDraftChange({ decision: opt.value as ReviewDecisionValue })}
                >
                  {opt.label}
                </button>
              ))}
            </div>
          </div>

          <label className="wb2-review-field">
            <span className="wb2-review-field__label">Reviewer</span>
            <input
              type="text"
              className="wb2-review-input"
              value={draft.reviewer}
              maxLength={MAX_REVIEWER_CHARS}
              placeholder="name or initials"
              data-wb2-review-reviewer
              onChange={(e) => onDraftChange({ reviewer: e.target.value })}
            />
          </label>

          <label className="wb2-review-field">
            <span className="wb2-review-field__label">Comment</span>
            <textarea
              className="wb2-review-textarea"
              value={draft.comment}
              maxLength={MAX_REVIEW_COMMENT_CHARS}
              rows={3}
              placeholder="Reviewer notes"
              data-wb2-review-comment
              onChange={(e) => onDraftChange({ comment: e.target.value })}
            />
          </label>

          <p className="wb2-review-meta" data-wb2-review-meta aria-live="polite">
            <span className={`wb2-chip wb2-chip--${draft.decision === 'pass' ? 'live' : draft.decision === 'fail' ? 'blocked' : 'unavailable'}`} data-wb2-review-state={draft.decision}>
              draft: {draft.decision}
            </span>
            <span
              className="wb2-persistence-status"
              data-wb2-persistence-status={receipt.status}
              data-wb2-persistence-display={receipt.displayStatus}
              data-wb2-persistence={receipt.persistence}
              data-wb2-persistence-error-code={receipt.errorCode || undefined}
              data-wb2-persistence-error-path={receipt.errorPath || undefined}
            >
              {receipt.displayStatus}
            </span>
            {draft.updatedAt ? <> · updated {new Date(draft.updatedAt).toLocaleString()}</> : <> · not yet edited</>}
            <> · commit <code className="wb2-mono">{sourceCommitSha.slice(0, 12)}</code></>
          </p>
          <p className="wb2-action-hint" data-wb2-persistence-hint>{persistenceHint(receipt)}</p>
        </div>
      ) : (
        <p className="wb2-unavailable" data-wb2-unavailable>Load a valid case to record a reviewer draft.</p>
      )}
    </section>
  )
}
