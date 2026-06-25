// Data provider layer for Workbench v2 (Case Contract v2).
// The provider is the only place that knows where data comes from; it validates
// against the v2 contract before handing a case to the UI.

import demoCaseRaw from './fixtures/demo-case.v2.json'
import { validateWorkbenchCaseV2, type CaseValidation, type WorkbenchCaseV2 } from './caseSchema'

export type ProviderMode = 'demo' | 'live'

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

function toResult(validation: CaseValidation, sourcePath: string): WorkbenchLoadResult {
  if (validation.ok && validation.value) {
    return { status: 'ready', caseV2: validation.value, validation, sourcePath, loadedAt: nowIso(), error: null }
  }
  return { status: 'invalid', caseV2: null, validation, sourcePath, loadedAt: nowIso(), error: validation.errors.join('; ') }
}

export interface WorkbenchDataProvider {
  readonly mode: ProviderMode
  readonly sourceLabel: string
  load(): Promise<WorkbenchLoadResult>
}

export class DemoWorkbenchProvider implements WorkbenchDataProvider {
  readonly mode: ProviderMode = 'demo'
  readonly sourceLabel = 'demo:workbench-v2/fixtures/demo-case.v2.json'

  async load(): Promise<WorkbenchLoadResult> {
    return toResult(validateWorkbenchCaseV2(demoCaseRaw as unknown), this.sourceLabel)
  }
}

export class LiveWorkbenchProvider implements WorkbenchDataProvider {
  readonly mode: ProviderMode = 'live'
  readonly sourceLabel: string
  private readonly url: string
  private readonly fetchImpl: typeof fetch

  constructor(options: { url?: string; fetchImpl?: typeof fetch } = {}) {
    this.url = options.url ?? '/evidence/workbench-case.json'
    this.sourceLabel = `live:${this.url}`
    this.fetchImpl = options.fetchImpl ?? fetch
  }

  async load(): Promise<WorkbenchLoadResult> {
    try {
      const response = await this.fetchImpl(this.url, { cache: 'no-store' })
      if (!response.ok) {
        return { status: 'missing', caseV2: null, validation: null, sourcePath: this.sourceLabel, loadedAt: nowIso(), error: `HTTP ${response.status}` }
      }
      return toResult(validateWorkbenchCaseV2(await response.json()), this.sourceLabel)
    } catch (error) {
      return { status: 'error', caseV2: null, validation: null, sourcePath: this.sourceLabel, loadedAt: nowIso(), error: String((error as Error)?.message ?? error) }
    }
  }
}

export interface ProviderOptions {
  url?: string
  fetchImpl?: typeof fetch
}

export function createWorkbenchProvider(mode: ProviderMode, options: ProviderOptions = {}): WorkbenchDataProvider {
  return mode === 'live' ? new LiveWorkbenchProvider(options) : new DemoWorkbenchProvider()
}
