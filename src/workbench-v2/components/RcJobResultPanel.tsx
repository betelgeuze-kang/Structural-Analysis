import { useEffect, useRef, useState, type ReactElement } from 'react'
import type { RcJobReview } from '../model/rcJobReview'
import type { RcObject } from '../model/rcJobSchema'
import type { RcResultGeometry } from '../model/rcResultVisualization'
import { RcDeformedShape, RcHistoryPlot } from './RcResultVisualization'

type Column = [string, (row: RcObject) => unknown]
function text(value: unknown): string {
  if (typeof value === 'number') return Number.isFinite(value) ? String(value) : 'unavailable'
  if (typeof value === 'string' || typeof value === 'boolean') return String(value)
  return value === null || value === undefined ? 'unavailable' : JSON.stringify(value)
}
function Table({ label, rows, columns, name }: { label: string; rows: RcObject[]; columns: Column[]; name: string }): ReactElement {
  return <div style={{ overflowX: 'auto', maxWidth: '100%' }} tabIndex={0} role="region" aria-label={label}>
    <table data-rc-table={name} className="wb2-table">
      <caption>{label}</caption>
      <thead><tr>{columns.map(([title]) => <th key={title} style={{ whiteSpace: 'nowrap' }}>{title}</th>)}</tr></thead>
      <tbody>{rows.map((row, index) => <tr key={index}>{columns.map(([title, value], column) => column === 0
        ? <th key={title} scope="row" style={{ whiteSpace: 'nowrap' }}>{text(value(row))}</th>
        : <td key={title} style={{ whiteSpace: 'nowrap' }}>{text(value(row))}</td>)}</tr>)}</tbody>
    </table>
  </div>
}
function pointKey(point: RcObject): string {
  return JSON.stringify([point.member_id, point.integration_point_index, point.fiber_index])
}
function sectionKey(point: RcObject): string { return JSON.stringify([point.member_id, point.integration_point_index]) }

