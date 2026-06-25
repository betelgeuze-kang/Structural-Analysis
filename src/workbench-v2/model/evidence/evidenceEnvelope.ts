// Read-only evidence loading contract.
//
// loadEvidence fetches a stored evidence JSON and reports availability only:
// `ready` (fetched + parsed) or `missing` (HTTP/network/parse failure). It never
// modifies the evidence and never invents a value. Higher-level meaning
// (blocked / stale / readiness) is derived separately by the interpreter so the
// loader cannot accidentally launder a failure into a pass.

export type EvidenceState = 'ready' | 'stale' | 'missing' | 'blocked'

export interface EvidenceEnvelope<T> {
  state: EvidenceState
  sourcePath: string
  sourceCommitSha?: string
  loadedAt: string
  data?: T
  error?: string
}

function extractCommit(data: unknown): string | undefined {
  if (data && typeof data === 'object' && !Array.isArray(data)) {
    const sha = (data as Record<string, unknown>).source_commit_sha
    if (typeof sha === 'string' && sha.trim() !== '') return sha
  }
  return undefined
}

export async function loadEvidence<T>(
  path: string,
  options: { fetchImpl?: typeof fetch } = {},
): Promise<EvidenceEnvelope<T>> {
  const loadedAt = new Date().toISOString()
  const doFetch = options.fetchImpl ?? (typeof fetch === 'function' ? fetch : undefined)
  if (!doFetch) {
    return { state: 'missing', sourcePath: path, loadedAt, error: 'No fetch implementation available.' }
  }
  try {
    const response = await doFetch(path, { cache: 'no-store' })
    if (!response.ok) {
      return { state: 'missing', sourcePath: path, loadedAt, error: `HTTP ${response.status}` }
    }
    const data = (await response.json()) as T
    return { state: 'ready', sourcePath: path, sourceCommitSha: extractCommit(data), loadedAt, data }
  } catch (error) {
    return { state: 'missing', sourcePath: path, loadedAt, error: String((error as Error)?.message ?? error) }
  }
}
