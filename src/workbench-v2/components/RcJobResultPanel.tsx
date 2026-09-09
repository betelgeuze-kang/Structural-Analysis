import { useEffect, useRef, useState, type ReactElement } from 'react'
import type { RcJobReview } from '../model/rcJobReview'
import type { RcObject } from '../model/rcJobSchema'

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

export function RcJobResultPanel({ jobId, review }: { jobId: string; review: RcJobReview }): ReactElement {
  const { summary } = review
  const preloadCount = summary.hasPreload ? 1 : 0
  const [index, setIndex] = useState(summary.targets.length - 1 + preloadCount)
  const [row, setRow] = useState<RcObject | null>(null)
  const [selectedPoint, setSelectedPoint] = useState('')
  const [material, setMaterial] = useState<RcObject[] | null>(null)
  const [materialPage, setMaterialPage] = useState(Math.floor((summary.targets.length - 1 + preloadCount) / 20))
  const [error, setError] = useState<string | null>(null)
  const urls = useRef(new Set<string>())
  useEffect(() => review.onFailure(setError), [review])
  useEffect(() => () => { for (const url of urls.current) URL.revokeObjectURL(url); urls.current.clear() }, [])
  useEffect(() => {
    let active = true
    setRow(null)
    review.epoch(index).then((value) => {
      if (!active) return
      setRow(value)
      setSelectedPoint((current) => value.fiber_results.some((point: RcObject) => pointKey(point) === current)
        ? current : pointKey(value.fiber_results[0]))
    }).catch(() => { if (active) setError('Stored RC step is unavailable.') })
    return () => { active = false }
  }, [review, index])
  useEffect(() => {
    let active = true
    setMaterial(null)
    if (selectedPoint) {
      const [memberId, integrationPoint, fiberIndex] = JSON.parse(selectedPoint)
      const request = review.materialPage
        ? review.materialPage(memberId, integrationPoint, fiberIndex, materialPage * 20, 20)
        : review.material(memberId, integrationPoint, fiberIndex)
      request.then((value) => {
        if (active) setMaterial(value)
      }).catch(() => { if (active) setError('Stored RC material history is unavailable.') })
    }
    return () => { active = false }
  }, [review, selectedPoint, materialPage])
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
  return <section data-rc-review={row ? 'verified' : 'loading'} className="wb2-frame3d-job" style={{ minWidth: 0, maxWidth: '100%' }} aria-label="Stored experimental RC result">
    <h3 className="wb2-panel__title">Stored experimental RC result</h3>
    <p className="wb2-note" data-rc-authority>{summary.historyFile
      ? 'Stored record order, checkpoint links and physical values match the recorded assemblies. The browser does not rerun the solver, authenticate the model or source, or establish independent validation, design approval or release readiness.'
      : 'Original bytes and stored request, receipt and checkpoint bindings verified. Fresh replay is a retained worker attestation. This browser does not rerun the solver or establish independent validation, design approval or release readiness.'}</p>
    {summary.historyFile ? <p data-rc-history-status>Stored history: {summary.historyFile.status} · {summary.targets.length}/{summary.historyFile.declaredTargets} lateral targets · {summary.historyFile.bytes} bytes.</p> : null}
    <dl className="wb2-kv">
      <dt>Control</dt><dd>{summary.control.node_id} · {summary.control.component} ({summary.control.unit})</dd>
      <dt>{summary.historyFile ? 'Declared canonical model identity' : 'Source revision'}</dt><dd className="wb2-mono" style={{ overflowWrap: 'anywhere' }} data-rc-source>{summary.sourceRevision}</dd>
      <dt>Source attestation</dt><dd>Caller declaration; not independently attested</dd>
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
      const next = Number(event.target.value)
      if (next !== index) { setRow(null); setIndex(next) }
    }}>
      {summary.hasPreload ? <option value={0}>Preload: constant loads</option> : null}
      {summary.targets.map((target, i) => <option key={i} value={i + preloadCount}>Step {i + 1 + preloadCount}: {target} m</option>)}
    </select>
    {!row ? <p role="status">Loading stored step…</p> : <>
      <p data-rc-selected>{summary.hasPreload && index === 0 ? <>Preload · constant loads</> : <>Step {row.epoch} · target {summary.targets[index - preloadCount]} m</>} · load factor {row.load_factor}</p>
      <p className="wb2-mono" style={{ overflowWrap: 'anywhere' }}>Checkpoint {row.checkpoint_hash}</p>
      <Table name="nodes" label={`Node displacements · RC step ${row.epoch}`} rows={row.node_displacements}
        columns={[
          ['Node', (r) => r.node_id], ['UX (m)', (r) => r.UX_m], ['UY (m)', (r) => r.UY_m], ['UZ (m)', (r) => r.UZ_m],
          ['RX (rad)', (r) => r.RX_rad], ['RY (rad)', (r) => r.RY_rad], ['RZ (rad)', (r) => r.RZ_rad],
        ]} />
      <Table name="reactions" label={`Support reactions · RC step ${row.epoch}`} rows={row.support_reactions}
        columns={ [['Node', (r) => r.node_id], ['DOF', (r) => r.dof], ['Value (SI)', (r) => r.value_si], ['Unit', (r) => r.unit]] } />
      <Table name="members" label={`Member end forces · RC step ${row.epoch}`} rows={row.member_end_forces}
        columns={[
          ['Member', (r) => r.member_id], ['i FX (N)', (r) => r.local_end_i.FX_N], ['i FY (N)', (r) => r.local_end_i.FY_N], ['i MZ (N*m)', (r) => r.local_end_i.MZ_Nm],
          ['j FX (N)', (r) => r.local_end_j.FX_N], ['j FY (N)', (r) => r.local_end_j.FY_N], ['j MZ (N*m)', (r) => r.local_end_j.MZ_Nm],
        ]} />
      <Table name="sections" label={`Section response · RC step ${row.epoch}`} rows={row.section_results}
        columns={[
          ['Member', (r) => r.member_id], ['Integration point', (r) => r.integration_point_index], ['Axial strain', (r) => r.axial_strain],
          ['Curvature (1/m)', (r) => r.curvature_z_per_m], ['Axial force (N)', (r) => r.axial_force_N], ['Moment (N*m)', (r) => r.moment_z_Nm],
        ]} />
      <Table name="fibers" label={`Fiber response · RC step ${row.epoch}`} rows={row.fiber_results}
        columns={[
          ['Member', (r) => r.member_id], ['Integration point', (r) => r.integration_point_index], ['Fiber', (r) => r.fiber_id],
          ['Material', (r) => r.material_kind], ['Strain', (r) => r.strain], ['Stress (MPa)', (r) => r.stress_MPa],
        ]} />
      <label htmlFor={`${jobId}-rc-material`}>RC material point history</label>{' '}
      <select id={`${jobId}-rc-material`} value={selectedPoint} onChange={(event) => {
        if (event.target.value !== selectedPoint) { setMaterial(null); setSelectedPoint(event.target.value) }
      }} style={{ maxWidth: '100%' }}>
        {row.fiber_results.map((p: RcObject) => <option key={pointKey(p)} value={pointKey(p)}>{p.member_id} · point {p.integration_point_index} · {p.fiber_id} ({p.material_kind})</option>)}
      </select>
      {material ? <>
        <p data-rc-material-count>{materialCount} stored material steps · showing {materialPage * 20 + 1}–{Math.min(materialCount, (materialPage + 1) * 20)}</p>
        <label htmlFor={`${jobId}-rc-material-page`}>Material history steps</label>{' '}
        <select id={`${jobId}-rc-material-page`} value={materialPage} onChange={(event) => {
          const next = Number(event.target.value)
          if (next !== materialPage) { setMaterial(null); setMaterialPage(next) }
        }}>
          {Array.from({ length: Math.ceil(materialCount / 20) }, (_, page) => <option key={page} value={page}>Steps {page * 20 + 1}–{Math.min(materialCount, (page + 1) * 20)}</option>)}
        </select>
        <Table name="material-history" label="Selected material point · stored history" rows={review.materialPage ? material : material.slice(materialPage * 20, (materialPage + 1) * 20)}
        columns={[
          ['Step', (r) => r.epoch], ['Strain', (r) => r.strain], ['Stress (MPa)', (r) => r.stress_MPa],
          ...stateKeys.map((key): Column => [key, (r) => r.material_state[key]]),
        ]} />
      </> : <p role="status">Loading stored material history…</p>}
    </>}
    <div className="wb2-actions">
      {summary.artifactRoles.map((role) => <button type="button" className="wb2-btn" key={role} onClick={() => void download(role)}>
        Download RC {role === 'checkpoint' ? 'saved job checkpoint' : role === 'terminal' ? 'terminal restart' : role}
      </button>)}
    </div>
  </section>
}
