import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactElement } from 'react'
import { JobServicePanel } from './JobServicePanel'
import { RcQuantityReportPanel } from './RcQuantityReportPanel'
import { RcModelEditor } from './RcModelEditor'
import { RcScenarioComparisonPanel, type RcScenarioProjectSnapshot } from './RcScenarioComparisonPanel'
import { RcJobDiagnosticsPanel } from './RcJobDiagnosticsPanel'
import { rcRequestChanges } from '../model/rcJobDiagnostics'
import { loadWorkbenchJob, type JobLoadResult } from '../model/jobProvider'
import { createJobWorkflowTransport, type JobAuthorizationProvider, type RcJobTransport } from '../model/jobTransport'
import { loadRcJobRequest, refreshRcJob, resumeRcJob, submitRcJob, verifyRcSubmissionBinding, SUBMIT_MAX_BYTES } from '../model/rcWorkflowProvider'
import { parseNativeJsonStrict } from '../model/nativeFrameProvider'
import type { RcJobReview } from '../model/rcJobReview'
import type { RcCorotationalReportReview } from '../model/rcCorotationalReportReview'
import { isRcCorotationalRequest, validateRcRequestProfile } from '../model/rcJobSchema'
import type { WorkbenchJobView } from '../model/jobSchema'
import { beginRcPhaseSession, traceRcPhase } from '../model/rcWorkflowTrace'
import { RC_PROJECT_MAX_BYTES, parseRcProjectFile, serializeRcProjectFile, rcProjectJobRef, type RcProjectFile, type RcProjectJobRef, type RcProjectScope } from '../model/rcProjectFile'

const JOB_ID = /^job_[0-9a-f]{32}$/
const terminal = (job: WorkbenchJobView) => ['succeeded', 'failed', 'cancelled'].includes(job.status)
const empty = (): JobLoadResult => ({ status: 'unconfigured', job: null, errors: [] })
const projectScope = (transport: RcJobTransport): RcProjectScope => ({ collectionUrl: transport.collectionUrl, tenantId: transport.tenantId ?? null })
const sameScope = (a: RcProjectScope | null, b: RcProjectScope): boolean => a?.collectionUrl === b.collectionUrl && a.tenantId === b.tenantId

export function rcWorkflowMessage(error: unknown, operation: 'read' | 'submit' | 'resume' | 'save' = 'read'): string {
  const message = error instanceof Error ? error.message : ''
  if (message.includes('authorization_scope_changed')) return 'Authentication scope changed. Reopen this project with the current account.'
  if (/^rc_(?:request|checkpoint|result|evidence|artifacts|corotational_report)_too_large$/.test(message)) return 'This saved result exceeds this workspace’s review size limit.'
  if (message === 'rc_review_budget_invalid') return 'This workspace’s review size limit is invalid. Contact the workspace administrator.'
  const status = /(?:http_|HTTP_|HTTP )([0-9]{3})/.exec(message)?.[1]
  if (status === '401' || status === '403') return 'Authentication is unavailable. Reopen with the current account.'
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
  return /authorization_|(?:http_|HTTP_)(?:401|403)/.test(message)
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
  const corotational = isRcCorotationalRequest(value)
  return <details data-rc-input-summary={saved ? 'stored' : 'draft'}>
    <summary>{saved ? 'Stored RC input' : 'Local RC input draft'}</summary>
    <dl className="wb2-kv"><dt>Case</dt><dd>{typeof value.case_id === 'string' ? value.case_id : 'not specified'}</dd>
      <dt>Source</dt><dd className="wb2-mono">{typeof value.source_revision === 'string' ? value.source_revision : 'not specified'}</dd>
      <dt>Profile</dt><dd>{corotational ? 'Experimental corotational nodal control' : 'Bounded RC fiber control'}</dd>
      <dt>Model</dt><dd>{Array.isArray(model?.nodes) ? model?.nodes.length : '?'} nodes · {Array.isArray(model?.elements) ? model?.elements.length : '?'} members</dd>
    </dl>
    <p>{saved ? 'This is the hash-checked request stored by the service.' : corotational ? 'The service validates the experimental nodal model, control, fixed loads and execution policy when explicitly submitted.' : 'The service validates supported cantilever, control and material contracts when explicitly submitted.'}</p>
    <pre style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxHeight: '18rem', overflow: 'auto' }}>{JSON.stringify(config ?? {}, null, 2)}</pre>
  </details>
}

