// Workbench Case Contract v2.
//
// Carries real analysis results + provenance. Validation policy:
// - UNKNOWN FIELDS ARE ALLOWED (forward-compatible): unrecognized keys are kept
//   and ignored, never an error.
// - HARD BLOCK (case rejected) when: schemaVersion is wrong, the source checksum
//   is missing, or the explicit unit/coordinate contract is missing or unsupported.
//   We will not show analysis values after silently coercing engineering semantics.
// - SOFT (convergence unavailable) when analysis.converged is absent: the case
//   still loads, but convergence is reported as UNAVAILABLE, never inferred.
// - Every numeric engineering value is normalized to one explicit state:
//   available (with a domain-valid finite number), unavailable (field absent),
//   or invalid (present but malformed, non-finite, or outside its domain).

export type UnitSystem = 'SI'
export type CoordinateSystem = 'global_xyz'

export interface CaseProvenance {
  sourcePath: string
  sourceSha256: string
  sourceCommitSha: string
  engineVersion: string
  generatedAt: string
}

export interface AvailableValue<T> {
  state: 'available'
  value: T
}

export interface UnavailableValue {
  state: 'unavailable'
  reason: string
}

export interface InvalidValue {
  state: 'invalid'
  reason: string
}

export type ExplicitValue<T> = AvailableValue<T> | UnavailableValue | InvalidValue
export type EngineeringValue = ExplicitValue<number>
export type TextValue = ExplicitValue<string>

export interface CaseModel {
  unitSystem: UnitSystem
  coordinateSystem: CoordinateSystem
  nodeCount: EngineeringValue
  elementCount: EngineeringValue
  dofCount: EngineeringValue
}

export interface CaseAnalysis {
  type: string
  solver: string
  converged: ExplicitValue<boolean>
  loadScale: EngineeringValue
  iterationCount: EngineeringValue
  residualTolerance: EngineeringValue
  finalNormalizedResidual: EngineeringValue
  finalRelativeIncrement: EngineeringValue
  equationScaling6DOF: EquationScaling6DOFValues
  /** Optional explicit run status when not converged (e.g. 'failed'). */
  status?: 'idle' | 'validating' | 'running' | 'converged' | 'failed'
}

export interface EquationScaling6DOFValues {
  reference_force: EngineeringValue
  characteristic_length: EngineeringValue
  translation_residual_norm: EngineeringValue
  rotation_residual_norm: EngineeringValue
  scaled_residual_norm: EngineeringValue
  translation_increment_norm: EngineeringValue
  rotation_increment_norm: EngineeringValue
  scaled_increment_norm: EngineeringValue
  scaled_tangent_condition: EngineeringValue
  scaling_hash: TextValue
}

export interface ResidualStep {
  iteration: EngineeringValue
  residual: EngineeringValue
  relativeIncrement: EngineeringValue
  alpha: EngineeringValue
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

function hasOwn(record: Record<string, unknown>, key: string): boolean {
  return Object.prototype.hasOwnProperty.call(record, key)
}

export function isAvailableValue<T>(value: ExplicitValue<T>): value is AvailableValue<T> {
  return value.state === 'available'
}

function unavailable(label: string): UnavailableValue {
  return { state: 'unavailable', reason: `${label} is not present` }
}

function invalid(reason: string, warnings: string[]): InvalidValue {
  warnings.push(reason)
  return { state: 'invalid', reason }
}

type NumberDomain = (value: number) => string | null

const finiteNumber: NumberDomain = () => null
const nonNegativeNumber: NumberDomain = (value) => (
  value >= 0 ? null : 'must be greater than or equal to zero'
)
const positiveNumber: NumberDomain = (value) => (
  value > 0 ? null : 'must be greater than zero'
)
const atLeastOne: NumberDomain = (value) => (
  value >= 1 ? null : 'must be greater than or equal to one'
)
const nonNegativeInteger: NumberDomain = (value) => (
  Number.isInteger(value) && value >= 0 ? null : 'must be a non-negative integer'
)

function engineeringNumber(
  record: Record<string, unknown>,
  key: string,
  label: string,
  domain: NumberDomain,
  warnings: string[],
): EngineeringValue {
  if (!hasOwn(record, key)) return unavailable(label)
  const value = record[key]
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return invalid(`${label} is invalid (expected a finite number)`, warnings)
  }
  const domainError = domain(value)
  if (domainError) return invalid(`${label} is invalid (${domainError})`, warnings)
  return { state: 'available', value }
}

