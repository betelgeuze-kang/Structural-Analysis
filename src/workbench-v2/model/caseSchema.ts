// Workbench Case Contract v2.
//
// Evidence policy:
// - Missing engineering values remain UNAVAILABLE. They are never replaced by
//   numeric zero, unit load scale, unit line-search alpha, or "unknown".
// - Present but malformed values remain INVALID with a reason.
// - Explicitly unsupported producer values remain UNSUPPORTED.
// - Unknown fields are preserved at every normalized object level.
// - Unit and coordinate-system mismatches remain hard blocks because showing
//   values under silently changed engineering semantics would be unsafe.

export type UnitSystem = 'SI'
export type CoordinateSystem = 'global_xyz'

export type EvidenceValue<T> =
  | { status: 'available'; value: T }
  | { status: 'unavailable' }
  | { status: 'invalid'; reason: string }
  | { status: 'unsupported'; reason: string }

export interface CaseProvenance {
  sourcePath: EvidenceValue<string>
  sourceSha256: EvidenceValue<string>
  sourceCommitSha: EvidenceValue<string>
  engineVersion: EvidenceValue<string>
  generatedAt: EvidenceValue<string>
  [extra: string]: unknown
}

export interface CaseModel {
  unitSystem: UnitSystem
  coordinateSystem: CoordinateSystem
  nodeCount: EvidenceValue<number>
  elementCount: EvidenceValue<number>
  dofCount: EvidenceValue<number>
  [extra: string]: unknown
}

export type AnalysisStatus = 'idle' | 'validating' | 'running' | 'converged' | 'failed'

export interface EquationScalingEvidence {
  characteristicLength: EvidenceValue<number>
  rawTranslationalResidual: EvidenceValue<number>
  rawRotationalResidual: EvidenceValue<number>
  dimensionlessScaledResidual: EvidenceValue<number>
  rawTranslationIncrement: EvidenceValue<number>
  rawRotationIncrement: EvidenceValue<number>
  dimensionlessScaledIncrement: EvidenceValue<number>
  scaledConditionNumber: EvidenceValue<number>
  scalingHash: EvidenceValue<string>
  [extra: string]: unknown
}

export interface CaseAnalysis {
  type: EvidenceValue<string>
  solver: EvidenceValue<string>
  converged: EvidenceValue<boolean>
  loadScale: EvidenceValue<number>
  iterationCount: EvidenceValue<number>
  residualTolerance: EvidenceValue<number>
  finalNormalizedResidual: EvidenceValue<number>
  finalRelativeIncrement: EvidenceValue<number>
  status: EvidenceValue<AnalysisStatus>
  equationScaling: EvidenceValue<EquationScalingEvidence>
  [extra: string]: unknown
}

export interface ResidualStep {
  iteration: EvidenceValue<number>
  residual: EvidenceValue<number>
  relativeIncrement: EvidenceValue<number>
  alpha: EvidenceValue<number>
  equationScaling: EvidenceValue<EquationScalingEvidence>
  [extra: string]: unknown
}

export interface WorkbenchCaseV2 {
  schemaVersion: 'workbench-case.v2'
  provenance: CaseProvenance
  model: CaseModel
  analysis?: CaseAnalysis
  residualHistory: EvidenceValue<ResidualStep[]>
  [extra: string]: unknown
}

export interface CaseValidation {
  ok: boolean
  value: WorkbenchCaseV2 | null
  errors: string[]
  warnings: string[]
  convergenceAvailable: boolean
}

const SOURCE_SHA256_PATTERN = /^sha256:[0-9a-f]{64}$/

function isRecord(v: unknown): v is Record<string, unknown> {
  return !!v && typeof v === 'object' && !Array.isArray(v)
}

export function evidenceValue<T>(evidence: EvidenceValue<T> | null | undefined): T | null {
  return evidence?.status === 'available' ? evidence.value : null
}

export function formatEvidence<T>(
  evidence: EvidenceValue<T>,
  format: (value: T) => string = (value) => String(value),
): string {
  if (evidence.status === 'available') return format(evidence.value)
  return evidence.status.toUpperCase()
}

