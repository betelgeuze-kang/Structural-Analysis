// Human review draft storage for Workbench v2.
//
// A draft is a reviewer-authored note, never an automated verdict. Persistence
// is synchronous and fail-closed: the UI receives a stable receipt for every
// read/write and cannot claim a local save unless the serialized value was
// written and read back from localStorage.

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

export const REVIEW_DRAFT_STORAGE_POLICY = 'workbench_review_draft_storage_v1'

export const REVIEW_DRAFT_DISPLAY_STATUS = {
  saved: 'Saved locally',
  session: 'Session-only',
  unavailable: 'Storage unavailable',
  retained: 'Previous state retained',
} as const

export type ReviewDraftDisplayStatus =
  (typeof REVIEW_DRAFT_DISPLAY_STATUS)[keyof typeof REVIEW_DRAFT_DISPLAY_STATUS]
export type ReviewDraftPersistenceStatus =
  | 'session_only'
  | 'blocked'
  | 'empty'
  | 'ready'
  | 'corrupted_removed'
  | 'persisted'
export type ReviewDraftPersistence = 'none' | 'memory_only' | 'local_storage'
export type ReviewDraftPersistenceOperation = 'initialize' | 'read' | 'write'

export interface ReviewDraftPersistenceReceipt {
  policy: typeof REVIEW_DRAFT_STORAGE_POLICY
  ok: boolean
  operation: ReviewDraftPersistenceOperation
  status: ReviewDraftPersistenceStatus
  displayStatus: ReviewDraftDisplayStatus
  persistence: ReviewDraftPersistence
  errorCode: string
  errorPath: string
  cleanupErrorCode: string
  cleanupErrorPath: string
  corruptedEntryRemoved: boolean
  draftRetained: boolean
}

export interface ReviewDraftState {
  draft: ReviewDraft
  receipt: ReviewDraftPersistenceReceipt
}

export interface ReviewDraftPersistenceMetadata {
  policy: typeof REVIEW_DRAFT_STORAGE_POLICY
  ok: boolean
  operation: ReviewDraftPersistenceOperation
  status: ReviewDraftPersistenceStatus
  display_status: ReviewDraftDisplayStatus
  persistence: ReviewDraftPersistence
  error_code: string
  error_path: string
  cleanup_error_code: string
  cleanup_error_path: string
  corrupted_entry_removed: boolean
  draft_retained: boolean
}

type ReviewDraftStorage = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>

export interface ReviewDraftPersistenceOptions {
  /** Explicit adapter for deterministic tests. Omit to use window.localStorage. */
  storage?: ReviewDraftStorage | null
  /** Deterministic timestamp source for tests. */
  now?: () => string
}

interface StableFailure {
  code: string
  path: string
}

interface StorageResolution {
  storage: ReviewDraftStorage | null
  failure: StableFailure | null
}

const STORAGE_PREFIX = 'wb2-review-draft:'
const MAX_SOURCE_COMMIT_CHARS = 256
export const MAX_REVIEWER_CHARS = 256
export const MAX_REVIEW_COMMENT_CHARS = 20_000
const MAX_SERIALIZED_DRAFT_CHARS = 32_768

function freezeDraft(draft: ReviewDraft): ReviewDraft {
  return Object.freeze({ ...draft })
}

function makeReceipt(
  values: Partial<ReviewDraftPersistenceReceipt> &
    Pick<ReviewDraftPersistenceReceipt, 'ok' | 'operation' | 'status' | 'displayStatus' | 'persistence'>,
): ReviewDraftPersistenceReceipt {
  return Object.freeze({
    policy: REVIEW_DRAFT_STORAGE_POLICY,
    errorCode: '',
    errorPath: '',
    cleanupErrorCode: '',
    cleanupErrorPath: '',
    corruptedEntryRemoved: false,
    draftRetained: false,
    ...values,
  })
}

