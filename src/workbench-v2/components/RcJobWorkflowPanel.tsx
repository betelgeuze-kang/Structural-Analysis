import { useEffect, useMemo, useRef, useState, type ReactElement } from 'react'
import { JobServicePanel } from './JobServicePanel'
import { RcQuantityReportPanel } from './RcQuantityReportPanel'
import { loadWorkbenchJob, type JobLoadResult } from '../model/jobProvider'
import { createJobWorkflowTransport, type JobAuthorizationProvider, type RcJobTransport } from '../model/jobTransport'
import { loadRcJobRequest, refreshRcJob, resumeRcJob, submitRcJob, verifyRcSubmissionBinding, SUBMIT_MAX_BYTES } from '../model/rcWorkflowProvider'
import { parseNativeJsonStrict } from '../model/nativeFrameProvider'
import type { RcJobReview } from '../model/rcJobReview'
import type { WorkbenchJobView } from '../model/jobSchema'

const JOB_ID = /^job_[0-9a-f]{32}$/
const terminal = (job: WorkbenchJobView) => ['succeeded', 'failed', 'cancelled'].includes(job.status)
const empty = (): JobLoadResult => ({ status: 'unconfigured', job: null, errors: [] })

export function rcWorkflowMessage(error: unknown, operation: 'read' | 'submit' | 'resume' | 'save' = 'read'): string {
  const message = error instanceof Error ? error.message : ''
  if (message.includes('authorization_scope_changed')) return 'Authentication scope changed. Reopen this project with the current account.'
  const status = /(?:http_|HTTP_|HTTP )([0-9]{3})/.exec(message)?.[1]
  if (status === '401') return 'Authentication is unavailable. Reopen with the current account.'
  if (status === '404') return 'This saved job or report is unavailable for the current account.'
  if (status === '409') return 'The saved source or submission key conflicts. Refresh the exact job before an explicit retry.'
  if (status === '400' || status === '413') return 'The input was rejected. Keep the draft and check its supported fields and size.'
  if (operation !== 'read' && (status === '503' || message === 'job_api_request_failed')) {
    return 'The RC action outcome is unconfirmed. Refresh the saved state before deciding on another action. The draft has been retained.'
  }
  if (status === '503' || message === 'job_api_request_failed' || message === 'job API request failed') return 'The saved RC state is temporarily unavailable. Refresh to read it again. The draft has been retained.'
  return 'The requested RC action could not be verified. The draft has been retained.'
}
export function rcWorkflowAuthorizationFailure(error: unknown): boolean {
  const message = error instanceof Error ? error.message : ''
  return /authorization_|(?:http_|HTTP_)401/.test(message)
}
export function rcProjectLink(jobId: string, reportId?: string): string {
  const url = new URL(location.pathname, location.origin)
  url.hash = '/workbench-v2'
  url.searchParams.set('rcJob', jobId)
  if (reportId) url.searchParams.set('rcReport', reportId)
  return url.href
}
function configuredJob(collection: string, statusUrl?: string): string | undefined {
  if (!statusUrl) return undefined
  const base = new URL(collection, location.origin), status = new URL(statusUrl, location.origin)
  const prefix = `${base.pathname.replace(/\/+$/, '')}/`
  if (status.origin !== base.origin || status.search || status.hash || status.username || status.password || !status.pathname.startsWith(prefix)) return undefined
  const id = status.pathname.slice(prefix.length)
  return JOB_ID.test(id) ? id : undefined
}
function sourceKey(job: WorkbenchJobView): string {
  return JSON.stringify([job.job_id, job.request, job.revision, job.terminal_event_hash, job.checkpoint, job.result, job.evidence])
}
function InputSummary({ value, saved }: { value: Record<string, unknown>; saved: boolean }): ReactElement {
  const model = value.model as Record<string, unknown> | undefined
  const config = value.config as Record<string, unknown> | undefined
  return <details data-rc-input-summary={saved ? 'stored' : 'draft'}>
    <summary>{saved ? 'Stored RC input' : 'Local RC input draft'}</summary>
    <dl className="wb2-kv"><dt>Case</dt><dd>{typeof value.case_id === 'string' ? value.case_id : 'not specified'}</dd>
      <dt>Source</dt><dd className="wb2-mono">{typeof value.source_revision === 'string' ? value.source_revision : 'not specified'}</dd>
      <dt>Model</dt><dd>{Array.isArray(model?.nodes) ? model?.nodes.length : '?'} nodes · {Array.isArray(model?.elements) ? model?.elements.length : '?'} members</dd>
    </dl>
    <p>{saved ? 'This is the hash-checked request stored by the service.' : 'The service validates support, control, preload and material contracts when explicitly submitted.'}</p>
    <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxHeight: '18rem', overflow: 'auto' }}>{JSON.stringify(config ?? {}, null, 2)}</pre>
  </details>
}

