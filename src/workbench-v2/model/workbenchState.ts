// Workbench v2 UI state model + reducer (Case Contract v2).
//
// The temporary "residualHistory.length > 0 ? converged : idle" rule is gone.
// Run status now derives from analysis.converged, and convergence that is not
// present is reported as UNAVAILABLE (convergenceAvailable=false), never guessed.

import type { WorkbenchCaseV2 } from './caseSchema'

export type DataMode = 'demo' | 'live' | 'stale' | 'unavailable'

export type RunStatus = 'idle' | 'validating' | 'running' | 'converged' | 'failed'

export interface WorkbenchState {
  dataMode: DataMode
  caseId: string | null
  runStatus: RunStatus
  convergenceAvailable: boolean
  selectedMemberId: string | null
  warnings: string[]
}

export const initialWorkbenchState: WorkbenchState = {
  dataMode: 'unavailable',
  caseId: null,
  runStatus: 'idle',
  convergenceAvailable: false,
  selectedMemberId: null,
  warnings: [],
}

/** Derive run status from analysis. Never infers convergence from residual length. */
export function deriveRunStatus(caseV2: WorkbenchCaseV2, convergenceAvailable: boolean): RunStatus {
  if (!convergenceAvailable || !caseV2.analysis) return 'idle'
  if (caseV2.analysis.converged) return 'converged'
  return caseV2.analysis.status ?? 'failed'
}

export type WorkbenchAction =
  | { type: 'case_loaded'; dataMode: DataMode; caseV2: WorkbenchCaseV2; convergenceAvailable: boolean; warnings: string[] }
  | { type: 'load_failed'; errors: string[] }
  | { type: 'select_member'; memberId: string | null }
  | { type: 'reset' }

export function workbenchReducer(state: WorkbenchState, action: WorkbenchAction): WorkbenchState {
  switch (action.type) {
    case 'case_loaded':
      return {
        ...state,
        dataMode: action.dataMode,
        caseId: action.caseV2.provenance.sourcePath,
        runStatus: deriveRunStatus(action.caseV2, action.convergenceAvailable),
        convergenceAvailable: action.convergenceAvailable,
        warnings: action.warnings,
      }
    case 'load_failed':
      return { ...initialWorkbenchState, dataMode: 'unavailable', runStatus: 'idle', warnings: action.errors }
    case 'select_member':
      return { ...state, selectedMemberId: action.memberId }
    case 'reset':
      return initialWorkbenchState
    default:
      return state
  }
}
