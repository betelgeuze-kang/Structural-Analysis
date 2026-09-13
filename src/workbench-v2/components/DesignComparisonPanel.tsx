import type { ReactElement } from 'react'
import type { DesignComparisonLoadResult } from '../model/designComparisonProvider'
import type { DesignComparisonRow } from '../model/designComparisonSchema'
import { MATERIAL_HISTORY_LIMITS, MATERIAL_HISTORY_METRICS } from '../model/designComparisonSchema'
import { EngineeringValueText } from './EngineeringValueText'

const number = (value: number | null | undefined): ReactElement => <EngineeringValueText value={typeof value === 'number' ? { status: 'available', value } : { status: 'unavailable' }} />
const change = (metric: string, value: number | null | undefined): ReactElement => <div className="wb2-muted" data-design-delta={metric}>Change: {number(value)}</div>
const sections = (row: DesignComparisonRow): string => (row.canonical_model.sections as Array<Record<string, unknown>>)
  .map((section) => `${section.id}: ${section.width_m} × ${section.depth_m} m; bars ${section.top_bar_count}+${section.bottom_bar_count} × ${section.bar_area_m2} m²`).join('; ')

export function DesignComparisonPanel({ load, title = 'Physical design comparison', titleId = 'wb2-design-comparison-title' }: { load: DesignComparisonLoadResult; title?: string; titleId?: string }): ReactElement {
  if (load.status !== 'verified' || !load.bundle) {
    return <section className="wb2-panel" data-design-comparison={load.status} aria-labelledby={titleId}>
      <h2 id={titleId} className="wb2-panel__title">{title}</h2>
      <p className="wb2-unavailable" data-wb2-unavailable>{load.status === 'loading' ? 'Loading physical design comparison…' : `UNAVAILABLE — ${load.errors[0] ?? 'No physical design comparison bundle is configured.'}`}</p>
    </section>
  }
  const { report, manifest } = load.bundle
  const price = report.price_basis
  const materialRequested = report.schema_version === 'public-rc-fiber-design-comparison.v3'
  const historyRequested = report.schema_version === 'public-rc-fiber-design-comparison.v2' || materialRequested
  const materialLimits = materialRequested ? report.identity.material_history_limits as Record<string, number> : null
  const materialLabels = ['Steel accumulated plastic strain', 'Concrete tensile damage', 'Concrete compressive damage']
  return <section className="wb2-panel" data-design-comparison="verified" aria-labelledby={titleId}>
    <h2 id={titleId} className="wb2-panel__title">{title}</h2>
    <p className="wb2-note">Source <code className="wb2-mono">{manifest.source_revision.slice(0, 12)}</code> · report <code className="wb2-mono">{report.report_hash}</code></p>
    <p className="wb2-note">{price ? `Declared material prices: ${price.currency} · ${price.as_of} · ${price.source}` : 'Material prices unavailable.'}</p>
    {price ? <p className="wb2-note">Price table <code className="wb2-mono">{price.price_table_hash}</code></p> : null}
    <p className="wb2-note">Quantity and response changes are candidate minus baseline, in the column units. Estimate reduction is baseline minus candidate. A response change alone does not establish an improvement.</p>
    {historyRequested ? <p className="wb2-note" data-design-history-scope>History limits cover every positive committed load step. They do not verify extrema between steps or cyclic and dynamic histories. Selection requires terminal and history limits to pass.</p> : null}
    {materialRequested ? <p className="wb2-note" data-design-material-history-scope style={{ overflowWrap: 'anywhere' }}>Material memory maxima cover every accepted epoch and are compared with the caller’s explicit limits. Retained plastic memory is not a current yielding event. A failed or unavailable material screen prevents selection within this scope while verified terminal quantities remain visible. These screens do not establish design-code compliance or independent physical validation.</p> : null}
    <div className="wb2-table-scroll" role="region" aria-label="Physical alternatives" tabIndex={0}>
      <table className="wb2-table" data-design-comparison-table>
        <thead><tr><th scope="col">Candidate / members</th><th scope="col">Concrete (m³)</th><th scope="col">Longitudinal rebar (kg)</th><th scope="col">Material estimate{price ? ` (${price.currency})` : ''}</th><th scope="col">Estimate reduction</th><th scope="col">Terminal translation (m)</th><th scope="col">Terminal fiber strain</th>{historyRequested ? <><th scope="col">Committed history translation (m)</th><th scope="col">Committed history fiber strain</th></> : null}{materialRequested ? materialLabels.map(label => <th scope="col" key={label} style={{ whiteSpace: 'normal', minWidth: '10rem' }}>{label}<br />Accepted-epoch maximum</th>) : null}<th scope="col">Reference / limits</th></tr></thead>
        <tbody>{report.rows.map((row) => <tr key={row.candidate_id} data-design-candidate={row.candidate_id} data-design-selected={report.selection.candidate_id === row.candidate_id}>
          <td>{row.candidate_id}{report.selection.candidate_id === row.candidate_id ? ' · selected within declared scope' : ''}<br /><span className="wb2-mono">{row.quantities?.members.map((member) => `${member.member_id} (${member.section_id})`).join(', ') ?? 'UNAVAILABLE'}</span><br />{sections(row)}<br /><code className="wb2-mono">{row.model_checksum}</code></td>
          <td>{number(row.quantities?.totals.gross_concrete_volume_m3)}{change('gross_concrete_volume_m3', row.difference_from_baseline?.quantity_delta.gross_concrete_volume_m3)}</td>
          <td>{number(row.quantities?.totals.longitudinal_rebar_mass_kg)}{change('longitudinal_rebar_mass_kg', row.difference_from_baseline?.quantity_delta.longitudinal_rebar_mass_kg)}</td>
          <td>{number(row.material_estimate?.total)}</td>
          <td>{number(row.difference_from_baseline?.scoped_material_estimate_reduction)}</td>
          <td>{number(row.performance?.terminal_maximum_translation_m)}{change('terminal_maximum_translation_m', row.difference_from_baseline?.terminal_performance_delta.terminal_maximum_translation_m)}</td>
          <td>{number(row.performance?.terminal_maximum_absolute_fiber_strain)}{change('terminal_maximum_absolute_fiber_strain', row.difference_from_baseline?.terminal_performance_delta.terminal_maximum_absolute_fiber_strain)}</td>
          {historyRequested ? <><td data-design-history-translation>{number(row.full_history_verification_pass ? row.performance?.history_maximum_translation_m : undefined)}</td><td data-design-history-strain>{number(row.full_history_verification_pass ? row.performance?.history_maximum_absolute_fiber_strain : undefined)}</td></> : null}
          {materialRequested ? MATERIAL_HISTORY_METRICS.map((key, index) => <td key={key} data-design-material-metric={key} style={{ whiteSpace: 'normal' }}>{number(row.full_material_history_verification_pass ? row.performance?.[key] : undefined)}<div className="wb2-muted" data-design-material-limit={MATERIAL_HISTORY_LIMITS[index]}>Caller limit ≤ {number(materialLimits?.[MATERIAL_HISTORY_LIMITS[index]])}</div></td>) : null}
          <td>{row.full_reference_verification_pass ? 'full reference verified' : row.status} / terminal {row.terminal_limit_status}{historyRequested ? <div data-design-history-status>{row.full_history_verification_pass ? 'committed history verified' : 'committed history UNAVAILABLE'} / {row.history_limit_status}</div> : null}{materialRequested ? <div data-design-material-history-status style={{ overflowWrap: 'anywhere', whiteSpace: 'normal' }}>{row.full_material_history_verification_pass ? 'material memory verified' : 'material memory UNAVAILABLE'} / {row.material_history_limit_status}</div> : null}</td>
        </tr>)}</tbody>
      </table>
    </div>
    <p className="wb2-muted">Gross concrete and authored straight longitudinal bars only. Transverse reinforcement, laps, anchorage, waste, formwork, labor, fabrication, transport and tax are excluded. Terminal translation and fiber-strain screens are caller-declared. These estimates are not verified quotes, confirmed currency savings or engineering approval.</p>
  </section>
}