export function RcJobResultPanel({ jobId, review }: { jobId: string; review: RcJobReview }): ReactElement {
  const { summary } = review
  const preloadCount = summary.hasPreload ? 1 : 0
  const [index, setIndex] = useState(summary.targets.length - 1 + preloadCount)
  const [step, setStep] = useState<{ owner: RcJobReview; index: number; value: RcObject } | null>(null)
  const row = step?.owner === review && step.index === index ? step.value : null
  const [geometrySource, setGeometrySource] = useState<{ owner: RcJobReview; value: RcResultGeometry } | null>(null)
  const geometry = geometrySource?.owner === review ? geometrySource.value : null
  const [geometryError, setGeometryError] = useState('')
  const [selectedMember, setSelectedMember] = useState('')
  const [deformationScale, setDeformationScale] = useState('1')
  const [selectedPoint, setSelectedPoint] = useState('')
  const [materialSource, setMaterialSource] = useState<{ owner: RcJobReview; key: string; rows: RcObject[] } | null>(null)
  const [materialPage, setMaterialPage] = useState(Math.floor((summary.targets.length - 1 + preloadCount) / 20))
  const materialKey = JSON.stringify([selectedPoint, materialPage])
  const materialMatchesMember = !selectedMember || (selectedPoint && JSON.parse(selectedPoint)[0] === selectedMember)
  const material = materialMatchesMember && materialSource?.owner === review && materialSource.key === materialKey ? materialSource.rows : null
  const [materialError, setMaterialError] = useState('')
  const [selectedSection, setSelectedSection] = useState('')
  const [sectionPage, setSectionPage] = useState(Math.floor((summary.targets.length - 1 + preloadCount) / 20))
  const [sectionSource, setSectionSource] = useState<{ owner: RcJobReview; key: string; rows: RcObject[] } | null>(null)
  const sectionHistoryKey = JSON.stringify([selectedSection, sectionPage])
  const sectionMatchesMember = !selectedMember || (selectedSection && JSON.parse(selectedSection)[0] === selectedMember)
  const sectionHistory = sectionMatchesMember && sectionSource?.owner === review && sectionSource.key === sectionHistoryKey ? sectionSource.rows : null
  const [sectionError, setSectionError] = useState('')
  const [error, setError] = useState<string | null>(null)
  const urls = useRef(new Set<string>())
  function unavailable(error: unknown, message: string, local: (value: string) => void): void {
    const code = error instanceof Error ? error.message : ''
    if (/authorization|scope_changed|(?:http_|HTTP_)(?:401|403)|rc_review_disposed/.test(code)) setError(message)
    else local(message)
  }
  useEffect(() => review.onFailure(setError), [review])
  useEffect(() => () => { for (const url of urls.current) URL.revokeObjectURL(url); urls.current.clear() }, [])
  useEffect(() => {
    let active = true
    setGeometrySource(null); setSelectedMember(''); setGeometryError('')
    if (review.geometry) review.geometry().then(value => { if (active) setGeometrySource({ owner: review, value }) })
      .catch(error => { if (active) unavailable(error, 'Stored RC geometry is unavailable.', setGeometryError) })
    return () => { active = false }
  }, [review])
  useEffect(() => {
    let active = true
    setStep(null)
    review.epoch(index).then((value) => {
      if (!active) return
      setStep({ owner: review, index, value })
    }).catch(() => { if (active) setError('Stored RC step is unavailable.') })
    return () => { active = false }
  }, [review, index])
  useEffect(() => {
    if (!row) return
    const fibers = row.fiber_results.filter((value: RcObject) => !selectedMember || value.member_id === selectedMember)
    const sections = row.section_results.filter((value: RcObject) => !selectedMember || value.member_id === selectedMember)
    setSelectedPoint(current => fibers.some((point: RcObject) => pointKey(point) === current) ? current : fibers.length ? pointKey(fibers[0]) : '')
    setSelectedSection(current => sections.some((point: RcObject) => sectionKey(point) === current) ? current : sections.length ? sectionKey(sections[0]) : '')
  }, [row, selectedMember])
  useEffect(() => {
    let active = true
    setMaterialSource(null); setMaterialError('')
    if (selectedPoint) {
      const [memberId, integrationPoint, fiberIndex] = JSON.parse(selectedPoint)
      const request = review.materialPage
        ? review.materialPage(memberId, integrationPoint, fiberIndex, materialPage * 20, 20)
        : review.material(memberId, integrationPoint, fiberIndex)
      request.then((value) => {
        if (active) setMaterialSource({ owner: review, key: materialKey, rows: value })
      }).catch(error => { if (active) unavailable(error, 'Stored RC material history is unavailable.', setMaterialError) })
    }
    return () => { active = false }
  }, [review, selectedPoint, materialPage])
  useEffect(() => {
    let active = true
    setSectionSource(null); setSectionError('')
    if (selectedSection && review.sectionPage) {
      const [memberId, integrationPoint] = JSON.parse(selectedSection)
      review.sectionPage(memberId, integrationPoint, sectionPage * 20, 20).then(value => {
        if (active) setSectionSource({ owner: review, key: sectionHistoryKey, rows: value })
      }).catch(error => { if (active) unavailable(error, 'Stored RC section history is unavailable.', setSectionError) })
    }
    return () => { active = false }
  }, [review, selectedSection, sectionPage])
  function inspectState(next: number): void {
    if (!Number.isSafeInteger(next) || next < 0 || next >= summary.targets.length + preloadCount) return
    if (next !== index) { setStep(null); setIndex(next) }
    setMaterialPage(Math.floor(next / 20)); setSectionPage(Math.floor(next / 20))
  }
  async function download(role: string): Promise<void> {
    try {
      const blob = await review.download(role)
      const url = URL.createObjectURL(blob), anchor = document.createElement('a')
      urls.current.add(url)
      anchor.href = url; anchor.download = `${jobId}-rc-${role}.${role === 'history' ? 'ndjson' : 'json'}`
      document.body.append(anchor); anchor.click(); anchor.remove()
      window.setTimeout(() => { URL.revokeObjectURL(url); urls.current.delete(url) }, 0)
    } catch { setError('Original RC artifact is unavailable.') }
  }
  if (error) return <section data-rc-review="invalid" role="alert"><h3>RC result unavailable</h3><p>{error}</p></section>
  const point = row?.fiber_results.find((p: RcObject) => pointKey(p) === selectedPoint)
  const stateKeys = point ? Object.keys(point.material_state).filter((key) => key !== 'schema_version') : []
  const materialCount = review.materialPage ? summary.targets.length + preloadCount : (material?.length ?? 0)
  const sectionCount = summary.targets.length + preloadCount
  const memberRows = (rows: RcObject[]) => rows.filter(value => !selectedMember || value.member_id === selectedMember)
  const visibleMaterial = material ? review.materialPage ? material : material.slice(materialPage * 20, (materialPage + 1) * 20) : null
  return <section data-rc-review={row ? 'verified' : 'loading'} className="wb2-rc-job" style={{ minWidth: 0, maxWidth: '100%' }} aria-label="Stored experimental RC result">
    <h3 className="wb2-panel__title">Stored experimental RC result</h3>
    <p className="wb2-note" data-rc-authority>{summary.historyFile
      ? 'Stored record order, checkpoint links and physical values match the recorded assemblies. The browser does not rerun the solver, authenticate the model or source, or establish independent validation, design approval or release readiness.'
      : 'Original bytes and stored request, receipt and checkpoint bindings verified. Fresh replay is a retained worker attestation. This browser does not rerun the solver or establish independent validation, design approval or release readiness.'}</p>
    {summary.historyFile ? <p data-rc-history-status>Stored history: {summary.historyFile.status} · {summary.targets.length}/{summary.historyFile.declaredTargets} lateral targets · {summary.historyFile.bytes} bytes.</p> : null}
    <dl className="wb2-kv">
      {summary.pinRoller ? <>
        <dt>Experimental support profile</dt><dd data-rc-pin-roller-profile>Pin/roller beam · pin {summary.pinRoller.pin} (UX/UY), roller {summary.pinRoller.roller} (UY)</dd>
      </> : null}
      {summary.assemblyReuse ? <><dt>Intermediate calculation reuse</dt><dd data-rc-reuse>Enabled · same result verification required</dd></> : null}
      <dt>Control</dt><dd>{summary.control.node_id} · {summary.control.component} ({summary.control.unit})</dd>
      <dt>{summary.historyFile ? 'Declared canonical model identity' : 'Source revision'}</dt><dd className="wb2-mono" style={{ overflowWrap: 'anywhere' }} data-rc-source>{summary.sourceRevision}</dd>
      <dt>Source attestation</dt><dd>Caller declaration; not independently attested</dd>
      {summary.fixedGuided ? <>
        <dt>Experimental support profile</dt><dd data-rc-fixed-guided-profile>Fixed/axial guide · fixed {summary.fixedGuided.fixed}, guided {summary.fixedGuided.guided} ({summary.fixedGuided.axial} free)</dd>
      </> : null}
      {summary.historyFile ? <>
        <dt>Known step calls in this file</dt><dd data-rc-core>{summary.knownCoreCalls}</dd>
        <dt>Known Newton iterations in this file</dt><dd>{summary.knownNewtonIterations}</dd>
        <dt>Step calls with unknown work</dt><dd>{summary.historyFile.unknownCalls}</dd>
        <dt>Full execution cost</dt><dd data-rc-unknown>Unavailable from this file. Earlier runs, repeated work and interrupted unpublished calls require separate execution reports.</dd>
      </> : <>
      <dt>Reserved API invocations</dt><dd data-rc-reserved>{summary.reservedInvocations}</dd>
      <dt>Confirmed in successful receipts</dt><dd>{summary.confirmedInvocations}</dd>
      <dt>Known core calls in successful receipts</dt><dd data-rc-core>{summary.knownCoreCalls}</dd>
      <dt>Known Newton iterations in successful receipts</dt><dd>{summary.knownNewtonIterations}</dd>
      <dt>Unaccounted execution work</dt><dd data-rc-unknown>{summary.unknownWork ? 'Unknown work remains; these counts are subtotals.' : 'No reservation gap or unknown work reported in this completed bundle.'}</dd>
      </>}
    </dl>
    {summary.hasPreload ? <>
      <p data-rc-preload-note>Constant loads are applied before the lateral targets. Preload is included in the stored material history and core-call totals.</p>
      <Table name="constant-loads" label="Constant nodal loads" rows={summary.constantLoads ?? []}
        columns={ [['Node', (r) => r.node_id], ['FX (kN)', (r) => r.FX_kN], ['FY (kN)', (r) => r.FY_kN], ['MZ (kN*m)', (r) => r.MZ_kNm]] } />
    </> : null}
    <label htmlFor={`${jobId}-rc-target`}>RC target to inspect</label>{' '}
    <select id={`${jobId}-rc-target`} value={index} style={{ maxWidth: '100%' }} onChange={(event) => {
      inspectState(Number(event.target.value))
    }}>
      {summary.hasPreload ? <option value={0}>Preload: constant loads</option> : null}
      {summary.targets.map((target, i) => <option key={i} value={i + preloadCount}>Step {i + 1 + preloadCount}: {target} m</option>)}
    </select>
    {!row ? <p role="status">Loading stored step…</p> : <>
      <p data-rc-selected>{summary.hasPreload && index === 0 ? <>Preload · constant loads</> : <>Step {row.epoch} · target {summary.targets[index - preloadCount]} m</>} · load factor {row.load_factor}</p>
      <p className="wb2-mono" style={{ overflowWrap: 'anywhere' }}>Checkpoint {row.checkpoint_hash}</p>
      {geometry ? <RcDeformedShape geometry={geometry} displacements={row.node_displacements.map((node: RcObject) => ({ nodeId: node.node_id, ux: node.UX_m, uy: node.UY_m }))}
        selectedMember={selectedMember} onSelectMember={setSelectedMember} scale={deformationScale} onScaleChange={setDeformationScale} />
        : <p>{geometryError || 'Verified model geometry is unavailable for this review.'}</p>}
      <p data-rc-selected-member style={{ overflowWrap: 'anywhere' }}>{selectedMember ? `Member ${selectedMember}: member, section and fiber tables below are filtered to this member.` : 'Showing all members, sections and fibers.'} Nodal displacements and support reactions retain the complete model.</p>
      <Table name="nodes" label={`Node displacements · RC step ${row.epoch}`} rows={row.node_displacements}
        columns={[
          ['Node', (r) => r.node_id], ['UX (m)', (r) => r.UX_m], ['UY (m)', (r) => r.UY_m], ['UZ (m)', (r) => r.UZ_m],
          ['RX (rad)', (r) => r.RX_rad], ['RY (rad)', (r) => r.RY_rad], ['RZ (rad)', (r) => r.RZ_rad],
        ]} />
      <Table name="reactions" label={`Support reactions · RC step ${row.epoch}`} rows={row.support_reactions}
        columns={ [['Node', (r) => r.node_id], ['DOF', (r) => r.dof], ['Value (SI)', (r) => r.value_si], ['Unit', (r) => r.unit]] } />
      <p>Member end forces below use each member's local axes: FX and FY in N, MZ in N*m. These are stored endpoint values; no continuous force diagram is inferred.</p>
      <Table name="members" label={`Member end forces · RC step ${row.epoch}`} rows={memberRows(row.member_end_forces)}
        columns={[
          ['Member', (r) => r.member_id], ['i FX (N)', (r) => r.local_end_i.FX_N], ['i FY (N)', (r) => r.local_end_i.FY_N], ['i MZ (N*m)', (r) => r.local_end_i.MZ_Nm],
          ['j FX (N)', (r) => r.local_end_j.FX_N], ['j FY (N)', (r) => r.local_end_j.FY_N], ['j MZ (N*m)', (r) => r.local_end_j.MZ_Nm],
        ]} />
      <Table name="sections" label={`Section response · RC step ${row.epoch}`} rows={memberRows(row.section_results)}
        columns={[
          ['Member', (r) => r.member_id], ['Integration point', (r) => r.integration_point_index], ['Axial strain', (r) => r.axial_strain],
          ['Curvature (1/m)', (r) => r.curvature_z_per_m], ['Axial force (N)', (r) => r.axial_force_N], ['Moment (N*m)', (r) => r.moment_z_Nm],
        ]} />
      {review.sectionPage ? <section data-rc-section-history>
        <label htmlFor={`${jobId}-rc-section`}>RC section history</label>{' '}
        <select id={`${jobId}-rc-section`} value={selectedSection} style={{ maxWidth: '100%' }} onChange={event => setSelectedSection(event.target.value)}>
          {memberRows(row.section_results).map(section => <option key={sectionKey(section)} value={sectionKey(section)}>{section.member_id} · integration point {section.integration_point_index}</option>)}
        </select>{' '}
        <label htmlFor={`${jobId}-rc-section-page`}>Section history steps</label>{' '}
        <select id={`${jobId}-rc-section-page`} value={sectionPage} onChange={event => setSectionPage(Number(event.target.value))}>
          {Array.from({ length: Math.ceil(sectionCount / 20) }, (_, page) => <option key={page} value={page}>Steps {page * 20 + 1}–{Math.min(sectionCount, (page + 1) * 20)}</option>)}
        </select>
        {sectionHistory ? <>
          <RcHistoryPlot label="Section moment–curvature history" xLabel="Curvature (1/m)" yLabel="Moment (N*m)"
            points={sectionHistory.map(value => ({ state: value.epoch - 1, x: value.curvature_z_per_m, y: value.moment_z_Nm }))} selectedState={index} onSelectState={inspectState} />
          <Table name="section-history" label="Selected section · stored history" rows={sectionHistory} columns={[
            ['Step', value => value.epoch], ['Axial strain', value => value.axial_strain], ['Curvature (1/m)', value => value.curvature_z_per_m],
            ['Axial force (N)', value => value.axial_force_N], ['Moment (N*m)', value => value.moment_z_Nm],
          ]} />
        </> : <p role="status">{sectionError || 'Loading stored section history…'}</p>}
      </section> : <p>Section history is unavailable for this review.</p>}
      <Table name="fibers" label={`Fiber response · RC step ${row.epoch}`} rows={memberRows(row.fiber_results)}
        columns={[
          ['Member', (r) => r.member_id], ['Integration point', (r) => r.integration_point_index], ['Fiber', (r) => r.fiber_id],
          ['Material', (r) => r.material_kind], ['Strain', (r) => r.strain], ['Stress (MPa)', (r) => r.stress_MPa],
        ]} />
      <label htmlFor={`${jobId}-rc-material`}>RC material point history</label>{' '}
      <select id={`${jobId}-rc-material`} value={selectedPoint} onChange={(event) => {
        if (event.target.value !== selectedPoint) setSelectedPoint(event.target.value)
      }} style={{ maxWidth: '100%' }}>
        {memberRows(row.fiber_results).map((p: RcObject) => <option key={pointKey(p)} value={pointKey(p)}>{p.member_id} · point {p.integration_point_index} · {p.fiber_id} ({p.material_kind})</option>)}
      </select>
      {material ? <>
        <p data-rc-material-count>{materialCount} stored material steps · showing {materialPage * 20 + 1}–{Math.min(materialCount, (materialPage + 1) * 20)}</p>
        <label htmlFor={`${jobId}-rc-material-page`}>Material history steps</label>{' '}
        <select id={`${jobId}-rc-material-page`} value={materialPage} onChange={(event) => {
          const next = Number(event.target.value)
          if (next !== materialPage) setMaterialPage(next)
        }}>
          {Array.from({ length: Math.ceil(materialCount / 20) }, (_, page) => <option key={page} value={page}>Steps {page * 20 + 1}–{Math.min(materialCount, (page + 1) * 20)}</option>)}
        </select>
        <RcHistoryPlot label="Fiber stress–strain history" xLabel="Strain (1)" yLabel="Stress (MPa)"
          points={(visibleMaterial ?? []).map(value => ({ state: value.epoch - 1, x: value.strain, y: value.stress_MPa }))} selectedState={index} onSelectState={inspectState} />
        <Table name="material-history" label="Selected material point · stored history" rows={visibleMaterial ?? []}
        columns={[
          ['Step', (r) => r.epoch], ['Strain', (r) => r.strain], ['Stress (MPa)', (r) => r.stress_MPa],
          ...stateKeys.map((key): Column => [key, (r) => r.material_state[key]]),
        ]} />
      </> : <p role="status">{materialError || 'Loading stored material history…'}</p>}
    </>}
    <div className="wb2-actions">
      {summary.artifactRoles.map((role) => <button type="button" className="wb2-btn" key={role} onClick={() => void download(role)}>
        Download RC {role === 'checkpoint' ? 'saved job checkpoint' : role === 'terminal' ? 'terminal restart' : role}
      </button>)}
    </div>
  </section>
}