export function RcJobWorkflowPanel({ collectionUrl, initialJobStatusUrl, initialJobId, initialReportId, authorize }: {
  collectionUrl: string; initialJobStatusUrl?: string; initialJobId?: string; initialReportId?: string; authorize?: JobAuthorizationProvider
}): ReactElement {
  const [authEpoch, setAuthEpoch] = useState(0)
  const [openId, setOpenId] = useState('')
  const [requestedId, setRequestedId] = useState<string>()
  const [draft, setDraft] = useState('')
  const [draftValue, setDraftValue] = useState<Record<string, unknown> | null>(null)
  const intent = useRef<{ bytes: Uint8Array; key: string; text: string } | null>(null)
  const [intentVersion, setIntentVersion] = useState(0)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [resumeRefreshRequired, setResumeRefreshRequired] = useState<string | null>(null)
  const resumeRefreshJob = useRef<string | null>(null)
  const generation = useRef(0)
  const fileGeneration = useRef(0)
  const controllerRef = useRef<AbortController | undefined>(undefined)
  const pollTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const [session, setSession] = useState<{ key: string; transport: RcJobTransport | null; load: JobLoadResult; input: Record<string, unknown> | null }>({ key: '', transport: null, load: empty(), input: null })
  const review = useRef<RcJobReview | undefined>(undefined)
  const fullSource = useRef('')
  const immutableRequest = useRef('')
  const [refreshEpoch, setRefreshEpoch] = useState(0)
  const key = JSON.stringify([collectionUrl, initialJobStatusUrl, initialJobId, initialReportId, requestedId, authEpoch, refreshEpoch])
  const current = session.key === key ? session : { key, transport: null, load: empty(), input: null }

  function invalidate(error: unknown, operation: 'read' | 'submit' | 'resume' | 'save' = 'read'): void {
    setMessage(rcWorkflowMessage(error, operation))
    if (rcWorkflowAuthorizationFailure(error)) {
      generation.current++
      controllerRef.current?.abort()
      if (pollTimer.current) clearTimeout(pollTimer.current)
      setBusy(false)
      review.current?.dispose(); review.current = undefined
      setSession({ key, transport: null, load: empty(), input: null })
    }
  }
  const historicalAuthorization = useMemo<JobAuthorizationProvider | undefined>(() => {
    if (!authorize || !current.transport) return undefined
    const transport = current.transport, ownGeneration = generation.current
    return async context => {
      try {
        await transport.verifyAuthorizationScope()
        if (generation.current !== ownGeneration) throw new Error('job_authorization_scope_changed')
        const credentials = await authorize(context)
        if (credentials.tenantId !== transport.tenantId || generation.current !== ownGeneration) throw new Error('job_authorization_scope_changed')
        return { tenantId: credentials.tenantId, bearerToken: credentials.bearerToken }
      } catch (error) { if (generation.current === ownGeneration) invalidate(error); throw error }
    }
  }, [authorize, current.transport, key])
  const historicalTransport = useMemo(() => current.transport && current.load.job
    ? current.transport.readTransport(current.load.job.job_id) : undefined, [current.transport, current.load.job?.job_id])
  const verifyHistoricalScope = useMemo(() => {
    if (!current.transport) return undefined
    const transport = current.transport, ownGeneration = generation.current
    return async () => {
      try {
        await transport.verifyAuthorizationScope()
        if (generation.current !== ownGeneration) throw new Error('job_authorization_scope_changed')
      } catch (error) { if (generation.current === ownGeneration) invalidate(error); throw error }
    }
  }, [current.transport, key])
  useEffect(() => {
    const controller = new AbortController(), ownGeneration = ++generation.current
    controllerRef.current = controller; fileGeneration.current++
    let transport: RcJobTransport | null = null
    const active = () => !controller.signal.aborted && ownGeneration === generation.current
    review.current?.dispose(); review.current = undefined; fullSource.current = ''; immutableRequest.current = ''
    setSession({ key, transport: null, load: { status: 'loading', job: null, errors: [] }, input: null })
    setMessage(''); setBusy(false)
    const invalidSavedId = initialJobId !== undefined && !JOB_ID.test(initialJobId)
    const savedId = requestedId ?? (invalidSavedId ? undefined : initialJobId ?? configuredJob(collectionUrl, initialJobStatusUrl))
    async function poll(jobId: string): Promise<void> {
      if (!transport || !active()) return
      try {
        const job = await refreshRcJob(transport, jobId)
        if (!active()) return
        if (immutableRequest.current && immutableRequest.current !== job.request.content_hash) throw new Error('rc_request_identity_changed')
        if (!immutableRequest.current) {
          const input = await loadRcJobRequest(transport, job)
          if (!active()) return
          if (input.value.operation !== 'bounded_rc_fiber_direct_control') throw new Error('rc_request_kind_invalid')
          immutableRequest.current = job.request.content_hash
          setSession(old => ({ ...old, input: input.value }))
        }
        let loaded: JobLoadResult = { status: 'ready', job, errors: [], artifactStatus: 'not_published' }
        if (job.status === 'succeeded') {
          const identity = sourceKey(job)
          if (fullSource.current === identity && review.current) loaded = { ...loaded, artifactStatus: 'verified', rcReview: review.current }
          else {
            review.current?.dispose(); review.current = undefined
            loaded = await loadWorkbenchJob(`${transport.collectionUrl}/${jobId}`, controller.signal, undefined, transport.readTransport(jobId))
            if (!active()) { loaded.rcReview?.dispose(); return }
            if (!loaded.job || sourceKey(loaded.job) !== identity || loaded.status !== 'ready') throw new Error('rc_terminal_source_unavailable')
            if (loaded.rcReview) {
              const original = loaded.rcReview
              const guard = async <T,>(operation: () => Promise<T>): Promise<T> => {
                try {
                  await transport!.verifyAuthorizationScope()
                  if (!active()) throw new Error('rc_session_stale')
                  const result = await operation()
                  await transport!.verifyAuthorizationScope()
                  if (!active()) throw new Error('rc_session_stale')
                  return result
                } catch (error) { if (active()) invalidate(error); throw error }
              }
              const scoped: RcJobReview = { ...original,
                epoch: index => guard(() => original.epoch(index)),
                material: (member, point, fiber) => guard(() => original.material(member, point, fiber)),
                download: role => guard(() => original.download(role)),
                ...(original.materialPage ? { materialPage: (member: string, point: number, fiber: number, start: number, count: number) => guard(() => original.materialPage!(member, point, fiber, start, count)) } : {}),
                ...(original.verifyQuantityReport ? { verifyQuantityReport: (...args: Parameters<NonNullable<RcJobReview['verifyQuantityReport']>>) => guard(() => original.verifyQuantityReport!(...args)) } : {}),
                ...(original.downloadQuantityReport ? { downloadQuantityReport: (id: string) => guard(() => original.downloadQuantityReport!(id)) } : {}),
              }
              review.current = scoped; loaded = { ...loaded, rcReview: scoped }; fullSource.current = identity
            }
          }
        } else {
          review.current?.dispose(); review.current = undefined; fullSource.current = ''
          if (job.status === 'failed' && job.attempt > 0) {
            loaded = await loadWorkbenchJob(`${transport.collectionUrl}/${jobId}`, controller.signal, undefined, transport.readTransport(jobId))
            if (!active()) return
            if (!loaded.job || sourceKey(loaded.job) !== sourceKey(job)) throw new Error('rc_terminal_source_unavailable')
          }
        }
        await transport.verifyAuthorizationScope()
        if (!active()) { loaded.rcReview?.dispose(); return }
        setSession(old => ({ ...old, key, transport, load: loaded }))
        if (resumeRefreshJob.current === jobId) {
          resumeRefreshJob.current = null
          setResumeRefreshRequired(null)
        }
        if (!terminal(job)) pollTimer.current = setTimeout(() => void poll(jobId), 2000)
      } catch (error) {
        if (!active()) return
        review.current?.dispose(); review.current = undefined
        setSession({ key, transport: null, input: null, load: { status: 'invalid', job: null, errors: [rcWorkflowMessage(error)], artifactStatus: 'invalid' } })
        setMessage(rcWorkflowMessage(error))
      }
    }
    createJobWorkflowTransport(collectionUrl, controller.signal, authorize).then(value => {
      if (!active()) return
      transport = value
      setSession({ key, transport: value, load: savedId ? { status: 'loading', job: null, errors: [] } : empty(), input: null })
      if (invalidSavedId && !requestedId) setMessage('The saved RC job identifier is invalid. Open an exact job explicitly.')
      if (savedId) { setOpenId(savedId); void poll(savedId) }
    }).catch(error => { if (active()) setMessage(rcWorkflowMessage(error)) })
    return () => { controller.abort(); fileGeneration.current++; if (pollTimer.current) clearTimeout(pollTimer.current); review.current?.dispose(); review.current = undefined }
  }, [key, collectionUrl, authorize])

  function replaceDraft(text: string): void {
    fileGeneration.current++
    setDraft(text); intent.current = null; setIntentVersion(v => v + 1); setDraftValue(null)
    try {
      if (new TextEncoder().encode(text).byteLength > SUBMIT_MAX_BYTES) return
      const value = parseNativeJsonStrict(text)
      if (value && typeof value === 'object' && !Array.isArray(value)) setDraftValue(value as Record<string, unknown>)
    } catch { /* The local draft is never granted stored-input authority. */ }
  }
  async function submit(): Promise<void> {
    if (!current.transport || busy) return
    const ownGeneration = generation.current
    fileGeneration.current++
    setBusy(true); setMessage('')
    try {
      const bytes = new TextEncoder().encode(draft)
      if (!draftValue || draftValue.operation !== 'bounded_rc_fiber_direct_control' || bytes.byteLength === 0 || bytes.byteLength > SUBMIT_MAX_BYTES) throw new Error('rc_input_invalid')
      if (!intent.current || intent.current.text !== draft) intent.current = { bytes, text: draft, key: `rc-ui-${crypto.randomUUID()}` }
      const job = await submitRcJob(current.transport, intent.current.bytes, intent.current.key)
      await verifyRcSubmissionBinding(current.transport, job, intent.current.bytes)
      await current.transport.verifyAuthorizationScope()
      if (generation.current !== ownGeneration) return
      setRequestedId(job.job_id); setOpenId(job.job_id); setRefreshEpoch(v => v + 1)
    } catch (error) { if (generation.current === ownGeneration) invalidate(error, 'submit') }
    finally { if (generation.current === ownGeneration) setBusy(false) }
  }
  async function retry(): Promise<void> {
    if (!current.transport || current.load.job?.status !== 'failed' || busy || resumeRefreshJob.current === current.load.job.job_id) return
    const ownGeneration = generation.current
    const jobId = current.load.job.job_id
    setBusy(true); setMessage('')
    try {
      await resumeRcJob(current.transport, current.load.job)
      if (generation.current === ownGeneration) setRefreshEpoch(v => v + 1)
    } catch (error) {
      if (generation.current === ownGeneration) {
        resumeRefreshJob.current = jobId; setResumeRefreshRequired(jobId)
        invalidate(error, 'resume')
      }
    }
    finally { if (generation.current === ownGeneration) setBusy(false) }
  }
  return <section className="wb2-panel" data-rc-workflow="project" aria-labelledby="wb2-rc-workflow-title">
    <h2 id="wb2-rc-workflow-title" className="wb2-panel__title">RC project workflow</h2>
    <p>Open one durable RC job or explicitly submit its complete typed input. Saved analysis, quantities and declared prices stay bound to that job.</p>
    <div className="wb2-actions"><label>Saved RC job ID <input aria-label="Saved RC job ID" value={openId} onChange={e => setOpenId(e.target.value)} maxLength={36} /></label>
      <button type="button" className="wb2-btn" disabled={!JOB_ID.test(openId) || busy} onClick={() => { setRequestedId(openId); setRefreshEpoch(v => v + 1) }}>Open saved RC job</button>
      <button type="button" className="wb2-btn" disabled={busy} onClick={() => { setAuthEpoch(v => v + 1) }}>Refresh account and job</button></div>
    <details><summary>Submit a new RC input</summary>
      <label>Typed RC request JSON <textarea aria-label="Typed RC request JSON" disabled={busy} rows={8} value={draft} onChange={e => replaceDraft(e.target.value)} style={{ display: 'block', width: '100%' }} /></label>
      <label>Choose RC request JSON file <input aria-label="Choose RC request JSON file" disabled={busy} type="file" accept="application/json,.json" onChange={async e => {
        const file = e.target.files?.[0]; if (!file) return
        const ownFileGeneration = ++fileGeneration.current
        if (file.size > SUBMIT_MAX_BYTES) { setMessage('The RC input exceeds the supported request size.'); return }
        try {
          const bytes = await file.arrayBuffer()
          if (fileGeneration.current === ownFileGeneration) replaceDraft(new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(bytes))
        } catch { if (fileGeneration.current === ownFileGeneration) setMessage('The selected RC input could not be read.') }
      }} /></label>
      {draftValue ? <InputSummary value={draftValue} saved={false} /> : draft ? <p role="status">A complete supported JSON object is required.</p> : null}
      <button type="button" className="wb2-btn" data-rc-submit-intent={intentVersion} disabled={!current.transport || !draftValue || busy} onClick={() => void submit()}>Submit RC analysis</button>
      <p className="wb2-muted">An uncertain submission retry retains the same input and submission key. Change the input to start a different submission.</p>
    </details>
    {message ? <p role="alert" data-rc-workflow-error>{message}</p> : null}
    {current.input ? <InputSummary value={current.input} saved /> : null}
    {current.load.job ? <p><a data-rc-project-link href={rcProjectLink(current.load.job.job_id)} target="_blank" rel="noopener">Reopen this RC project</a></p> : null}
    {resumeRefreshRequired && resumeRefreshRequired === openId ? <p data-rc-resume-unconfirmed>The resume outcome is unconfirmed. Open the saved job or refresh the account and job to check its current state before another resume.</p> : null}
    {current.load.job?.status === 'failed' ? <button type="button" className="wb2-btn" data-rc-explicit-retry disabled={!current.transport || busy || resumeRefreshRequired === current.load.job.job_id} onClick={() => void retry()}>
      {current.load.job.checkpoint ? 'Resume RC from saved checkpoint' : 'Retry RC from the beginning'}
    </button> : null}
    <JobServicePanel key={`${key}:${current.load.job?.job_id}:${current.load.job?.attempt}`} loadStatus={current.load.status} job={current.load.job} errors={current.load.errors} artifactStatus={current.load.artifactStatus}
      engineeringResultIr={current.load.engineeringResultIr} frame3dResult={current.load.frame3dResult} frame3dArtifacts={current.load.frame3dArtifacts}
      rcReview={current.load.rcReview} failureDiagnostic={current.load.failureDiagnostic}
      jobAuthorization={historicalAuthorization}
      jobReadTransport={historicalTransport} verifyJobAuthorizationScope={verifyHistoricalScope}
      jobStatusUrl={current.load.job && current.transport ? `${current.transport.collectionUrl}/${current.load.job.job_id}` : undefined} />
    {current.transport && current.load.job && current.load.rcReview && current.load.artifactStatus === 'verified' ?
      <RcQuantityReportPanel key={`${current.transport.tenantId}:${sourceKey(current.load.job)}`} transport={current.transport} job={current.load.job}
        review={current.load.rcReview} initialReportId={current.load.job.job_id === initialJobId || current.load.job.job_id === configuredJob(collectionUrl, initialJobStatusUrl) ? initialReportId : undefined}
        onAuthorizationFailure={invalidate} /> : null}
  </section>
}
