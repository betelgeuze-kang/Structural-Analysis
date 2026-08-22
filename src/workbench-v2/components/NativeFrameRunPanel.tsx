import { useState, type FormEvent, type ReactElement } from 'react'
import {
  createNativeFrameJobId,
  readModelIrFile,
  submitAndRunNativeFrameJob,
} from '../model/nativeFrameRunClient'
import { StateChip } from './StateChip'

interface NativeFrameRunPanelProps {
  submissionUrl?: string
  onJobAvailable: (jobViewUrl: string) => void
}

type PanelStatus = 'idle' | 'reading' | 'submitting' | 'running' | 'succeeded' | 'failed'

export function NativeFrameRunPanel({
  submissionUrl,
  onJobAvailable,
}: NativeFrameRunPanelProps): ReactElement {
  const [modelText, setModelText] = useState('')
  const [modelName, setModelName] = useState('')
  const [loadKind, setLoadKind] = useState<'pattern' | 'combination'>('pattern')
  const [loadId, setLoadId] = useState('LC1')
  const [resultId, setResultId] = useState('result.workbench.LC1')
  const [reportId, setReportId] = useState('report.workbench.LC1')
  const [status, setStatus] = useState<PanelStatus>('idle')
  const [error, setError] = useState('')
  const [jobId, setJobId] = useState('')
  const busy = status === 'reading' || status === 'submitting' || status === 'running'

  async function selectModel(file: File | undefined): Promise<void> {
    setModelText('')
    setModelName('')
    setError('')
    if (!file) {
      setStatus('idle')
      return
    }
    setStatus('reading')
    try {
      setModelText(await readModelIrFile(file))
      setModelName(file.name)
      setStatus('idle')
    } catch (reason: unknown) {
      setStatus('failed')
      setError(String((reason as Error)?.message ?? reason))
    }
  }

  async function submit(event: FormEvent): Promise<void> {
    event.preventDefault()
    if (!submissionUrl || !modelText || busy) return
    setError('')
    const nextJobId = createNativeFrameJobId()
    setJobId(nextJobId)
    setStatus('submitting')
    try {
      setStatus('running')
      const outcome = await submitAndRunNativeFrameJob({
        submissionUrl,
        jobId: nextJobId,
        modelIrJson: modelText,
        loadSource: { kind: loadKind, id: loadId.trim() },
        resultId: resultId.trim(),
        reportId: reportId.trim(),
      })
      onJobAvailable(outcome.jobViewUrl)
      if (outcome.status === 'succeeded') {
        setStatus('succeeded')
      } else {
        setStatus('failed')
        setError(`${outcome.error?.code ?? 'native_analysis_failed'}: ${outcome.error?.detail ?? 'analysis failed'}`)
      }
    } catch (reason: unknown) {
      setStatus('failed')
      setError(String((reason as Error)?.message ?? reason))
    }
  }

  if (!submissionUrl) {
    return (
      <section className="wb2-panel" aria-labelledby="wb2-native-run-title" data-native-frame-run="unconfigured">
        <h2 id="wb2-native-run-title" className="wb2-panel__title">Native Frame3D run</h2>
        <StateChip state="UNAVAILABLE" srLabel="Native Workbench execution" />
        <p className="wb2-unavailable" data-wb2-unavailable>
          No same-origin loopback workstation submission endpoint is configured. Browser execution is unavailable.
        </p>
      </section>
    )
  }

  return (
    <section className="wb2-panel" aria-labelledby="wb2-native-run-title" data-native-frame-run={status}>
      <h2 id="wb2-native-run-title" className="wb2-panel__title">Native Frame3D run</h2>
      <form className="wb2-native-run-form" onSubmit={(event) => void submit(event)}>
        <label className="wb2-review-field">
          <span className="wb2-review-field__label">ModelIR v2 file</span>
          <input
            type="file"
            accept="application/json,.json"
            className="wb2-review-input"
            data-native-frame-model-file
            disabled={busy}
            onChange={(event) => void selectModel(event.target.files?.[0])}
          />
        </label>
        <div className="wb2-native-run-grid">
          <label className="wb2-review-field">
            <span className="wb2-review-field__label">Load source</span>
            <select
              className="wb2-review-input"
              value={loadKind}
              disabled={busy}
              data-native-frame-load-kind
              onChange={(event) => setLoadKind(event.target.value as 'pattern' | 'combination')}
            >
              <option value="pattern">Pattern</option>
              <option value="combination">Combination</option>
            </select>
          </label>
          <label className="wb2-review-field">
            <span className="wb2-review-field__label">Load ID</span>
            <input className="wb2-review-input" value={loadId} disabled={busy} data-native-frame-load-id onChange={(event) => setLoadId(event.target.value)} />
          </label>
          <label className="wb2-review-field">
            <span className="wb2-review-field__label">Result ID</span>
            <input className="wb2-review-input" value={resultId} disabled={busy} data-native-frame-result-id onChange={(event) => setResultId(event.target.value)} />
          </label>
          <label className="wb2-review-field">
            <span className="wb2-review-field__label">Report ID</span>
            <input className="wb2-review-input" value={reportId} disabled={busy} data-native-frame-report-id onChange={(event) => setReportId(event.target.value)} />
          </label>
        </div>
        <div className="wb2-actions">
          <button type="submit" className="wb2-btn" disabled={busy || !modelText} data-native-frame-run-submit>
            {status === 'running' ? 'Running native analysis…' : status === 'submitting' ? 'Submitting…' : 'Submit and run'}
          </button>
          <span className="wb2-action-hint" data-native-frame-model-name>{modelName || 'No ModelIR selected'}</span>
        </div>
      </form>
      {status === 'succeeded' ? (
        <p className="wb2-note" data-native-frame-run-job>
          Completed <code className="wb2-mono">{jobId}</code>. Result and report remain bounded candidates until the strict bundle replay below succeeds.
        </p>
      ) : null}
      {error ? <p className="wb2-note wb2-note--warn" role="alert" data-native-frame-run-error>{error}</p> : null}
      <p className="wb2-note">
        Loopback child-worker execution with strict live job-view polling. The run request remains synchronous; this is not a background queue. A worker timeout or process failure after strict Running is recorded as terminal Failed without bundle authority. Cancellation, resume, crash recovery and retry are not established; the worker boundary is not a privilege sandbox or resource limit, and external validation, design and release authority are not established.
      </p>
    </section>
  )
}
