// Shared types for the Evidence Console React surface.

export type ReviewerDecisionKey = 'PASS' | 'REVIEW' | 'FAIL'

export interface Provenance {
  model_file: string | null
  model_sha256: string | null
  source_tool: string | null
  engine_version: string | null
  analysis_kind: string | null
  generated_at: string | null
}

export interface ComparisonRow {
  quantity: string | null
  unit: string | null
  reference: number | null
  engine: number | null
  tolerance_rel: number | null
}

export interface ResidualRow {
  metric: string | null
  unit: string | null
  value: number | null
  tolerance: number | null
  within_tolerance: boolean | null
}

export interface WorstMember {
  member_id: string | null
  story: string | null
  governing_check: string | null
  dcr: number | null
}

export interface EvidenceCase {
  id: string
  name: string | null
  structure_family: string | null
  load_combination: string | null
  reviewer_decision: string | null
  reviewer_decision_note: string | null
  provenance: Provenance | null
  reference_vs_engine: ComparisonRow[]
  residual_audit: ResidualRow[]
  worst: WorstMember | null
}

export interface EvidenceDataset {
  schema_version: string | null
  dataset_kind: string | null
  is_demo: boolean
  engine_version: string | null
  claim_boundary: string | null
  cases: EvidenceCase[]
}

export type ReadinessAvailability = 'available' | 'missing'
export type ReadinessGate = 'BLOCKED' | 'READY' | 'UNKNOWN' | string
export type ReadinessFreshness = 'fresh' | 'stale' | 'unknown'

export interface ReadinessState {
  availability: ReadinessAvailability
  error: string | null
  source: string | null
  status: string
  launchReady: boolean | null
  gate: ReadinessGate
  freshness: ReadinessFreshness
  staleReason: string | null
  sourceCommit: string | null
  sourceCommitShort: string | null
  generatedAt: string | null
  summaryLine: string | null
  blockers: string[]
  claimBoundary: string | null
  nextAction: string | null
}

export type LoadStatus = 'loading' | 'ready' | 'missing' | 'error'

export interface DatasetResult {
  status: LoadStatus
  dataset: EvidenceDataset | null
  error: string | null
}

export type ProviderMode = 'mock' | 'live'

export interface ReproduceBundle {
  schema_version: 'evidence-console-reproduce-bundle.v1'
  dataset_kind: string
  is_demo: boolean
  claim_boundary: string | null
  engine_version: string | null
  provider_mode: ProviderMode
  exported_at: string
  case: EvidenceCase
}
