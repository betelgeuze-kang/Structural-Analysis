import { sha256Bytes } from './checksum'
import { parseNativeJsonStrict } from './nativeFrameProvider'
import { validateDesignComparisonManifest, validateDesignComparisonReport } from './designComparisonSchema'
import { candidateProcessSlotKey, validateCandidateProcessManifest, validateCandidateProcessReview, type CandidateLoadedArtifact, type CandidateLoadedComparison, type VerifiedCandidateProcessReview } from './candidateProcessSchema'

export type CandidateProcessStatus = 'unconfigured' | 'loading' | 'verified' | 'integrity_unavailable' | 'missing' | 'invalid' | 'error'
export interface CandidateProcessLoadResult { status: CandidateProcessStatus; bundle: VerifiedCandidateProcessReview | null; errors: string[] }
const empty = (status: CandidateProcessStatus, message?: string): CandidateProcessLoadResult => ({ status, bundle: null, errors: message ? [message] : [] })
const FILE_LIMIT = 64 * 1024 * 1024
const TOTAL_LIMIT = 256 * 1024 * 1024

// Bound nesting before entering the existing duplicate-key/finite-number parser.
// Strings and escaped quotes cannot contribute to structural depth.
export function parseCandidateProcessJson(bytes: Uint8Array): unknown {
  const text = new TextDecoder('utf-8', { fatal: true }).decode(bytes)
  let depth = 0; let quoted = false; let escaped = false
  for (const character of text) {
    if (quoted) { if (escaped) escaped = false; else if (character === '\\') escaped = true; else if (character === '"') quoted = false }
    else if (character === '"') quoted = true
    else if (character === '{' || character === '[') { if (++depth > 64) throw new Error('candidate process JSON nesting exceeds limit') }
    else if (character === '}' || character === ']') depth--
  }
  const value = parseNativeJsonStrict(text)
  let nodes = 0
  const finite = (item: unknown): void => {
    if (++nodes > 2_000_000) throw new Error('candidate process JSON node limit exceeded')
    if (typeof item === 'number' && !Number.isFinite(item)) throw new Error('candidate process JSON number is not finite')
    if (Array.isArray(item)) item.forEach(finite)
    else if (item !== null && typeof item === 'object') Object.values(item).forEach(finite)
  }
  finite(value)
  return value
}

export async function loadCandidateProcessReview(url: string | undefined, signal?: AbortSignal): Promise<CandidateProcessLoadResult> {
  if (!url) return empty('unconfigured')
  try {
    const manifestUrl = new URL(url, window.location.href)
    if (manifestUrl.origin !== window.location.origin || !['http:', 'https:'].includes(manifestUrl.protocol) || manifestUrl.username || manifestUrl.password || manifestUrl.search || manifestUrl.hash) throw new Error('candidate process manifest must be a same-origin URL without credentials, query or fragment')
    let total = 0
    const read = async (target: URL, maximum: number, identity?: { byte_length: number; sha256: string }): Promise<Uint8Array> => {
      if (signal?.aborted) throw new DOMException('Aborted', 'AbortError')
      const response = await fetch(target.href, { method: 'GET', credentials: 'same-origin', redirect: 'error', cache: 'no-store', headers: { Accept: 'application/json' }, signal })
      if (response.status === 404) throw new Error('candidate process not found')
      if (!response.ok) throw new Error(`candidate process HTTP ${response.status}`)
      if (response.url && response.url !== target.href) throw new Error('candidate process response URL changed')
      if (!/^application\/(?:json|[a-z0-9.+-]+\+json)\b/i.test(response.headers.get('content-type') ?? '')) throw new Error('candidate process content type is invalid')
      const declared = Number(response.headers.get('content-length'))
      if (Number.isFinite(declared) && declared > maximum) throw new Error('candidate process file exceeds size limit')
      if (!response.body) throw new Error('candidate process response body is missing')
      const reader = response.body.getReader(); const chunks: Uint8Array[] = []; let length = 0
      try {
        for (;;) {
          const next = await reader.read(); if (next.done) break
          length += next.value.byteLength; total += next.value.byteLength
          if (length > maximum || total > TOTAL_LIMIT) { await reader.cancel(); throw new Error('candidate process byte budget exceeded') }
          chunks.push(next.value)
        }
      } finally { reader.releaseLock() }
      const result = new Uint8Array(length); let offset = 0
      for (const chunk of chunks) { result.set(chunk, offset); offset += chunk.byteLength }
      if (identity && length !== identity.byte_length) throw new Error('candidate process byte length mismatch')
      const digest = await sha256Bytes(result)
      if (digest === null) throw new Error('candidate process integrity unavailable')
      if (identity && digest !== identity.sha256) throw new Error('candidate process SHA-256 mismatch')
      return result
    }
    const manifestBytes = await read(manifestUrl, 4 * 1024 * 1024)
    const manifest = validateCandidateProcessManifest(parseCandidateProcessJson(manifestBytes))
    const suiteUrl = new URL(manifest.suite_file, manifestUrl)
    const suiteBytes = await read(suiteUrl, FILE_LIMIT, { byte_length: manifest.suite_byte_length, sha256: manifest.suite_sha256 })
    const suite = parseCandidateProcessJson(suiteBytes)
    const artifacts = new Map<string, CandidateLoadedArtifact>()
    // source_path is only a lookup label from the producer. Only validated bundle-relative file is fetched.
    for (const entry of manifest.artifacts) {
      const bytes = await read(new URL(entry.file, manifestUrl), FILE_LIMIT, entry)
      // Failed worker files may be malformed. Preserve their bound bytes; only
      // required inputs and artifacts claimed valid must supply parsed objects.
      let value: unknown
      try { value = parseCandidateProcessJson(bytes) } catch { value = undefined }
      artifacts.set(entry.source_path, { bytes, value })
    }
    const comparisons = new Map<string, CandidateLoadedComparison>()
    for (const entry of manifest.comparisons) {
      const nestedUrl = new URL(entry.manifest_file, manifestUrl)
      const nestedBytes = await read(nestedUrl, 16 * 1024, { byte_length: entry.manifest_byte_length, sha256: entry.manifest_sha256 })
      const nested = validateDesignComparisonManifest(parseCandidateProcessJson(nestedBytes))
      const reportUrl = new URL(nested.report_file, nestedUrl)
      const reportBytes = await read(reportUrl, FILE_LIMIT, { byte_length: nested.report_byte_length, sha256: nested.report_sha256 })
      const report = validateDesignComparisonReport(parseCandidateProcessJson(reportBytes), nested)
      comparisons.set(candidateProcessSlotKey(entry.case_id, entry.phase, entry.repetition, entry.strategy), { bundle: { manifest: nested, report, manifestUrl: nestedUrl.href, reportUrl: reportUrl.href }, manifestBytes: nestedBytes, reportBytes })
    }
    const validated = validateCandidateProcessReview(suite, manifest, artifacts, comparisons)
    if (signal?.aborted) throw new DOMException('Aborted', 'AbortError')
    return { status: 'verified', bundle: { manifest, ...validated, manifestUrl: manifestUrl.href, suiteUrl: suiteUrl.href, manifestBytes, suiteBytes }, errors: [] }
  } catch (error) {
    if ((error as Error)?.name === 'AbortError') return empty('unconfigured')
    const message = (error as Error)?.message ?? 'candidate process request failed'
    return empty(message === 'candidate process not found' ? 'missing' : message === 'candidate process integrity unavailable' ? 'integrity_unavailable' : 'invalid', message)
  }
}
