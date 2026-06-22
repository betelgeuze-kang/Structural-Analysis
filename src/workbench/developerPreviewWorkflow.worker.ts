import type {
  DeveloperPreviewWorkflowStatus,
  DeveloperPreviewWorkflowWorkerTask,
} from './developerPreviewWorkflow'

export type DeveloperPreviewWorkflowWorkerRequest = {
  task: DeveloperPreviewWorkflowWorkerTask
  caseId: string
  runId: string
  payloadChecksum?: string
}

export type DeveloperPreviewWorkflowWorkerResponse = {
  task: DeveloperPreviewWorkflowWorkerTask
  status: DeveloperPreviewWorkflowStatus
  processedOn: 'web_worker'
  caseId: string
  runId: string
  claimBoundary: string
}

type DeveloperPreviewWorkflowWorkerHost = {
  onmessage: ((event: MessageEvent<DeveloperPreviewWorkflowWorkerRequest>) => void) | null
  postMessage: (message: DeveloperPreviewWorkflowWorkerResponse) => void
}

const workerHost = self as unknown as DeveloperPreviewWorkflowWorkerHost
const knownWorkerTasks: DeveloperPreviewWorkflowWorkerTask[] = ['ifc_parse', 'result_processing']

function normalizeWorkerTask(task: string | undefined): DeveloperPreviewWorkflowWorkerTask {
  if (knownWorkerTasks.includes(task as DeveloperPreviewWorkflowWorkerTask)) {
    return task as DeveloperPreviewWorkflowWorkerTask
  }
  return 'result_processing'
}

workerHost.onmessage = (event) => {
  const task = normalizeWorkerTask(event.data?.task)
  workerHost.postMessage({
    task,
    status: 'blocked',
    processedOn: 'web_worker',
    caseId: event.data?.caseId ?? 'missing-case',
    runId: event.data?.runId ?? 'missing-run',
    claimBoundary:
      'This Web Worker boundary separates large IFC parsing and result processing from the UI thread; it does not prove execution.',
  })
}
