import { useEffect, useRef, useState, type ReactElement } from 'react'
import { loadRcControlDesign, type RcDesignSession } from '../model/rcControlDesignProvider'
import type { JobAuthorizationProvider } from '../model/jobTransport'
import type { RcObject } from '../model/rcJobSchema'
const shown = (value: unknown) => typeof value === 'number' ? String(value) : 'UNAVAILABLE'
const metrics = [
  ['maximum_translation_m', 'Path translation (m)'], ['maximum_absolute_fiber_strain', 'Path fiber strain'],
  ['maximum_steel_accumulated_plastic_strain', 'Steel accumulated plastic strain'], ['maximum_concrete_tensile_damage', 'Concrete tensile damage'],
  ['maximum_concrete_compressive_damage', 'Concrete compressive damage'], ['terminal_maximum_translation_m', 'Terminal translation (m)'],
  ['terminal_maximum_absolute_fiber_strain', 'Terminal fiber strain'],
]
export function RcControlDesignPanel({ url, authorize }: { url: string; authorize?: JobAuthorizationProvider }): ReactElement {
  const [session, setSession] = useState<RcDesignSession | null>(null)
  const [state, setState] = useState('loading')
  const [selected, setSelected] = useState<string | null>(null)
  const urls = useRef(new Set<string>())
  useEffect(() => {
    const controller = new AbortController()
    let loaded: RcDesignSession | null = null
    setSession(null); setState('loading'); setSelected(null)
    loadRcControlDesign(url, controller.signal, authorize).then(value => {
      loaded = value
      if (controller.signal.aborted) { value.dispose(); return }
      value.onFailure(() => { setSession(null); setState('invalid'); setSelected(null) })
      setSession(value); setState('verified'); setSelected(value.report.selected_candidate_id)
    }).catch(() => { if (!controller.signal.aborted) setState('invalid') })
    return () => { controller.abort(); loaded?.dispose(); for (const value of urls.current) URL.revokeObjectURL(value); urls.current.clear() }
  }, [url, authorize])
  async function download(candidate: string, role: string) {
    try {
      const blob = await session!.download(candidate, role), href = URL.createObjectURL(blob), anchor = document.createElement('a')
      urls.current.add(href); anchor.href = href; anchor.download = `${candidate}-rc-design-${role}.json`
      document.body.append(anchor); anchor.click(); anchor.remove()
      window.setTimeout(() => { URL.revokeObjectURL(href); urls.current.delete(href) }, 0)
    } catch { setSession(null); setState('invalid'); setSelected(null) }
  }
  if (!session) return <section className="wb2-panel" data-rc-design={state}><h2>Experimental RC design comparison</h2><p role="status">{state === 'loading' ? 'Checking original candidate artifacts…' : 'UNAVAILABLE — RC comparison artifacts could not be verified.'}</p></section>
  const { report, models } = session
  const current = report.rows.find((r: RcObject) => r.candidate_id === selected)
  return <section className="wb2-panel wb2-rc-design" data-rc-design="verified" style={{ minWidth: 0, maxWidth: '100%', overflowWrap: 'anywhere' }}>
    <h2 className="wb2-panel__title">Experimental RC design comparison</h2>
    <p data-rc-design-authority>Original artifacts and stored full-path verification bindings checked. The browser does not rerun the solver. Caller limits, quantities and prices do not establish independent physical validation, code compliance, a verified quote or design approval.</p>
    <p>{report.control_request.targets_m.length} authored targets per design · {report.verified_count}/{report.candidate_denominator} designs have complete stored verification · execution {report.status}</p>
    {report.control_request.constant_nodal_loads ? <p data-rc-design-constants>Constant nodal loads (node, FX kN, FY kN, MZ kN·m): {report.control_request.constant_nodal_loads.map((r: RcObject) => `${r.node_id}, ${r.FX_kN}, ${r.FY_kN}, ${r.MZ_kNm}`).join('; ')}. Every analysis and fresh verification includes its own preload. Path screens include that accepted preload.</p> : null}
    <p>Source declaration <code>{report.source_revision}</code> · report <code data-rc-design-hash>{report.report_hash}</code></p>
    <p>{report.prices ? `Declared prices: ${report.prices.currency} · ${report.prices.as_of} · ${report.prices.source}` : 'Prices unavailable; no cost-based candidate can be selected.'}</p>
    <p data-rc-design-recommendation>Lowest declared estimate among verified candidates passing all screens: {report.selected_candidate_id ?? 'UNAVAILABLE'}. Current selection: {selected ?? 'none'}.</p>
    <p>Whole-study elapsed {report.total_wall_ns / 1e9} s · process CPU {report.total_process_cpu_ns / 1e9} s. Includes preparation, original analysis, fresh verification and artifact I/O; excludes final report write. Unknown work remains unknown.</p>
    <div className="wb2-table-scroll" role="region" aria-label="RC design alternatives" tabIndex={0}>
      <table className="wb2-table"><thead><tr><th>Candidate</th><th>Concrete (m³)</th><th>Longitudinal rebar (kg)</th><th>Scoped estimate</th><th>Estimate reduction</th><th>Verification / selection</th></tr></thead>
        <tbody>{report.rows.map((row: RcObject) => <tr key={row.candidate_id} data-rc-design-candidate={row.candidate_id}>
          <td>{row.candidate_id}<br /><code>{row.quantities?.model_checksum ?? 'UNAVAILABLE'}</code></td>
          <td style={{ whiteSpace: 'nowrap' }}>{shown(row.quantities?.totals.gross_concrete_volume_m3)}<br />Δ {shown(row.quantity_delta?.gross_concrete_volume_m3)}</td>
          <td style={{ whiteSpace: 'nowrap' }}>{shown(row.quantities?.totals.longitudinal_rebar_mass_kg)}<br />Δ {shown(row.quantity_delta?.longitudinal_rebar_mass_kg)}</td>
          <td style={{ whiteSpace: 'nowrap' }}>{shown(row.material_estimate?.total)} {report.prices?.currency}</td>
          <td style={{ whiteSpace: 'nowrap' }}>{shown(row.scoped_estimate_reduction)}</td>
          <td>{row.status}<br /><button type="button" className="wb2-btn" disabled={!row.selection_eligible || !report.prices} aria-pressed={selected === row.candidate_id} onClick={() => setSelected(row.candidate_id)}>Select {row.candidate_id}</button></td>
        </tr>)}</tbody></table>
    </div>
    {report.rows.map((row: RcObject) => <details key={row.candidate_id} data-rc-design-details={row.candidate_id} open={selected === row.candidate_id}>
      <summary>{row.candidate_id} — screens, execution cost and original artifacts</summary>
      <p>Result identity <code>{row.artifacts.result?.sha256 ?? 'UNAVAILABLE'}</code>. {row.failure ? `Failure phase: ${row.failure.phase}; kind: ${row.failure.kind}.` : ''}</p>
      <div className="wb2-table-scroll" role="region" aria-label={`${row.candidate_id} RC screens`} tabIndex={0}><table className="wb2-table"><thead><tr><th>Metric</th><th>Maximum</th><th>Change from baseline</th><th>Caller limit</th><th>Status</th></tr></thead><tbody>
        {metrics.map(([key, label]) => <tr key={key} data-rc-design-metric={key}><td>{label}</td><td style={{ whiteSpace: 'nowrap' }}>{shown(row.performance?.[key])}</td><td style={{ whiteSpace: 'nowrap' }} data-rc-design-performance-delta={key}>{shown(typeof row.performance?.[key] === 'number' && typeof report.rows[0].performance?.[key] === 'number' ? row.performance[key] - report.rows[0].performance[key] : null)}</td><td>{shown(row.screens?.[key]?.limit)}</td><td>{row.screens?.[key]?.status ?? 'not requested or unavailable'}</td></tr>)}
      </tbody></table></div>
      <p>Terminal signed load factor: {shown(row.performance?.terminal_load_factor)}. Maxima cover {report.control_request.constant_nodal_loads ? 'the accepted preload and targets' : 'accepted targets'}; they do not cover extrema between targets.</p>
      <div className="wb2-table-scroll" role="region" aria-label={`${row.candidate_id} RC execution costs`} tabIndex={0}><table className="wb2-table"><thead><tr><th>Entry</th><th>State</th><th>Core calls</th><th>Newton / linear</th><th>Unknown work</th><th>Elapsed / CPU (s)</th></tr></thead><tbody>
        {row.invocations.map((i: RcObject) => <tr key={i.phase}><td>{i.phase}</td><td>{i.status}</td><td>{shown(i.work?.attempted_step_count)}</td><td>{shown(i.work?.known_newton_iteration_count)} / {shown(i.work?.known_linear_solve_count)}</td><td>{i.unknown_execution_work ? 'UNKNOWN' : 'none reported'}</td><td>{i.wall_ns / 1e9} / {i.process_cpu_ns / 1e9}</td></tr>)}
      </tbody></table></div>
      <div className="wb2-rc-design-downloads">{Object.keys(row.artifacts).map(role => <button type="button" className="wb2-btn" key={role} onClick={() => { void download(row.candidate_id, role) }}>Download {row.candidate_id} {role.replace(/_/g, ' ')}</button>)}</div>
    </details>)}
    {current && models[current.candidate_id] ? <div data-rc-design-selected={selected}>
      <h3>Selected candidate: {selected}</h3>
      <p>Model <code>{current.quantities.model_checksum}</code> · result <code>{current.artifacts.result.sha256}</code> · price table <code>{report.price_table_hash}</code></p>
      <p>{models[current.candidate_id].sections.map((s: RcObject) => `${s.id}: width ${s.width_m} m, depth ${s.depth_m} m, cover ${s.cover_m} m; ${s.top_bar_count} top and ${s.bottom_bar_count} bottom bars at ${s.bar_area_m2} m²`).join('; ')}</p>
      <p>Selection refers to these original artifacts and the unchanged authored control path. It does not launch analysis or confer design approval.</p>
    </div> : null}
    <button type="button" className="wb2-btn" onClick={() => { void download('study', 'comparison') }}>Download original RC comparison</button>
    <p>Quantity changes are candidate minus baseline; estimate reduction is baseline minus candidate. Gross concrete and authored straight longitudinal bars only. Transverse reinforcement, laps, anchorage, waste, formwork, labor, fabrication, transport and tax are excluded. Confirmed savings remain unavailable.</p>
  </section>
}