export function evidenceReason<T>(evidence: EvidenceValue<T>): string | undefined {
  return evidence.status === 'invalid' || evidence.status === 'unsupported'
    ? evidence.reason
    : undefined
}

export function evidenceField<T, U>(
  evidence: EvidenceValue<T>,
  select: (value: T) => EvidenceValue<U>,
): EvidenceValue<U> {
  if (evidence.status === 'available') return select(evidence.value)
  if (evidence.status === 'unavailable') return { status: 'unavailable' }
  return { status: evidence.status, reason: evidence.reason }
}

function available<T>(value: T): EvidenceValue<T> {
  return { status: 'available', value }
}

function unavailable<T>(): EvidenceValue<T> {
  return { status: 'unavailable' }
}

function invalid<T>(reason: string): EvidenceValue<T> {
  return { status: 'invalid', reason }
}

function normalizeEvidence<T>(
  raw: unknown,
  parse: (value: unknown) => EvidenceValue<T>,
): EvidenceValue<T> {
  if (isRecord(raw) && typeof raw.status === 'string') {
    if (raw.status === 'unavailable') return unavailable()
    if (raw.status === 'invalid') {
      return invalid(
        typeof raw.reason === 'string' && raw.reason.trim()
          ? raw.reason
          : 'producer marked value invalid without a reason',
      )
    }
    if (raw.status === 'unsupported') {
      return {
        status: 'unsupported',
        reason:
          typeof raw.reason === 'string' && raw.reason.trim()
            ? raw.reason
            : 'producer marked value unsupported without a reason',
      }
    }
    if (raw.status === 'available') return parse(raw.value)
    return invalid(`unknown evidence status: ${String(raw.status)}`)
  }
  return parse(raw)
}

function stringEvidence(raw: unknown, label: string): EvidenceValue<string> {
  return normalizeEvidence(raw, (value) => {
    if (value == null) return unavailable()
    if (typeof value !== 'string' || value.trim() === '') {
      return invalid(`${label} must be a non-empty string`)
    }
    return available(value)
  })
}

function sha256Evidence(
  raw: unknown,
  label: string,
): EvidenceValue<string> {
  const normalized = stringEvidence(raw, label)
  if (normalized.status !== 'available') return normalized
  return SOURCE_SHA256_PATTERN.test(normalized.value)
    ? normalized
    : invalid(
        `${label} must match sha256 followed by 64 lowercase hexadecimal digits`,
      )
}

function numberEvidence(
  raw: unknown,
  label: string,
  predicate: (value: number) => boolean,
  requirement: string,
): EvidenceValue<number> {
  return normalizeEvidence(raw, (value) => {
    if (value == null) return unavailable()
    if (typeof value !== 'number' || !Number.isFinite(value) || !predicate(value)) {
      return invalid(`${label} must be ${requirement}`)
    }
    return available(value)
  })
}

function finiteEvidence(raw: unknown, label: string): EvidenceValue<number> {
  return numberEvidence(raw, label, () => true, 'finite')
}

function nonnegativeEvidence(raw: unknown, label: string): EvidenceValue<number> {
  return numberEvidence(raw, label, (value) => value >= 0, 'finite and nonnegative')
}

function nonnegativeIntegerEvidence(raw: unknown, label: string): EvidenceValue<number> {
  return numberEvidence(
    raw,
    label,
    (value) => value >= 0 && Number.isInteger(value),
    'a nonnegative integer',
  )
}

function positiveFiniteEvidence(raw: unknown, label: string): EvidenceValue<number> {
  return numberEvidence(raw, label, (value) => value > 0, 'finite and positive')
}

function booleanEvidence(raw: unknown, label: string): EvidenceValue<boolean> {
  return normalizeEvidence(raw, (value) => {
    if (value == null) return unavailable()
    return typeof value === 'boolean'
      ? available(value)
      : invalid(`${label} must be boolean`)
  })
}

