import { expect, test } from '@playwright/test'

import { validateWorkbenchCaseV2 } from '../../src/workbench-v2/model/caseSchema'
import { deriveResultVerdict, deriveRunStatus } from '../../src/workbench-v2/model/workbenchState'

type NumericalStatus = 'converged' | 'not_converged'

function caseWithStatus(
  status: 'failed' | NumericalStatus,
  converged: unknown = false,
  includeConverged = true,
): Record<string, unknown> {
  return {
    schemaVersion: 'workbench-case.v2',
    capability_profile: 'planar_frame_verified_alpha.v1',
    provenance: {
      sourcePath: 'tests/status-taxonomy.json',
      sourceSha256: `sha256:${'f'.repeat(64)}`,
      sourceCommitSha: 'status-taxonomy-test',
      engineVersion: 'test-engine',
      generatedAt: '2026-08-05T00:00:00Z',
    },
    model: {
      unitSystem: 'SI',
      coordinateSystem: 'global_xyz',
    },
    analysis: {
      type: 'nonlinear_static',
      solver: 'test-solver',
      status,
      ...(includeConverged ? { converged } : {}),
    },
    residualHistory: [],
  }
}

test('failed execution keeps run and result status but exposes no numerical convergence evidence', () => {
  const validation = validateWorkbenchCaseV2(caseWithStatus('failed'))

  expect(validation.ok).toBe(true)
  expect(validation.value?.analysis?.status).toBe('failed')
  expect(validation.value?.analysis?.converged.status).toBe('unavailable')
  expect(validation.convergenceAvailable).toBe(false)
  expect(validation.warnings.join(' ')).toContain('analysis.status=failed')
  expect(deriveRunStatus(validation.value!, validation.convergenceAvailable)).toBe('failed')
  expect(deriveResultVerdict(validation.value!, validation.convergenceAvailable)).toBe('failed')
})

test('completed numerical non-convergence retains explicit false evidence and a distinct result verdict', () => {
  const validation = validateWorkbenchCaseV2(caseWithStatus('not_converged'))

  expect(validation.ok).toBe(true)
  expect(validation.value?.analysis?.status).toBe('not_converged')
  expect(validation.value?.analysis?.converged).toEqual({ status: 'available', value: false })
  expect(validation.convergenceAvailable).toBe(true)
  expect(deriveRunStatus(validation.value!, validation.convergenceAvailable)).toBe('not_converged')
  expect(deriveResultVerdict(validation.value!, validation.convergenceAvailable)).toBe('not_converged')
})

test.each([
  ['converged', false],
  ['not_converged', true],
] as const)(
  'contradictory %s status and converged=%s evidence is invalid, never a terminal numerical verdict',
  (status, converged) => {
    const validation = validateWorkbenchCaseV2(caseWithStatus(status, converged))

    expect(validation.ok).toBe(true)
    expect(validation.value?.analysis?.status).toBe(status)
    expect(validation.value?.analysis?.converged.status).toBe('invalid')
    expect(validation.convergenceAvailable).toBe(false)
    expect(validation.warnings.join(' ')).toContain(`analysis.converged contradicts analysis.status=${status}`)
    expect(deriveRunStatus(validation.value!, validation.convergenceAvailable)).toBe('not_run')
    expect(deriveResultVerdict(validation.value!, validation.convergenceAvailable)).toBe('invalid')
  },
)

test('a numerical status without convergence evidence remains unavailable', () => {
  const validation = validateWorkbenchCaseV2(caseWithStatus('not_converged', false, false))

  expect(validation.ok).toBe(true)
  expect(validation.value?.analysis?.status).toBe('not_converged')
  expect(validation.value?.analysis?.converged.status).toBe('unavailable')
  expect(validation.convergenceAvailable).toBe(false)
  expect(deriveRunStatus(validation.value!, validation.convergenceAvailable)).toBe('not_run')
  expect(deriveResultVerdict(validation.value!, validation.convergenceAvailable)).toBe('unavailable')
})

test('unsupported convergence evidence remains unsupported even with a numerical status', () => {
  const validation = validateWorkbenchCaseV2(caseWithStatus(
    'not_converged',
    { status: 'unsupported', reason: 'producer does not expose convergence truth' },
  ))

  expect(validation.ok).toBe(true)
  expect(validation.value?.analysis?.converged).toEqual({
    status: 'unsupported',
    reason: 'producer does not expose convergence truth',
  })
  expect(validation.convergenceAvailable).toBe(false)
  expect(deriveResultVerdict(validation.value!, validation.convergenceAvailable)).toBe('unsupported')
})
