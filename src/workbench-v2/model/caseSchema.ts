// Workbench Case Contract v2.
//
// Carries real analysis results + provenance. Validation policy:
// - UNKNOWN FIELDS ARE ALLOWED (forward-compatible): unrecognized keys are kept
//   and ignored, never an error.
// - HARD BLOCK (case rejected) when: schemaVersion is wrong, the source checksum
//   is missing or not strict sha256:<64 lowercase hex>, or the explicit
//   unit/coordinate contract is missing or unsupported.
//   We will not show analysis values after silently coercing engineering semantics.
// - SOFT (convergence unavailable) when analysis.converged is absent: the case
//   still loads, but convergence is reported as UNAVAILABLE, never inferred.
// - Every numeric engineering value is normalized to one explicit status:
//   available (with a domain-valid finite number), unavailable (field absent),
//   invalid (present but malformed, non-finite, or outside its domain), or
//   unsupported (the producer explicitly declares that result unsupported).

export type UnitSystem = 'SI'
export type CoordinateSystem = 'global_xyz'

export interface CaseProvenance {
  sourcePath: string
  sourceSha256: string
  sourceCommitSha: string
  engineVersion: string
  generatedAt: string
  [extra: string]: unknown
}

export interface AvailableValue<T> {
  status: 'available'
  value: T
}

export interface UnavailableValue {
  status: 'unavailable'
}

export interface InvalidValue {
  status: 'invalid'
  reason: string
}

export interface UnsupportedValue {
  status: 'unsupported'
  reason: string
}

export type EvidenceValue<T> =
  | AvailableValue<T>
  | UnavailableValue
  | InvalidValue
  | UnsupportedValue
export type ExplicitValue<T> = EvidenceValue<T>
export type EngineeringValue = EvidenceValue<number>
export type TextValue = EvidenceValue<string>

export const PLANAR_VERIFIED_ALPHA_PROFILE = 'planar_frame_verified_alpha.v1' as const

export interface ProductProfileEvidence {
  id: TextValue
  public: EvidenceValue<boolean>
  releaseEligible: EvidenceValue<boolean>
}

export type AnalysisStatus =
  | 'idle'
  | 'validating'
  | 'running'
  | 'converged'
  | 'not_converged'
  | 'failed'
  | 'blocked'
  | 'not_run'

export interface CaseModel {
  unitSystem: UnitSystem
  coordinateSystem: CoordinateSystem
  nodeCount: EngineeringValue
  elementCount: EngineeringValue
  dofCount: EngineeringValue
  [extra: string]: unknown
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
  /** Normalized solver status. It is checked against `converged`. */
  status: AnalysisStatus
  [extra: string]: unknown
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
  [extra: string]: unknown
}

export interface ResidualStep {
  iteration: EngineeringValue
  residual: EngineeringValue
  relativeIncrement: EngineeringValue
  alpha: EngineeringValue
  [extra: string]: unknown
}

export interface WorkbenchCaseV2 {
  schemaVersion: 'workbench-case.v2'
  provenance: CaseProvenance
  model: CaseModel
  analysis?: CaseAnalysis
  residualHistory: ResidualStep[]
  productProfile: ProductProfileEvidence
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
  return value.status === 'available'
}

function unavailable(): UnavailableValue {
  return { status: 'unavailable' }
}

function invalid(reason: string, warnings: string[]): InvalidValue {
  warnings.push(reason)
  return { status: 'invalid', reason }
}

type RawEvidence =
  | { kind: 'value'; value: unknown }
  | UnavailableValue
  | InvalidValue
  | UnsupportedValue

/**
 * Producers may emit a primitive value or an explicit EvidenceValue envelope.
 * Missing fields remain unavailable. An explicit unsupported status is preserved;
 * malformed envelopes become invalid and never fall back to a numeric value.
 */
function rawEvidence(
  record: Record<string, unknown>,
  key: string,
  label: string,
  warnings: string[],
): RawEvidence {
  if (!hasOwn(record, key)) return unavailable()
  const raw = record[key]
  if (!isRecord(raw) || !hasOwn(raw, 'status')) return { kind: 'value', value: raw }

  if (raw.status === 'available') {
    if (!hasOwn(raw, 'value')) {
      return invalid(`${label} is invalid (available evidence has no value)`, warnings)
    }
    return { kind: 'value', value: raw.value }
  }
  if (raw.status === 'unavailable') return unavailable()
  if (raw.status === 'invalid' || raw.status === 'unsupported') {
    const reason = str(raw.reason)
    if (!reason) {
      return invalid(`${label} is invalid (${String(raw.status)} evidence has no reason)`, warnings)
    }
    if (raw.status === 'unsupported') return { status: 'unsupported', reason }
    warnings.push(`${label} is invalid (${reason})`)
    return { status: 'invalid', reason }
  }
  return invalid(`${label} is invalid (unknown evidence status)`, warnings)
}

