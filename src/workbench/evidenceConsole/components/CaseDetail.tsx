import type { ReactElement, ReactNode } from 'react'
import type { ComparisonRow, EvidenceCase, EvidenceDataset, ProviderMode, ReproduceBundle, ResidualRow } from '../types'
import { formatNumber, hasValue, normalizeDecision } from '../format'
import { DecisionPill } from './DecisionPill'
import { Unavailable, UnavailablePill } from './Unavailable'

function Section({ title, children }: { title: string; children: ReactNode }): ReactElement {
  return (
    <div className="ec-section">
      <h3>{title}</h3>
      {children}
    </div>
  )
}

function KV({ label, value }: { label: string; value: string | null }): ReactElement {
  return (
    <>
      <dt>{label}</dt>
      <dd>{hasValue(value) ? value : <UnavailablePill />}</dd>
    </>
  )
}

function numText(value: number | null, unit: string | null): ReactNode {
  const formatted = formatNumber(value)
  if (formatted == null) return <UnavailablePill label="n/a" />
  return hasValue(unit) && unit !== '-' ? `${formatted} ${unit}` : formatted
}

function ComparisonTable({ rows }: { rows: ComparisonRow[] }): ReactElement {
  return (
    <div className="ec-table-scroll" role="region" aria-label="Reference vs engine comparison table" tabIndex={0}>
      <table className="ec-table">
        <thead>
          <tr>
            <th>Quantity</th>
            <th className="ec-num">Reference</th>
            <th className="ec-num">Engine</th>
            <th className="ec-num">Δ (rel)</th>
            <th>Within tol</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => {
            const bothNumeric =
              typeof row.reference === 'number' && typeof row.engine === 'number' && row.reference !== 0
            const relDelta = bothNumeric ? Math.abs((row.engine as number) - (row.reference as number)) / Math.abs(row.reference as number) : null
            const within = relDelta != null && row.tolerance_rel != null ? relDelta <= row.tolerance_rel : null
            return (
              <tr key={`${row.quantity ?? 'row'}-${i}`}>
                <td>{hasValue(row.quantity) ? row.quantity : '—'}</td>
                <td className="ec-num">{numText(row.reference, row.unit)}</td>
                <td className="ec-num">{numText(row.engine, row.unit)}</td>
                <td className="ec-num">{relDelta == null ? <UnavailablePill label="n/a" /> : `${(relDelta * 100).toFixed(2)}%`}</td>
                <td>
                  {within == null ? (
                    <UnavailablePill label="n/a" />
                  ) : (
                    <span className={within ? 'ec-flag-ok' : 'ec-flag-out'}>{within ? 'within' : 'exceeded'}</span>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

function ResidualTable({ rows }: { rows: ResidualRow[] }): ReactElement {
  return (
    <div className="ec-table-scroll" role="region" aria-label="Residual audit table" tabIndex={0}>
      <table className="ec-table">
        <thead>
          <tr>
            <th>Metric</th>
            <th className="ec-num">Value</th>
            <th className="ec-num">Tolerance</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={`${row.metric ?? 'metric'}-${i}`}>
              <td>{hasValue(row.metric) ? row.metric : '—'}</td>
              <td className="ec-num">{numText(row.value, row.unit)}</td>
              <td className="ec-num">{numText(row.tolerance, row.unit)}</td>
              <td>
                {row.within_tolerance == null ? (
                  <UnavailablePill label="n/a" />
                ) : (
                  <span className={row.within_tolerance ? 'ec-flag-ok' : 'ec-flag-out'}>
                    {row.within_tolerance ? 'within' : 'exceeded'}
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

interface CaseDetailProps {
  caseItem: EvidenceCase
  dataset: EvidenceDataset
  providerMode: ProviderMode
}

export function CaseDetail({ caseItem, dataset, providerMode }: CaseDetailProps): ReactElement {
  const subParts = [caseItem.structure_family, caseItem.load_combination].filter((v): v is string => hasValue(v))
  const decisionKey = normalizeDecision(caseItem.reviewer_decision)

  function exportBundle(): void {
    const bundle: ReproduceBundle = {
      schema_version: 'evidence-console-reproduce-bundle.v1',
      dataset_kind: dataset.dataset_kind ?? 'demo_fixture',
      is_demo: dataset.is_demo === true,
      claim_boundary: dataset.claim_boundary,
      engine_version: dataset.engine_version,
      provider_mode: providerMode,
      exported_at: new Date().toISOString(),
      case: caseItem,
    }
    const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = `reproduce_bundle_${caseItem.id}.json`
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  }

  return (
    <section id="ec-react-detail" className="ec-panel" aria-label="Case evidence detail" tabIndex={-1}>
      <div className="ec-detail-head">
        <div>
          <h2>{hasValue(caseItem.name) ? caseItem.name : caseItem.id}</h2>
          <p className="ec-detail-sub">{subParts.length ? subParts.join(' · ') : 'No metadata'}</p>
        </div>
        <DecisionPill decision={caseItem.reviewer_decision} />
      </div>

      <Section title="Source / provenance inspector">
        {caseItem.provenance ? (
          <dl className="ec-kv">
            <KV label="Model file" value={caseItem.provenance.model_file} />
            <KV label="Model SHA-256" value={caseItem.provenance.model_sha256} />
            <KV label="Source tool" value={caseItem.provenance.source_tool} />
            <KV label="Engine version" value={caseItem.provenance.engine_version} />
            <KV label="Analysis kind" value={caseItem.provenance.analysis_kind} />
            <KV label="Generated at" value={caseItem.provenance.generated_at} />
          </dl>
        ) : (
          <Unavailable message="Source provenance not attached for this case." />
        )}
      </Section>

      <Section title="Reference vs engine comparison">
        {caseItem.reference_vs_engine.length ? (
          <ComparisonTable rows={caseItem.reference_vs_engine} />
        ) : (
          <Unavailable message="No reference-vs-engine comparison attached." />
        )}
      </Section>

      <Section title="Residual audit">
        {caseItem.residual_audit.length ? (
          <ResidualTable rows={caseItem.residual_audit} />
        ) : (
          <Unavailable message="No residual audit attached for this case." />
        )}
      </Section>

      <Section title="Worst member / story">
        {caseItem.worst ? (
          <dl className="ec-kv">
            <KV label="Member" value={caseItem.worst.member_id} />
            <KV label="Story" value={caseItem.worst.story} />
            <KV label="Governing check" value={caseItem.worst.governing_check} />
            <KV label="D/C ratio" value={formatNumber(caseItem.worst.dcr)} />
          </dl>
        ) : (
          <Unavailable message="Governing member/story not attached for this case." />
        )}
      </Section>

      <Section title="Reviewer decision (PASS / REVIEW / FAIL)">
        <DecisionPill decision={caseItem.reviewer_decision} />
        {hasValue(caseItem.reviewer_decision_note) ? (
          <p className="ec-reviewer-note">{caseItem.reviewer_decision_note}</p>
        ) : null}
        {!decisionKey ? (
          <p className="ec-reviewer-note">
            No verdict is recorded for this case. A verdict is shown only when present in the evidence; it is never
            defaulted to PASS.
          </p>
        ) : null}
      </Section>

      <Section title="Reproduce bundle export">
        <div className="ec-actions">
          <button type="button" className="ec-btn" data-ec-export={caseItem.id} onClick={exportBundle}>
            Export reproduce bundle (JSON)
          </button>
          <span className="ec-action-hint">
            {providerMode === 'mock' ? 'DEMO bundle' : 'Live bundle'} — inputs only, not a validated reproduction artifact.
          </span>
        </div>
      </Section>
    </section>
  )
}
