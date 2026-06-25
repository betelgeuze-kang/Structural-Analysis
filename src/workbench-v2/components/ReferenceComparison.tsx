import type { ReactElement } from 'react'
import type { ReferenceRow } from '../model/caseSchema'

interface ReferenceComparisonProps {
  rows: ReferenceRow[]
  sourceLabel: string
}

function fmt(value: number | null, unit: string | null): string {
  if (value == null) return 'n/a'
  const text = Number.isInteger(value) ? String(value) : value.toFixed(4).replace(/0+$/, '').replace(/\.$/, '')
  return unit && unit !== '-' ? `${text} ${unit}` : text
}

export function ReferenceComparison({ rows, sourceLabel }: ReferenceComparisonProps): ReactElement {
  return (
    <section className="wb2-panel" aria-labelledby="wb2-reference-title">
      <h2 id="wb2-reference-title" className="wb2-panel__title">Reference comparison</h2>
      {rows.length ? (
        <>
          <div className="wb2-table-scroll" role="region" aria-label="Reference comparison table" tabIndex={0}>
            <table className="wb2-table">
              <thead>
                <tr>
                  <th>Quantity</th>
                  <th className="wb2-num">Reference</th>
                  <th className="wb2-num">Engine</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => (
                  <tr key={`${row.quantity ?? 'row'}-${index}`}>
                    <td>{row.quantity ?? '—'}</td>
                    <td className="wb2-num">{fmt(row.reference, row.unit)}</td>
                    <td className="wb2-num">{fmt(row.engine, row.unit)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="wb2-provenance" data-wb2-provenance>Source: {sourceLabel}</p>
        </>
      ) : (
        <p className="wb2-unavailable" data-wb2-unavailable>
          No reference comparison attached for this dataset.
        </p>
      )}
    </section>
  )
}
