import { useEffect, useRef, useState, type ReactElement } from 'react'
import { createJobWorkflowTransport, type JobAuthorizationProvider, type RcJobTransport } from '../model/jobTransport'
import { loadWorkbenchJob } from '../model/jobProvider'
import type { WorkbenchJobView } from '../model/jobSchema'
import {
  compareRcScenarios, exportRcScenarios, RC_SCENARIO_LIMIT, rcScenarioSafeMessage,
  rcScenarioAuthorizationFailure, rcScenarioRecordedWallSeconds, type RcScenarioIntent, type RcScenarioSummary,
} from '../model/rcScenarioComparison'
import { captureRcScenario, RcScenarioUnconfirmedError, runRcScenario } from '../model/rcScenarioRunner'
import { loadRcJobDiagnostics } from '../model/rcJobDiagnostics'
import { refreshRcJob } from '../model/rcWorkflowProvider'
import type { RcProjectScenario, RcProjectScope, RcProjectJobRef } from '../model/rcProjectFile'

type ScenarioStatus = 'captured' | 'submitting' | 'waiting' | 'succeeded' | 'failed' | 'cancelled' | 'unconfirmed' | 'unavailable'
interface Scenario {
  intent: RcScenarioIntent; status: ScenarioStatus; attempted: boolean
  jobRef: RcProjectScenario['job']; job?: WorkbenchJobView; summary?: RcScenarioSummary; message?: string
}
export interface RcScenarioProjectSnapshot {
  scenarios: RcProjectScenario[]; baselineId: string | null; variantId: string | null; busy: boolean; scope: RcProjectScope | null; restoreRevision: number | null
}
export interface RcScenarioComparisonPanelProps {
  collectionUrl: string
  authorize?: JobAuthorizationProvider
  draft: Record<string, unknown> | null
  draftText?: string
  disabled?: boolean
  onOpenJob?(jobId: string, reference?: RcProjectJobRef): void
  projectRestore?: { revision: number; scope: RcProjectScope; scenarios: RcProjectScenario[]; baselineId: string | null; variantId: string | null }
  onProjectChange?(state: RcScenarioProjectSnapshot): void
}
const COLORS = ['#3a83dc', '#df8f36', '#43a879', '#ba6dbc']
function number(value: number | null): string { return value === null ? 'Unknown' : value.toExponential(6) }
function Curve({ rows }: { rows: Scenario[] }): ReactElement | null {
  if (!rows.length) return null
  const points = rows.flatMap(row => row.summary!.curve)
  if (!points.length) return null
  const xs = points.map(row => row.displacementM), ys = points.map(row => row.loadFactor)
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys)
  // Scale before subtraction so finite extreme values cannot overflow the
  // SVG coordinates when the range spans both signs.
  const xScale = Math.max(Math.abs(x0), Math.abs(x1)) || 1, yScale = Math.max(Math.abs(y0), Math.abs(y1)) || 1
  const x = (value: number) => 54 + (value / xScale - x0 / xScale) / ((x1 / xScale - x0 / xScale) || 1) * 550
  const y = (value: number) => 211 - (value / yScale - y0 / yScale) / ((y1 / yScale - y0 / yScale) || 1) * 170
  return <figure>
    <svg viewBox="0 0 660 270" role="img" aria-label="Accepted control displacement versus load factor by scenario" style={{ width: '100%', maxWidth: 760 }}>
      <path d="M54 30 V211 H620" fill="none" stroke="currentColor" />
      <text x="54" y="235" fill="currentColor" fontSize="12">{number(x0)}</text><text x="510" y="235" fill="currentColor" fontSize="12">{number(x1)}</text>
      <text x="280" y="258" fill="currentColor" fontSize="12">Control displacement (m)</text><text x="55" y="20" fill="currentColor" fontSize="12">Load factor (1), {number(y0)} to {number(y1)}</text>
      {rows.map((row, index) => <polyline key={row.intent.id} data-scenario-curve={row.intent.id} fill="none" stroke={COLORS[index]} strokeWidth="2"
        points={row.summary!.curve.map(point => `${x(point.displacementM)},${y(point.loadFactor)}`).join(' ')} />)}
    </svg>
    <figcaption>{rows.map((row, index) => <span key={row.intent.id} style={{ color: COLORS[index], marginRight: 16 }}>{row.intent.name}</span>)}
      Recorded accepted states in original order; corotational subdivisions are retained. Lines are visual guides.</figcaption>
  </figure>
}

