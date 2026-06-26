// Public benchmark case schema + verification lifecycle + comparability rules.
//
// Honesty rules encoded here:
// - geometry_only is never accuracy-comparable;
// - a run command is offered ONLY for cases with a registered runnerId;
// - the lifecycle reflects what is actually verified, not what we hope.

import catalogRaw from './benchmarkCatalog.json'

export type TruthClass =
  | 'analytic'
  | 'independent_solver'
  | 'commercial_reference'
  | 'experimental'
  | 'geometry_only'

export type LocalAvailability = 'available' | 'external' | 'missing'
export type SizeClass = 'small' | 'medium' | 'large' | 'unknown'

export type LifecycleStatus =
  | 'DISCOVERED'
  | 'ACQUIRED'
  | 'NORMALIZED'
  | 'REFERENCE_ATTACHED'
  | 'RUNNABLE'
  | 'VALIDATED'

export interface BenchmarkVerification {
  licenseId: string | null
  licenseUrl: string | null
  licenseVerified: boolean
  truthClassVerified: boolean
  truthEvidencePath: string | null
  referenceResultsAvailable: boolean
  referenceResultsPath: string | null
  referenceSolver: string | null
  referenceSolverVersion: string | null
  acquisitionCommand: string | null
  runnerId: string | null
}

export interface BenchmarkCase {
  id: string
  title: string
  sourceUrl: string
  sourceVersion: string
  license: string
  truthClass: TruthClass
  structureFamily: string
  analysisTypes: string[]
  nodeCount?: number
  elementCount?: number
  checksum?: string
  localAvailability: LocalAvailability
  sourceFormat?: string | null
  fileBytes?: number | null
  sizeClass?: SizeClass
  truthClassBasis?: string
  firstValidationTarget: boolean
  verification: BenchmarkVerification
  allSourceUrls?: string[]
}

export interface BenchmarkCatalog {
  schemaVersion: string
  catalogKind: string
  disclaimer: string
  accuracyExclusionRule: string
  generatedAt: string | null
  cases: BenchmarkCase[]
}

const TRUTH_CLASSES: TruthClass[] = [
  'analytic',
  'independent_solver',
  'commercial_reference',
  'experimental',
  'geometry_only',
]

function str(v: unknown): string | null {
  return typeof v === 'string' && v.trim() !== '' ? v : null
}
function bool(v: unknown): boolean {
  return v === true
}
function asTruthClass(v: unknown): TruthClass {
  return TRUTH_CLASSES.includes(v as TruthClass) ? (v as TruthClass) : 'geometry_only'
}
function asAvailability(v: unknown): LocalAvailability {
  return v === 'available' || v === 'external' || v === 'missing' ? v : 'missing'
}

function normalizeVerification(v: unknown): BenchmarkVerification {
  const r = (v && typeof v === 'object' ? v : {}) as Record<string, unknown>
  return {
    licenseId: str(r.licenseId),
    licenseUrl: str(r.licenseUrl),
    licenseVerified: bool(r.licenseVerified),
    truthClassVerified: bool(r.truthClassVerified),
    truthEvidencePath: str(r.truthEvidencePath),
    referenceResultsAvailable: bool(r.referenceResultsAvailable),
    referenceResultsPath: str(r.referenceResultsPath),
    referenceSolver: str(r.referenceSolver),
    referenceSolverVersion: str(r.referenceSolverVersion),
    acquisitionCommand: str(r.acquisitionCommand),
    runnerId: str(r.runnerId),
  }
}

function normalizeCase(raw: unknown): BenchmarkCase | null {
  if (!raw || typeof raw !== 'object') return null
  const r = raw as Record<string, unknown>
  const id = str(r.id)
  if (!id) return null
  return {
    id,
    title: str(r.title) ?? id,
    sourceUrl: str(r.sourceUrl) ?? '',
    sourceVersion: str(r.sourceVersion) ?? 'unspecified',
    license: str(r.license) ?? 'unknown',
    truthClass: asTruthClass(r.truthClass),
    structureFamily: str(r.structureFamily) ?? 'unspecified',
    analysisTypes: Array.isArray(r.analysisTypes) ? r.analysisTypes.filter((x): x is string => typeof x === 'string') : [],
    checksum: str(r.checksum) ?? undefined,
    localAvailability: asAvailability(r.localAvailability),
    sourceFormat: str(r.sourceFormat),
    fileBytes: typeof r.fileBytes === 'number' ? r.fileBytes : null,
    sizeClass: (['small', 'medium', 'large', 'unknown'] as SizeClass[]).includes(r.sizeClass as SizeClass)
      ? (r.sizeClass as SizeClass)
      : 'unknown',
    truthClassBasis: str(r.truthClassBasis) ?? undefined,
    firstValidationTarget: bool(r.firstValidationTarget),
    verification: normalizeVerification(r.verification),
    allSourceUrls: Array.isArray(r.allSourceUrls) ? r.allSourceUrls.filter((x): x is string => typeof x === 'string') : [],
  }
}

export function normalizeCatalog(raw: unknown): BenchmarkCatalog {
  const r = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>
  const cases = Array.isArray(r.cases)
    ? r.cases.map((c) => normalizeCase(c)).filter((c): c is BenchmarkCase => c != null)
    : []
  return {
    schemaVersion: str(r.schema_version) ?? 'unknown',
    catalogKind: str(r.catalog_kind) ?? 'candidate',
    disclaimer: str(r.disclaimer) ?? '',
    accuracyExclusionRule: str(r.accuracy_exclusion_rule) ?? '',
    generatedAt: str(r.generated_at),
    cases,
  }
}

export function getBenchmarkCatalog(): BenchmarkCatalog {
  return normalizeCatalog(catalogRaw as unknown)
}

/** Lifecycle status from what is actually verified. */
export function deriveLifecycle(c: BenchmarkCase): LifecycleStatus {
  const v = c.verification
  if (v.licenseVerified && v.truthClassVerified && v.referenceResultsAvailable && v.runnerId) return 'VALIDATED'
  if (v.runnerId) return 'RUNNABLE'
  if (v.referenceResultsAvailable) return 'REFERENCE_ATTACHED'
  if (c.localAvailability === 'available') return c.sourceFormat ? 'NORMALIZED' : 'ACQUIRED'
  return 'DISCOVERED'
}

/** geometry_only is never accuracy-comparable. */
export function isAccuracyComparable(c: BenchmarkCase): boolean {
  return c.truthClass !== 'geometry_only' && c.verification.referenceResultsAvailable && c.localAvailability === 'available'
}

export function comparabilityReason(c: BenchmarkCase): string {
  if (c.truthClass === 'geometry_only') return 'geometry_only — import/topology/rendering only; excluded from accuracy averaging'
  if (c.localAvailability !== 'available') return `not locally available (${c.localAvailability})`
  if (!c.verification.referenceResultsAvailable) return 'no reference results attached yet'
  if (!c.verification.truthClassVerified) return 'comparable, but truth class is unverified'
  return 'accuracy-comparable'
}

export type RunCommandResult =
  | { runnable: true; command: string; reason?: undefined }
  | { runnable: false; reason: string; command?: undefined }

/** A run command is offered ONLY when a runner is registered for the case. */
export function benchmarkRunCommand(c: BenchmarkCase): RunCommandResult {
  if (!c.verification.runnerId) {
    return { runnable: false, reason: 'No benchmark runner registered' }
  }
  const fmt = c.sourceFormat ? ` --source-format ${c.sourceFormat}` : ''
  return { runnable: true, command: `run-benchmark --runner ${c.verification.runnerId} --case ${c.id}${fmt}` }
}