function explicitBoolean(
  record: Record<string, unknown>,
  key: string,
  label: string,
  warnings: string[],
): ExplicitValue<boolean> {
  if (!hasOwn(record, key)) return unavailable(label)
  const value = record[key]
  if (typeof value !== 'boolean') {
    return invalid(`${label} is invalid (expected a boolean)`, warnings)
  }
  return { state: 'available', value }
}

function explicitSha256(
  record: Record<string, unknown>,
  key: string,
  label: string,
  warnings: string[],
): TextValue {
  if (!hasOwn(record, key)) return unavailable(label)
  const value = record[key]
  if (typeof value !== 'string' || !/^sha256:[0-9a-f]{64}$/.test(value)) {
    return invalid(`${label} is invalid (expected sha256:<64 lowercase hex>)`, warnings)
  }
  return { state: 'available', value }
}

function normalizeEquationScaling(
  analysis: Record<string, unknown>,
  warnings: string[],
): EquationScaling6DOFValues {
  const label = 'analysis.equation_scaling_6dof'
  const raw = analysis.equation_scaling_6dof
  if (raw !== undefined && !isRecord(raw)) {
    warnings.push(`${label} is invalid (expected an object)`)
  }
  const scaling = isRecord(raw) ? raw : {}
  const missingOrInvalid = <T>(field: string): ExplicitValue<T> => (
    raw === undefined
      ? unavailable(`${label}.${field}`)
      : { state: 'invalid', reason: `${label} is invalid (expected an object)` }
  )
  const number = (
    field: string,
    domain: NumberDomain,
  ): EngineeringValue => (
    isRecord(raw)
      ? engineeringNumber(scaling, field, `${label}.${field}`, domain, warnings)
      : missingOrInvalid<number>(field)
  )
  return {
    reference_force: number('reference_force', positiveNumber),
    characteristic_length: number('characteristic_length', positiveNumber),
    translation_residual_norm: number('translation_residual_norm', nonNegativeNumber),
    rotation_residual_norm: number('rotation_residual_norm', nonNegativeNumber),
    scaled_residual_norm: number('scaled_residual_norm', nonNegativeNumber),
    translation_increment_norm: number('translation_increment_norm', nonNegativeNumber),
    rotation_increment_norm: number('rotation_increment_norm', nonNegativeNumber),
    scaled_increment_norm: number('scaled_increment_norm', nonNegativeNumber),
    scaled_tangent_condition: number('scaled_tangent_condition', atLeastOne),
    scaling_hash: isRecord(raw)
      ? explicitSha256(scaling, 'scaling_hash', `${label}.scaling_hash`, warnings)
      : missingOrInvalid<string>('scaling_hash'),
  }
}

function toRunStatus(v: unknown): CaseAnalysis['status'] {
  return v === 'idle' || v === 'validating' || v === 'running' || v === 'converged' || v === 'failed' ? v : undefined
}