/** Separate from benchmark readiness comparison: these are explicitly submitted
 * designs and bounded quantities from their original verified review session.
 */
export function RcScenarioComparisonPanel({ collectionUrl, authorize, draft, draftText, disabled = false, onOpenJob, projectRestore, onProjectChange }: RcScenarioComparisonPanelProps): ReactElement {
  const [scenarios, setScenarios] = useState<Scenario[]>([])
  const current = useRef<Scenario[]>([])
  const [name, setName] = useState('Design 1')
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('Capture up to four designs, then explicitly run them in sequence.')
  const [baselineId, setBaselineId] = useState('')
  const [variantId, setVariantId] = useState('')
  const [sessionScope, setSessionScope] = useState<RcProjectScope | null>(null)
  const previousScope = useRef<RcProjectScope | null>(null)
  const selections = useRef({ baselineId, variantId }); selections.current = { baselineId, variantId }
  const projectCallback = useRef(onProjectChange), appliedRestore = useRef<number | null>(null)
  const preserveRestoredSelection = useRef(false)
  projectCallback.current = onProjectChange
  const transport = useRef<RcJobTransport | null>(null)
  const scope = useRef<AbortController | null>(null)
  const generation = useRef(0), running = useRef(false)
  const update = (next: Scenario[]) => { current.current = next; setScenarios(next) }
  const patch = (id: string, partial: Partial<Scenario>) => update(current.current.map(row => row.intent.id === id ? { ...row, ...partial } : row))

  useEffect(() => {
    const retained = { rows: current.current, selections: selections.current, scope: previousScope.current, revision: appliedRestore.current }
    const epoch = ++generation.current, controller = new AbortController()
    scope.current = controller; transport.current = null; running.current = false
    preserveRestoredSelection.current = false
    appliedRestore.current = null
    setBusy(false); update([]); setBaselineId(''); setVariantId(''); setSessionScope(null)
    const active = () => epoch === generation.current && !controller.signal.aborted
    let verifying = false
    function invalidate(): void {
      if (!active()) return
      controller.abort(); transport.current = null; generation.current++; running.current = false
      update([]); setBaselineId(''); setVariantId(''); setBusy(false); setSessionScope(null)
      setMessage('Authorization changed or became unavailable. Reopen this workspace to start a new session.')
    }
    void createJobWorkflowTransport(collectionUrl, controller.signal, authorize).then(value => {
      if (active()) {
        const nextScope = { collectionUrl: value.collectionUrl, tenantId: value.tenantId ?? null }
        transport.current = value; previousScope.current = nextScope; setSessionScope(nextScope)
        if (retained.scope?.collectionUrl === nextScope.collectionUrl && retained.scope.tenantId === nextScope.tenantId) {
          // A replacement sign-in callback is not a new authoring project.
          // Retain custody within the same scope, but re-read every result.
          appliedRestore.current = retained.revision; preserveRestoredSelection.current = true
          update(retained.rows.map(row => ({ intent: row.intent, attempted: row.attempted, jobRef: row.jobRef,
            status: row.jobRef ? 'unavailable' : row.attempted ? 'unconfirmed' : 'captured' })))
          setBaselineId(retained.selections.baselineId); setVariantId(retained.selections.variantId)
          setMessage('Authorization refreshed. Designs are retained; refresh saved jobs to verify their results again.')
        } else setMessage('Capture up to four designs, then explicitly run them in sequence.')
      }
    }).catch(() => { if (active()) setMessage('Scenario service is unavailable for this session.') })
    // Revoke visible retained summaries as well as future network access when
    // the host changes tenants while the queue is idle.
    const timer = setInterval(() => {
      if (!active() || !transport.current || verifying) return
      verifying = true
      void transport.current.verifyAuthorizationScope().catch(invalidate).finally(() => { verifying = false })
    }, 2000)
    return () => { controller.abort(); clearInterval(timer); if (epoch === generation.current) generation.current++; transport.current = null }
  }, [collectionUrl, authorize])

  useEffect(() => {
    projectCallback.current?.({
      scenarios: scenarios.map(row => ({ intent: row.intent, attempted: row.attempted, job: row.jobRef })),
      baselineId: baselineId || null, variantId: variantId || null, busy, scope: sessionScope, restoreRevision: appliedRestore.current,
    })
  }, [scenarios, baselineId, variantId, busy, sessionScope])

  useEffect(() => {
    const session = transport.current, controller = scope.current, epoch = generation.current
    if (!projectRestore || appliedRestore.current === projectRestore.revision || !session || !controller || !sessionScope || running.current) return
    if (projectRestore.scope.collectionUrl !== session.collectionUrl || projectRestore.scope.tenantId !== (session.tenantId ?? null)) {
      setMessage('The project belongs to a different service or tenant. Its scenarios were not restored.')
      return
    }
    let cancelled = false
    running.current = true; setBusy(true)
    const active = () => !cancelled && epoch === generation.current && !controller.signal.aborted
    // The parent admits the project only in its original endpoint/tenant scope.
    // Recheck that same live scope immediately before restoring local intents.
    void session.verifyAuthorizationScope().then(() => {
      if (!active()) return
      appliedRestore.current = projectRestore.revision
      preserveRestoredSelection.current = true
      update(projectRestore.scenarios.map(row => ({
        intent: row.intent, attempted: row.attempted, jobRef: row.job,
        status: row.job ? 'unavailable' : row.attempted ? 'unconfirmed' : 'captured',
        message: row.job ? 'Restored job reference. Refresh to verify the current stored request and result.'
          : row.attempted ? 'The prior submission outcome is unconfirmed. Any explicit retry retains its original bytes and key.' : undefined,
      })))
      setBaselineId(projectRestore.baselineId ?? ''); setVariantId(projectRestore.variantId ?? '')
      setMessage('Project scenarios restored. No job was submitted or read; refresh known jobs explicitly to verify their results.')
    }).catch(error => {
      if (!active()) return
      if (rcScenarioAuthorizationFailure(error)) {
        controller.abort(); generation.current++; transport.current = null; running.current = false
        update([]); setBaselineId(''); setVariantId(''); setBusy(false); setSessionScope(null)
      }
      setMessage(rcScenarioSafeMessage(error))
    }).finally(() => { if (active()) { running.current = false; setBusy(false) } })
    return () => { cancelled = true; if (epoch === generation.current) { running.current = false; setBusy(false) } }
  }, [projectRestore, sessionScope])

  function capture(): void {
    if (!draft || busy || disabled || current.current.length >= RC_SCENARIO_LIMIT) return
    try {
      const intent = captureRcScenario(draft, name, undefined, draftText)
      update([...current.current, { intent, status: 'captured', attempted: false, jobRef: null }]); setName(`Design ${current.current.length + 1}`)
      setMessage('The design is captured as immutable request bytes. Running it requires the Run captured designs button.')
    } catch { setMessage('The design name or RC request is invalid. Correct the draft before capturing it.') }
  }

  async function execute(ids: string[]): Promise<void> {
    if (disabled || running.current || !transport.current || !scope.current || scope.current.signal.aborted) return
    running.current = true; setBusy(true)
    const epoch = generation.current, session = transport.current, signal = scope.current.signal
    const active = () => epoch === generation.current && !signal.aborted
    try {
      for (const id of ids) {
        if (!active()) return
        const row = current.current.find(item => item.intent.id === id)
        if (!row || row.status === 'succeeded' || row.status === 'failed' || row.status === 'cancelled') continue
        patch(id, { status: row.jobRef ? 'waiting' : 'submitting', attempted: true, summary: undefined, message: undefined })
        let submittedJob = row.job
        try {
          // A restored reference is authoritative for submission custody even
          // if its fresh GET fails. Never turn that failure into a POST.
          if (row.jobRef) {
            const fresh = await refreshRcJob(session, row.jobRef.jobId)
            if (fresh.request.content_hash !== row.jobRef.requestHash) throw new Error('rc_scenario_request_binding_changed')
            submittedJob = fresh
          }
          const job = await runRcScenario(session, row.intent, {
            signal, existingJob: submittedJob,
            onJob: next => {
              submittedJob = next
              if (active()) patch(id, { job: next, jobRef: { jobId: next.job_id, requestHash: next.request.content_hash }, status: 'waiting' })
            },
          })
          if (!active()) return
          if (job.status === 'failed' || job.status === 'cancelled') {
            patch(id, { job, status: job.status, message: 'No succeeded numerical result is available. This job is not automatically retried.' }); continue
          }
          if (job.status !== 'succeeded') {
            patch(id, { job, status: 'waiting', message: 'The bounded polling interval ended. Refresh this stored job to continue monitoring.' })
            setMessage('The queue paused while a known job remains active. Refresh its stored state before continuing.'); break
          }
          const sourceTransport = session.readTransport(job.job_id, signal)
          let authorizationDenied: number | null = null
          const observe = async (pending: Promise<Response>): Promise<Response> => {
            const response = await pending
            if (response.status === 401 || response.status === 403) authorizationDenied = response.status
            return response
          }
          // loadWorkbenchJob sanitizes artifact-read failures. Retain only the
          // HTTP authorization status so revocation also clears prior summaries;
          // no response body or tenant credential is retained here.
          const observedTransport = {
            ...sourceTransport, withSignal: undefined,
            get: (role?: string, accept?: string) => observe(sourceTransport.get(role, accept)),
            getCorotationalReport: sourceTransport.getCorotationalReport
              ? (binding: Parameters<NonNullable<typeof sourceTransport.getCorotationalReport>>[0]) => observe(sourceTransport.getCorotationalReport!(binding)) : undefined,
          }
          const loaded = await loadWorkbenchJob(`${session.collectionUrl}/${job.job_id}`, signal, authorize, observedTransport)
          const review = loaded.rcReview ?? loaded.rcCorotationalReview
          try {
            await session.verifyAuthorizationScope(); signal.throwIfAborted()
            if (!active()) return
            if (authorizationDenied !== null) throw new Error(`job_api_http_${authorizationDenied}`)
            if (!loaded.job || loaded.job.job_id !== job.job_id || loaded.job.request.content_hash !== job.request.content_hash
              || loaded.job.result?.content_hash !== job.result?.content_hash || loaded.job.evidence?.content_hash !== job.evidence?.content_hash
              || loaded.job.checkpoint?.content_hash !== job.checkpoint?.content_hash || loaded.job.revision !== job.revision
              || loaded.job.terminal_event_hash !== job.terminal_event_hash
              || !['verified', 'report_verified'].includes(loaded.artifactStatus ?? '') || !review?.comparisonSummary) throw new Error('rc_scenario_review_unavailable')
            const summary = await review.comparisonSummary()
            if (loaded.rcReview && session.getRcInvocations) {
              try { summary.recordedPhaseWallSeconds = rcScenarioRecordedWallSeconds(summary, await loadRcJobDiagnostics(session, job)) }
              catch (error) { if (rcScenarioAuthorizationFailure(error)) throw error }
            }
            await session.verifyAuthorizationScope(); signal.throwIfAborted()
            if (!active()) return
            if (summary.bindings.jobId !== job.job_id || summary.bindings.requestHash !== job.request.content_hash
              || summary.bindings.resultHash !== job.result?.content_hash || summary.bindings.evidenceHash !== job.evidence?.content_hash
              || summary.bindings.checkpointHash !== (job.checkpoint?.content_hash ?? null) || summary.bindings.revision !== job.revision
              || summary.bindings.terminalEventHash !== job.terminal_event_hash) throw new Error('rc_scenario_review_binding_invalid')
            patch(id, { job, summary, status: 'succeeded' })
            setBaselineId(previous => previous || id)
            setVariantId(previous => preserveRestoredSelection.current ? previous || id : id)
          } finally { review?.dispose() }
        } catch (error) {
          if (!active()) return
          const safe = rcScenarioSafeMessage(error)
          if (rcScenarioAuthorizationFailure(error)) {
            scope.current?.abort(); generation.current++; transport.current = null; running.current = false; setBusy(false)
            update([]); setBaselineId(''); setVariantId(''); setSessionScope(null); setMessage(safe); break
          }
          const unconfirmed = error instanceof RcScenarioUnconfirmedError
          patch(id, { status: unconfirmed ? 'unconfirmed' : 'unavailable', job: submittedJob, message: safe })
          setMessage(safe)
          // A failed artifact read can follow an already-created job. Never
          // advance the queue or create a new submission after this ambiguity.
          break
        }
      }
    } finally {
      // A completed/aborted old generation cannot unlock a newer session's
      // active queue while its host authorization callback is still pending.
      if (epoch === generation.current) { running.current = false; setBusy(false) }
    }
  }

  async function download(): Promise<void> {
    const session = transport.current, epoch = generation.current
    if (!session || busy || disabled) return
    try {
      await session.verifyAuthorizationScope()
      if (epoch !== generation.current || scope.current?.signal.aborted) return
      const payload = exportRcScenarios(current.current.map(row => ({ name: row.intent.name, status: row.status, jobId: row.jobRef?.jobId, summary: row.summary })), current.current.find(row => row.intent.id === baselineId)?.jobRef?.jobId ?? null)
      await session.verifyAuthorizationScope()
      if (epoch !== generation.current || scope.current?.signal.aborted) return
      const url = URL.createObjectURL(new Blob([payload], { type: 'application/json' }))
      const anchor = document.createElement('a'); anchor.href = url; anchor.download = 'rc-scenario-comparison.json'; anchor.click()
      setTimeout(() => URL.revokeObjectURL(url), 0)
    } catch (error) {
      if (epoch === generation.current) {
        if (rcScenarioAuthorizationFailure(error)) { scope.current?.abort(); generation.current++; transport.current = null; update([]); setBaselineId(''); setVariantId(''); setSessionScope(null) }
        setMessage(rcScenarioSafeMessage(error))
      }
    }
  }

  const succeeded = scenarios.filter(row => row.status === 'succeeded' && row.summary)
  const baseline = succeeded.find(row => row.intent.id === baselineId), variant = succeeded.find(row => row.intent.id === variantId)
  let comparison = null, comparisonUnavailable = false
  try { comparison = baseline?.summary && variant?.summary ? compareRcScenarios(baseline.summary, variant.summary) : null }
  catch { comparisonUnavailable = true }
  const unresolved = scenarios.some(row => row.status === 'unconfirmed' || (!!row.jobRef && ['waiting', 'unavailable'].includes(row.status)))
  const pending = scenarios.filter(row => row.status === 'captured').map(row => row.intent.id)
  return <section className="wb2-panel" data-rc-scenario-comparison>
    <h3>Design scenarios</h3>
    <p>Capture the current validated RC draft after each edit. Up to four independent durable jobs run sequentially after an explicit action. Failed or unavailable results remain visible.</p>
    <label>Scenario name <input value={name} maxLength={80} disabled={busy || disabled} onChange={event => setName(event.target.value)} /></label>{' '}
    <button type="button" disabled={!draft || busy || disabled || scenarios.length >= RC_SCENARIO_LIMIT} onClick={capture}>Capture current design</button>{' '}
    <button type="button" disabled={busy || disabled || !transport.current || !pending.length || unresolved} onClick={() => void execute(pending)}>Run captured designs</button>{' '}
    <button type="button" disabled={busy || disabled || !scenarios.length || !transport.current} onClick={() => void download()}>Export scenario JSON</button>
    <p role="status">{message}</p>
    <ul>{scenarios.map(row => <li key={row.intent.id} data-scenario-id={row.intent.id}>
      <strong>{row.intent.name}</strong> — <span>{row.status}</span>{row.jobRef && <> · <code>{row.jobRef.jobId}</code>{onOpenJob && <> <button type="button" disabled={busy || disabled} onClick={() => onOpenJob(row.jobRef!.jobId, row.jobRef!)}>Open job</button></>}</>}
      {row.message && <p>{row.message}</p>}
      {row.status === 'captured' && <button type="button" disabled={busy || disabled} onClick={() => {
        update(current.current.filter(item => item.intent.id !== row.intent.id))
        if (baselineId === row.intent.id) setBaselineId('')
        if (variantId === row.intent.id) setVariantId('')
      }}>Remove {row.intent.name}</button>}
      {['unconfirmed', 'waiting', 'unavailable'].includes(row.status) && <button type="button" disabled={busy || disabled} onClick={() => void execute([row.intent.id])}>{row.jobRef ? `Refresh ${row.intent.name}` : `Retry same submission for ${row.intent.name}`}</button>}
      {row.summary && <details><summary>Original bindings and recorded work</summary>
        <dl><dt>Source revision (caller declaration)</dt><dd><code>{row.summary.sourceRevision}</code></dd>
          <dt>Review</dt><dd>{row.summary.reviewKind}</dd><dt>Request</dt><dd><code>{row.summary.bindings.requestHash}</code></dd><dt>Result</dt><dd><code>{row.summary.bindings.resultHash}</code></dd><dt>Evidence</dt><dd><code>{row.summary.bindings.evidenceHash}</code></dd>
          <dt>Recorded analysis and verification phase wall time (s)</dt><dd>{number(row.summary.recordedPhaseWallSeconds)}</dd><dt>Unaccounted work</dt><dd>{row.summary.unknownWork ? 'Unknown work remains' : 'No pending recorded reservation'}</dd>
          <dt>Member forces</dt><dd>{row.summary.memberForcesAvailable ? 'Available from original result review' : 'Unavailable in the saved nodal report'}</dd><dt>Financial cost</dt><dd>Unknown; no price or cost is inferred.</dd></dl>
      </details>}
    </li>)}</ul>
    {succeeded.length > 0 && <>
      <label>Baseline design <select value={baselineId} disabled={busy || disabled} onChange={event => setBaselineId(event.target.value)}>
        {baselineId && !baseline && <option value={baselineId} disabled>Stored baseline awaiting verification</option>}
        {succeeded.map(row => <option key={row.intent.id} value={row.intent.id}>{row.intent.name}</option>)}
      </select></label>{' '}
      <label>Compared design <select value={variantId} disabled={busy || disabled} onChange={event => setVariantId(event.target.value)}>
        {variantId && !variant && <option value={variantId} disabled>Stored compared design awaiting verification</option>}
        {succeeded.map(row => <option key={row.intent.id} value={row.intent.id}>{row.intent.name}</option>)}
      </select></label>
      {comparisonUnavailable && <p>The comparison is unavailable because the bounded numerical difference cannot be represented.</p>}
      <Curve rows={comparison?.compatible ? [baseline!, ...(baselineId === variantId ? [] : [variant!])] : baseline ? [baseline] : []} />
      {comparison && <><p>{comparison.compatible ? `Final target occurrence ${baseline!.summary!.targetIndex + 1}, ${number(baseline!.summary!.targetM)} m. ${comparison.reason}` : `Incompatible designs: ${comparison.reason}`}</p>
        {comparison.compatible && <p>Recorded analysis and verification phase wall time (s): baseline {number(comparison.recordedPhaseWallTimeSeconds!.baseline)}, compared {number(comparison.recordedPhaseWallTimeSeconds!.variant)}, delta {number(comparison.recordedPhaseWallTimeSeconds!.delta)}. Financial cost: Unknown.</p>}
        {comparison.compatible && <div className="wb2-table-wrap"><table><caption>Matched final target quantities; member end forces use local axes; delta = compared design − baseline</caption><thead><tr><th>Quantity</th><th>Entity</th><th>Component</th><th>Unit</th><th>Baseline</th><th>Compared</th><th>Delta</th></tr></thead><tbody>{comparison.rows.map(row => <tr key={row.key}><td>{row.kind}</td><td>{row.entity}</td><td>{row.component}</td><td>{row.unit}</td><td>{number(row.baseline)}</td><td>{number(row.variant)}</td><td>{number(row.delta)}</td></tr>)}</tbody></table></div>}</>}
    </>}
    <p>These are derived differences between experimental software runs. Source declarations and hashes do not establish independent physical validation, benchmark accuracy, design authority or release readiness.</p>
  </section>
}
