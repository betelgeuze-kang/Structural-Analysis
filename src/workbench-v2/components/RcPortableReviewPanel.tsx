import { useEffect, useRef, useState, type ReactElement } from 'react'
import { openRcPortableReview, RC_PORTABLE_REVIEW_MAX_BYTES, type RcPortableReview } from '../model/rcPortableReview'
import type { RcCorotationalStateChoice } from '../model/rcCorotationalReportReview'
import type { RcCorotationalReportResponse } from '../model/rcCorotationalReportSchema'
import type { RcResultGeometry } from '../model/rcResultVisualization'
import { NodalTable, RcCorotationalControlDescription } from './RcCorotationalReportPanel'
import { RcDeformedShape, RcHistoryPlot } from './RcResultVisualization'
import '../workbenchV2.css'

const PAGE_SIZE = 20

/** This workspace receives files only. It never mounts a service-backed panel. */
export function RcPortableReviewPanel(): ReactElement {
  const [review, setReview] = useState<RcPortableReview | null>(null)
  const [epoch, setEpoch] = useState(0)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const generation = useRef(0), current = useRef<RcPortableReview | null>(null)
  const opening = useRef<AbortController | null>(null)
  const workbenchUrl = new URL(window.location.href)
  workbenchUrl.pathname = workbenchUrl.pathname.replace(/\/rc-review\/*$/, '/')
  workbenchUrl.hash = '/workbench-v2'
  useEffect(() => () => {
    generation.current++; opening.current?.abort(); current.current?.dispose(); current.current = null
  }, [])

  async function open(file?: File): Promise<void> {
    if (!file) return
    const own = ++generation.current
    opening.current?.abort()
    const controller = new AbortController(); opening.current = controller
    setMessage('')
    if (!file.size || file.size > RC_PORTABLE_REVIEW_MAX_BYTES) {
      setBusy(false)
      setMessage('Choose a non-empty portable RC review file of at most 112 MiB. Any previously opened review is retained.')
      return
    }
    setBusy(true)
    try {
      const bytes = new Uint8Array(await file.arrayBuffer())
      controller.signal.throwIfAborted()
      const candidate = await openRcPortableReview(bytes, controller.signal)
      if (own !== generation.current) { candidate.dispose(); return }
      const previous = current.current
      current.current = candidate; setReview(candidate); setEpoch(own)
      previous?.dispose()
      setMessage('Opened saved input and nodal results. No analysis was run.')
    } catch {
      if (own === generation.current) setMessage('This file could not be verified. Any previously opened review is retained.')
    } finally {
      if (own === generation.current) { setBusy(false); opening.current = null }
    }
  }

  return <main className="wb2-portable-workspace" data-rc-portable-workspace>
    <nav aria-label="RC workspace"><a href={workbenchUrl.href}>Return to Workbench</a></nav>
    <h1>Open a saved RC result</h1>
    <p>Read a portable RC review file on this computer without connecting to the original job service.</p>
    <p>Opening a file only reads stored input and results. To run a new analysis, return to the Workbench and submit it explicitly.</p>
    <label className="wb2-portable-file">Open portable RC review file{' '}
      <input type="file" aria-label="Open portable RC review file" accept="application/json,.json" disabled={busy}
        onChange={event => { void open(event.target.files?.[0]); event.target.value = '' }} />
    </label>
    {busy ? <p role="status">Checking the selected file…</p> : null}
    {message ? <p role="status" data-rc-portable-file-status>{message}</p> : null}
    {review ? <PortableNodalResults key={epoch} review={review} />
      : <p className="wb2-note">In a saved corotational nodal report, choose “Export portable RC review” to create a file for this workspace.</p>}
  </main>
}

function PortableNodalResults({ review }: { review: RcPortableReview }): ReactElement {
  const { summary } = review
  const [index, setIndex] = useState(summary.stateCount - 1)
  const [page, setPage] = useState(Math.floor((summary.stateCount - 1) / PAGE_SIZE))
  const [choices, setChoices] = useState<RcCorotationalStateChoice[] | null>(null)
  const [state, setState] = useState<RcCorotationalReportResponse | null>(null)
  const [geometry, setGeometry] = useState<RcResultGeometry | null>(null)
  const [memberId, setMemberId] = useState(''), [scale, setScale] = useState('1')
  const [failure, setFailure] = useState(''), [fileMessage, setFileMessage] = useState('')
  const [downloading, setDownloading] = useState(false)
  const [geometryUnavailable, setGeometryUnavailable] = useState(false)
  const generation = useRef(0), urls = useRef(new Set<string>())
  useEffect(() => () => {
    generation.current++
    for (const url of urls.current) URL.revokeObjectURL(url)
    urls.current.clear()
  }, [])
  useEffect(() => review.onFailure(() => setFailure('This saved review is no longer available. Open the file again.')), [review])
  useEffect(() => {
    let active = true
    review.geometry().then(value => {
      if (active) { setGeometry(value); setMemberId(value.members[0]?.id ?? '') }
    }).catch(() => { if (active) setGeometryUnavailable(true) })
    return () => { active = false }
  }, [review])
  useEffect(() => {
    let active = true; setChoices(null)
    review.statePage(page * PAGE_SIZE, PAGE_SIZE).then(value => { if (active) setChoices(value) })
      .catch(() => { if (active) setFailure('The saved state list could not be read.') })
    return () => { active = false }
  }, [review, page])
  useEffect(() => {
    let active = true; setState(null)
    review.state(index).then(value => { if (active) setState(value) })
      .catch(() => { if (active) setFailure('The selected nodal state could not be read.') })
    return () => { active = false }
  }, [review, index])

  function selectState(next: number): void {
    if (!Number.isSafeInteger(next) || next < 0 || next >= summary.stateCount || next === index) return
    setState(null); setIndex(next)
    const nextPage = Math.floor(next / PAGE_SIZE)
    if (nextPage !== page) { setChoices(null); setPage(nextPage) }
  }
  async function download(kind: 'request' | 'report'): Promise<void> {
    if (downloading) return
    const own = generation.current
    setDownloading(true); setFileMessage('')
    try {
      const blob = await (kind === 'request' ? review.requestDownload() : review.reportDownload())
      if (own !== generation.current) return
      const url = URL.createObjectURL(blob), anchor = document.createElement('a')
      urls.current.add(url); anchor.href = url
      anchor.download = kind === 'request' ? `${summary.jobId}-original-rc-input.json` : `${summary.reportId}-corotational-nodal-report.json`
      document.body.append(anchor); anchor.click(); anchor.remove()
      window.setTimeout(() => { URL.revokeObjectURL(url); urls.current.delete(url) }, 0)
    } catch { if (own === generation.current) setFileMessage('The stored file could not be downloaded.') }
    finally { if (own === generation.current) setDownloading(false) }
  }
  const member = geometry?.members.find(row => row.id === memberId)
  const selectedNodes = member ? [member.nodeI, member.nodeJ] : []
  if (failure) return <section role="alert" data-rc-portable-review="unavailable"><h2>Saved review unavailable</h2><p>{failure}</p></section>
  return <section className="wb2-rc-job" data-rc-portable-review="verified" aria-label="Portable RC nodal results">
    <h2>Saved RC nodal results</h2>
    <p data-rc-portable-custody>File integrity checked. Origin is not authenticated.</p>
    <p className="wb2-note">The input, job record and report agree within this file. They have not been authenticated against the original service. These checks do not establish independent physical validation or design approval.</p>
    <dl className="wb2-kv">
      <dt>Case</dt><dd>{summary.caseId}</dd>
      <dt>Recorded control</dt><dd><RcCorotationalControlDescription control={summary.control} /></dd>
      <dt>Authored targets completed</dt><dd>{summary.targetProgress.completed}/{summary.targetProgress.total}</dd>
      <dt>Accepted response states</dt><dd>{summary.stateCount} · includes preload and accepted subdivisions</dd>
      <dt>Control solver attempts used</dt><dd>{summary.attemptProgress.completed}/{summary.attemptProgress.maximum}</dd>
      <dt>Reserved API invocations</dt><dd>{summary.reservedInvocations}/{summary.maximumInvocations}</dd>
      <dt>Recorded API invocations</dt><dd>{summary.recordedInvocations} · {summary.pendingInvocations} reservation(s) without a recorded result</dd>
      <dt>Known preload / replay / control solver calls</dt><dd>{summary.knownWork.preload_solver_calls} / {summary.knownWork.restart_replay_solver_calls} / {summary.knownWork.control_solver_calls}</dd>
      <dt>Unaccounted execution work</dt><dd data-rc-portable-unknown>{summary.unknownWork ? 'Unknown work remains. Known counts are subtotals.' : 'No unknown work is declared in this saved report.'}</dd>
    </dl>
    <details><summary>Recorded source and file scope</summary>
      <p className="wb2-mono" style={{ overflowWrap: 'anywhere' }}>Source revision: {summary.sourceRevision} · caller declaration</p>
      <p className="wb2-mono" style={{ overflowWrap: 'anywhere' }}>Report: {summary.reportId}</p>
      <p>This version contains one completed job’s original input and nodal report. Detailed member, section and fiber histories, original result/evidence artifacts and a rerun environment are not included. Keep the project and original service records for those materials.</p>
    </details>
    <label>Portable accepted state page{' '}
      <select aria-label="Portable accepted state page" value={page} onChange={event => selectState(Number(event.target.value) * PAGE_SIZE)}>
        {Array.from({ length: Math.ceil(summary.stateCount / PAGE_SIZE) }, (_, i) => <option key={i} value={i}>States {i * PAGE_SIZE}–{Math.min(summary.stateCount - 1, (i + 1) * PAGE_SIZE - 1)}</option>)}
      </select>
    </label>{' '}
    <label>Portable accepted state{' '}
      <select aria-label="Portable accepted state" value={index} disabled={!choices} onChange={event => selectState(Number(event.target.value))}>
        {(choices ?? []).map(row => <option key={row.state_index} value={row.state_index}>State {row.state_index}: {row.phase} · {row.control_displacement_m} m</option>)}
      </select>
    </label>
    <div className="wb2-actions">
      <button type="button" className="wb2-btn" disabled={!index} onClick={() => selectState(index - 1)}>Previous accepted state</button>
      <button type="button" className="wb2-btn" disabled={index === summary.stateCount - 1} onClick={() => selectState(index + 1)}>Next accepted state</button>
    </div>
    {!state ? <p role="status">Loading saved nodal state…</p> : <>
      <p data-rc-portable-selected>Accepted state {state.state_index} · {state.phase} · control {state.control_displacement_m} m · load factor {state.load_factor}</p>
      {geometry ? <RcDeformedShape geometry={geometry} displacements={state.nodes.map(node => ({ nodeId: node.node_id, ux: node.displacements_m_rad[0], uy: node.displacements_m_rad[1] }))}
        selectedMember={memberId} onSelectMember={setMemberId} scale={scale} onScaleChange={setScale} />
        : <p>{geometryUnavailable ? 'Model shape is unavailable. Saved nodal tables remain available.' : 'Loading model shape…'}</p>}
      {member ? <p>Member {member.id}: {member.nodeI} → {member.nodeJ}. Endpoint rows are highlighted below.</p> : null}
      {choices ? <><p>History page: accepted states {page * PAGE_SIZE}–{Math.min(summary.stateCount - 1, (page + 1) * PAGE_SIZE - 1)} of {summary.stateCount}. Stored order is preserved.</p>
        <RcHistoryPlot label="Portable accepted control history" xLabel="Control displacement (m)" yLabel="Load factor (dimensionless)"
          points={choices.map(row => ({ state: row.state_index, x: row.control_displacement_m, y: row.load_factor }))} selectedState={index} onSelectState={selectState} />
      </> : null}
      <NodalTable nodes={state.nodes} kind="displacements_m_rad" state={state.state_index} selectedNodes={selectedNodes} />
      <NodalTable nodes={state.nodes} kind="external_loads_kn_knm" state={state.state_index} selectedNodes={selectedNodes} />
      <NodalTable nodes={state.nodes} kind="reactions_kn_knm" state={state.state_index} selectedNodes={selectedNodes} />
      <p className="wb2-note">A zero reaction at a free DOF is not the applied load. Use the stored applied nodal load table.</p>
    </>}
    <div className="wb2-actions">
      <button type="button" className="wb2-btn" disabled={downloading} onClick={() => void download('request')}>Download original RC input</button>
      <button type="button" className="wb2-btn" disabled={downloading} onClick={() => void download('report')}>Download stored nodal report</button>
    </div>
    {fileMessage ? <p role="status">{fileMessage}</p> : null}
  </section>
}
