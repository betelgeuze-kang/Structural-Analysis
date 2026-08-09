import type { ReactElement } from 'react'
import type { PublishedFrame3DLoadControlResult } from '../model/frame3dLoadControlResult'
import { StateChip } from './StateChip'

interface Frame3DLoadControlCandidatePanelProps {
  result: PublishedFrame3DLoadControlResult
}

function shortHash(value: string): string {
  return `${value.slice(0, 15)}…${value.slice(-8)}`
}

function metric(value: number): string {
  return Number.isFinite(value) ? value.toExponential(4) : 'UNAVAILABLE'
}

export function Frame3DLoadControlCandidatePanel({
  result,
}: Frame3DLoadControlCandidatePanelProps): ReactElement {
  return (
    <section
      className="wb2-panel"
      aria-labelledby="wb2-frame3d-load-control-title"
      data-frame3d-load-control-candidate="verified"
      data-workbench-execution="false"
      data-public-product-promotion="false"
      data-release-eligible="false"
    >
      <h2 id="wb2-frame3d-load-control-title" className="wb2-panel__title">
        Frame3D load-control candidate
      </h2>
      <div className="wb2-run-head">
        <StateChip state="LIVE" srLabel="Verified bounded candidate" />
        <span className="wb2-run-status-label">verified durable result</span>
      </div>
      <p className="wb2-muted">
        Verified bounded CPU candidate. Convergence and displacement are authoritative within this bounded request.
        Reactions and member recovery are core-replayed solver-derived candidate outputs, not Numerical ResultIR authority.
        External V&amp;V is not attached. No design, code, release, or commercial authority.
      </p>
      <p className="wb2-muted">
        Raw solver steps, checkpoint displacements, and member basic/global force arrays are intentionally omitted.
      </p>
      <dl className="wb2-kv">
        <dt>Adapter</dt><dd className="wb2-mono">{result.adapterId}</dd>
        <dt>Result contract</dt><dd className="wb2-mono">{result.resultContract}</dd>
        <dt>Logical result hash</dt><dd className="wb2-mono">{shortHash(result.resultHash)}</dd>
        <dt>Numerical ResultIR logical hash</dt><dd className="wb2-mono">{shortHash(result.numericalResultIr.resultHash)}</dd>
        <dt>ModelIR binding</dt><dd className="wb2-mono">{shortHash(result.source.modelIrContentHash)}</dd>
        <dt>Load schedule</dt>
        <dd data-frame3d-schedule-complete="true">
          {result.schedule.completedPrefixCount}/{result.schedule.loadFactors.length} complete · final load factor {result.schedule.finalLoadFactor.toFixed(3)}
        </dd>
        <dt>Durable suffix</dt>
        <dd data-frame3d-resume-prefix={result.schedule.resumeCompletedPrefixCount}>
          resume prefix {result.schedule.resumeCompletedPrefixCount} · accepted suffix {result.schedule.acceptedSuffixStepCount}
        </dd>
        <dt>Model breadth</dt><dd>{result.source.nodeIds.length} nodes · {result.source.memberIds.length} members</dd>
        <dt>Numerical ResultIR reaction</dt>
        <dd data-frame3d-numerical-reaction-authority="not_evaluated">not_evaluated</dd>
        <dt>Numerical ResultIR member force</dt>
        <dd data-frame3d-numerical-member-authority="not_evaluated">not_evaluated</dd>
        <dt>Outer reaction recovery</dt>
        <dd data-frame3d-recovery-reaction-authority="bounded_candidate">bounded_candidate</dd>
        <dt>Outer member recovery</dt>
        <dd data-frame3d-recovery-member-authority="bounded_candidate">bounded_candidate</dd>
        <dt>Full-node equilibrium</dt>
        <dd data-frame3d-equilibrium="pass">
          scaled {metric(result.equilibrium.maximumScaledBalanceResidual)} ≤ {metric(result.equilibrium.scaledTolerance)}
        </dd>
        <dt>Force balance</dt>
        <dd>{metric(result.equilibrium.maximumForceBalanceResidualN)} N ≤ {metric(result.equilibrium.forceToleranceN)} N</dd>
        <dt>Moment balance</dt>
        <dd>{metric(result.equilibrium.maximumMomentBalanceResidualNM)} N·m ≤ {metric(result.equilibrium.momentToleranceNM)} N·m</dd>
        <dt>Workbench execution</dt><dd data-frame3d-workbench-execution="false">false</dd>
        <dt>External V&amp;V level</dt><dd data-frame3d-external-vv="0">0</dd>
        <dt>Design authority</dt><dd data-frame3d-design-authority="false">false</dd>
        <dt>Public product promotion</dt><dd data-frame3d-public-promotion="false">false</dd>
        <dt>Release eligible</dt><dd data-frame3d-release-eligible="false">false</dd>
        <dt>Commercial use</dt><dd data-frame3d-commercial-use="false">false</dd>
      </dl>
    </section>
  )
}
