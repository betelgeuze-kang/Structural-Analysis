import { useEffect, useState, type ReactElement } from 'react'
import type { DataMode } from '../model/workbenchState'
import {
  defaultDraft,
  loadDraft,
  reviewDecisionOptions,
  saveDraft,
  type ReviewDecisionValue,
  type ReviewDraft,
} from '../model/reviewDraft'
import { StateChip } from './StateChip'

interface ReviewDecisionProps {
  dataMode: DataMode
  sourceCommitSha: string | null
}

/**
 * Review panel. The automated verdict is always UNAVAILABLE — nothing is
 * inferred. Below it, a reviewer can record a DRAFT decision (pass/review/fail)
 * with a comment. The draft is a human note, stored only in localStorage and
 * included in the export; it is never presented as an automated result.
 */
export function ReviewDecision({ dataMode, sourceCommitSha }: ReviewDecisionProps): ReactElement {
  const note =
    dataMode === 'demo'
      ? 'Demo data with no solver evidence — a PASS/REVIEW/FAIL result is never inferred here.'
      : 'No verdict is shown unless it is present in attached evidence; it is never defaulted to PASS.'

  const [draft, setDraft] = useState<ReviewDraft>(() => defaultDraft(sourceCommitSha ?? ''))

  useEffect(() => {
    if (sourceCommitSha) setDraft(loadDraft(sourceCommitSha))
  }, [sourceCommitSha])

  function update(patch: Partial<ReviewDraft>): void {
    if (!sourceCommitSha) return
    setDraft((prev) => saveDraft({ ...prev, ...patch, sourceCommitSha }))
  }

  return (
    <section className="wb2-panel" aria-labelledby="wb2-verdict-title">
      <h2 id="wb2-verdict-title" className="wb2-panel__title">Review decision</h2>

      <div className="wb2-review-auto">
        <span className="wb2-review-auto__label">Automated verdict</span>
        <StateChip state="UNAVAILABLE" srLabel="Automated verdict" />
      </div>
      <p className="wb2-note">{note}</p>

      {sourceCommitSha ? (
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
                  onClick={() => update({ decision: opt.value as ReviewDecisionValue })}
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
              placeholder="name or initials"
              data-wb2-review-reviewer
              onChange={(e) => update({ reviewer: e.target.value })}
            />
          </label>

          <label className="wb2-review-field">
            <span className="wb2-review-field__label">Comment</span>
            <textarea
              className="wb2-review-textarea"
              value={draft.comment}
              rows={3}
              placeholder="Reviewer notes — saved locally only"
              data-wb2-review-comment
              onChange={(e) => update({ comment: e.target.value })}
            />
          </label>

          <p className="wb2-review-meta" data-wb2-review-meta>
            <span className={`wb2-chip wb2-chip--${draft.decision === 'pass' ? 'live' : draft.decision === 'fail' ? 'blocked' : 'unavailable'}`} data-wb2-review-state={draft.decision}>
              draft: {draft.decision}
            </span>
            {draft.updatedAt ? <> · saved locally {new Date(draft.updatedAt).toLocaleString()}</> : <> · not yet saved</>}
            <> · commit <code className="wb2-mono">{sourceCommitSha.slice(0, 12)}</code></>
          </p>
          <p className="wb2-action-hint">Stored in this browser only (localStorage) and included in the export. No server save.</p>
        </div>
      ) : (
        <p className="wb2-unavailable" data-wb2-unavailable>Load a valid case to record a reviewer draft.</p>
      )}
    </section>
  )
}
