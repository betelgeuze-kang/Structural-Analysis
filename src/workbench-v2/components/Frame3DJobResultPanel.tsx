import { useMemo, useState, type ReactElement } from 'react'
import type { Frame3DJobReview } from '../model/frame3dJobSchema'
import type { Frame3DJobArtifacts } from '../model/jobProvider'
import { BooleanEvidenceValueText, EngineeringValueText } from './EngineeringValueText'

interface Frame3DJobResultPanelProps {
  jobId: string
  review: Frame3DJobReview
  artifacts: Frame3DJobArtifacts
}

function number(value: unknown, integer = false): ReactElement {
  return <EngineeringValueText value={typeof value === 'number' && Number.isFinite(value)
    ? { status: 'available', value } : { status: 'unavailable' }} integer={integer} />
}

function flag(value: unknown): ReactElement {
  return <BooleanEvidenceValueText value={typeof value === 'boolean'
    ? { status: 'available', value } : { status: 'unavailable' }} />
}

function downloadBytes(bytes: Uint8Array, filename: string): void {
  const url = URL.createObjectURL(new Blob([bytes.slice()], { type: 'application/json' }))
  const anchor = document.createElement('a')
  try {
    anchor.href = url
    anchor.download = filename
    document.body.append(anchor)
    anchor.click()
  } finally {
    anchor.remove()
    // Let the browser consume the click before releasing the temporary URL.
    window.setTimeout(() => URL.revokeObjectURL(url), 0)
  }
}

