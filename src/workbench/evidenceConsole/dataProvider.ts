// Mock / live data provider split for the Evidence Console.
//
// Both providers implement the same interface. The mock provider is fully
// offline and deterministic (bundled demo fixtures), which is what the React
// surface defaults to while the launch gate is blocked. The live provider
// fetches the same shapes from runtime URLs (read-only readiness artifact +
// a cases endpoint) for when validated evidence is wired up.

import demoCasesRaw from '../../evidence-console/fixtures/evidence_console_demo_cases.json'
import readinessSnapshotRaw from './fixtures/readiness_snapshot.json'
import { missingReadiness, normalizeReadiness } from './readiness'
import type {
  ComparisonRow,
  DatasetResult,
  EvidenceCase,
  EvidenceDataset,
  Provenance,
  ProviderMode,
  ReadinessState,
  ResidualRow,
  WorstMember,
} from './types'

export const DEFAULT_READINESS_URL =
  '/implementation/phase1/release_evidence/productization/evidence_console_scope_status.json'
export const DEFAULT_CASES_URL = '/src/evidence-console/fixtures/evidence_console_demo_cases.json'

function str(value: unknown): string | null {
  return typeof value === 'string' && value.trim() !== '' ? value : null
}

function num(value: unknown): number | null {
  return typeof value === 'number' && !Number.isNaN(value) ? value : null
}

function bool(value: unknown): boolean | null {
  return typeof value === 'boolean' ? value : null
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : null
}

function normalizeProvenance(value: unknown): Provenance | null {
  const r = asRecord(value)
  if (!r) return null
  return {
    model_file: str(r.model_file),
    model_sha256: str(r.model_sha256),
    source_tool: str(r.source_tool),
    engine_version: str(r.engine_version),
    analysis_kind: str(r.analysis_kind),
    generated_at: str(r.generated_at),
  }
}

function normalizeComparison(value: unknown): ComparisonRow[] {
  if (!Array.isArray(value)) return []
  return value.map((row) => {
    const r = asRecord(row) ?? {}
    return {
      quantity: str(r.quantity),
      unit: str(r.unit),
      reference: num(r.reference),
      engine: num(r.engine),
      tolerance_rel: num(r.tolerance_rel),
    }
  })
}

function normalizeResidual(value: unknown): ResidualRow[] {
  if (!Array.isArray(value)) return []
  return value.map((row) => {
    const r = asRecord(row) ?? {}
    return {
      metric: str(r.metric),
      unit: str(r.unit),
      value: num(r.value),
      tolerance: num(r.tolerance),
      within_tolerance: bool(r.within_tolerance),
    }
  })
}

function normalizeWorst(value: unknown): WorstMember | null {
  const r = asRecord(value)
  if (!r) return null
  return {
    member_id: str(r.member_id),
    story: str(r.story),
    governing_check: str(r.governing_check),
    dcr: num(r.dcr),
  }
}

function normalizeCase(value: unknown): EvidenceCase | null {
  const r = asRecord(value)
  const id = r ? str(r.id) : null
  if (!r || !id) return null
  return {
    id,
    name: str(r.name),
    structure_family: str(r.structure_family),
    load_combination: str(r.load_combination),
    reviewer_decision: str(r.reviewer_decision),
    reviewer_decision_note: str(r.reviewer_decision_note),
    provenance: normalizeProvenance(r.provenance),
    reference_vs_engine: normalizeComparison(r.reference_vs_engine),
    residual_audit: normalizeResidual(r.residual_audit),
    worst: normalizeWorst(r.worst),
  }
}

export function normalizeDataset(value: unknown): EvidenceDataset {
  const r = asRecord(value) ?? {}
  const cases = Array.isArray(r.cases)
    ? r.cases.map((c) => normalizeCase(c)).filter((c): c is EvidenceCase => c != null)
    : []
  return {
    schema_version: str(r.schema_version),
    dataset_kind: str(r.dataset_kind) ?? 'demo_fixture',
    is_demo: bool(r.is_demo) ?? false,
    engine_version: str(r.engine_version),
    claim_boundary: str(r.claim_boundary),
    cases,
  }
}

export interface EvidenceDataProvider {
  readonly mode: ProviderMode
  loadDataset(): Promise<DatasetResult>
  loadReadiness(): Promise<ReadinessState>
}

/** Offline, deterministic provider backed by bundled demo fixtures. */
export class MockEvidenceDataProvider implements EvidenceDataProvider {
  readonly mode: ProviderMode = 'mock'

  async loadDataset(): Promise<DatasetResult> {
    const dataset = normalizeDataset(demoCasesRaw as unknown)
    if (!dataset.cases.length) {
      return { status: 'missing', dataset: null, error: 'Mock fixture contained no cases.' }
    }
    return { status: 'ready', dataset, error: null }
  }

  async loadReadiness(): Promise<ReadinessState> {
    return normalizeReadiness(readinessSnapshotRaw as unknown, { source: 'mock:readiness_snapshot.json' })
  }
}

/** Live provider that fetches the read-only readiness artifact and a cases endpoint. */
export class LiveEvidenceDataProvider implements EvidenceDataProvider {
  readonly mode: ProviderMode = 'live'
  private readonly casesUrl: string
  private readonly readinessUrl: string
  private readonly fetchImpl: typeof fetch

  constructor(options: { casesUrl?: string; readinessUrl?: string; fetchImpl?: typeof fetch } = {}) {
    this.casesUrl = options.casesUrl ?? DEFAULT_CASES_URL
    this.readinessUrl = options.readinessUrl ?? DEFAULT_READINESS_URL
    this.fetchImpl = options.fetchImpl ?? fetch
  }

  async loadDataset(): Promise<DatasetResult> {
    try {
      const response = await this.fetchImpl(this.casesUrl, { cache: 'no-store' })
      if (!response.ok) return { status: 'missing', dataset: null, error: `HTTP ${response.status}` }
      const dataset = normalizeDataset(await response.json())
      if (!dataset.cases.length) return { status: 'missing', dataset: null, error: 'No cases in live dataset.' }
      return { status: 'ready', dataset, error: null }
    } catch (error) {
      return { status: 'error', dataset: null, error: String((error as Error)?.message ?? error) }
    }
  }

  async loadReadiness(): Promise<ReadinessState> {
    try {
      const response = await this.fetchImpl(this.readinessUrl, { cache: 'no-store' })
      if (!response.ok) return missingReadiness(`HTTP ${response.status}`, this.readinessUrl)
      return normalizeReadiness(await response.json(), { source: this.readinessUrl })
    } catch (error) {
      return missingReadiness(String((error as Error)?.message ?? error), this.readinessUrl)
    }
  }
}

export interface ProviderOptions {
  casesUrl?: string
  readinessUrl?: string
  fetchImpl?: typeof fetch
}

export function createEvidenceDataProvider(
  mode: ProviderMode,
  options: ProviderOptions = {},
): EvidenceDataProvider {
  return mode === 'live' ? new LiveEvidenceDataProvider(options) : new MockEvidenceDataProvider()
}
