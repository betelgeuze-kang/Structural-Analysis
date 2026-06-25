// Workbench v2 UI state model + reducer.
//
// Notes on the design principles:
// - viewer selection and inspector selection are unified into a single
//   `selectedMemberId` so the 3D view and the inspector never disagree.
// - the reducer holds only UI-facing state; data loading lives in the
//   provider/adapter, not here and not in App.tsx.

import type { WorkbenchModel } from './caseSchema'

export type DataMode = 'demo' | 'live' | 'stale' | 'unavailable'

export type RunStatus = 'idle' | 'validating' | 'running' | 'converged' | 'failed'

export interface WorkbenchState {
  dataMode: DataMode
  projectId: string | null
  caseId: string | null
  runStatus: RunStatus
  residualHistory: number[]
  selectedMemberId: string | null
  warnings: string[]
}

export const initialWorkbenchState: WorkbenchState = {
  dataMode: 'unavailable',
  projectId: null,
  caseId: null,
  runStatus: 'idle',
  residualHistory: [],
  selectedMemberId: null,
  warnings: [],
}

export function toDataMode(raw: string | null | undefined): DataMode {
  switch (String(raw ?? '').toLowerCase()) {
    case 'demo':
      return 'demo'
    case 'live':
      return 'live'
    case 'stale':
      return 'stale'
    default:
      return 'unavailable'
  }
}

export type WorkbenchAction =
  | { type: 'model_loaded'; model: WorkbenchModel; warnings?: string[] }
  | { type: 'load_failed'; error: string }
  | { type: 'select_member'; memberId: string | null }
  | { type: 'set_run_status'; status: RunStatus }
  | { type: 'reset' }

export function workbenchReducer(state: WorkbenchState, action: WorkbenchAction): WorkbenchState {
  switch (action.type) {
    case 'model_loaded': {
      const { model } = action
      return {
        ...state,
        dataMode: toDataMode(model.dataModeRaw),
        projectId: model.project.id,
        caseId: model.case.id,
        residualHistory: model.residualHistory,
        // converged only when there is real residual history; demo stays idle.
        runStatus: model.residualHistory.length > 0 ? 'converged' : 'idle',
        selectedMemberId: model.members[0]?.id ?? null,
        warnings: action.warnings ?? [],
      }
    }
    case 'load_failed':
      return { ...initialWorkbenchState, dataMode: 'unavailable', runStatus: 'failed', warnings: [action.error] }
    case 'select_member':
      return { ...state, selectedMemberId: action.memberId }
    case 'set_run_status':
      return { ...state, runStatus: action.status }
    case 'reset':
      return initialWorkbenchState
    default:
      return state
  }
}
