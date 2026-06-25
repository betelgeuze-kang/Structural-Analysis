// Data provider layer for Workbench v2.
//
// The provider is the only place that knows where data comes from. UI
// components receive a normalized model + provenance, never a path or fetch.
// demo and live providers are interchangeable behind one interface.

import demoCaseRaw from '../../../prototype/structural-workbench/demo-case.json'
import { normalizeModel, type WorkbenchModel } from './caseSchema'

export type ProviderMode = 'demo' | 'live'

export interface WorkbenchLoadResult {
  status: 'ready' | 'missing' | 'error'
  model: WorkbenchModel | null
  /** Provenance: where the model came from. For display only. */
  sourcePath: string
  loadedAt: string
  error: string | null
}

export interface WorkbenchDataProvider {
  readonly mode: ProviderMode
  /** Human-readable provenance label for the source. */
  readonly sourceLabel: string
  load(): Promise<WorkbenchLoadResult>
}

function nowIso(): string {
  return new Date().toISOString()
}

/** Offline provider backed by the bundled prototype demo fixture. */
export class DemoWorkbenchProvider implements WorkbenchDataProvider {
  readonly mode: ProviderMode = 'demo'
  readonly sourceLabel = 'demo:structural-workbench/demo-case.json'

  async load(): Promise<WorkbenchLoadResult> {
    const model = normalizeModel(demoCaseRaw as unknown)
    return { status: 'ready', model, sourcePath: this.sourceLabel, loadedAt: nowIso(), error: null }
  }
}

/** Live provider that reads a model from a runtime URL (read-only). */
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
        return { status: 'missing', model: null, sourcePath: this.sourceLabel, loadedAt: nowIso(), error: `HTTP ${response.status}` }
      }
      const model = normalizeModel(await response.json())
      return { status: 'ready', model, sourcePath: this.sourceLabel, loadedAt: nowIso(), error: null }
    } catch (error) {
      return {
        status: 'error',
        model: null,
        sourcePath: this.sourceLabel,
        loadedAt: nowIso(),
        error: String((error as Error)?.message ?? error),
      }
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
