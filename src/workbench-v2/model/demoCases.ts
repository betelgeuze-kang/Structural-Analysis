import convergedRaw from './fixtures/demo-case.v2.json'
import failedRaw from './fixtures/failed-case.v2.json'
import unavailableRaw from './fixtures/unavailable-case.v2.json'
import { normalizeWorkbenchCase, type WorkbenchCaseV2 } from './caseSchema'

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

export const demoCases = {
  converged: normalizeWorkbenchCase(convergedWithImportHealth),
  failed: normalizeWorkbenchCase(failedRaw),
  unavailable: normalizeWorkbenchCase(unavailableRaw),
} as const satisfies Record<string, WorkbenchCaseV2>

export type DemoCaseId = keyof typeof demoCases

export const defaultDemoCaseId: DemoCaseId = 'converged'

export function getDemoCase(caseId: DemoCaseId): WorkbenchCaseV2 {
  return demoCases[caseId]
}