interface RcJobWorkflowPanelProps {
  rcReviewResultMaxBytes?: number
  collectionUrl: string; initialJobStatusUrl?: string; initialJobId?: string; initialReportId?: string; authorize?: JobAuthorizationProvider
}

export function RcJobWorkflowPanel(props: RcJobWorkflowPanelProps): ReactElement {
  // A saved link is a new session. Local Open/submit intent must never shadow
  // later Back/Forward navigation, including a different report on the same job.
  const source = JSON.stringify([props.collectionUrl, props.initialJobStatusUrl, props.initialJobId, props.initialReportId, props.rcReviewResultMaxBytes])
  return <RcJobWorkflowSession key={source} {...props} />
}

function RcJobWorkflowSession({ collectionUrl, initialJobStatusUrl, initialJobId, initialReportId, authorize, rcReviewResultMaxBytes }: RcJobWorkflowPanelProps): ReactElement {
  const [authEpoch, setAuthEpoch] = useState(0)
  const [openId, setOpenId] = useState('')
  const [requestedId, setRequestedId] = useState<string>()
  const [draft, setDraft] = useState('')
  const [draftValue, setDraftValue] = useState<Record<string, unknown> | null>(null)
  const [editorDirty, setEditorDirty] = useState(false)
  const [changedRun, setChangedRun] = useState<{ jobId: string; requestHash: string; tenantId: string | undefined; input: Record<string, unknown>; originalStatus?: string; childId?: string; childRequestHash?: string; submitted?: Record<string, unknown> } | null>(null)
  const [changedReferences, setChangedReferences] = useState<RcProjectFile['changedRun']>(null)
  const intent = useRef<{ bytes: Uint8Array; key: string; text: string; job: RcProjectJobRef | null } | null>(null)
  const intentScope = useRef<RcProjectScope | null>(null)
  const lastScope = useRef<RcProjectScope | null>(null)
  const selectedRef = useRef<RcProjectJobRef | null>(null)
  const [projectBusy, setProjectBusy] = useState(false)
  const [projectMessage, setProjectMessage] = useState('')
  const [projectRestore, setProjectRestore] = useState<{ revision: number; scope: RcProjectScope; scenarios: RcProjectFile['scenarios']; baselineId: string | null; variantId: string | null }>()
  const [scenarioState, setScenarioState] = useState<RcScenarioProjectSnapshot>({ scenarios: [], baselineId: null, variantId: null, busy: false, scope: null, restoreRevision: null })
  const onProjectChange = useCallback((state: typeof scenarioState) => setScenarioState(state), [])
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
  const corotationalReview = useRef<RcCorotationalReportReview | undefined>(undefined)
  function disposeReviews(): void {
    review.current?.dispose(); review.current = undefined
    corotationalReview.current?.dispose(); corotationalReview.current = undefined
  }
  const fullSource = useRef('')
  const immutableRequest = useRef('')
  const [refreshEpoch, setRefreshEpoch] = useState(0)
  const key = JSON.stringify([collectionUrl, initialJobStatusUrl, initialJobId, initialReportId, requestedId, authEpoch, refreshEpoch])
  const current = session.key === key ? session : { key, transport: null, load: empty(), input: null }

  function invalidate(error: unknown, operation: 'read' | 'submit' | 'resume' | 'save' = 'read'): void {
    setMessage(rcWorkflowMessage(error, operation))
    if (rcWorkflowAuthorizationFailure(error)) {
      setChangedRun(null)
      setChangedReferences(null)
      intent.current = null; intentScope.current = null; selectedRef.current = null
      setProjectRestore(undefined); setProjectBusy(false)
      generation.current++
      controllerRef.current?.abort()
      if (pollTimer.current) clearTimeout(pollTimer.current)
      setBusy(false)
      disposeReviews()
      setSession({ key, transport: null, load: empty(), input: null })
    }
  }
  useEffect(() => {
    const controller = new AbortController(), ownGeneration = ++generation.current
    beginRcPhaseSession(controller.signal, ownGeneration)
    traceRcPhase(controller.signal, 'effect.setup')
    controllerRef.current = controller; fileGeneration.current++
    let transport: RcJobTransport | null = null
    const active = () => !controller.signal.aborted && ownGeneration === generation.current
    disposeReviews(); fullSource.current = ''; immutableRequest.current = ''
    setSession({ key, transport: null, load: { status: 'loading', job: null, errors: [] }, input: null })
    setMessage(''); setBusy(false); setProjectBusy(false)
    const invalidSavedId = initialJobId !== undefined && !JOB_ID.test(initialJobId)
    const savedId = requestedId ?? (invalidSavedId ? undefined : initialJobId ?? configuredJob(collectionUrl, initialJobStatusUrl))
    async function poll(jobId: string): Promise<void> {
      if (!transport || !active()) return
      traceRcPhase(controller.signal, 'poll.begin')
      try {
        traceRcPhase(controller.signal, 'poll.job.begin')
        const job = await refreshRcJob(transport, jobId)
        traceRcPhase(controller.signal, 'poll.job.end')
        if (!active()) return
        if (selectedRef.current?.jobId === jobId && selectedRef.current.requestHash !== job.request.content_hash) throw new Error('rc_project_job_binding_changed')
        if (immutableRequest.current && immutableRequest.current !== job.request.content_hash) throw new Error('rc_request_identity_changed')
        if (!immutableRequest.current) {
          const input = await loadRcJobRequest(transport, job)
          if (!active()) return
          validateRcRequestProfile(input.value)
          immutableRequest.current = job.request.content_hash
          setSession(old => ({ ...old, input: input.value }))
        }
        let loaded: JobLoadResult = { status: 'ready', job, errors: [], artifactStatus: 'not_published' }
        if (job.status === 'succeeded') {
          const identity = sourceKey(job)
          if (fullSource.current === identity && corotationalReview.current) loaded = { ...loaded, artifactStatus: 'report_verified', rcCorotationalReview: corotationalReview.current }
          else if (fullSource.current === identity && review.current) loaded = { ...loaded, artifactStatus: 'verified', rcReview: review.current }
          else {
            disposeReviews()
            loaded = await loadWorkbenchJob(`${transport.collectionUrl}/${jobId}`, controller.signal, undefined, transport.readTransport(jobId), rcReviewResultMaxBytes)
            if (!active()) { loaded.rcReview?.dispose(); loaded.rcCorotationalReview?.dispose(); return }
            if (loaded.status === 'error' && loaded.errors.length === 1) throw new Error(loaded.errors[0])
            if (!loaded.job || sourceKey(loaded.job) !== identity || loaded.status !== 'ready') throw new Error('rc_terminal_source_unavailable')
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
            if (loaded.rcCorotationalReview) {
              const original = loaded.rcCorotationalReview
              const scoped: RcCorotationalReportReview = { ...original,
                ...(original.comparisonSummary ? { comparisonSummary: () => guard(() => original.comparisonSummary!()) } : {}),
                state: index => guard(() => original.state(index)),
                statePage: (start, count) => guard(() => original.statePage(start, count)),
                download: () => guard(() => original.download()),
                reopen: bytes => guard(() => original.reopen(bytes)),
              }
              corotationalReview.current = scoped; loaded = { ...loaded, rcCorotationalReview: scoped }; fullSource.current = identity
            }
            if (loaded.rcReview) {
              const original = loaded.rcReview
              const scoped: RcJobReview = { ...original,
                ...(original.comparisonSummary ? { comparisonSummary: () => guard(() => original.comparisonSummary!()) } : {}),
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
          disposeReviews(); fullSource.current = ''
          if (job.status === 'failed' && job.attempt > 0) {
            traceRcPhase(controller.signal, 'poll.failed-load.begin')
            loaded = await loadWorkbenchJob(`${transport.collectionUrl}/${jobId}`, controller.signal, undefined, transport.readTransport(jobId), rcReviewResultMaxBytes)
            traceRcPhase(controller.signal, 'poll.failed-load.end')
            if (!active()) return
            if (!loaded.job || sourceKey(loaded.job) !== sourceKey(job)) throw new Error('rc_terminal_source_unavailable')
          }
        }
        await transport.verifyAuthorizationScope()
        if (!active()) { loaded.rcReview?.dispose(); loaded.rcCorotationalReview?.dispose(); return }
        selectedRef.current = rcProjectJobRef(job)
        traceRcPhase(controller.signal, loaded.status === 'ready' ? 'ui.ready.queue' : 'ui.other.queue')
        setSession(old => ({ ...old, key, transport, load: loaded }))
        if (resumeRefreshJob.current === jobId) {
          resumeRefreshJob.current = null
          setResumeRefreshRequired(null)
        }
        if (!terminal(job)) pollTimer.current = setTimeout(() => void poll(jobId), 2000)
      } catch (error) {
        traceRcPhase(controller.signal, 'poll.error')
        if (!active()) return
        disposeReviews()
        setSession({ key, transport: rcWorkflowAuthorizationFailure(error) ? null : transport, input: null,
          load: { status: 'invalid', job: null, errors: [rcWorkflowMessage(error)], artifactStatus: 'invalid' } })
        invalidate(error)
      }
    }
    createJobWorkflowTransport(collectionUrl, controller.signal, authorize).then(value => {
      if (!active()) return
      if (lastScope.current && !sameScope(lastScope.current, projectScope(value))) {
        intent.current = null; intentScope.current = null; selectedRef.current = null
        setChangedRun(null); setChangedReferences(null); setProjectRestore(undefined)
      }
      lastScope.current = projectScope(value)
      transport = value
      traceRcPhase(controller.signal, 'transport.ready')
      setSession({ key, transport: value, load: savedId ? { status: 'loading', job: null, errors: [] } : empty(), input: null })
      if (invalidSavedId && !requestedId) setMessage('The saved RC job identifier is invalid. Open an exact job explicitly.')
      if (savedId) { setOpenId(savedId); void poll(savedId) }
    }).catch(error => { if (active()) setMessage(rcWorkflowMessage(error)) })
    return () => { traceRcPhase(controller.signal, 'effect.cleanup'); generation.current++; controller.abort(); fileGeneration.current++; if (pollTimer.current) clearTimeout(pollTimer.current); disposeReviews() }
  }, [key, collectionUrl, authorize, rcReviewResultMaxBytes])
  useLayoutEffect(() => {
    if (current.transport && current.load.status === 'ready') traceRcPhase(current.transport, 'ui.ready.commit')
  }, [key, current.transport, current.load.status, current.load.job?.job_id, current.load.job?.attempt])

  function replaceDraft(text: string): void {
    fileGeneration.current++
    setDraft(text)
    if (intent.current?.text !== text) { intent.current = null; intentScope.current = null; setIntentVersion(v => v + 1) }
    setDraftValue(null)
    try {
      if (new TextEncoder().encode(text).byteLength > SUBMIT_MAX_BYTES) return
      const value = parseNativeJsonStrict(text)
      if (value && typeof value === 'object' && !Array.isArray(value)) setDraftValue(value as Record<string, unknown>)
    } catch { /* The local draft is never granted stored-input authority. */ }
  }
  async function submit(): Promise<void> {
    if (!current.transport || busy || projectBusy || editorDirty) return
    const ownGeneration = generation.current
    fileGeneration.current++
    setBusy(true); setMessage('')
    try {
      const bytes = new TextEncoder().encode(draft)
      if (!draftValue || bytes.byteLength === 0 || bytes.byteLength > SUBMIT_MAX_BYTES) throw new Error('rc_input_invalid')
      validateRcRequestProfile(draftValue)
      if (changedRun && !changedRun.childId && changedRun.tenantId === current.transport.tenantId
        && rcRequestChanges(changedRun.input, draftValue).changes.length === 0) throw new Error('rc_changed_run_requires_edit')
      await current.transport.verifyAuthorizationScope()
      if (generation.current !== ownGeneration) return
      if (intent.current && !sameScope(intentScope.current, projectScope(current.transport))) throw new Error('job_authorization_scope_changed')
      if (!intent.current || intent.current.text !== draft) {
        intent.current = { bytes, text: draft, key: `rc-ui-${crypto.randomUUID()}`, job: null }
        intentScope.current = projectScope(current.transport)
      }
      const submittedIntent = intent.current
      // Restored known jobs are read even when unavailable. Their identifiers
      // must never be discarded in favor of a fresh submission.
      const job = submittedIntent.job
        ? await refreshRcJob(current.transport, submittedIntent.job.jobId)
        : await submitRcJob(current.transport, submittedIntent.bytes, submittedIntent.key)
      if (generation.current !== ownGeneration) return
      if (submittedIntent.job && submittedIntent.job.requestHash !== job.request.content_hash) throw new Error('rc_project_job_binding_changed')
      submittedIntent.job = rcProjectJobRef(job)
      await verifyRcSubmissionBinding(current.transport, job, submittedIntent.bytes)
      await current.transport.verifyAuthorizationScope()
      if (generation.current !== ownGeneration) return
      if (changedRun && !changedRun.childId && changedRun.tenantId === current.transport.tenantId) {
        setChangedRun({ ...changedRun, childId: job.job_id, childRequestHash: job.request.content_hash, submitted: structuredClone(draftValue) })
        setChangedReferences({ original: { jobId: changedRun.jobId, requestHash: changedRun.requestHash }, child: rcProjectJobRef(job) })
      }
      selectedRef.current = rcProjectJobRef(job)
      setRequestedId(job.job_id); setOpenId(job.job_id); setRefreshEpoch(v => v + 1)
    } catch (error) { if (generation.current === ownGeneration) invalidate(error, 'submit') }
    finally { if (generation.current === ownGeneration) setBusy(false) }
  }
  async function retry(): Promise<void> {
    if (!current.transport || current.load.job?.status !== 'failed' || busy || projectBusy || resumeRefreshJob.current === current.load.job.job_id) return
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
  async function prepareChangedRun(): Promise<void> {
    if (!current.transport || !current.input || current.load.job?.status !== 'failed' || busy || projectBusy) return
    const own = generation.current
    const transport = current.transport, job = current.load.job
    setBusy(true)
    try {
      const stored = await loadRcJobRequest(transport, job)
      await transport.verifyAuthorizationScope()
      if (generation.current !== own) return
      setChangedRun({ jobId: job.job_id, requestHash: job.request.content_hash, tenantId: transport.tenantId, input: stored.value, originalStatus: job.status })
      setChangedReferences({ original: rcProjectJobRef(job), child: null })
      replaceDraft(new TextDecoder('utf-8', { fatal: true }).decode(stored.bytes))
      setMessage('Failed input copied. Edit and apply the draft, review the changes below, then explicitly submit a new job.')
    } catch (error) { if (generation.current === own) invalidate(error) }
    finally { if (generation.current === own) setBusy(false) }
  }
  const projectDisabled = busy || projectBusy || editorDirty || scenarioState.busy || !current.transport
    || !sameScope(scenarioState.scope, projectScope(current.transport))
    || (!!projectRestore && scenarioState.restoreRevision !== projectRestore.revision)
  function selectJob(jobId: string, expected?: RcProjectJobRef): void {
    const known = [selectedRef.current, intent.current?.job, ...scenarioState.scenarios.map(row => row.job), changedReferences?.original, changedReferences?.child]
    selectedRef.current = expected ?? known.find(ref => ref?.jobId === jobId) ?? null
    setRequestedId(jobId); setOpenId(jobId); setRefreshEpoch(value => value + 1)
  }
  async function saveProject(): Promise<void> {
    if (projectDisabled || !current.transport) return
    const transport = current.transport, own = generation.current
    fileGeneration.current++
    setProjectBusy(true); setProjectMessage('')
    try {
      await transport.verifyAuthorizationScope()
      if (own !== generation.current) return
      const scope = projectScope(transport)
      if (!sameScope(scenarioState.scope, scope) || (intent.current && !sameScope(intentScope.current, scope))) throw new Error('job_authorization_scope_changed')
      const project: RcProjectFile = {
        schema: 'rc-workbench-project.v1', scope, draft,
        submission: intent.current ? { serialized: intent.current.text, idempotencyKey: intent.current.key, job: intent.current.job } : null,
        selectedJob: selectedRef.current,
        changedRun: changedReferences,
        scenarios: scenarioState.scenarios, baselineId: scenarioState.baselineId, variantId: scenarioState.variantId,
      }
      const payload = serializeRcProjectFile(project)
      await transport.verifyAuthorizationScope()
      if (own !== generation.current) return
      const url = URL.createObjectURL(new Blob([payload], { type: 'application/json' }))
      const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'rc-workbench-project.json'
      document.body.append(anchor); anchor.click(); anchor.remove()
      setTimeout(() => URL.revokeObjectURL(url), 0)
      setProjectMessage('Project saved. Open this file to restore the draft, design submissions and job links. Results are verified again when opened.')
    } catch (error) {
      if (own === generation.current) {
        setProjectMessage('The project could not be saved. Keep this workspace open and check its account and input size.')
        if (rcWorkflowAuthorizationFailure(error)) invalidate(error)
      }
    } finally { if (own === generation.current) setProjectBusy(false) }
  }
  async function openProject(file: File): Promise<void> {
    if (projectDisabled || !current.transport) return
    if (!file.size || file.size > RC_PROJECT_MAX_BYTES) { setProjectMessage('The project file is empty or exceeds the supported size. The current project is retained.'); return }
    const transport = current.transport, own = generation.current, ownFile = ++fileGeneration.current
    const active = () => own === generation.current && ownFile === fileGeneration.current
    setProjectBusy(true); setProjectMessage('')
    try {
      await transport.verifyAuthorizationScope()
      const text = new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(await file.arrayBuffer())
      if (!active()) return
      const project = parseRcProjectFile(text, projectScope(transport))
      let restoredChange: typeof changedRun = null
      let relationUnavailable = false
      // File-provided relations carry identifiers only. Read their requests
      // again before displaying an original/changed input comparison.
      if (project.changedRun) try {
        const original = await refreshRcJob(transport, project.changedRun.original.jobId)
        if (original.request.content_hash !== project.changedRun.original.requestHash) throw new Error('rc_project_job_binding_changed')
        const input = await loadRcJobRequest(transport, original)
        validateRcRequestProfile(input.value)
        restoredChange = { jobId: original.job_id, requestHash: original.request.content_hash, tenantId: transport.tenantId, input: input.value, originalStatus: original.status }
        if (project.changedRun.child) {
          const child = await refreshRcJob(transport, project.changedRun.child.jobId)
          if (child.request.content_hash !== project.changedRun.child.requestHash) throw new Error('rc_project_job_binding_changed')
          const submitted = await loadRcJobRequest(transport, child)
          validateRcRequestProfile(submitted.value)
          restoredChange = { ...restoredChange, childId: child.job_id, childRequestHash: child.request.content_hash, submitted: submitted.value }
        }
      } catch (error) {
        if (rcWorkflowAuthorizationFailure(error)) throw error
        restoredChange = null; relationUnavailable = true
      }
      await transport.verifyAuthorizationScope()
      if (!active()) return
      replaceDraft(project.draft)
      intent.current = project.submission ? { text: project.submission.serialized, bytes: new TextEncoder().encode(project.submission.serialized), key: project.submission.idempotencyKey, job: project.submission.job } : null
      intentScope.current = project.submission ? project.scope : null
      selectedRef.current = project.selectedJob
      setChangedRun(restoredChange); setChangedReferences(project.changedRun); setEditorDirty(false)
      setRequestedId(project.selectedJob?.jobId ?? ''); setOpenId(project.selectedJob?.jobId ?? '')
      setResumeRefreshRequired(null); resumeRefreshJob.current = null
      setProjectRestore(previous => ({ revision: (previous?.revision ?? 0) + 1, scope: project.scope,
        scenarios: project.scenarios, baselineId: project.baselineId, variantId: project.variantId }))
      setRefreshEpoch(value => value + 1)
      setProjectMessage('Project opened. No analysis was submitted. Refresh saved designs to verify their results, or explicitly run captured designs. Submission retries retain their original input and key.'
        + (relationUnavailable ? ' The original/changed job links were retained, but their inputs are unavailable for comparison.' : ''))
    } catch (error) {
      if (active()) {
        setProjectMessage('The project could not be opened: its format, account, service or referenced input could not be verified. The current project is retained.')
        if (rcWorkflowAuthorizationFailure(error)) invalidate(error)
      }
    } finally { if (own === generation.current) setProjectBusy(false) }
  }
  const activeChangedRun = changedRun?.tenantId === current.transport?.tenantId ? changedRun : null
  const requestDiff = activeChangedRun ? rcRequestChanges(activeChangedRun.input, activeChangedRun.submitted ?? draftValue) : null
  return <section className="wb2-panel" data-rc-workflow="project" aria-labelledby="wb2-rc-workflow-title">
    <h2 id="wb2-rc-workflow-title" className="wb2-panel__title">RC project workflow</h2>
    <p>Open one durable RC job or explicitly submit its complete typed input. Saved analysis and any supported report stay bound to that job.</p>
    <section data-rc-project-file aria-label="RC project file">
      <h3>Save and reopen your work</h3>
      <p>Save the applied input draft, captured designs and job links in a project file. Opening a file replaces this workspace's local project and checks its account and service. Saved results are read and verified again; opening never submits an analysis.</p>
      <button type="button" disabled={projectDisabled} onClick={() => void saveProject()}>Save RC project</button>{' '}
      <label>Open RC project file <input aria-label="Open RC project file" type="file" accept="application/json,.json" disabled={projectDisabled} onChange={event => {
        const file = event.target.files?.[0]; event.target.value = ''; if (file) void openProject(file)
      }} /></label>
      {editorDirty && <p>Apply or undo local model edits before saving or opening a project.</p>}
      {projectMessage && <p role="status" data-rc-project-file-message>{projectMessage}</p>}
      {changedReferences && !activeChangedRun && <div data-rc-project-unverified-relation>
        <p>Original/changed input comparison unavailable. Retained original job: <code>{changedReferences.original.jobId}</code>
          {changedReferences.child && <> · retained new job: <code>{changedReferences.child.jobId}</code></>}. Open the project file again to recheck these inputs.</p>
        <button type="button" disabled={busy || projectBusy} onClick={() => setChangedReferences(null)}>End unavailable changed-run comparison</button>
      </div>}
    </section>
    <div className="wb2-actions"><label>Saved RC job ID <input aria-label="Saved RC job ID" value={openId} onChange={e => setOpenId(e.target.value)} maxLength={36} /></label>
      <button type="button" className="wb2-btn" disabled={!JOB_ID.test(openId) || busy || projectBusy} onClick={() => selectJob(openId)}>Open saved RC job</button>
      <button type="button" className="wb2-btn" disabled={busy || projectBusy} onClick={() => { setChangedRun(null); setProjectRestore(undefined); setAuthEpoch(v => v + 1) }}>Refresh account and job</button></div>
    <details open={!!activeChangedRun && !activeChangedRun.childId}><summary>Submit a new RC input</summary>
      <RcModelEditor value={draftValue} disabled={busy || projectBusy} onDirtyChange={setEditorDirty} onChange={value => replaceDraft(JSON.stringify(value, null, 2))} />
      <label>Typed RC request JSON <textarea aria-label="Typed RC request JSON" disabled={busy || projectBusy} rows={8} value={draft} onChange={e => replaceDraft(e.target.value)} style={{ display: 'block', width: '100%' }} /></label>
      <label>Choose RC request JSON file <input aria-label="Choose RC request JSON file" disabled={busy || projectBusy} type="file" accept="application/json,.json" onChange={async e => {
        const file = e.target.files?.[0]; if (!file) return
        const ownFileGeneration = ++fileGeneration.current
        if (file.size > SUBMIT_MAX_BYTES) { setMessage('The RC input exceeds the supported request size.'); return }
        try {
          const bytes = await file.arrayBuffer()
          if (fileGeneration.current === ownFileGeneration) replaceDraft(new TextDecoder('utf-8', { fatal: true, ignoreBOM: true }).decode(bytes))
        } catch { if (fileGeneration.current === ownFileGeneration) setMessage('The selected RC input could not be read.') }
      }} /></label>
      {draftValue ? <InputSummary value={draftValue} saved={false} /> : draft ? <p role="status">A complete supported JSON object is required.</p> : null}
      {activeChangedRun && requestDiff ? <section data-rc-changed-run><h3>Changed-run comparison</h3>
        <p>Original job: <a href={rcProjectLink(activeChangedRun.jobId)}>{activeChangedRun.jobId}</a> · request <code>{activeChangedRun.requestHash}</code></p>
        <p>{activeChangedRun.childId ? <>New job: <a href={rcProjectLink(activeChangedRun.childId)}>{activeChangedRun.childId}</a>. Original status when read: {activeChangedRun.originalStatus ?? 'failed'}; current new job status: {current.load.job?.job_id === activeChangedRun.childId ? current.load.job.status : 'open the new job to verify'}.</> : <>Original status when read: {activeChangedRun.originalStatus ?? 'failed'}. Review each change before submitting a new job. This input comparison does not provide a verified numerical result delta.</>}</p>
        <div style={{ overflowX: 'auto' }}><table className="wb2-table"><caption>Original input → {activeChangedRun.childId ? 'submitted new input' : 'local draft'}</caption><thead><tr><th>Path</th><th>Before</th><th>After</th></tr></thead><tbody>{requestDiff.changes.map(row => <tr key={row.path}><td><code>{row.path}</code></td><td>{row.before}</td><td>{row.after}</td></tr>)}</tbody></table></div>
        {requestDiff.truncated ? <p>Change display limited to 200 rows. Review the complete JSON before submission.</p> : null}
        <button type="button" className="wb2-btn" disabled={busy || projectBusy} onClick={() => { setChangedRun(null); setChangedReferences(null) }}>End changed-run comparison</button>
      </section> : null}
      {editorDirty ? <p role="status">Apply or undo the local model edits before submitting or capturing a design.</p> : null}
      <button type="button" className="wb2-btn" data-rc-submit-intent={intentVersion} disabled={!current.transport || !draftValue || busy || projectBusy || editorDirty || (!!activeChangedRun && !activeChangedRun.childId && requestDiff?.changes.length === 0)} onClick={() => void submit()}>Submit RC analysis</button>
      <p className="wb2-muted">An uncertain submission retry retains the same input and submission key. Change the input to start a different submission.</p>
    </details>
    <RcScenarioComparisonPanel key={`${collectionUrl}:${authEpoch}`} collectionUrl={collectionUrl} authorize={authorize} draft={editorDirty ? null : draftValue} draftText={draft}
      disabled={projectBusy} projectRestore={projectRestore} onProjectChange={onProjectChange}
      onOpenJob={selectJob} />
    {message ? <p role="alert" data-rc-workflow-error>{message}</p> : null}
    {current.input ? <InputSummary value={current.input} saved /> : null}
    {current.load.job ? <p><a data-rc-project-link href={rcProjectLink(current.load.job.job_id)} target="_blank" rel="noopener">Reopen this RC project</a></p> : null}
    {resumeRefreshRequired && resumeRefreshRequired === openId ? <p data-rc-resume-unconfirmed>The resume outcome is unconfirmed. Open the saved job or refresh the account and job to check its current state before another resume.</p> : null}
    {current.load.job?.status === 'failed' ? <button type="button" className="wb2-btn" data-rc-explicit-retry disabled={!current.transport || busy || projectBusy || resumeRefreshRequired === current.load.job.job_id} onClick={() => void retry()}>
      {current.load.job.checkpoint ? 'Resume RC from saved checkpoint' : 'Retry RC from the beginning'}
    </button> : null}
    <JobServicePanel key={`${key}:${current.load.job?.job_id}:${current.load.job?.attempt}`} loadStatus={current.load.status} job={current.load.job} errors={current.load.errors} artifactStatus={current.load.artifactStatus}
      engineeringResultIr={current.load.engineeringResultIr} rcReview={current.load.rcReview} rcCorotationalReview={current.load.rcCorotationalReview}
      expectedCorotationalReportId={current.load.job?.job_id === initialJobId || current.load.job?.job_id === configuredJob(collectionUrl, initialJobStatusUrl) ? initialReportId : undefined} />
    {current.transport && current.load.job && current.input && terminal(current.load.job) ? <RcJobDiagnosticsPanel key={`${key}:${sourceKey(current.load.job)}`} transport={current.transport} job={current.load.job}
      onAuthorizationFailure={invalidate} onPrepareChangedRun={() => void prepareChangedRun()} /> : null}
    {current.transport && current.load.job && current.load.rcReview && current.load.artifactStatus === 'verified' ?
      <RcQuantityReportPanel key={`${current.transport.tenantId}:${sourceKey(current.load.job)}`} transport={current.transport} job={current.load.job}
        review={current.load.rcReview} initialReportId={current.load.job.job_id === initialJobId || current.load.job.job_id === configuredJob(collectionUrl, initialJobStatusUrl) ? initialReportId : undefined}
        onAuthorizationFailure={invalidate} /> : null}
  </section>
}
