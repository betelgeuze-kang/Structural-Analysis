// Human review draft for Workbench v2.
//
// This is intentionally NOT an automated verdict. The workbench never infers a
// PASS/REVIEW/FAIL; a person records a draft decision, which is persisted only
// to localStorage and included in the JSON export. It is keyed by the case's
// source commit so a draft follows the exact evidence it was written against.

export type ReviewDecisionValue = 'unreviewed' | 'pass' | 'review' | 'fail'

export interface ReviewDraft {
  decision: ReviewDecisionValue
  comment: string
  reviewer: string
  updatedAt: string | null
  sourceCommitSha: string
}

export const reviewDecisionOptions: { value: ReviewDecisionValue; label: string }[] = [
  { value: 'unreviewed', label: 'Unreviewed' },
  { value: 'pass', label: 'Pass (reviewer)' },
  { value: 'review', label: 'Needs review' },
  { value: 'fail', label: 'Fail (reviewer)' },
]

const STORAGE_PREFIX = 'wb2-review-draft:'

export function defaultDraft(sourceCommitSha: string): ReviewDraft {
  return { decision: 'unreviewed', comment: '', reviewer: '', updatedAt: null, sourceCommitSha }
}

function storageKey(sourceCommitSha: string): string {
  return `${STORAGE_PREFIX}${sourceCommitSha}`
}

function getStorage(): Storage | null {
  try {
    if (typeof window === 'undefined' || !window.localStorage) return null
    return window.localStorage
  } catch {
    return null
  }
}

export function loadDraft(sourceCommitSha: string): ReviewDraft {
  const base = defaultDraft(sourceCommitSha)
  const store = getStorage()
  if (!store) return base
  try {
    const raw = store.getItem(storageKey(sourceCommitSha))
    if (!raw) return base
    const parsed = JSON.parse(raw) as Partial<ReviewDraft>
    const decision: ReviewDecisionValue =
      parsed.decision === 'pass' || parsed.decision === 'review' || parsed.decision === 'fail'
        ? parsed.decision
        : 'unreviewed'
    return {
      decision,
      comment: typeof parsed.comment === 'string' ? parsed.comment : '',
      reviewer: typeof parsed.reviewer === 'string' ? parsed.reviewer : '',
      updatedAt: typeof parsed.updatedAt === 'string' ? parsed.updatedAt : null,
      sourceCommitSha,
    }
  } catch {
    return base
  }
}

export function saveDraft(draft: ReviewDraft): ReviewDraft {
  const next: ReviewDraft = { ...draft, updatedAt: new Date().toISOString() }
  const store = getStorage()
  if (store) {
    try {
      store.setItem(storageKey(draft.sourceCommitSha), JSON.stringify(next))
    } catch {
      /* persistence is best-effort; the in-memory draft is still returned */
    }
  }
  return next
}