type NumberDomain = (value: number) => string | null

const finiteNumber: NumberDomain = () => null
const nonNegativeNumber: NumberDomain = (value) => (
  value >= 0 ? null : 'must be greater than or equal to zero'
)
const positiveNumber: NumberDomain = (value) => (
  value > 0 ? null : 'must be greater than zero'
)
const openClosedUnitInterval: NumberDomain = (value) => (
  value > 0 && value <= 1 ? null : 'must be greater than zero and less than or equal to one'
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
  const evidence = rawEvidence(record, key, label, warnings)
  if (!('kind' in evidence)) return evidence
  const value = evidence.value
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    return invalid(`${label} is invalid (expected a finite number)`, warnings)
  }
  const domainError = domain(value)
  if (domainError) return invalid(`${label} is invalid (${domainError})`, warnings)
  return { status: 'available', value }
}

function explicitBoolean(
  record: Record<string, unknown>,
  key: string,
  label: string,
  warnings: string[],
): ExplicitValue<boolean> {
  const evidence = rawEvidence(record, key, label, warnings)
  if (!('kind' in evidence)) return evidence
  const value = evidence.value
  if (typeof value !== 'boolean') {
    return invalid(`${label} is invalid (expected a boolean)`, warnings)
  }
  return { status: 'available', value }
}

