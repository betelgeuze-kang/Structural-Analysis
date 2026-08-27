import type { ReactElement } from 'react'
import type { CaseModel } from '../model/caseSchema'
import { summarizeImportHealth } from '../model/importHealth'

export interface ImportHealthPanelProps {
  model: CaseModel
}

function displayCount(value: number | undefined): string {
  return value == null ? 'UNAVAILABLE' : value.toLocaleString()
}

export function ImportHealthPanel({ model }: ImportHealthPanelProps): ReactElement {
  const summary = summarizeImportHealth(model)
  const stateLabel = summary.status.toUpperCase()

  return (
    <section
      className="wb2-panel wb2-import-health"
      aria-labelledby="wb2-import-health-title"
      data-wb2-import-health
      data-import-health-status={summary.status}
    >
      <div className="wb2-panel__heading">
        <div>
          <p className="wb2-kicker">Producer-supplied import evidence</p>
          <h2 id="wb2-import-health-title" className="wb2-panel__title">Import health</h2>
        </div>
        <span className="wb2-chip" data-state={stateLabel}>{stateLabel}</span>
      </div>

      <p className="wb2-note">
        This panel reports only attached import-health evidence. It does not infer a clean import,
        analysis readiness, numerical authority, design authority, or release readiness.
      </p>

      {summary.status === 'unavailable' ? (
        <p className="wb2-unavailable" data-wb2-import-health-unavailable>
          No import-health evidence is attached. A clean import is not inferred.
        </p>
      ) : (
        <>
          <dl className="wb2-kv">
            <div><dt>Schema</dt><dd>{summary.schemaVersion ?? 'UNAVAILABLE'}</dd></div>
            <div><dt>Source format</dt><dd>{summary.sourceFormat ?? 'UNAVAILABLE'}</dd></div>
            <div><dt>Supported objects</dt><dd>{displayCount(summary.supportedObjectCount)}</dd></div>
            <div><dt>Partial objects</dt><dd>{displayCount(summary.partialObjectCount)}</dd></div>
            <div><dt>Unsupported objects</dt><dd>{displayCount(summary.unsupportedObjectCount)}</dd></div>
            <div><dt>Silent loss</dt><dd>{summary.silentLossStatus.toUpperCase()}</dd></div>
          </dl>

          {summary.issues.length ? (
            <div className="wb2-table-wrap">
              <table className="wb2-table" data-wb2-import-health-table>
                <thead>
                  <tr>
                    <th scope="col">Severity</th>
                    <th scope="col">Code</th>
                    <th scope="col">Source</th>
                    <th scope="col">Entity</th>
                    <th scope="col">Blocking</th>
                    <th scope="col">Diagnostic</th>
                  </tr>
                </thead>
                <tbody>
                  {summary.issues.map((issue, index) => {
                    const source = issue.sourcePath
                      ? `${issue.sourcePath}${issue.sourceLine ? `:${issue.sourceLine}` : ''}`
                      : 'UNAVAILABLE'
                    return (
                      <tr key={`${issue.code}-${index}`} data-import-health-code={issue.code}>
                        <td>{issue.severity}</td>
                        <td>{issue.code}</td>
                        <td>{source}</td>
                        <td>{issue.entityId ?? 'UNAVAILABLE'}</td>
                        <td>{issue.blocking ? 'yes' : 'no'}</td>
                        <td>
                          {issue.message}
                          {issue.remediation ? ` Remediation: ${issue.remediation}` : ''}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <p className="wb2-note">No issue rows were supplied.</p>
          )}
        </>
      )}
    </section>
  )
}
