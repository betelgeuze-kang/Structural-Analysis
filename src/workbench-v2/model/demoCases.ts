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

const convergedRecord = convergedRaw as unknown as Record<string, unknown>
const convergedModel = convergedRecord.model as Record<string, unknown>
const convergedWithImportHealth = {
  ...convergedRecord,
  model: {
    ...convergedModel,
    importHealth: {
      schemaVersion: 'workbench-import-health.v1',
      sourceFormat: 'MGT',
      supportedObjectCount: 2964,
      partialObjectCount: 12,
      unsupportedObjectCount: 4,
      silentLossDetected: false,
      issues: [
        {
          code: 'mgt_elastic_link_metadata_only',
          severity: 'warning',
          blocking: false,
          message: 'Elastic-link semantics were retained as metadata and are not analysis-authoritative.',
          sourcePath: 'demo/mgt-plant-02.mgt',
          sourceLine: 184,
          entityId: 'ELINK-17',
          remediation: 'Replace the link with a supported representation or keep the analysis scope blocked.',
        },
      ],
    },
  },
}

export const demoCases: DemoCaseEntry[] = [
  {
    id: 'converged',
    label: 'Converged (demo)',
    description: 'Nonlinear static run that reaches the residual tolerance.',
    raw: convergedWithImportHealth,
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
