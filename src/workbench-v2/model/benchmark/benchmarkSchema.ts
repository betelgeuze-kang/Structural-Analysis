// Public benchmark case schema + comparability rules.
//
// The honesty rule is encoded here: geometry_only data is never accuracy-
// comparable, and a case is only accuracy-comparable when it has a non-geometry
// truth class, reference results, and is locally available.

import catalogRaw from './benchmarkCatalog.json'

export type TruthClass =
  | 'analytic'
  | 'independent_solver'
  | 'commercial_reference'
  | 'experimental'
  | 'geometry_only'

export type LocalAvailability = 'available' | 'external' | 'missing'
export type SizeClass = 'small' | 'medium' | 'large' | 'unknown'

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
  // honesty annotations (extensions to the base schema)
  sourceFormat?: string | null
  fileBytes?: number | null
  sizeClass?: SizeClass
  truthClassVerified?: boolean
  truthClassBasis?: string
  licenseVerified?: boolean
  referenceResultsAvailable?: boolean
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

function asTruthClass(value: unknown): TruthClass {
  return TRUTH_CLASSES.includes(value as TruthClass) ? (value as TruthClass) : 'geometry_only'
}

function asAvailability(value: unknown): LocalAvailability {
  return value === 'available' || value === 'external' || value === 'missing' ? value : 'missing'
}

function normalizeCase(raw: unknown): BenchmarkCase | null {
  if (!raw || typeof raw !== 'object') return null
  const r = raw as Record<string, unknown>
  const id = typeof r.id === 'string' && r.id.trim() ? r.id : null
  if (!id) return null
  return {
    id,
    title: typeof r.title === 'string' ? r.title : id,
    sourceUrl: typeof r.sourceUrl === 'string' ? r.sourceUrl : '',
    sourceVersion: typeof r.sourceVersion === 'string' ? r.sourceVersion : 'unspecified',
    license: typeof r.license === 'string' ? r.license : 'unknown',
    truthClass: asTruthClass(r.truthClass),
    structureFamily: typeof r.structureFamily === 'string' ? r.structureFamily : 'unspecified',
    analysisTypes: Array.isArray(r.analysisTypes) ? r.analysisTypes.filter((x): x is string => typeof x === 'string') : [],
    checksum: typeof r.checksum === 'string' ? r.checksum : undefined,
    localAvailability: asAvailability(r.localAvailability),
    sourceFormat: typeof r.sourceFormat === 'string' ? r.sourceFormat : null,
    fileBytes: typeof r.fileBytes === 'number' ? r.fileBytes : null,
    sizeClass: (['small', 'medium', 'large', 'unknown'] as SizeClass[]).includes(r.sizeClass as SizeClass)
      ? (r.sizeClass as SizeClass)
      : 'unknown',
    truthClassVerified: r.truthClassVerified === true,
    truthClassBasis: typeof r.truthClassBasis === 'string' ? r.truthClassBasis : undefined,
    licenseVerified: r.licenseVerified === true,
    referenceResultsAvailable: r.referenceResultsAvailable === true,
    allSourceUrls: Array.isArray(r.allSourceUrls) ? r.allSourceUrls.filter((x): x is string => typeof x === 'string') : [],
  }
}

export function normalizeCatalog(raw: unknown): BenchmarkCatalog {
  const r = (raw && typeof raw === 'object' ? raw : {}) as Record<string, unknown>
  const cases = Array.isArray(r.cases)
    ? r.cases.map((c) => normalizeCase(c)).filter((c): c is BenchmarkCase => c != null)
    : []
  return {
    schemaVersion: typeof r.schema_version === 'string' ? r.schema_version : 'unknown',
    catalogKind: typeof r.catalog_kind === 'string' ? r.catalog_kind : 'candidate',
    disclaimer: typeof r.disclaimer === 'string' ? r.disclaimer : '',
    accuracyExclusionRule: typeof r.accuracy_exclusion_rule === 'string' ? r.accuracy_exclusion_rule : '',
    generatedAt: typeof r.generated_at === 'string' ? r.generated_at : null,
    cases,
  }
}

export function getBenchmarkCatalog(): BenchmarkCatalog {
  return normalizeCatalog(catalogRaw as unknown)
}

/** A case is accuracy-comparable only with a non-geometry truth class, reference
 * results, and local availability. geometry_only is always excluded. */
export function isAccuracyComparable(c: BenchmarkCase): boolean {
  return c.truthClass !== 'geometry_only' && c.referenceResultsAvailable === true && c.localAvailability === 'available'
}

export function comparabilityReason(c: BenchmarkCase): string {
  if (c.truthClass === 'geometry_only') return 'geometry_only — import/topology/rendering only; excluded from accuracy averaging'
  if (c.localAvailability !== 'available') return `not locally available (${c.localAvailability})`
  if (!c.referenceResultsAvailable) return 'no reference results attached yet'
  if (!c.truthClassVerified) return 'comparable, but truth class is unverified (format-inferred)'
  return 'accuracy-comparable'
}

/** Example run command (guidance only). */
export function buildRunCommand(c: BenchmarkCase): string {
  const fmt = c.sourceFormat ? ` --source-format ${c.sourceFormat}` : ''
  return `python scripts/run_benchmark_case.py --case ${c.id}${fmt}`
}
