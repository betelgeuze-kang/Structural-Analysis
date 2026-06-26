import {
  type DeveloperPreviewWorkflowStatus,
  normalizeDeveloperPreviewWorkflowStatus,
} from './developerPreviewWorkflow'

export type DeveloperPreviewWorkflowStateInput = {
  workflowShellStepPassCount: number
  executionWorkflowStepPassCount: number
  requiredWorkflowStepCount: number
  humanObservationPass: boolean
  blockerCount: number
}

export type DeveloperPreviewWorkflowState = {
  routeId: 'developer-preview-local-workflow'
  caseId: 'open-benchmark-seed-corpus'
  runId: 'execution-receipt-pending'
  status: DeveloperPreviewWorkflowStatus
  statusLabel: string
  routeLabel: string
  caseLabel: string
  runLabel: string
  claimBoundary: string
  metrics: Array<{ label: string; value: string }>
}

export function buildDeveloperPreviewWorkflowState(
  input: DeveloperPreviewWorkflowStateInput,
): DeveloperPreviewWorkflowState {
  const executionReady =
    input.executionWorkflowStepPassCount >= input.requiredWorkflowStepCount && input.humanObservationPass
  const status = normalizeDeveloperPreviewWorkflowStatus(executionReady ? 'ready' : 'blocked')
  return {
    routeId: 'developer-preview-local-workflow',
    caseId: 'open-benchmark-seed-corpus',
    runId: 'execution-receipt-pending',
    status,
    statusLabel: `route/case/run ${status}`,
    routeLabel: 'Developer Preview local GUI workflow route',
    caseLabel: 'Open benchmark seed corpus case set',
    runLabel: executionReady ? 'validated execution run' : 'execution receipt pending',
    claimBoundary:
      'route/case/run-centered workflow state is UI state structure only; it does not prove execution, human UX pass, or Developer Preview RC readiness.',
    metrics: [
      { label: 'Route', value: 'developer-preview-local-workflow' },
      { label: 'Case', value: 'open-benchmark-seed-corpus' },
      { label: 'Run', value: executionReady ? 'validated' : 'pending' },
      { label: 'Blockers', value: String(input.blockerCount) },
    ],
  }
}
