// Data provider layer for Workbench v2 (Case Contract v2).
// The provider is the only place that knows where data comes from; it validates
// against the v2 contract before handing a case to the UI.

import { validateWorkbenchCaseV2, type CaseValidation, type WorkbenchCaseV2 } from './caseSchema'
import { getDemoCase, defaultDemoCaseId, type DemoCaseId } from './demoCases'

export type ProviderMode = 'demo' | 'live'

const LIVE_CASE_TIMEOUT_MS = 8000
const LIVE_CASE_MAX_BYTES = 256 * 1024
const JSON_CONTENT_TYPE_RE = /^application\/(?:json|[\w.+-]+\+json)\b/i

export interface WorkbenchLoadResult {
  status: 'ready' | 'invalid' | 'missing' | 'error'
  caseV2: WorkbenchCaseV2 | null
  validation: CaseValidation | null
  sourcePath: string
  loadedAt: string
  error: string | null
}

function nowIso(): string {
  return new Date().toISOString()
}

function errorResult(sourcePath: string, error: string): WorkbenchLoadResult {
  return { status: 'error', caseV2: null, validation: null, sourcePath, loadedAt: nowIso(), error }
}

function toResult(validation: CaseValidation, sourcePath: string): WorkbenchLoadResult {
  if (validation.ok && validation.value) {
    return { status: 'ready', caseV2: validation.value, validation, sourcePath, loadedAt: nowIso(), error: null }
  }
  return { status: 'invalid', caseV2: null, validation, sourcePath, loadedAt: nowIso(), error: validation.errors.join('; ') }
}

function byteLength(text: string): number {
  return typeof TextEncoder !== 'undefined' ? new TextEncoder().encode(text).byteLength : text.length
}

function abortErrorMessage(error: unknown, timeoutMs: number): string | null {
  const name = (error as { name?: unknown } | null)?.name
  if (name === 'AbortError') {
    return `live case request timed out after ${timeoutMs}ms`
  }
  return null
}

export interface WorkbenchDataProvider {
  readonly mode: ProviderMode
  readonly sourceLabel: string
  load(): Promise<WorkbenchLoadResult>
}

export class DemoWorkbenchProvider implements WorkbenchDataProvider {
  readonly mode: ProviderMode = 'demo'
  readonly sourceLabel: string
  readonly demoCaseId: DemoCaseId

  constructor(demoCaseId: DemoCaseId = defaultDemoCaseId) {
    this.demoCaseId = demoCaseId
    this.sourceLabel = `demo:${demoCaseId}`
  }

  async load(): Promise<WorkbenchLoadResult> {
    const entry = getDemoCase(this.demoCaseId)
    return toResult(validateWorkbenchCaseV2(entry.raw), `demo:${entry.id}:${entry.label}`)
  }
}

export class LiveWorkbenchProvider implements WorkbenchDataProvider {
  readonly mode: ProviderMode = 'live'
  readonly sourceLabel: string
  private readonly url: string
  private readonly fetchImpl: typeof fetch
  private readonly timeoutMs: number
  private readonly maxBytes: number

  constructor(options: { url?: string; fetchImpl?: typeof fetch; timeoutMs?: number; maxBytes?: number } = {}) {
    this.url = options.url ?? '/evidence/workbench-case.json'
    this.sourceLabel = `live:${this.url}`
    this.fetchImpl = options.fetchImpl ?? fetch
    this.timeoutMs = options.timeoutMs ?? LIVE_CASE_TIMEOUT_MS
    this.maxBytes = options.maxBytes ?? LIVE_CASE_MAX_BYTES
  }

  async load(): Promise<WorkbenchLoadResult> {
    const controller = typeof AbortController !== 'undefined' ? new AbortController() : null
    const timeoutId = controller
      ? globalThis.setTimeout(() => controller.abort(), this.timeoutMs)
      : null

    try {
      const response = await this.fetchImpl(this.url, {
        cache: 'no-store',
        signal: controller?.signal,
      })
      if (!response.ok) {
        return { status: 'missing', caseV2: null, validation: null, sourcePath: this.sourceLabel, loadedAt: nowIso(), error: `HTTP ${response.status}` }
      }

      const contentType = response.headers.get('content-type') ?? ''
      if (!JSON_CONTENT_TYPE_RE.test(contentType)) {
        return errorResult(this.sourceLabel, `unexpected live case content-type: ${contentType || '<missing>'}`)
      }

      const contentLengthHeader = response.headers.get('content-length')
      const contentLength = contentLengthHeader ? Number(contentLengthHeader) : null
      if (contentLength !== null && Number.isFinite(contentLength) && contentLength > this.maxBytes) {
        return errorResult(this.sourceLabel, `live case payload too large: ${contentLength} bytes (limit ${this.maxBytes})`)
      }

      const text = await response.text()
      const size = byteLength(text)
      if (size > this.maxBytes) {
        return errorResult(this.sourceLabel, `live case payload too large: ${size} bytes (limit ${this.maxBytes})`)
      }

      try {
        return toResult(validateWorkbenchCaseV2(JSON.parse(text)), this.sourceLabel)
      } catch (error) {
        return errorResult(this.sourceLabel, `invalid live case JSON: ${String((error as Error)?.message ?? error)}`)
      }
    } catch (error) {
      return errorResult(
        this.sourceLabel,
        abortErrorMessage(error, this.timeoutMs) ?? String((error as Error)?.message ?? error),
      )
    } finally {
      if (timeoutId !== null) {
        globalThis.clearTimeout(timeoutId)
      }
    }
  }
}

export interface ProviderOptions {
  url?: string
  fetchImpl?: typeof fetch
  demoCaseId?: DemoCaseId
  timeoutMs?: number
  maxBytes?: number
}

export function createWorkbenchProvider(mode: ProviderMode, options: ProviderOptions = {}): WorkbenchDataProvider {
  return mode === 'live' ? new LiveWorkbenchProvider(options) : new DemoWorkbenchProvider(options.demoCaseId)
}
