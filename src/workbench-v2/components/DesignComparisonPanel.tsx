import type { ReactElement } from 'react'
import type { DesignComparisonLoadResult } from '../model/designComparisonProvider'
import type { DesignComparisonRow } from '../model/designComparisonSchema'
import { EngineeringValueText } from './EngineeringValueText'

const number = (value: number | null | undefined): ReactElement => <EngineeringValueText value={typeof value === 'number' ? { status: 'available', value } : { status: 'unavailable' }} />
const sections = (row: DesignComparisonRow): string => (row.canonical_model.sections as Array<Record<string, unknown>>)
  .map((section) => `${section.id}: ${section.width_m} × ${section.depth_m} m; bars ${section.top_bar_count}+${section.bottom_bar_count} × ${section.bar_area_m2} m²`).join('; ')

export function DesignComparisonPanel({ load }: { load: DesignComparisonLoadResult }): ReactElement {
  if (load.status !== 'verified' || !load.bundle) {
    return <section className="wb2-panel" data-design-comparison={load.status} aria-labelledby="wb2-design-comparison-title">
      <h2 id="wb2-design-comparison-title" className="wb2-panel__title">Physical design comparison</h2>
      <p className="wb2-unavailable" data-wb2-unavailable>{load.status === 'loading' ? 'Loading physical design comparison…' : `UNAVAILABLE — ${load.errors[0] ?? 'No physical design comparison bundle is configured.'}`}</p>
    </section>
  }
  const { report, manifest } = load.bundle
  const price = report.price_basis
  return <section className="wb2-panel" data-design-comparison="verified" aria-labelledby="wb2-design-comparison-title">
    <h2 id="wb2-design-comparison-title" className="wb2-panel__title">Physical design comparison</h2>
    <p className="wb2-note">Source <code className="wb2-mono">{manifest.source_revision.slice(0, 12)}</code> · report <code className="wb2-mono">{report.report_hash}</code></p>
    <p className="wb2-note">{price ? `Declared material prices: ${price.currency} · ${price.as_of} · ${price.source}` : 'Material prices unavailable.'}</p>
    {price ? <p className="wb2-note">Price table <code className="wb2-mono">{price.price_table_hash}</code></p> : null}
    <div className="wb2-table-scroll" role="region" aria-label="Physical alternatives" tabIndex={0}>
      <table className="wb2-table" data-design-comparison-table>
        <thead><tr><th>Candidate / members</th><th>Concrete (m³)</th><th>Longitudinal rebar (kg)</th><th>Material estimate{price ? ` (${price.currency})` : ''}</th><th>Estimate reduction</th><th>Terminal translation (m)</th><th>Terminal fiber strain</th><th>Reference / limits</th></tr></thead>
        <tbody>{report.rows.map((row) => <tr key={row.candidate_id} data-design-candidate={row.candidate_id} data-design-selected={report.selection.candidate_id === row.candidate_id}>
          <td>{row.candidate_id}{report.selection.candidate_id === row.candidate_id ? ' · selected within declared scope' : ''}<br /><span className="wb2-mono">{row.quantities?.members.map((member) => `${member.member_id} (${member.section_id})`).join(', ') ?? 'UNAVAILABLE'}</span><br />{sections(row)}<br /><code className="wb2-mono">{row.model_checksum}</code></td>
          <td>{number(row.quantities?.totals.gross_concrete_volume_m3)}</td>
          <td>{number(row.quantities?.totals.longitudinal_rebar_mass_kg)}</td>
          <td>{number(row.material_estimate?.total)}</td>
          <td>{number(row.difference_from_baseline?.scoped_material_estimate_reduction)}</td>
          <td>{number(row.performance?.terminal_maximum_translation_m)}</td>
          <td>{number(row.performance?.terminal_maximum_absolute_fiber_strain)}</td>
          <td>{row.full_reference_verification_pass ? 'full reference verified' : row.status} / {row.terminal_limit_status}</td>
        </tr>)}</tbody>
      </table>
    </div>
    <p className="wb2-muted">Gross concrete and authored straight longitudinal bars only. Transverse reinforcement, laps, anchorage, waste, formwork, labor, fabrication, transport and tax are excluded. Terminal translation and fiber-strain screens are caller-declared. These estimates are not verified quotes, confirmed currency savings or engineering approval.</p>
  </section>
}
