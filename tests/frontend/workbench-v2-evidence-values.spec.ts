import { expect, test } from '@playwright/test'
import {
  validateWorkbenchCaseV2,
  type EvidenceValue,
} from '../../src/workbench-v2/model/caseSchema'

function available<T>(evidence: EvidenceValue<T>): T {
  expect(evidence.status).toBe('available')
  if (evidence.status !== 'available') throw new Error('evidence is unavailable')
  return evidence.value
}

function baseCase(): Record<string, unknown> {
  return {
    schemaVersion: 'workbench-case.v2',
    topUnknown: { retained: true },
    provenance: {
      sourcePath: 'tests/evidence-case.json',
      sourceSha256: `sha256:${'a'.repeat(64)}`,
      sourceCommitSha: 'abc123',
      engineVersion: 'test-engine',
      generatedAt: '2026-07-28T00:00:00Z',
      nestedUnknown: 7,
    },
    model: {
      unitSystem: 'SI',
      coordinateSystem: 'global_xyz',
      nodeCount: 0,
      elementCount: 1,
      dofCount: 6,
      nestedUnknown: 8,
    },
    analysis: {
      type: 'linear_static',
      solver: 'cpu',
      converged: true,
      loadScale: 0,
      iterationCount: 1,
      residualTolerance: 1e-8,
      finalNormalizedResidual: 0,
      finalRelativeIncrement: {
        status: 'unsupported',
        reason: 'direct linear solve has no iterative increment',
      },
      status: 'converged',
      nestedUnknown: 9,
    },
    residualHistory: [
      {
        iteration: 1,
        residual: 0,
        nestedUnknown: 10,
      },
    ],
  }
}

test('preserves explicit zero and never fills missing residual evidence', () => {
  const result = validateWorkbenchCaseV2(baseCase())

  expect(result.ok).toBe(true)
  expect(result.value).not.toBeNull()
  const value = result.value!
  expect(value.model.nodeCount).toEqual({ status: 'available', value: 0 })
  expect(value.analysis?.loadScale).toEqual({ status: 'available', value: 0 })
  expect(value.analysis?.finalNormalizedResidual).toEqual({
    status: 'available',
    value: 0,
  })
  expect(value.analysis?.finalRelativeIncrement).toEqual({
    status: 'unsupported',
    reason: 'direct linear solve has no iterative increment',
  })
  const row = available(value.residualHistory)[0]
  expect(row.relativeIncrement).toEqual({ status: 'unavailable' })
  expect(row.alpha).toEqual({ status: 'unavailable' })
  expect(row.equationScaling).toEqual({ status: 'unavailable' })
})

test('marks invalid hash, counts, tolerance, alpha, and iteration sequence', () => {
  const raw = baseCase()
  const provenance = raw.provenance as Record<string, unknown>
  const model = raw.model as Record<string, unknown>
  const analysis = raw.analysis as Record<string, unknown>
  provenance.sourceSha256 = 'sha256:not-a-digest'
  model.elementCount = -1
  model.dofCount = Number.NaN
  analysis.iterationCount = 1.5
  analysis.residualTolerance = 0
  raw.residualHistory = [
    { iteration: 2, residual: 1, relativeIncrement: 0, alpha: 1 },
    { iteration: 2, residual: 1, relativeIncrement: Number.NaN, alpha: 2 },
    { iteration: 1, residual: 1, relativeIncrement: 0, alpha: 1 },
  ]

  const result = validateWorkbenchCaseV2(raw)
  expect(result.ok).toBe(true)
  const value = result.value!
  expect(value.provenance.sourceSha256.status).toBe('invalid')
  expect(value.model.elementCount.status).toBe('invalid')
  expect(value.model.dofCount.status).toBe('invalid')
  expect(value.analysis?.iterationCount.status).toBe('invalid')
  expect(value.analysis?.residualTolerance.status).toBe('invalid')
  const rows = available(value.residualHistory)
  expect(rows[1].iteration.status).toBe('invalid')
  expect(rows[1].relativeIncrement.status).toBe('invalid')
  expect(rows[1].alpha.status).toBe('invalid')
  expect(rows[2].iteration.status).toBe('invalid')
})

test('preserves nested unknown fields and normalizes snake-case scaling evidence', () => {
  const raw = baseCase()
  const scalingHash = `sha256:${'b'.repeat(64)}`
  const analysis = raw.analysis as Record<string, unknown>
  analysis.equation_scaling = {
    characteristic_length: 3,
    raw_translational_residual_norm: 0,
    raw_rotational_residual_norm: 0,
    dimensionless_scaled_residual_norm: 0,
    raw_translation_increment_norm: 0,
    raw_rotation_increment_norm: 0,
    dimensionless_scaled_increment_norm: 0,
    scaled_tangent_condition: 12,
    scaling_hash: scalingHash,
    nestedScalingUnknown: 11,
  }

  const result = validateWorkbenchCaseV2(raw)
  expect(result.ok).toBe(true)
  const value = result.value!
  expect((value.topUnknown as { retained: boolean }).retained).toBe(true)
  expect(value.provenance.nestedUnknown).toBe(7)
  expect(value.model.nestedUnknown).toBe(8)
  expect(value.analysis?.nestedUnknown).toBe(9)
  expect(available(value.residualHistory)[0].nestedUnknown).toBe(10)
  const scaling = available(value.analysis!.equationScaling)
  expect(scaling.characteristicLength).toEqual({ status: 'available', value: 3 })
  expect(scaling.dimensionlessScaledResidual).toEqual({
    status: 'available',
    value: 0,
  })
  expect(scaling.scalingHash).toEqual({
    status: 'available',
    value: scalingHash,
  })
  expect(scaling.nestedScalingUnknown).toBe(11)
})
