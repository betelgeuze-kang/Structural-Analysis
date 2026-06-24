// Read-only readiness adapter for the Evidence Console.
//
// The adapter reads an existing readiness artifact (the Evidence Console scope
// status JSON) WITHOUT modifying it, and normalizes it into a small, stable
// shape the UI can render. It never fabricates a verdict: if the artifact is
// absent, unreadable, or stale, that is surfaced explicitly as
// missing / stale / blocked rather than being smoothed over.

/** Default location of the read-only readiness artifact, relative to the page. */
export const DEFAULT_READINESS_SRC =
  '../../implementation/phase1/release_evidence/productization/evidence_console_scope_status.json';

/** Readiness evidence older than this is reported as stale (21 days). */
export const MAX_READINESS_AGE_MS = 21 * 24 * 60 * 60 * 1000;

function asString(value) {
  return typeof value === 'string' && value.trim() !== '' ? value : null;
}

function asStringArray(value) {
  if (!Array.isArray(value)) return [];
  return value.map((v) => asString(v)).filter((v) => v != null);
}

/** Short 8-character commit form for display. */
export function shortCommit(sha) {
  const s = asString(sha);
  if (!s) return null;
  return s.length > 8 ? s.slice(0, 8) : s;
}

function emptyNormalized(extra) {
  return {
    availability: 'missing',
    error: null,
    source: null,
    status: 'unknown',
    launchReady: null,
    gate: 'UNKNOWN',
    freshness: 'unknown',
    staleReason: null,
    ageMs: null,
    sourceCommit: null,
    sourceCommitShort: null,
    generatedAt: null,
    summaryLine: null,
    blockers: [],
    claimBoundary: null,
    nextAction: null,
    schemaVersion: null,
    reasonCode: null,
    ...extra,
  };
}

/**
 * Derive the overall gate label from status + launch_ready.
 * Returns BLOCKED / READY / UNKNOWN (or the upper-cased status as a fallback).
 */
export function deriveGate(status, launchReady) {
  if (status === 'blocked' || launchReady === false) return 'BLOCKED';
  if (launchReady === true && status !== 'blocked') return 'READY';
  if (status) return String(status).toUpperCase();
  return 'UNKNOWN';
}

/**
 * Evaluate freshness of the artifact relative to `now`.
 * Missing/invalid timestamps are reported as unknown, never as fresh.
 */
export function evaluateFreshness(generatedAt, now, maxAgeMs = MAX_READINESS_AGE_MS) {
  const iso = asString(generatedAt);
  if (!iso) return { freshness: 'unknown', staleReason: 'No generated_at timestamp present.', ageMs: null };
  const parsed = Date.parse(iso);
  if (Number.isNaN(parsed)) {
    return { freshness: 'unknown', staleReason: 'Unparseable generated_at timestamp.', ageMs: null };
  }
  const ageMs = now - parsed;
  if (ageMs > maxAgeMs) {
    const ageDays = Math.floor(ageMs / (24 * 60 * 60 * 1000));
    const maxDays = Math.floor(maxAgeMs / (24 * 60 * 60 * 1000));
    return { freshness: 'stale', staleReason: `Generated ${ageDays} day(s) ago (max ${maxDays}).`, ageMs };
  }
  return { freshness: 'fresh', staleReason: null, ageMs };
}

/**
 * Normalize a raw readiness artifact object into the adapter shape.
 * Returns availability:'available' only when the payload is a usable object.
 */
export function normalizeReadiness(raw, { now = Date.now(), source = null } = {}) {
  if (!raw || typeof raw !== 'object') {
    return emptyNormalized({ availability: 'missing', error: 'Readiness payload was not an object.', source });
  }
  const status = asString(raw.status) || 'unknown';
  const launchReady = typeof raw.launch_ready === 'boolean' ? raw.launch_ready : null;
  const { freshness, staleReason, ageMs } = evaluateFreshness(raw.generated_at, now);
  const sourceCommit = asString(raw.source_commit_sha);

  return {
    availability: 'available',
    error: null,
    source,
    status,
    launchReady,
    gate: deriveGate(status, launchReady),
    freshness,
    staleReason,
    ageMs,
    sourceCommit,
    sourceCommitShort: shortCommit(sourceCommit),
    generatedAt: asString(raw.generated_at),
    summaryLine: asString(raw.summary_line),
    blockers: asStringArray(raw.blockers),
    claimBoundary: asString(raw.claim_boundary),
    nextAction: asString(raw.summary && raw.summary.next_action),
    schemaVersion: asString(raw.schema_version),
    reasonCode: asString(raw.reason_code),
  };
}

/**
 * Fetch and normalize the readiness artifact (read-only).
 * A 404 / network error / parse error resolves to availability:'missing';
 * it never throws and never produces a fabricated ready/PASS state.
 */
export async function fetchReadiness(url = DEFAULT_READINESS_SRC, { now = Date.now(), fetchImpl } = {}) {
  const doFetch = fetchImpl || (typeof fetch === 'function' ? fetch : null);
  if (!doFetch) {
    return emptyNormalized({ error: 'No fetch implementation available.', source: url });
  }
  try {
    const response = await doFetch(url, { cache: 'no-store' });
    if (!response.ok) {
      return emptyNormalized({ error: `HTTP ${response.status}`, source: url });
    }
    const raw = await response.json();
    return normalizeReadiness(raw, { now, source: url });
  } catch (error) {
    return emptyNormalized({ error: String((error && error.message) || error), source: url });
  }
}