function makeState(draft: ReviewDraft, receipt: ReviewDraftPersistenceReceipt): ReviewDraftState {
  return Object.freeze({ draft: freezeDraft(draft), receipt })
}

export function defaultDraft(sourceCommitSha: string): ReviewDraft {
  return freezeDraft({
    decision: 'unreviewed',
    comment: '',
    reviewer: '',
    updatedAt: null,
    sourceCommitSha,
  })
}

function storageKey(sourceCommitSha: string): string {
  return `${STORAGE_PREFIX}${sourceCommitSha}`
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === 'object' && !Array.isArray(value)
}

function isDecision(value: unknown): value is ReviewDecisionValue {
  return value === 'unreviewed' || value === 'pass' || value === 'review' || value === 'fail'
}

function isTimestamp(value: unknown): value is string | null {
  return value === null || (
    typeof value === 'string'
    && value.length <= 64
    && value.length > 0
    && Number.isFinite(Date.parse(value))
  )
}

function normalizedDraft(value: unknown, sourceCommitSha: string): ReviewDraft | null {
  if (
    !isRecord(value)
    || !isDecision(value.decision)
    || typeof value.comment !== 'string'
    || value.comment.length > MAX_REVIEW_COMMENT_CHARS
    || typeof value.reviewer !== 'string'
    || value.reviewer.length > MAX_REVIEWER_CHARS
    || !isTimestamp(value.updatedAt)
    || value.sourceCommitSha !== sourceCommitSha
  ) {
    return null
  }
  return freezeDraft({
    decision: value.decision,
    comment: value.comment,
    reviewer: value.reviewer,
    updatedAt: value.updatedAt,
    sourceCommitSha,
  })
}

function stableStorageFailure(error: unknown, operation: 'access' | 'get' | 'set' | 'verify' | 'remove'): StableFailure {
  const record = isRecord(error) ? error : {}
  const name = typeof record.name === 'string' ? record.name : ''
  const code = typeof record.code === 'number' ? record.code : null
  const path = `/storage/${operation}`
  if (name === 'QuotaExceededError' || code === 22 || code === 1014) {
    return { code: 'review_draft_storage_quota_exceeded', path }
  }
  if (name === 'SecurityError') {
    return { code: 'review_draft_storage_access_denied', path }
  }
  return { code: `review_draft_storage_${operation}_failed`, path }
}

function resolveStorage(options: ReviewDraftPersistenceOptions): StorageResolution {
  if (Object.prototype.hasOwnProperty.call(options, 'storage')) {
    return options.storage
      ? { storage: options.storage, failure: null }
      : {
          storage: null,
          failure: {
            code: 'review_draft_storage_adapter_unavailable',
            path: '/storage/access',
          },
        }
  }
  try {
    if (typeof window === 'undefined') return { storage: null, failure: null }
    const storage = window.localStorage
    return storage
      ? { storage, failure: null }
      : {
          storage: null,
          failure: {
            code: 'review_draft_storage_adapter_unavailable',
            path: '/storage/access',
          },
        }
  } catch (error) {
    return { storage: null, failure: stableStorageFailure(error, 'access') }
  }
}

export function createReviewDraftState(sourceCommitSha: string): ReviewDraftState {
  return makeState(
    defaultDraft(sourceCommitSha),
    makeReceipt({
      ok: true,
      operation: 'initialize',
      status: 'session_only',
      displayStatus: REVIEW_DRAFT_DISPLAY_STATUS.session,
      persistence: 'memory_only',
      draftRetained: true,
    }),
  )
}