function statusEvidence(raw: unknown): EvidenceValue<AnalysisStatus> {
  return normalizeEvidence(raw, (value) => {
    if (value == null) return unavailable()
    return value === 'idle'
      || value === 'validating'
      || value === 'running'
      || value === 'converged'
      || value === 'failed'
      ? available(value)
      : invalid('analysis.status is not a supported run status')
  })
}

function pick(
  record: Record<string, unknown>,
  ...keys: string[]
): unknown {
  for (const key of keys) {
    if (Object.prototype.hasOwnProperty.call(record, key)) return record[key]
  }
  return undefined
}

function normalizeEquationScaling(
  raw: unknown,
  label: string,
): EvidenceValue<EquationScalingEvidence> {
  return normalizeEvidence(raw, (value) => {
    if (value == null) return unavailable()
    if (!isRecord(value)) {
      return invalid(`${label} must be an object`)
    }
    return available({
      ...value,
      characteristicLength: positiveFiniteEvidence(
        pick(value, 'characteristicLength', 'characteristic_length'),
        `${label}.characteristicLength`,
      ),
      rawTranslationalResidual: nonnegativeEvidence(
        pick(
          value,
          'rawTranslationalResidual',
          'raw_translational_residual_norm',
          'translation_residual_norm',
        ),
        `${label}.rawTranslationalResidual`,
      ),
      rawRotationalResidual: nonnegativeEvidence(
        pick(
          value,
          'rawRotationalResidual',
          'raw_rotational_residual_norm',
          'rotation_residual_norm',
        ),
        `${label}.rawRotationalResidual`,
      ),
      dimensionlessScaledResidual: nonnegativeEvidence(
        pick(
          value,
          'dimensionlessScaledResidual',
          'dimensionless_scaled_residual_norm',
          'scaled_residual_norm',
          'scaled_residual_relative_inf',
        ),
        `${label}.dimensionlessScaledResidual`,
      ),
      rawTranslationIncrement: nonnegativeEvidence(
        pick(
          value,
          'rawTranslationIncrement',
          'raw_translation_increment_norm',
          'translation_increment_norm',
        ),
        `${label}.rawTranslationIncrement`,
      ),
      rawRotationIncrement: nonnegativeEvidence(
        pick(
          value,
          'rawRotationIncrement',
          'raw_rotation_increment_norm',
          'rotation_increment_norm',
        ),
        `${label}.rawRotationIncrement`,
      ),
      dimensionlessScaledIncrement: nonnegativeEvidence(
        pick(
          value,
          'dimensionlessScaledIncrement',
          'dimensionless_scaled_increment_norm',
          'scaled_increment_norm',
        ),
        `${label}.dimensionlessScaledIncrement`,
      ),
      scaledConditionNumber: positiveFiniteEvidence(
        pick(
          value,
          'scaledConditionNumber',
          'scaled_condition_number',
          'scaled_tangent_condition',
        ),
        `${label}.scaledConditionNumber`,
      ),
      scalingHash: sha256Evidence(
        pick(value, 'scalingHash', 'scaling_hash'),
        `${label}.scalingHash`,
      ),
    })
  })
}

function normalizeResidualHistory(raw: unknown): EvidenceValue<ResidualStep[]> {
  const forwarded = normalizeEvidence(raw, (value) => {
    if (value == null) return unavailable<ResidualStep[]>()
    if (!Array.isArray(value)) {
      return invalid<ResidualStep[]>('residualHistory must be an array')
    }

    const seen = new Set<number>()
    let previousIteration: number | null = null
    const rows: ResidualStep[] = value.map((row, index) => {
      if (!isRecord(row)) {
        const reason = `residualHistory[${index}] must be an object`
        return {
          iteration: invalid(reason),
          residual: invalid(reason),
          relativeIncrement: invalid(reason),
          alpha: invalid(reason),
          equationScaling: invalid(reason),
        }
      }

      let iteration = nonnegativeIntegerEvidence(
        row.iteration,
        `residualHistory[${index}].iteration`,
      )
      if (iteration.status === 'available') {
        const current = iteration.value
        if (seen.has(current)) {
          iteration = invalid(
            `residualHistory[${index}].iteration duplicates ${current}`,
          )
        } else {
          seen.add(current)
          if (previousIteration != null && current <= previousIteration) {
            iteration = invalid(
              `residualHistory iterations must be strictly increasing; ${current} follows ${previousIteration}`,
            )
          } else {
            previousIteration = current
          }
        }
      }

      return {
        ...row,
        iteration,
        residual: nonnegativeEvidence(
          row.residual,
          `residualHistory[${index}].residual`,
        ),
        relativeIncrement: nonnegativeEvidence(
          row.relativeIncrement,
          `residualHistory[${index}].relativeIncrement`,
        ),
        alpha: numberEvidence(
          row.alpha,
          `residualHistory[${index}].alpha`,
          (number) => number > 0 && number <= 1,
          'finite and in (0, 1]',
        ),
        equationScaling: normalizeEquationScaling(
          pick(row, 'equationScaling', 'equation_scaling'),
          `residualHistory[${index}].equationScaling`,
        ),
      }
    })
    return available(rows)
  })
  return forwarded
}