function normalizeResidualHistory(v: unknown, warnings: string[]): ResidualStep[] {
  if (v === undefined) return []
  if (!Array.isArray(v)) {
    warnings.push('residualHistory is invalid (expected an array)')
    return []
  }
  return v
    .map((row, index) => {
      if (!isRecord(row)) {
        warnings.push(`residualHistory[${index}] is invalid (expected an object)`)
        return null
      }
      return {
        iteration: engineeringNumber(row, 'iteration', `residualHistory[${index}].iteration`, nonNegativeInteger, warnings),
        residual: engineeringNumber(row, 'residual', `residualHistory[${index}].residual`, nonNegativeNumber, warnings),
        relativeIncrement: engineeringNumber(
          row,
          'relativeIncrement',
          `residualHistory[${index}].relativeIncrement`,
          nonNegativeNumber,
          warnings,
        ),
        alpha: engineeringNumber(row, 'alpha', `residualHistory[${index}].alpha`, nonNegativeNumber, warnings),
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
  const unitSystem = str(model.unitSystem)
  const coordinateSystem = str(model.coordinateSystem)
  if (!unitSystem) {
    errors.push('model.unitSystem is missing (units required)')
  } else if (unitSystem !== 'SI') {
    errors.push(`unsupported model.unitSystem: ${unitSystem} (expected SI)`)
  }
  if (!coordinateSystem) {
    errors.push('model.coordinateSystem is missing (coordinate system required)')
  } else if (coordinateSystem !== 'global_xyz') {
    errors.push(`unsupported model.coordinateSystem: ${coordinateSystem} (expected global_xyz)`)
  }

  const analysis = isRecord(raw.analysis) ? raw.analysis : null
  if (hasOwn(raw, 'analysis') && analysis == null) {
    warnings.push('analysis is invalid (expected an object)')
  }
  const converged = analysis
    ? explicitBoolean(analysis, 'converged', 'analysis.converged', warnings)
    : unavailable('analysis.converged')
  const convergenceAvailable = isAvailableValue(converged)
  if (converged.state === 'unavailable') {
    warnings.push('analysis.converged is missing — convergence is UNAVAILABLE, not inferred')
  } else if (converged.state === 'invalid') {
    warnings.push('analysis.converged is INVALID — convergence is UNAVAILABLE, not inferred')
  }

  if (errors.length > 0) {
    return { ok: false, value: null, errors, warnings, convergenceAvailable }
  }

  // Build a typed value; unknown fields on `raw` are retained via the index
  // signature. Unit and coordinate values were checked above and are preserved,
  // never silently replaced with supported defaults.
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
      unitSystem: unitSystem as UnitSystem,
      coordinateSystem: coordinateSystem as CoordinateSystem,
      nodeCount: engineeringNumber(model, 'nodeCount', 'model.nodeCount', nonNegativeInteger, warnings),
      elementCount: engineeringNumber(model, 'elementCount', 'model.elementCount', nonNegativeInteger, warnings),
      dofCount: engineeringNumber(model, 'dofCount', 'model.dofCount', nonNegativeInteger, warnings),
    },
    analysis: analysis
      ? {
          type: str(analysis.type) ?? 'unknown',
          solver: str(analysis.solver) ?? 'unknown',
          converged,
          loadScale: engineeringNumber(analysis, 'loadScale', 'analysis.loadScale', finiteNumber, warnings),
          iterationCount: engineeringNumber(
            analysis,
            'iterationCount',
            'analysis.iterationCount',
            nonNegativeInteger,
            warnings,
          ),
          residualTolerance: engineeringNumber(
            analysis,
            'residualTolerance',
            'analysis.residualTolerance',
            positiveNumber,
            warnings,
          ),
          finalNormalizedResidual: engineeringNumber(
            analysis,
            'finalNormalizedResidual',
            'analysis.finalNormalizedResidual',
            nonNegativeNumber,
            warnings,
          ),
          finalRelativeIncrement: engineeringNumber(
            analysis,
            'finalRelativeIncrement',
            'analysis.finalRelativeIncrement',
            nonNegativeNumber,
            warnings,
          ),
          equationScaling6DOF: normalizeEquationScaling(analysis, warnings),
          status: toRunStatus(analysis.status),
        }
      : undefined,
    residualHistory: normalizeResidualHistory(raw.residualHistory, warnings),
  } as WorkbenchCaseV2

  return { ok: true, value, errors, warnings, convergenceAvailable }
}