export function loadReviewDraftState(
  sourceCommitSha: string,
  options: ReviewDraftPersistenceOptions = {},
): ReviewDraftState {
  const base = defaultDraft(sourceCommitSha)
  if (!sourceCommitSha || sourceCommitSha.length > MAX_SOURCE_COMMIT_CHARS) {
    return makeState(base, makeReceipt({
      ok: false,
      operation: 'read',
      status: 'blocked',
      displayStatus: REVIEW_DRAFT_DISPLAY_STATUS.unavailable,
      persistence: 'none',
      errorCode: 'review_draft_source_commit_invalid',
      errorPath: '/draft/sourceCommitSha',
    }))
  }

  const resolution = resolveStorage(options)
  if (!resolution.storage) {
    if (!resolution.failure) return createReviewDraftState(sourceCommitSha)
    return makeState(base, makeReceipt({
      ok: false,
      operation: 'read',
      status: 'blocked',
      displayStatus: REVIEW_DRAFT_DISPLAY_STATUS.unavailable,
      persistence: 'none',
      errorCode: resolution.failure.code,
      errorPath: resolution.failure.path,
    }))
  }

  let raw: string | null
  try {
    raw = resolution.storage.getItem(storageKey(sourceCommitSha))
  } catch (error) {
    const failure = stableStorageFailure(error, 'get')
    return makeState(base, makeReceipt({
      ok: false,
      operation: 'read',
      status: 'blocked',
      displayStatus: REVIEW_DRAFT_DISPLAY_STATUS.unavailable,
      persistence: 'none',
      errorCode: failure.code,
      errorPath: failure.path,
    }))
  }

  if (!raw) {
    return makeState(base, makeReceipt({
      ok: true,
      operation: 'read',
      status: 'empty',
      displayStatus: REVIEW_DRAFT_DISPLAY_STATUS.session,
      persistence: 'memory_only',
      draftRetained: true,
    }))
  }

  let parsed: unknown
  let primaryFailure: StableFailure | null = null
  if (raw.length > MAX_SERIALIZED_DRAFT_CHARS) {
    primaryFailure = {
      code: 'review_draft_storage_value_too_large',
      path: '/storage/value',
    }
  } else {
    try {
      parsed = JSON.parse(raw) as unknown
    } catch {
      primaryFailure = {
        code: 'review_draft_storage_json_malformed',
        path: '/storage/value',
      }
    }
  }

  const storedDraft = primaryFailure ? null : normalizedDraft(parsed, sourceCommitSha)
  if (!storedDraft) {
    primaryFailure ??= {
      code: 'review_draft_storage_value_invalid',
      path: '/storage/value',
    }
    let corruptedEntryRemoved = false
    let cleanupFailure: StableFailure | null = null
    try {
      resolution.storage.removeItem(storageKey(sourceCommitSha))
      corruptedEntryRemoved = true
    } catch (error) {
      cleanupFailure = stableStorageFailure(error, 'remove')
    }
    return makeState(base, makeReceipt({
      ok: false,
      operation: 'read',
      status: 'corrupted_removed',
      displayStatus: REVIEW_DRAFT_DISPLAY_STATUS.unavailable,
      persistence: 'none',
      errorCode: primaryFailure.code,
      errorPath: primaryFailure.path,
      cleanupErrorCode: cleanupFailure?.code ?? '',
      cleanupErrorPath: cleanupFailure?.path ?? '',
      corruptedEntryRemoved,
    }))
  }

  return makeState(storedDraft, makeReceipt({
    ok: true,
    operation: 'read',
    status: 'ready',
    displayStatus: REVIEW_DRAFT_DISPLAY_STATUS.saved,
    persistence: 'local_storage',
    draftRetained: true,
  }))
}

function previousStateReceipt(
  previous: ReviewDraftState,
  failure: StableFailure,
): ReviewDraftPersistenceReceipt {
  return makeReceipt({
    ok: false,
    operation: 'write',
    status: 'blocked',
    displayStatus: REVIEW_DRAFT_DISPLAY_STATUS.retained,
    persistence: previous.receipt.persistence,
    errorCode: failure.code,
    errorPath: failure.path,
    draftRetained: true,
  })
}