/** Review only: all physical rows and export bytes arrive through the verified provider. */
export function Frame3DJobResultPanel({ jobId, review, artifacts }: Frame3DJobResultPanelProps): ReactElement {
  const [selectedIndex, setSelectedIndex] = useState(review.completedTargetCount - 1)
  const snapshots = useMemo(() => ({
    resultBytes: artifacts.resultBytes.slice(),
    evidenceBytes: artifacts.evidenceBytes.slice(),
    checkpointBytes: artifacts.checkpointBytes.slice(),
  }), [artifacts])
  const receipt = review.payload.receipts[Math.min(selectedIndex, review.completedTargetCount - 1)]
  const result = receipt.api_result
  const authority = result.authority
  const safeJobId = /^job_[0-9a-f]{32}$/.test(jobId) ? jobId : 'bounded-frame3d-job'
  const selectId = `${safeJobId}-authored-target`

  return <section className="wb2-frame3d-job" data-frame3d-job-review="verified" aria-label="Bounded 3D candidate result">
    <div className="wb2-run-head">
      <h3 className="wb2-panel__title">Bounded 3D candidate result</h3>
      <span className="wb2-frame3d-job__badge">Bounded 3D candidate</span>
    </div>
    <p className="wb2-note">Read-only review of verified candidate API artifacts. Job publication status does not establish solver convergence or engineering approval.</p>
    <dl className="wb2-kv">
      <dt>Authored progress</dt><dd data-frame3d-progress>{review.completedTargetCount} of {review.totalTargetCount} targets completed</dd>
      <dt>Control</dt><dd>{review.controlNodeId} · {review.controlDof} ({review.controlUnit})</dd>
      <dt>Source revision</dt><dd className="wb2-mono" data-frame3d-source>{review.sourceRevision}</dd>
      <dt>Source attestation</dt><dd>Caller declaration; not independently attested</dd>
      <dt>Request hash</dt><dd className="wb2-mono">{review.requestHash}</dd>
      <dt>Result hash</dt><dd className="wb2-mono">{review.resultHash}</dd>
      <dt>Terminal checkpoint SHA-256</dt><dd className="wb2-mono">{review.terminalCheckpointSha256}</dd>
      <dt>Reserved attempts</dt><dd data-frame3d-reserved>{number(review.reservedAttempts, true)}</dd>
      <dt>Confirmed attempts in retained receipts</dt><dd data-frame3d-confirmed>{number(review.confirmedAttempts, true)}</dd>
      <dt>Reservation gap</dt><dd data-frame3d-reservation-gap>{number(review.abandonedReservations, true)} reservations without retained confirmation</dd>
    </dl>
    <p className="wb2-note">The reservation gap can include abandoned work or a crash before a solver call. It is not a count of completed analyses.</p>

    <div className="wb2-frame3d-job__targets">
      <h4>Authored target path ({review.controlUnit})</h4>
      <ol aria-label="Authored target path">
        {review.targets.map((target, index) => <li key={index} data-frame3d-target={index + 1}>
          <span>Target {index + 1}: </span>{number(target)} <span>{review.controlUnit}</span>
        </li>)}
      </ol>
    </div>
    <label className="wb2-frame3d-job__selector" htmlFor={selectId}>
      <span>Authored target to inspect</span>
      <select id={selectId} value={receipt.target_index - 1} onChange={(event) => setSelectedIndex(Number(event.target.value))}>
        {review.payload.receipts.map((entry, index) => <option key={entry.target_index} value={index}>Target {entry.target_index}: {entry.authored_target} {review.controlUnit}</option>)}
      </select>
    </label>
    <p className="wb2-note" aria-live="polite" data-frame3d-selected-target>
      Inspecting target {receipt.target_index}: {number(receipt.authored_target)} {review.controlUnit}. Candidate API status: {result.status}. Contract pass: {flag(result.contract_pass)}.
    </p>
    <p className="wb2-note">Tables show the terminal state at the selected authored target. Intermediate cutback steps are not displayed.</p>

    <div className="wb2-table-scroll" role="region" aria-label="3D node displacements" tabIndex={0}>
      <table className="wb2-table" data-frame3d-node-displacements>
        <caption>Node displacements · target {receipt.target_index}</caption>
        <thead><tr><th scope="col">Node</th>{['UX (m)', 'UY (m)', 'UZ (m)', 'RX (rad)', 'RY (rad)', 'RZ (rad)'].map((label) => <th scope="col" className="wb2-num" key={label}>{label}</th>)}</tr></thead>
        <tbody>{result.node_displacements.map((row) => <tr key={row.node_id}>
          <th scope="row">{row.node_id}</th>
          {[row.UX_m, row.UY_m, row.UZ_m, row.RX_rad, row.RY_rad, row.RZ_rad].map((value, index) => <td className="wb2-num" key={index}>{number(value)}</td>)}
        </tr>)}</tbody>
      </table>
    </div>
    <div className="wb2-table-scroll" role="region" aria-label="3D support reactions" tabIndex={0}>
      <table className="wb2-table" data-frame3d-support-reactions>
        <caption>Support reactions · target {receipt.target_index}</caption>
        <thead><tr><th scope="col">Node</th><th scope="col">DOF</th><th scope="col" className="wb2-num">Reaction</th><th scope="col">Unit</th></tr></thead>
        <tbody>{result.support_reactions.map((row) => <tr key={`${row.node_id}:${row.dof}`}>
          <th scope="row">{row.node_id}</th><td>{row.dof}</td><td className="wb2-num">{number(row.value)}</td><td>{row.unit}</td>
        </tr>)}</tbody>
      </table>
    </div>
    <div className="wb2-table-scroll" role="region" aria-label="3D material states" tabIndex={0}>
      <table className="wb2-table" data-frame3d-material-states>
        <caption>Material states · target {receipt.target_index}</caption>
        <thead><tr><th scope="col">Member</th><th scope="col">Material</th><th scope="col" className="wb2-num">Plastic strain (1)</th><th scope="col" className="wb2-num">Backstress (MPa)</th><th scope="col" className="wb2-num">Accumulated plastic strain (1)</th><th scope="col" className="wb2-num">Dissipated energy density (MJ/m³)</th><th scope="col">State hash</th></tr></thead>
        <tbody>{result.material_states.map((row) => <tr key={`${row.member_id}:${row.material_id}`}>
          <th scope="row">{row.member_id}</th><td>{row.material_id}</td>
          <td className="wb2-num">{number(row.plastic_strain)}</td><td className="wb2-num">{number(row.backstress_mpa)}</td>
          <td className="wb2-num">{number(row.accumulated_plastic_strain)}</td><td className="wb2-num">{number(row.dissipated_energy_density_mj_per_m3)}</td>
          <td className="wb2-mono">{row.state_hash}</td>
        </tr>)}</tbody>
      </table>
    </div>

    <div className="wb2-frame3d-job__authority">
      <h4>Authority boundary</h4>
      <dl className="wb2-kv" data-frame3d-authority>
        <dt>Public capability registry</dt><dd>{flag(authority.capability_registry_public)}</dd>
        <dt>Workbench execution</dt><dd>{flag(authority.workbench_execution)}</dd>
        <dt>Independent operator attached</dt><dd>{flag(authority.independent_operator_attached)}</dd>
        <dt>External V&amp;V level</dt><dd>{number(authority.external_vv_level, true)}</dd>
        <dt>Design approval</dt><dd>{flag(authority.design_authority)}</dd>
        <dt>Formal verification Level 2</dt><dd>{flag(authority.formal_verification_level_2)}</dd>
        <dt>Release eligibility</dt><dd>{flag(authority.release_eligible)}</dd>
      </dl>
      <p className="wb2-note">Read-only inspection does not grant Workbench execution authority.</p>
    </div>
    <div className="wb2-actions" aria-label="Verified 3D artifact downloads">
      <button type="button" className="wb2-btn" onClick={() => downloadBytes(snapshots.resultBytes, `${safeJobId}-frame3d-result.json`)}>Download result JSON</button>
      <button type="button" className="wb2-btn" onClick={() => downloadBytes(snapshots.evidenceBytes, `${safeJobId}-frame3d-evidence.json`)}>Download evidence JSON</button>
      <button type="button" className="wb2-btn" onClick={() => downloadBytes(snapshots.checkpointBytes, `${safeJobId}-frame3d-terminal-checkpoint.json`)}>Download terminal checkpoint</button>
    </div>
    <p className="wb2-note">Downloads preserve the verified result, evidence and terminal checkpoint bytes. Selecting a target changes only the displayed rows.</p>
  </section>
}
