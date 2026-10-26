import { useEffect, useRef, useState, type ReactElement } from 'react'
import type { RcJobTransport } from '../model/jobTransport'
import type { WorkbenchJobView } from '../model/jobSchema'
import { rcScenarioAuthorizationFailure } from '../model/rcScenarioComparison'
import {
  createRcControlIntent, loadRcJobControl, postRcJobControl, RcControlConflictError,
  type RcControlAction, type RcJobControlCustody, type RcJobControlCustodyEntry,
  type RcJobControlIntent, type RcJobControlView,
} from '../model/rcJobControl'

export interface RcJobControlPanelProps {
  transport: RcJobTransport; job: WorkbenchJobView; custody: RcJobControlCustody; disabled?: boolean
  onAuthorizationFailure(error: unknown): void; onRefreshJob(): void
}
const empty = (): RcJobControlCustodyEntry => ({ intent: null, receipt: null, refreshRequired: false })
/** Controls only this durable job; stopping an HTTP read never stops analysis. */
export function RcJobControlPanel({ transport, job, custody, disabled = false, onAuthorizationFailure, onRefreshJob }: RcJobControlPanelProps): ReactElement {
  const custodyKey = JSON.stringify([transport.collectionUrl, transport.tenantId, job.job_id, job.request.content_hash])
  const [view, setView] = useState<RcJobControlView | null>(null)
  const [supported, setSupported] = useState<boolean | null>(null)
  const [busy, setBusy] = useState(false), [message, setMessage] = useState('')
  const [entry, setEntry] = useState(() => custody.current.get(custodyKey) ?? empty())
  const generation = useRef(0), activeOperation = useRef(false), latestJob = useRef(job)
  latestJob.current = job
  const callbacks = useRef({ onAuthorizationFailure, onRefreshJob }); callbacks.current = { onAuthorizationFailure, onRefreshJob }
  const refresh = useRef<(explicit?: boolean) => Promise<void>>(async () => {})
  function remember(next: RcJobControlCustodyEntry): void { custody.current.set(custodyKey, next); setEntry(next) }
  useEffect(() => {
    const own = ++generation.current
    const active = () => generation.current === own
    activeOperation.current = false; setBusy(false); setView(null); setSupported(null); setMessage('')
    setEntry(custody.current.get(custodyKey) ?? empty())
    async function read(explicit = false): Promise<void> {
      if (!active() || activeOperation.current) return
      activeOperation.current = true; setBusy(true)
      try {
        const next = await loadRcJobControl(transport, latestJob.current)
        if (!active()) return
        setSupported(next !== null); setView(next)
        if (!next) { setMessage('Job controls are unavailable on this service. No control request was sent.'); return }
        let retained = custody.current.get(custodyKey) ?? empty()
        const intent = retained.intent, acknowledged = intent && next.last_command?.control_id === intent.command.control_id
          && next.last_command.command_hash === intent.commandHash && next.last_command.action === intent.command.action
          && next.last_command.control_revision === intent.command.expected_control_revision + 1
        if (acknowledged) retained = { intent: null, refreshRequired: false, receipt: {
          schema_version: 'rc-job-control-command-result.v1', control_id: intent.command.control_id,
          command_hash: intent.commandHash, accepted_control_revision: next.last_command!.control_revision, view: next,
        } }
        else if (retained.refreshRequired) retained = { ...retained, refreshRequired: false }
        custody.current.set(custodyKey, retained); setEntry(retained)
        setMessage(acknowledged ? 'The stored command is confirmed by the current control state.' : '')
        if (explicit) callbacks.current.onRefreshJob()
      } catch (error) {
        if (!active()) return
        setView(null)
        if (rcScenarioAuthorizationFailure(error)) { callbacks.current.onAuthorizationFailure(error); return }
        setMessage('Job control state could not be verified. Refresh before making a new request.')
      } finally { if (active()) { activeOperation.current = false; setBusy(false) } }
    }
    refresh.current = read
    void read()
    const timer = setInterval(() => { void read() }, 2000)
    return () => { generation.current++; clearInterval(timer) }
  }, [transport, custodyKey, custody])

  async function send(action?: RcControlAction): Promise<void> {
    if (disabled || activeOperation.current || supported === false) return
    const own = generation.current, active = () => generation.current === own
    activeOperation.current = true; setBusy(true); setMessage('')
    let intent: RcJobControlIntent | null = (custody.current.get(custodyKey) ?? empty()).intent
    try {
      if (action) {
        if (intent || !view || entry.refreshRequired) return
        intent = await createRcControlIntent(view, action)
        await transport.verifyAuthorizationScope()
        if (!active()) return
        // Store before sending: remounts and unknown responses retain one ID/body.
        remember({ ...(custody.current.get(custodyKey) ?? empty()), intent })
      }
      if (!intent) return
      const receipt = await postRcJobControl(transport, latestJob.current, intent)
      if (!active()) return
      remember({ intent: null, receipt, refreshRequired: false }); setView(receipt.view); setSupported(true)
      setMessage('The control command was accepted. Its receipt and the current job state are shown separately.')
      callbacks.current.onRefreshJob()
    } catch (error) {
      if (!active()) return
      if (rcScenarioAuthorizationFailure(error)) { callbacks.current.onAuthorizationFailure(error); return }
      if (error instanceof RcControlConflictError) {
        remember({ ...(custody.current.get(custodyKey) ?? empty()), intent: null, refreshRequired: true })
        setView(null); setMessage('The observed job state changed or the command was rejected. Refresh, then make a new explicit choice.')
      } else setMessage(intent ? 'The control outcome is unconfirmed. Read the stored state or explicitly retry this same control request.' : 'This control request could not be prepared. Refresh the job state.')
    } finally { if (active()) { activeOperation.current = false; setBusy(false) } }
  }
  const locked = disabled || busy || !view || !!entry.intent || entry.refreshRequired
  return <section data-rc-job-control aria-label="Durable RC job controls">
    <h3>Control this job</h3>
    <p>These controls affect only <code>{job.job_id}</code>. Pause or cancel takes effect at a durable boundary after any current analysis and required verification. It does not immediately stop a numerical iteration.</p>
    {view && <p data-rc-job-control-state={view.state}>Current control state: <strong>{view.state.replace(/_/g, ' ')}</strong>. Stored job status: {view.job.status}.</p>}
    {view?.state === 'pause_pending' && <p>Pause requested; the current chunk may still be running. If it completes the full path, the job can finish without a paused checkpoint.</p>}
    {view?.state === 'cancel_pending' && <p>Cancellation requested; the current chunk and required verification may still finish. The last verified checkpoint is retained when available.</p>}
    {view?.state === 'paused' && <p>Pause applied. This job will not be claimed again until you explicitly resume it.</p>}
    {view?.state === 'terminal' && <p>This job has ended. A cancelled job cannot be resumed.</p>}
    {view?.last_command && <p data-rc-control-latest-command>Latest command: {view.last_command.action} · {view.last_command.disposition} · <code>{view.last_command.control_id}</code>
      {view.last_command.boundary && <> · boundary {view.last_command.boundary}</>}
      {view.last_command.applied_progress && <> · saved progress {view.last_command.applied_progress.completed}/{view.last_command.applied_progress.total}</>}
      {view.last_command.applied_checkpoint_hash && <> · checkpoint <code>{view.last_command.applied_checkpoint_hash}</code></>}</p>}
    <button type="button" disabled={locked || !view?.can_pause} onClick={() => void send('pause')}>Pause job</button>{' '}
    <button type="button" disabled={locked || !view?.can_cancel} onClick={() => void send('cancel')}>Cancel job</button>{' '}
    <button type="button" disabled={locked || !view?.can_resume_control} onClick={() => void send('resume')}>Resume paused job</button>{' '}
    <button type="button" disabled={disabled || busy} onClick={() => void refresh.current(true)}>Refresh job control</button>
    {entry.intent && <div data-rc-control-unconfirmed><p>Unconfirmed {entry.intent.command.action} command: <code>{entry.intent.command.control_id}</code>. A new command is blocked until this outcome is resolved.</p>
      <button type="button" disabled={disabled || busy || supported === false} onClick={() => void send()}>Retry same control request</button></div>}
    {entry.receipt && <p data-rc-control-receipt>Confirmed command receipt: <code>{entry.receipt.control_id}</code> · accepted control revision {entry.receipt.accepted_control_revision}. This may differ from the latest command above.</p>}
    {message && <p role="status" data-rc-control-message>{message}</p>}
  </section>
}
