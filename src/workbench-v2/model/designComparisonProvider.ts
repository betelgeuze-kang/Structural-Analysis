import { sha256Bytes } from './checksum'
import { parseNativeJsonStrict } from './nativeFrameProvider'
import { validateDesignComparisonManifest, validateDesignComparisonReport, type VerifiedDesignComparison } from './designComparisonSchema'

export type DesignComparisonStatus = 'unconfigured' | 'loading' | 'verified' | 'integrity_unavailable' | 'missing' | 'invalid' | 'error'
export interface DesignComparisonLoadResult { status: DesignComparisonStatus; bundle: VerifiedDesignComparison | null; errors: string[] }
const empty = (status: DesignComparisonStatus, error?: string): DesignComparisonLoadResult => ({ status, bundle: null, errors: error ? [error] : [] })

export async function loadDesignComparison(url: string | undefined, signal?: AbortSignal): Promise<DesignComparisonLoadResult> {
  if (!url) return empty('unconfigured')
  try {
    const manifestUrl = new URL(url, window.location.href)
    if (manifestUrl.origin !== window.location.origin || !['http:', 'https:'].includes(manifestUrl.protocol)
      || manifestUrl.username || manifestUrl.password || manifestUrl.search || manifestUrl.hash) {
      return empty('invalid', 'design comparison manifest must be a same-origin URL without credentials, query or fragment')
    }
    const manifest = validateDesignComparisonManifest(await readJson(manifestUrl, 16 * 1024, signal))
    const reportUrl = new URL(manifest.report_file, manifestUrl)
    const bytes = await readBytes(reportUrl, 64 * 1024 * 1024, signal)
    if (bytes.byteLength !== manifest.report_byte_length) return empty('invalid', 'design comparison report byte length mismatch')
    const digest = await sha256Bytes(bytes)
    if (digest === null) return empty('integrity_unavailable', 'design comparison SHA-256 verification is unavailable')
    if (digest !== manifest.report_sha256) return empty('invalid', 'design comparison report SHA-256 mismatch')
    const report = validateDesignComparisonReport(parse(bytes), manifest)
    return { status: 'verified', bundle: { manifest, report, manifestUrl: manifestUrl.href, reportUrl: reportUrl.href }, errors: [] }
  } catch (error: unknown) {
    if ((error as Error)?.name === 'AbortError') return empty('unconfigured')
    const detail = (error as Error)?.message ?? 'design comparison request failed'
    return empty(detail === 'design comparison not found' ? 'missing' : 'invalid', detail)
  }
}

async function readJson(url: URL, maximum: number, signal?: AbortSignal): Promise<unknown> { return parse(await readBytes(url, maximum, signal)) }
function parse(bytes: Uint8Array): unknown { return parseNativeJsonStrict(new TextDecoder('utf-8', { fatal: true }).decode(bytes)) }
async function readBytes(url: URL, maximum: number, signal?: AbortSignal): Promise<Uint8Array> {
  const response = await fetch(url.href, { method: 'GET', credentials: 'same-origin', redirect: 'error', cache: 'no-store', headers: { Accept: 'application/json' }, signal })
  if (response.status === 404) throw new Error('design comparison not found')
  if (!response.ok) throw new Error(`design comparison HTTP ${response.status}`)
  if (response.url && response.url !== url.href) throw new Error('design comparison response URL changed')
  if (!/^application\/(?:json|[a-z0-9.+-]+\+json)\b/i.test(response.headers.get('content-type') ?? '')) throw new Error('design comparison content type is invalid')
  const declared = Number(response.headers.get('content-length'))
  if (Number.isFinite(declared) && declared > maximum) throw new Error('design comparison exceeds size limit')
  if (!response.body) throw new Error('design comparison response body is missing')
  const reader = response.body.getReader()
  const chunks: Uint8Array[] = []
  let size = 0
  try {
    for (;;) {
      const next = await reader.read()
      if (next.done) break
      size += next.value.byteLength
      if (size > maximum) { await reader.cancel(); throw new Error('design comparison exceeds size limit') }
      chunks.push(next.value)
    }
  } finally { reader.releaseLock() }
  const bytes = new Uint8Array(size)
  let offset = 0
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength }
  return bytes
}
