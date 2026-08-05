// Catalog of bundled demo cases for Workbench v2.
//
// These are clearly-labelled DEMO fixtures used to exercise three honest
// result scenarios the UI must distinguish:
//   - converged: analysis present and numerically converged
//   - failed: execution failed; numerical convergence remains unavailable
//   - unavailable: no analysis or convergence information (never inferred)
//
// They are NOT validated solver artifacts. The provider validates each against
// the Case Contract v2 before the UI renders it.

import convergedRaw from './fixtures/demo-case.v2.json'
import failedRaw from './fixtures/demo-case-failed.v2.json'
import unavailableRaw from './fixtures/demo-case-unavailable.v2.json'

export type DemoCaseId = 'converged' | 'failed' | 'unavailable'

export interface DemoCaseEntry {
  id: DemoCaseId
  label: string
  /** Short honest description of what the case demonstrates. */
  description: string
  raw: unknown
}

export const demoCases: DemoCaseEntry[] = [
  {
    id: 'converged',
    label: 'Converged (demo)',
    description: 'Nonlinear static run that reaches the residual tolerance.',
    raw: convergedRaw,
  },
  {
    id: 'failed',
    label: 'Analysis failed (demo)',
    description: 'Execution terminates with status failed; numerical convergence remains unavailable.',
    raw: failedRaw,
  },
  {
    id: 'unavailable',
    label: 'Convergence unavailable (demo)',
    description: 'Imported model with no analysis attached; convergence is not inferred.',
    raw: unavailableRaw,
  },
]

export const defaultDemoCaseId: DemoCaseId = 'converged'

export function getDemoCase(id: string): DemoCaseEntry {
  return demoCases.find((c) => c.id === id) ?? demoCases[0]
}

export function isDemoCaseId(id: string): id is DemoCaseId {
  return demoCases.some((c) => c.id === id)
}