export function updateReviewDraftState(
  previous: ReviewDraftState,
  patch: Partial<ReviewDraft>,
  options: ReviewDraftPersistenceOptions = {},
): ReviewDraftState {
  let serialized: string
  let nextDraft: ReviewDraft
  try {
    const timestamp = (options.now ?? (() => new Date().toISOString()))()
    const candidate = {
      ...previous.draft,
      ...patch,
      sourceCommitSha: previous.draft.sourceCommitSha,
      updatedAt: timestamp,
    }
    const validated = normalizedDraft(candidate, previous.draft.sourceCommitSha)
    if (!validated) {
      return makeState(previous.draft, previousStateReceipt(previous, {
        code: 'review_draft_value_invalid',
        path: '/draft',
      }))
    }
    serialized = JSON.stringify(validated)
    if (serialized.length > MAX_SERIALIZED_DRAFT_CHARS) {
      return makeState(previous.draft, previousStateReceipt(previous, {
        code: 'review_draft_serialized_value_too_large',
        path: '/draft',
      }))
    }
    nextDraft = validated
  } catch {
    return makeState(previous.draft, previousStateReceipt(previous, {
      code: 'review_draft_serialization_failed',
      path: '/draft',
    }))
  }

  const resolution = resolveStorage(options)
  if (!resolution.storage) {
    const failure = resolution.failure ?? {
      code: 'review_draft_storage_adapter_unavailable',
      path: '/storage/access',
    }
    return makeState(nextDraft, makeReceipt({
      ok: false,
      operation: 'write',
      status: 'session_only',
      displayStatus: REVIEW_DRAFT_DISPLAY_STATUS.session,
      persistence: 'memory_only',
      errorCode: failure.code,
      errorPath: failure.path,
      draftRetained: true,
    }))
  }

  const key = storageKey(nextDraft.sourceCommitSha)
  try {
    resolution.storage.setItem(key, serialized)
  } catch (error) {
    const failure = stableStorageFailure(error, 'set')
    return makeState(nextDraft, makeReceipt({
      ok: false,
      operation: 'write',
      status: 'session_only',
      displayStatus: REVIEW_DRAFT_DISPLAY_STATUS.session,
      persistence: 'memory_only',
      errorCode: failure.code,
      errorPath: failure.path,
      draftRetained: true,
    }))
  }

  try {
    if (resolution.storage.getItem(key) !== serialized) {
      return makeState(nextDraft, makeReceipt({
        ok: false,
        operation: 'write',
        status: 'session_only',
        displayStatus: REVIEW_DRAFT_DISPLAY_STATUS.session,
        persistence: 'memory_only',
        errorCode: 'review_draft_storage_verification_mismatch',
        errorPath: '/storage/verify',
        draftRetained: true,
      }))
    }
  } catch (error) {
    const failure = stableStorageFailure(error, 'verify')
    return makeState(nextDraft, makeReceipt({
      ok: false,
      operation: 'write',
      status: 'session_only',
      displayStatus: REVIEW_DRAFT_DISPLAY_STATUS.session,
      persistence: 'memory_only',
      errorCode: failure.code,
      errorPath: failure.path,
      draftRetained: true,
    }))
  }

  return makeState(nextDraft, makeReceipt({
    ok: true,
    operation: 'write',
    status: 'persisted',
    displayStatus: REVIEW_DRAFT_DISPLAY_STATUS.saved,
    persistence: 'local_storage',
    draftRetained: true,
  }))
}

export function reviewDraftPersistenceMetadata(
  receipt: ReviewDraftPersistenceReceipt,
): ReviewDraftPersistenceMetadata {
  return Object.freeze({
    policy: receipt.policy,
    ok: receipt.ok,
    operation: receipt.operation,
    status: receipt.status,
    display_status: receipt.displayStatus,
    persistence: receipt.persistence,
    error_code: receipt.errorCode,
    error_path: receipt.errorPath,
    cleanup_error_code: receipt.cleanupErrorCode,
    cleanup_error_path: receipt.cleanupErrorPath,
    corrupted_entry_removed: receipt.corruptedEntryRemoved,
    draft_retained: receipt.draftRetained,
  })
}