function collectEvidenceWarning<T>(
  path: string,
  evidence: EvidenceValue<T>,
  warnings: string[],
): void {
  if (evidence.status === 'available') return
  if (evidence.status === 'unavailable') {
    warnings.push(`${path} is UNAVAILABLE`)
    return
  }
  warnings.push(`${path} is ${evidence.status.toUpperCase()}: ${evidence.reason}`)
}

/**
 * Validate a raw object as a WorkbenchCaseV2. Unknown fields are allowed and
 * preserved. Engineering values keep explicit evidence state through the UI.
 */
export function validateWorkbenchCaseV2(raw: unknown): CaseValidation {
  const errors: string[] = []
  const warnings: string[] = []

  if (!isRecord(raw)) {
    return {
      ok: false,
      value: null,
      errors: ['case is not an object'],
      warnings,
      convergenceAvailable: false,
    }
  }

  if (raw.schemaVersion !== 'workbench-case.v2') {
    errors.push(
      `unexpected schemaVersion: ${String(raw.schemaVersion)} (expected workbench-case.v2)`,
    )
  }

  const prov = isRecord(raw.provenance) ? raw.provenance : {}
  const provenance: CaseProvenance = {
    ...prov,
    sourcePath: stringEvidence(prov.sourcePath, 'provenance.sourcePath'),
    sourceSha256: sha256Evidence(
      prov.sourceSha256,
      'provenance.sourceSha256',
    ),
    sourceCommitSha: stringEvidence(
      prov.sourceCommitSha,
      'provenance.sourceCommitSha',
    ),
    engineVersion: stringEvidence(
      prov.engineVersion,
      'provenance.engineVersion',
    ),
    generatedAt: stringEvidence(prov.generatedAt, 'provenance.generatedAt'),
  }
  collectEvidenceWarning(
    'provenance.sourceSha256',
    provenance.sourceSha256,
    warnings,
  )

  const rawModel = isRecord(raw.model) ? raw.model : {}
  const unitSystem = typeof rawModel.unitSystem === 'string'
    ? rawModel.unitSystem.trim()
    : ''
  const coordinateSystem = typeof rawModel.coordinateSystem === 'string'
    ? rawModel.coordinateSystem.trim()
    : ''
  if (!unitSystem) {
    errors.push('model.unitSystem is missing (units required)')
  } else if (unitSystem !== 'SI') {
    errors.push(`unsupported model.unitSystem: ${unitSystem} (expected SI)`)
  }
  if (!coordinateSystem) {
    errors.push('model.coordinateSystem is missing (coordinate system required)')
  } else if (coordinateSystem !== 'global_xyz') {
    errors.push(
      `unsupported model.coordinateSystem: ${coordinateSystem} (expected global_xyz)`,
    )
  }

  const model: CaseModel = {
    ...rawModel,
    unitSystem: unitSystem as UnitSystem,
    coordinateSystem: coordinateSystem as CoordinateSystem,
    nodeCount: nonnegativeIntegerEvidence(
      rawModel.nodeCount,
      'model.nodeCount',
    ),
    elementCount: nonnegativeIntegerEvidence(
      rawModel.elementCount,
      'model.elementCount',
    ),
    dofCount: nonnegativeIntegerEvidence(rawModel.dofCount, 'model.dofCount'),
  }
  collectEvidenceWarning('model.nodeCount', model.nodeCount, warnings)
  collectEvidenceWarning('model.elementCount', model.elementCount, warnings)
  collectEvidenceWarning('model.dofCount', model.dofCount, warnings)

  const rawAnalysis = isRecord(raw.analysis) ? raw.analysis : null
  const analysis: CaseAnalysis | undefined = rawAnalysis
    ? {
        ...rawAnalysis,
        type: stringEvidence(rawAnalysis.type, 'analysis.type'),
        solver: stringEvidence(rawAnalysis.solver, 'analysis.solver'),
        converged: booleanEvidence(
          rawAnalysis.converged,
          'analysis.converged',
        ),
        loadScale: finiteEvidence(rawAnalysis.loadScale, 'analysis.loadScale'),
        iterationCount: nonnegativeIntegerEvidence(
          rawAnalysis.iterationCount,
          'analysis.iterationCount',
        ),
        residualTolerance: positiveFiniteEvidence(
          rawAnalysis.residualTolerance,
          'analysis.residualTolerance',
        ),
        finalNormalizedResidual: nonnegativeEvidence(
          rawAnalysis.finalNormalizedResidual,
          'analysis.finalNormalizedResidual',
        ),
        finalRelativeIncrement: nonnegativeEvidence(
          rawAnalysis.finalRelativeIncrement,
          'analysis.finalRelativeIncrement',
        ),
        status: statusEvidence(rawAnalysis.status),
        equationScaling: normalizeEquationScaling(
          pick(rawAnalysis, 'equationScaling', 'equation_scaling'),
          'analysis.equationScaling',
        ),
      }
    : undefined

  const convergenceAvailable = analysis?.converged.status === 'available'
  if (!convergenceAvailable) {
    warnings.push(
      'analysis.converged is UNAVAILABLE or INVALID — convergence is not inferred',
    )
  }
  if (analysis) {
    collectEvidenceWarning(
      'analysis.iterationCount',
      analysis.iterationCount,
      warnings,
    )
    collectEvidenceWarning(
      'analysis.residualTolerance',
      analysis.residualTolerance,
      warnings,
    )
    collectEvidenceWarning(
      'analysis.finalNormalizedResidual',
      analysis.finalNormalizedResidual,
      warnings,
    )
    collectEvidenceWarning(
      'analysis.finalRelativeIncrement',
      analysis.finalRelativeIncrement,
      warnings,
    )
    collectEvidenceWarning(
      'analysis.equationScaling',
      analysis.equationScaling,
      warnings,
    )
  }

  const residualHistory = normalizeResidualHistory(raw.residualHistory)
  collectEvidenceWarning('residualHistory', residualHistory, warnings)
  if (residualHistory.status === 'available') {
    residualHistory.value.forEach((row, index) => {
      collectEvidenceWarning(
        `residualHistory[${index}].iteration`,
        row.iteration,
        warnings,
      )
      collectEvidenceWarning(
        `residualHistory[${index}].residual`,
        row.residual,
        warnings,
      )
      collectEvidenceWarning(
        `residualHistory[${index}].relativeIncrement`,
        row.relativeIncrement,
        warnings,
      )
      collectEvidenceWarning(
        `residualHistory[${index}].alpha`,
        row.alpha,
        warnings,
      )
      collectEvidenceWarning(
        `residualHistory[${index}].equationScaling`,
        row.equationScaling,
        warnings,
      )
    })
  }

  if (errors.length > 0) {
    return {
      ok: false,
      value: null,
      errors,
      warnings,
      convergenceAvailable,
    }
  }

  const value = {
    ...raw,
    schemaVersion: 'workbench-case.v2',
    provenance,
    model,
    analysis,
    residualHistory,
  } as WorkbenchCaseV2

  return {
    ok: true,
    value,
    errors,
    warnings,
    convergenceAvailable,
  }
}
