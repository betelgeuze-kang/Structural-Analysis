import type { ReactElement } from 'react'
import type { WorkbenchCaseV2 } from '../model/caseSchema'
import type { ComparisonRow } from './ExportPanel'

interface ComparePanelProps {
  caseV2: WorkbenchCaseV2 | null
  rows: ComparisonRow[]
  onClear: () => void
}

/**
 * Compare set. Lists the benchmark cases the reviewer added for comparison and,
 * for each, what would be required to actually compare numerically. It never
 * synthesizes an accuracy delta: a real comparison needs attached reference
 * results AND a run on a registered runner, neither of which happens here. The
 * panel shows the gap honestly instead of inventing numbers.
 */
export function ComparePanel({ caseV2, rows, onClear }: ComparePanelProps): ReactElement {
  return (
    <section className="wb2-panel" aria-labelledby="wb2-compare-title" data-compare-panel>
      <h2 id="wb2-compare-title" className="wb2-panel__title">Compare</h2>

      {caseV2 ? (
        <p className="wb2-note">
          Current case: <code className="wb2-mono">{caseV2.provenance.sourcePath}</code> @{' '}
          <code className="wb2-mono">{caseV2.provenance.sourceCommitSha.slice(0, 12)}</code>
        </p>
      ) : null}

      {rows.length === 0 ? (
        <p className="wb2-unavailable" data-wb2-unavailable data-compare-empty>
          No comparison rows selected. Add benchmark cases from the Benchmarks section. A numeric accuracy
          comparison is never synthesized — it requires attached reference results and a registered runner.
        </p>
      ) : (
        <>
          <div className="wb2-table-scroll" role="region" aria-label="Comparison set" tabIndex={0}>
            <table className="wb2-table" data-compare-table>
              <thead>
                <tr>
                  <th>Case</th>
                  <th>Truth class</th>
                  <th>Accuracy-comparable</th>
                  <th>Reference results</th>
                  <th>Reference solver</th>
                  <th>Runner</th>
                  <th>Comparison status</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => {
                  const ready = r.referenceResultsAvailable && !!r.runnerId && r.comparable
                  return (
                    <tr key={r.id} data-compare-row={r.id}>
                      <td>{r.title}</td>
                      <td>{r.truthClass}</td>
                      <td>{r.comparable ? 'yes' : 'no'}</td>
                      <td>{r.referenceResultsAvailable ? (r.referenceResultsPath ?? 'available') : 'not attached'}</td>
                      <td>{r.referenceSolver ?? '—'}</td>
                      <td>{r.runnerId ?? 'none registered'}</td>
                      <td data-compare-status={ready ? 'ready' : 'blocked'}>
                        {ready
                          ? 'reference + runner present — comparison can be run offline'
                          : !r.comparable
                            ? 'excluded — not accuracy-comparable'
                            : !r.referenceResultsAvailable
                              ? 'blocked — no reference results attached'
                              : 'blocked — no runner registered'}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
          <div className="wb2-actions">
            <button type="button" className="wb2-mode-btn" data-compare-clear onClick={onClear}>
              Clear comparison ({rows.length})
            </button>
            <span className="wb2-action-hint">
              No delta is computed here. Numbers come only from a real run against attached references.
            </span>
          </div>
        </>
      )}
    </section>
  )
}