function explicitSha256(
  record: Record<string, unknown>,
  key: string,
  label: string,
  warnings: string[],
): TextValue {
  const evidence = rawEvidence(record, key, label, warnings)
  if (!('kind' in evidence)) return evidence
  const value = evidence.value
  if (typeof value !== 'string' || !/^sha256:[0-9a-f]{64}$/.test(value)) {
    return invalid(`${label} is invalid (expected sha256:<64 lowercase hex>)`, warnings)
  }
  return { status: 'available', value }
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
      ? unavailable()
      : { status: 'invalid', reason: `${label} is invalid (expected an object)` }
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
    ...scaling,
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

function toRunStatus(v: unknown): AnalysisStatus | undefined {
  return v === 'idle'
    || v === 'validating'
    || v === 'running'
    || v === 'converged'
    || v === 'not_converged'
    || v === 'failed'
    || v === 'blocked'
    || v === 'not_run'
    ? v
    : undefined
}

function normalizeAnalysisTruth(
  analysis: Record<string, unknown>,
  warnings: string[],
): { status: AnalysisStatus; converged: ExplicitValue<boolean> } {
  const declaredStatus = toRunStatus(analysis.status)
  const declaredConverged = explicitBoolean(analysis, 'converged', 'analysis.converged', warnings)

  if (hasOwn(analysis, 'status') && declaredStatus === undefined) {
    warnings.push(`analysis.status is invalid (${String(analysis.status)})`)
    return {
      status: 'not_run',
      converged: { status: 'invalid', reason: `analysis.status is invalid (${String(analysis.status)})` },
    }
  }

  // Legacy cases may omit status. Preserve their explicit boolean without
  // deriving truth from job state, residuals, or any other secondary signal.
  if (declaredStatus === undefined) {
    if (isAvailableValue(declaredConverged)) {
      return {
        status: declaredConverged.value ? 'converged' : 'not_converged',
        converged: declaredConverged,
      }
    }
    return { status: 'not_run', converged: declaredConverged }
  }

  if (declaredStatus === 'blocked' || declaredStatus === 'not_run'
      || declaredStatus === 'idle' || declaredStatus === 'validating' || declaredStatus === 'running') {
    if (isAvailableValue(declaredConverged)) {
      warnings.push(
        `analysis.converged is ignored because analysis.status=${declaredStatus}; convergence is UNAVAILABLE`,
      )
    }
    return { status: declaredStatus, converged: unavailable() }
  }

  const expected = declaredStatus === 'converged'
  if (!isAvailableValue(declaredConverged)) return { status: declaredStatus, converged: declaredConverged }
  if (declaredConverged.value !== expected) {
    const reason = `analysis.converged contradicts analysis.status=${declaredStatus}`
    warnings.push(reason)
    return { status: declaredStatus, converged: { status: 'invalid', reason } }
  }
  return { status: declaredStatus, converged: declaredConverged }
}

function normalizeResidualHistory(v: unknown, warnings: string[]): ResidualStep[] {
  if (v === undefined) return []
  if (!Array.isArray(v)) {
    warnings.push('residualHistory is invalid (expected an array)')
    return []
  }
  const history = v
    .map((row, index) => {
      if (!isRecord(row)) {
        warnings.push(`residualHistory[${index}] is invalid (expected an object)`)
        return null
      }
      return {
        ...row,
        iteration: engineeringNumber(row, 'iteration', `residualHistory[${index}].iteration`, nonNegativeInteger, warnings),
        residual: engineeringNumber(row, 'residual', `residualHistory[${index}].residual`, nonNegativeNumber, warnings),
        relativeIncrement: engineeringNumber(
          row,
          'relativeIncrement',
          `residualHistory[${index}].relativeIncrement`,
          nonNegativeNumber,
          warnings,
        ),
        alpha: engineeringNumber(row, 'alpha', `residualHistory[${index}].alpha`, openClosedUnitInterval, warnings),
      }
    })
    .filter((r): r is ResidualStep => r != null)

  const seenIterations = new Set<number>()
  let previousIteration: number | null = null
  return history.map((row, index) => {
    if (!isAvailableValue(row.iteration)) return row
    const iteration = row.iteration.value
    let reason: string | null = null
    if (seenIterations.has(iteration)) {
      reason = `residualHistory[${index}].iteration is invalid (duplicate iteration ${iteration})`
    } else if (previousIteration != null && iteration <= previousIteration) {
      reason = (
        `residualHistory[${index}].iteration is invalid `
        + `(iterations must be strictly increasing; previous ${previousIteration}, current ${iteration})`
      )
    }
    seenIterations.add(iteration)
    if (reason) {
      warnings.push(reason)
      return { ...row, iteration: { status: 'invalid', reason } }
    }
    previousIteration = iteration
    return row
  })
}

function normalizeProductProfile(raw: Record<string, unknown>, warnings: string[]): ProductProfileEvidence {
  const token = raw.capabilityProfile ?? raw.capability_profile
  if (token === undefined) {
    return {
      id: unavailable(),
      public: unavailable(),
      releaseEligible: unavailable(),
    }
  }
  if (typeof token !== 'string' || token.trim() === '') {
    const reason = 'capability profile is invalid (expected a non-empty string)'
    warnings.push(reason)
    return {
      id: { status: 'invalid', reason },
      public: { status: 'invalid', reason },
      releaseEligible: { status: 'invalid', reason },
    }
  }
  if (token === PLANAR_VERIFIED_ALPHA_PROFILE) {
    return {
      id: { status: 'available', value: token },
      public: { status: 'available', value: true },
      releaseEligible: { status: 'available', value: false },
    }
  }
  return {
    id: { status: 'available', value: token },
    public: unavailable(),
    releaseEligible: unavailable(),
  }
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
  const sourceSha256 = explicitSha256(
    prov,
    'sourceSha256',
    'provenance.sourceSha256',
    warnings,
  )
  if (sourceSha256.status === 'unavailable') {
    errors.push('provenance.sourceSha256 is missing — UNAVAILABLE (source checksum required)')
  } else if (sourceSha256.status === 'invalid') {
    errors.push(`provenance.sourceSha256 is INVALID (${sourceSha256.reason})`)
  } else if (sourceSha256.status === 'unsupported') {
    errors.push(`provenance.sourceSha256 is UNSUPPORTED (${sourceSha256.reason})`)
  }

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
  const analysisTruth = analysis
    ? normalizeAnalysisTruth(analysis, warnings)
    : { status: 'not_run' as const, converged: unavailable() }
  const converged = analysisTruth.converged
  const convergenceAvailable = isAvailableValue(converged)
  if (converged.status === 'unavailable') {
    warnings.push('analysis.converged is missing — convergence is UNAVAILABLE, not inferred')
  } else if (converged.status === 'invalid') {
    warnings.push('analysis.converged is INVALID — convergence is UNAVAILABLE, not inferred')
  } else if (converged.status === 'unsupported') {
    warnings.push('analysis.converged is UNSUPPORTED — convergence is UNAVAILABLE, not inferred')
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
      ...prov,
      sourcePath: str(prov.sourcePath) ?? 'unknown',
      sourceSha256: (sourceSha256 as AvailableValue<string>).value,
      sourceCommitSha: str(prov.sourceCommitSha) ?? 'unknown',
      engineVersion: str(prov.engineVersion) ?? 'unknown',
      generatedAt: str(prov.generatedAt) ?? 'unknown',
    },
    model: {
      ...model,
      unitSystem: unitSystem as UnitSystem,
      coordinateSystem: coordinateSystem as CoordinateSystem,
      nodeCount: engineeringNumber(model, 'nodeCount', 'model.nodeCount', nonNegativeInteger, warnings),
      elementCount: engineeringNumber(model, 'elementCount', 'model.elementCount', nonNegativeInteger, warnings),
      dofCount: engineeringNumber(model, 'dofCount', 'model.dofCount', nonNegativeInteger, warnings),
    },
    analysis: analysis
      ? {
          ...analysis,
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
          status: analysisTruth.status,
        }
      : undefined,
    residualHistory: normalizeResidualHistory(raw.residualHistory, warnings),
    productProfile: normalizeProductProfile(raw, warnings),
  } as WorkbenchCaseV2

  return { ok: true, value, errors, warnings, convergenceAvailable }
}
