// Workbench Case Contract v2.
//
// Carries real analysis results + provenance. Validation policy:
// - UNKNOWN FIELDS ARE ALLOWED (forward-compatible): unrecognized keys are kept
//   and ignored, never an error.
// - HARD BLOCK (case rejected) when: schemaVersion is wrong, the source checksum
//   is missing, or the unit system is missing — we will not show analysis values
//   without units or provenance.
// - SOFT (convergence unavailable) when analysis.converged is absent: the case
//   still loads, but convergence is reported as UNAVAILABLE, never inferred.

export type UnitSystem = 'SI'
export type CoordinateSystem = 'global_xyz'

export interface CaseProvenance {
  sourcePath: string
  sourceSha256: string
  sourceCommitSha: string
  engineVersion: string
  generatedAt: string
}

export interface CaseModel {
  unitSystem: UnitSystem
  coordinateSystem: CoordinateSystem
  nodeCount: number
  elementCount: number
  dofCount: number
}

export interface CaseAnalysis {
  type: string
  solver: string
  converged: boolean
  loadScale: number
  iterationCount: number
  residualTolerance: number
  finalNormalizedResidual: number
  finalRelativeIncrement: number
  /** Optional explicit run status when not converged (e.g. 'failed'). */
  status?: 'idle' | 'validating' | 'running' | 'converged' | 'failed'
}

export interface ResidualStep {
  iteration: number
  residual: number
  relativeIncrement: number
  alpha: number
}

export interface WorkbenchCaseV2 {
  schemaVersion: 'workbench-case.v2'
  provenance: CaseProvenance
  model: CaseModel
  analysis?: CaseAnalysis
  residualHistory: ResidualStep[]
  /** Forward-compatible: unknown top-level fields are preserved here. */
  [extra: string]: unknown
}

export interface CaseValidation {
  ok: boolean
  value: WorkbenchCaseV2 | null
  errors: string[]
  warnings: string[]
  convergenceAvailable: boolean
}

function isRecord(v: unknown): v is Record<string, unknown> {
  return !!v && typeof v === 'object' && !Array.isArray(v)
}
function str(v: unknown): string | null {
  return typeof v === 'string' && v.trim() !== '' ? v : null
}
function fin(v: unknown): number | null {
  return typeof v === 'number' && Number.isFinite(v) ? v : null
}

function toRunStatus(v: unknown): CaseAnalysis['status'] {
  return v === 'idle' || v === 'validating' || v === 'running' || v === 'converged' || v === 'failed' ? v : undefined
}

function normalizeResidualHistory(v: unknown): ResidualStep[] {
  if (!Array.isArray(v)) return []
  return v
    .map((row) => {
      if (!isRecord(row)) return null
      const iteration = fin(row.iteration)
      const residual = fin(row.residual)
      if (iteration == null || residual == null) return null
      return {
        iteration,
        residual,
        relativeIncrement: fin(row.relativeIncrement) ?? 0,
        alpha: fin(row.alpha) ?? 1,
      }
    })
    .filter((r): r is ResidualStep => r != null)
}

/**
 * Validate a raw object as a WorkbenchCaseV2. Unknown fields are allowed and
 * preserved. Returns block errors, soft warnings, and a convergenceAvailable
 * flag for the reducer/UI.
 */
export function validateWorkbenchCaseV2(raw: unknown): CaseValidation {
  const errors: string[] = []
  const warnings: string[] = []

  if (!isRecord(raw)) {
    return { ok: false, value: null, errors: ['case is not an object'], warnings, convergenceAvailable: false }
  }

  if (raw.schemaVersion !== 'workbench-case.v2') {
    errors.push(`unexpected schemaVersion: ${String(raw.schemaVersion)} (expected workbench-case.v2)`)
  }

  const prov = isRecord(raw.provenance) ? raw.provenance : {}
  if (!str(prov.sourceSha256)) errors.push('provenance.sourceSha256 is missing (source checksum required)')

  const model = isRecord(raw.model) ? raw.model : {}
  if (!str(model.unitSystem)) errors.push('model.unitSystem is missing (units required)')

  const analysis = isRecord(raw.analysis) ? raw.analysis : null
  const convergenceAvailable = analysis != null && typeof analysis.converged === 'boolean'
  if (!convergenceAvailable) warnings.push('analysis.converged is missing — convergence is UNAVAILABLE, not inferred')

  if (errors.length > 0) {
    return { ok: false, value: null, errors, warnings, convergenceAvailable }
  }

  // Build a typed value; unknown fields on `raw` are retained via the index
  // signature, satisfying the "unknown fields allowed" policy.
  const value = {
    ...raw,
    schemaVersion: 'workbench-case.v2',
    provenance: {
      sourcePath: str(prov.sourcePath) ?? 'unknown',
      sourceSha256: str(prov.sourceSha256) as string,
      sourceCommitSha: str(prov.sourceCommitSha) ?? 'unknown',
      engineVersion: str(prov.engineVersion) ?? 'unknown',
      generatedAt: str(prov.generatedAt) ?? 'unknown',
    },
    model: {
      unitSystem: 'SI' as UnitSystem,
      coordinateSystem: (str(model.coordinateSystem) ?? 'global_xyz') as CoordinateSystem,
      nodeCount: fin(model.nodeCount) ?? 0,
      elementCount: fin(model.elementCount) ?? 0,
      dofCount: fin(model.dofCount) ?? 0,
    },
    analysis: convergenceAvailable
      ? {
          type: str(analysis!.type) ?? 'unknown',
          solver: str(analysis!.solver) ?? 'unknown',
          converged: analysis!.converged as boolean,
          loadScale: fin(analysis!.loadScale) ?? 1,
          iterationCount: fin(analysis!.iterationCount) ?? 0,
          residualTolerance: fin(analysis!.residualTolerance) ?? 0,
          finalNormalizedResidual: fin(analysis!.finalNormalizedResidual) ?? 0,
          finalRelativeIncrement: fin(analysis!.finalRelativeIncrement) ?? 0,
          status: toRunStatus(analysis!.status),
        }
      : undefined,
    residualHistory: normalizeResidualHistory(raw.residualHistory),
  } as WorkbenchCaseV2

  return { ok: true, value, errors, warnings, convergenceAvailable }
}
