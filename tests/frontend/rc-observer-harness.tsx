import { StrictMode } from 'react'
import { createRoot, type Root } from 'react-dom/client'
import { RcJobWorkflowPanel } from '../../src/workbench-v2/components/RcJobWorkflowPanel'
import { createJobWorkflowTransport, JobArtifactError } from '../../src/workbench-v2/model/jobTransport'
import { loadWorkbenchJob } from '../../src/workbench-v2/model/jobProvider'
import { loadRcJobRequest, refreshRcJob } from '../../src/workbench-v2/model/rcWorkflowProvider'
import { beginRcPhaseSession } from '../../src/workbench-v2/model/rcWorkflowTrace'

interface Outcome {
  status: string
  errors: string[]
  errorKind: 'none' | 'JobArtifactError' | 'Error' | 'other'
  bytesEqual: boolean | null
  byteLength: number | null
  callerAborted: boolean
  observedSignals: number
  signalsAborted: number
  signalOverflow: boolean
}
declare global {
  interface Window {
    __RC_OBSERVER_CONFIG__: { jobId?: string; tenantId: string; bearerToken: string }
    __RC_OBSERVER_HARNESS__?: {
      replace: (jobId?: string) => void
      unmount: () => void
      mount: (jobId?: string) => void
      operate: (kind: 'request' | 'load' | 'cancel', jobId: string, expected: string) => Promise<Outcome>
      cancel: () => void
      signals: () => { count: number; aborted: number; overflow: boolean }
    }
  }
}

// Test-only entry. Calls real panel/providers; no solver model or numerical result is admitted.
const host = window.__RC_OBSERVER_CONFIG__
const authorize = () => ({ tenantId: host.tenantId, bearerToken: host.bearerToken })
const container = document.getElementById('rc-observer-root')!
let root: Root | undefined = createRoot(container)
const signals: AbortSignal[] = []
let signalOverflow = false
const nativeFetch = window.fetch
window.fetch = (input, init) => {
  if (init?.signal) {
    if (signals.length < 64) signals.push(init.signal)
    else signalOverflow = true
  }
  // Same arguments, promise and Response; no body/header mutation or fake transport.
  return nativeFetch.call(window, input, init)
}
const signalState = () => ({ count: signals.length, aborted: signals.filter(signal => signal.aborted).length, overflow: signalOverflow })
let panelJobId = host.jobId, renderRevision = 0
function render(jobId?: string) {
  panelJobId = jobId; renderRevision++
  root?.render(<StrictMode><RcJobWorkflowPanel collectionUrl="/api/v1/jobs" initialJobId={jobId} authorize={authorize} /></StrictMode>)
}
let operationController: AbortController | undefined
let operationGeneration = 700
async function operate(kind: 'request' | 'load' | 'cancel', jobId: string, expected: string): Promise<Outcome> {
  if (host.jobId !== undefined || panelJobId !== undefined || renderRevision !== 1 || operationController) {
    throw new Error('observer_control_requires_fresh_idle_panel_and_serial_operation')
  }
  const controller = new AbortController()
  operationController = controller
  const start = signals.length
  beginRcPhaseSession(controller.signal, ++operationGeneration)
  let result: Omit<Outcome, 'callerAborted' | 'observedSignals' | 'signalsAborted' | 'signalOverflow'>
  try {
    const transport = await createJobWorkflowTransport('/api/v1/jobs', controller.signal, authorize)
    if (kind === 'request') {
      const job = await refreshRcJob(transport, jobId)
      const stored = await loadRcJobRequest(transport, job)
      const expectedBytes = new TextEncoder().encode(expected)
      result = { status: 'request_verified', errors: [], errorKind: 'none',
        bytesEqual: stored.bytes.byteLength === expectedBytes.byteLength && stored.bytes.every((byte, index) => byte === expectedBytes[index]), byteLength: stored.bytes.byteLength }
    } else {
      const loaded = await loadWorkbenchJob(`${transport.collectionUrl}/${jobId}`, controller.signal, undefined, transport.readTransport(jobId))
      result = { status: loaded.status, errors: loaded.errors, errorKind: 'none', bytesEqual: null, byteLength: null }
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : ''
    const known = ['request_hash_mismatch', 'job_api_http_503', 'job_api_request_failed']
    result = { status: 'error', errors: [known.includes(message) ? message : 'unclassified_error'],
      errorKind: error instanceof JobArtifactError ? 'JobArtifactError' : error instanceof Error ? 'Error' : 'other', bytesEqual: null, byteLength: null }
  } finally {
    controller.abort()
    if (operationController === controller) operationController = undefined
  }
  const ownSignals = signals.slice(start)
  return { ...result, callerAborted: controller.signal.aborted, observedSignals: ownSignals.length,
    signalsAborted: ownSignals.filter(signal => signal.aborted).length, signalOverflow }
}
window.__RC_OBSERVER_HARNESS__ = {
  replace: render,
  unmount: () => { root?.unmount(); root = undefined },
  mount: jobId => { if (!root) root = createRoot(container); render(jobId) },
  operate,
  cancel: () => operationController?.abort(),
  signals: signalState,
}
render(host.jobId)
