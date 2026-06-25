import type { ReactElement } from 'react'
import type { WorkbenchCaseV2 } from '../model/caseSchema'

function shortSha(s: string): string {
  const v = s.startsWith('sha256:') ? s.slice(7) : s
  return v.length > 12 ? `${v.slice(0, 12)}…` : v
}

export function CaseSummary({ caseV2 }: { caseV2: WorkbenchCaseV2 }): ReactElement {
  const p = caseV2.provenance
  const m = caseV2.model
  return (
    <section className="wb2-panel" aria-labelledby="wb2-summary-title">
      <h2 id="wb2-summary-title" className="wb2-panel__title">Case &amp; provenance</h2>

      <dl className="wb2-kv">
        <dt>Source path</dt><dd><code className="wb2-mono">{p.sourcePath}</code></dd>
        <dt>Source checksum</dt><dd><code className="wb2-mono" title={p.sourceSha256}>{shortSha(p.sourceSha256)}</code></dd>
        <dt>Source commit</dt><dd><code className="wb2-mono" title={p.sourceCommitSha}>{p.sourceCommitSha.slice(0, 12)}</code></dd>
        <dt>Engine</dt><dd>{p.engineVersion}</dd>
        <dt>Generated at</dt><dd>{p.generatedAt}</dd>
      </dl>

      <h3 className="wb2-subhead">Model health</h3>
      <dl className="wb2-kv">
        <dt>Unit system</dt><dd>{m.unitSystem}</dd>
        <dt>Coordinate system</dt><dd>{m.coordinateSystem}</dd>
        <dt>Nodes</dt><dd>{m.nodeCount.toLocaleString()}</dd>
        <dt>Elements</dt><dd>{m.elementCount.toLocaleString()}</dd>
        <dt>DOF</dt><dd>{m.dofCount.toLocaleString()}</dd>
      </dl>
    </section>
  )
}
