import { useEffect, useRef, useState, type ReactElement } from 'react'
import type { RcCorotationalReportReview, RcCorotationalStateChoice } from '../model/rcCorotationalReportReview'
import type { RcCorotationalReportControl, RcCorotationalReportNode, RcCorotationalReportResponse } from '../model/rcCorotationalReportSchema'
import type { RcResultGeometry } from '../model/rcResultVisualization'
import { RcDeformedShape, RcHistoryPlot } from './RcResultVisualization'

const PAGE_SIZE = 20
export function RcCorotationalControlDescription({ control }: { control: RcCorotationalReportControl }): ReactElement {
  if (!('observation' in control)) return <>{control.node_id} · {control.component} (m)</>
  return <div data-rc-corotational-observation>
    <p>Weighted displacement observation (m)</p>
    <div role="region" aria-label="Movements included in this observation" tabIndex={0} style={{ overflowX: 'auto', maxWidth: '100%' }}>
    <table className="wb2-table">
      <caption>Movements included in this observation</caption>
      <thead><tr><th scope="col">Node</th><th scope="col">Movement</th><th scope="col">Factor</th></tr></thead>
      <tbody>{control.observation.terms.map(term => <tr key={`${term.node_id}:${term.component}`}>
        <th scope="row">{term.node_id}</th><td>{term.component} ({term.component === 'RZ' ? 'rad' : 'm'})</td>
        <td>{term.coefficient}{term.component === 'RZ' ? ' m/rad' : ''}</td>
      </tr>)}</tbody>
    </table>
    </div>
    <p className="wb2-note">The saved value combines these movements, including any support motion and rotation. Rotation factors define a linear observation, not a finite-rotation drift angle.</p>
  </div>
}
function NodalTable({ nodes, kind, state, selectedNodes }: { nodes: RcCorotationalReportNode[]; kind: 'displacements_m_rad' | 'external_loads_kn_knm' | 'reactions_kn_knm'; state: number; selectedNodes: string[] }): ReactElement {
  const displacement = kind === 'displacements_m_rad'
  const label = displacement ? 'Node displacements' : kind === 'external_loads_kn_knm' ? 'Applied nodal loads' : 'Support reactions (free DOF values are zero)'
  const columns = displacement ? ['UX (m)', 'UY (m)', 'RZ (rad)'] : ['FX (kN)', 'FY (kN)', 'MZ (kN*m)']
  return <div role="region" aria-label={`${label} · accepted state ${state}`} tabIndex={0} style={{ overflowX: 'auto', maxWidth: '100%' }}>
    <table className="wb2-table" data-rc-corotational-table={kind}>
      <caption>{label} · accepted state {state}</caption>
      <thead><tr><th scope="col">Node</th>{columns.map(title => <th scope="col" key={title} style={{ textTransform: 'none' }}>{title}</th>)}</tr></thead>
      <tbody>{nodes.map(node => <tr key={node.node_id} data-rc-selected-node={selectedNodes.includes(node.node_id) ? 'true' : 'false'} style={selectedNodes.includes(node.node_id) ? { background: 'var(--wb2-selection-bg, rgba(56, 189, 248, 0.12))' } : undefined}><th scope="row">{node.node_id}</th>{node[kind].map((value, i) => <td key={i}>{String(value)}</td>)}</tr>)}</tbody>
    </table>
  </div>
}
export function rcCorotationalReportLink(jobId: string, reportId: string): string {
  if (!/^job_[0-9a-f]{32}$/.test(jobId) || !/^rcc_[0-9a-f]{64}$/.test(reportId)) throw new Error('rc_corotational_report_link_invalid')
  const url = new URL(location.pathname, location.origin); url.hash = '/workbench-v2'
  url.searchParams.set('rcJob', jobId); url.searchParams.set('rcReport', reportId)
  return url.href
}
export function RcCorotationalReportPanel({ review, expectedReportId }: { review: RcCorotationalReportReview; expectedReportId?: string }): ReactElement {
  const { summary } = review
  const [index, setIndex] = useState(summary.stateCount - 1)
  const [page, setPage] = useState(Math.floor((summary.stateCount - 1) / PAGE_SIZE))
  const [choices, setChoices] = useState<RcCorotationalStateChoice[] | null>(null)
  const [state, setState] = useState<RcCorotationalReportResponse | null>(null)
  const [geometry, setGeometry] = useState<RcResultGeometry | null>(null)
  const [geometryMessage, setGeometryMessage] = useState('')
  const [selectedMember, setSelectedMember] = useState('')
  const [shapeScale, setShapeScale] = useState('1')
  const [failure, setFailure] = useState<string | null>(null)
  const [fileMessage, setFileMessage] = useState('')
  const [readingFile, setReadingFile] = useState(false)
  const generation = useRef(0), urls = useRef(new Set<string>())
  const linkMismatch = expectedReportId !== undefined && expectedReportId !== summary.reportId
  useEffect(() => review.onFailure(() => setFailure('The saved nodal report is no longer available. Reopen the project with the current account.')), [review])
  useEffect(() => () => { generation.current++; for (const url of urls.current) URL.revokeObjectURL(url); urls.current.clear() }, [])
  useEffect(() => {
    let active = true; setGeometry(null); setSelectedMember(''); setGeometryMessage('')
    if (!linkMismatch && review.geometry) review.geometry().then(value => {
      if (active) { setGeometry(value); setSelectedMember(value.members[0]?.id ?? '') }
    }).catch(() => { if (active) setGeometryMessage('The model shape is unavailable. Verified nodal tables remain available.') })
    return () => { active = false }
  }, [review, linkMismatch])
  useEffect(() => {
    let active = true; setChoices(null)
    if (!linkMismatch) review.statePage(page * PAGE_SIZE, PAGE_SIZE).then(rows => { if (active) setChoices(rows) }).catch(() => { if (active) setFailure('The saved state list could not be verified.') })
    return () => { active = false }
  }, [review, page, linkMismatch])
  useEffect(() => {
    let active = true; setState(null)
    if (!linkMismatch) review.state(index).then(row => { if (active) setState(row) }).catch(() => { if (active) setFailure('The selected nodal state could not be verified.') })
    return () => { active = false }
  }, [review, index, linkMismatch])
  async function download(): Promise<void> {
    try {
      const blob = await review.download(), url = URL.createObjectURL(blob), anchor = document.createElement('a')
      urls.current.add(url); anchor.href = url; anchor.download = `${summary.reportId}-corotational-nodal-report.json`
      document.body.append(anchor); anchor.click(); anchor.remove()
      window.setTimeout(() => { URL.revokeObjectURL(url); urls.current.delete(url) }, 0)
    } catch { setFileMessage('The exact saved report could not be downloaded.') }
  }
  async function reopen(file?: File): Promise<void> {
    if (!file || readingFile) return
    const ownGeneration = ++generation.current; setFileMessage('')
    if (!file.size || file.size > review.maximumBytes) { setFileMessage('The selected report exceeds the configured review size limit.'); return }
    setReadingFile(true)
    try {
      await review.reopen(new Uint8Array(await file.arrayBuffer()))
      if (generation.current === ownGeneration) setFileMessage('Reopened exact report bytes match this authenticated saved report.')
    } catch { if (generation.current === ownGeneration) setFileMessage('This file does not match the exact authenticated saved report. The saved review is retained.') }
    finally { if (generation.current === ownGeneration) setReadingFile(false) }
  }
  function inspectState(next: number): void {
    if (!Number.isSafeInteger(next) || next < 0 || next >= summary.stateCount || next === index) return
    setState(null); setIndex(next)
    const nextPage = Math.floor(next / PAGE_SIZE)
    if (page !== nextPage) { setChoices(null); setPage(nextPage) }
  }
  const member = geometry?.members.find(value => value.id === selectedMember)
  const selectedNodes = member ? [member.nodeI, member.nodeJ] : []
  if (linkMismatch || failure) return <section className="wb2-rc-job" data-rc-corotational-review="invalid" role="alert"><h3>Corotational nodal report unavailable</h3><p>{linkMismatch ? 'This report link does not match the authenticated report for the saved job.' : failure}</p></section>
  return <section className="wb2-rc-job" data-rc-corotational-review={state ? 'report_verified' : 'loading'} aria-label="Stored experimental corotational RC nodal report" style={{ minWidth: 0, maxWidth: '100%' }}>
    <h3 className="wb2-panel__title">Stored experimental corotational RC nodal report</h3>
    <p data-rc-corotational-authority>Report bytes, declarations and saved nodal values are verified for this authenticated job. Original result and evidence custody remains with the service. Worker verification is a stored attestation. Independent physical validation, design approval and release readiness are not granted.</p>
    <dl className="wb2-kv">
      <dt>Case</dt><dd>{summary.caseId}</dd>
      <dt>Control</dt><dd><RcCorotationalControlDescription control={summary.control} /></dd>
      <dt>Authored targets completed</dt><dd data-rc-corotational-targets>{summary.targetProgress.completed}/{summary.targetProgress.total}</dd>
      <dt>Control solver attempts used</dt><dd data-rc-corotational-attempts>{summary.attemptProgress.completed}/{summary.attemptProgress.maximum}</dd>
      <dt>Accepted response states</dt><dd data-rc-corotational-states>{summary.stateCount} · preload and accepted subdivisions are included separately</dd>
      <dt>Reserved API invocations</dt><dd data-rc-corotational-budget>{summary.reservedInvocations}/{summary.maximumInvocations}</dd>
      <dt>Recorded API invocations</dt><dd>{summary.recordedInvocations} · {summary.pendingInvocations} reservation(s) without a recorded result</dd>
      <dt>Known preload / replay / control solver calls</dt><dd>{summary.knownWork.preload_solver_calls} / {summary.knownWork.restart_replay_solver_calls} / {summary.knownWork.control_solver_calls}</dd>
      <dt>Unaccounted execution work</dt><dd data-rc-corotational-unknown>{summary.unknownWork ? 'Unknown work remains. Known counts are subtotals.' : 'No unknown work is declared in this saved report.'}</dd>
      <dt>Source revision</dt><dd className="wb2-mono" style={{ overflowWrap: 'anywhere' }}>{summary.sourceRevision} · caller declaration</dd>
      <dt>Report</dt><dd className="wb2-mono" data-rc-corotational-report-id style={{ overflowWrap: 'anywhere' }}>{summary.reportId}</dd>
    </dl>
    {summary.constantLoads.length ? <p data-rc-corotational-preload>Fixed nodal loads are retained through preload and controlled states. Their values are additional to the proportional reference loads.</p> : null}
    <label htmlFor={`${summary.jobId}-corotational-page`}>Accepted state page</label>{' '}
    <select id={`${summary.jobId}-corotational-page`} value={page} onChange={e => { const next = Number(e.target.value); setChoices(null); setState(null); setPage(next); setIndex(next * PAGE_SIZE) }}>
      {Array.from({ length: Math.ceil(summary.stateCount / PAGE_SIZE) }, (_, i) => <option key={i} value={i}>States {i * PAGE_SIZE}–{Math.min(summary.stateCount - 1, (i + 1) * PAGE_SIZE - 1)}</option>)}
    </select>{' '}
    <label htmlFor={`${summary.jobId}-corotational-state`}>Accepted state to inspect</label>{' '}
    <select id={`${summary.jobId}-corotational-state`} style={{ maxWidth: '100%' }} value={index} disabled={!choices} onChange={e => inspectState(Number(e.target.value))}>
      {(choices ?? []).map(row => <option key={row.state_index} value={row.state_index}>State {row.state_index}: {row.phase} · {row.control_displacement_m} m</option>)}
    </select>
    <div className="wb2-actions">
      <button type="button" className="wb2-btn" disabled={index === 0} onClick={() => inspectState(index - 1)}>Previous accepted state</button>
      <button type="button" className="wb2-btn" disabled={index === summary.stateCount - 1} onClick={() => inspectState(index + 1)}>Next accepted state</button>
    </div>
    {!state ? <p role="status">Loading saved nodal state…</p> : <>
      <p data-rc-corotational-selected>Accepted state {state.state_index} · {state.phase} · control {state.control_displacement_m} m · load factor {state.load_factor}</p>
      <p className="wb2-mono" style={{ overflowWrap: 'anywhere' }}>Checkpoint {state.checkpoint_hash}</p>
      {geometry ? <RcDeformedShape geometry={geometry} displacements={state.nodes.map(node => ({ nodeId: node.node_id, ux: node.displacements_m_rad[0], uy: node.displacements_m_rad[1] }))} selectedMember={selectedMember} onSelectMember={setSelectedMember} scale={shapeScale} onScaleChange={setShapeScale} /> : <p data-rc-geometry-status>{geometryMessage || (review.geometry ? 'Loading model shape…' : 'Verified model geometry is unavailable for this review.')}</p>}
      {member ? <p data-rc-corotational-selected-member style={{ overflowWrap: 'anywhere' }}>Member {member.id}: {member.nodeI} → {member.nodeJ}. Endpoint rows are highlighted below.</p> : null}
      {choices ? <>
        <p>History page: accepted states {page * PAGE_SIZE}–{Math.min(summary.stateCount - 1, (page + 1) * PAGE_SIZE - 1)} of {summary.stateCount}. Preload and accepted subdivisions retain their stored order.</p>
        <RcHistoryPlot label="Accepted control history" xLabel="Control displacement (m)" yLabel="Load factor (dimensionless)" points={choices.map(row => ({ state: row.state_index, x: row.control_displacement_m, y: row.load_factor }))} selectedState={index} onSelectState={inspectState} />
      </> : null}
      <p data-rc-corotational-member-unavailable>Member end forces, section moment–curvature and fiber stress–strain are unavailable in this saved nodal report.</p>
      <NodalTable nodes={state.nodes} kind="displacements_m_rad" state={state.state_index} selectedNodes={selectedNodes} />
      <NodalTable nodes={state.nodes} kind="external_loads_kn_knm" state={state.state_index} selectedNodes={selectedNodes} />
      <NodalTable nodes={state.nodes} kind="reactions_kn_knm" state={state.state_index} selectedNodes={selectedNodes} />
      <p className="wb2-note">{'observation' in summary.control ? 'This observation combines nodal movements. Use the applied nodal load table for force; a zero reaction at a free DOF is not the lateral load.' : 'A free control DOF has zero support reaction. Use the applied nodal load table for its force; do not interpret that zero reaction as the lateral load.'}</p>
    </>}
    <div className="wb2-actions"><button type="button" className="wb2-btn" onClick={() => void download()}>Download corotational nodal report</button>
      <label>Reopen corotational report JSON <input type="file" aria-label="Reopen corotational report JSON" accept="application/json,.json" disabled={readingFile} onChange={e => { void reopen(e.target.files?.[0]); e.target.value = '' }} /></label>
      <a data-rc-corotational-project-link href={rcCorotationalReportLink(summary.jobId, summary.reportId)} target="_blank" rel="noopener">Reopen this corotational report</a>
    </div>
    {fileMessage ? <p role="status" data-rc-corotational-file-status>{fileMessage}</p> : null}
  </section>
}
