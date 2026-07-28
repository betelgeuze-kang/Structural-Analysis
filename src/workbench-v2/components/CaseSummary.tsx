import type { ReactElement } from 'react'
import {
  formatEvidence,
  type WorkbenchCaseV2,
} from '../model/caseSchema'

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
        <dt>Source path</dt><dd><code className="wb2-mono">{formatEvidence(p.sourcePath)}</code></dd>
        <dt>Source checksum</dt><dd><code className="wb2-mono">{formatEvidence(p.sourceSha256, shortSha)}</code></dd>
        <dt>Source commit</dt><dd><code className="wb2-mono">{formatEvidence(p.sourceCommitSha, (value) => value.slice(0, 12))}</code></dd>
        <dt>Engine</dt><dd>{formatEvidence(p.engineVersion)}</dd>
        <dt>Generated at</dt><dd>{formatEvidence(p.generatedAt)}</dd>
      </dl>

      <h3 className="wb2-subhead">Model health</h3>
      <dl className="wb2-kv">
        <dt>Unit system</dt><dd>{m.unitSystem}</dd>
        <dt>Coordinate system</dt><dd>{m.coordinateSystem}</dd>
        <dt>Nodes</dt><dd>{formatEvidence(m.nodeCount, (value) => value.toLocaleString())}</dd>
        <dt>Elements</dt><dd>{formatEvidence(m.elementCount, (value) => value.toLocaleString())}</dd>
        <dt>DOF</dt><dd>{formatEvidence(m.dofCount, (value) => value.toLocaleString())}</dd>
      </dl>
    </section>
  )
}
