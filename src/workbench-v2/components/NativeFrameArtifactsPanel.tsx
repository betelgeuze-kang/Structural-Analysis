import type { ReactElement } from 'react'
import type { NativeFrameLoadResult } from '../model/nativeFrameProvider'
import { StateChip, type ChipState } from './StateChip'

interface NativeFrameArtifactsPanelProps {
  load: NativeFrameLoadResult
}

function chip(load: NativeFrameLoadResult): ChipState {
  if (load.status === 'missing') return 'MISSING'
  if (load.status === 'invalid') return 'BLOCKED'
  if (load.status === 'ready' && load.artifactStatus !== 'integrity_unavailable') return 'LIVE'
  return 'UNAVAILABLE'
}

function shortHash(value: string): string {
  return `${value.slice(0, 15)}…${value.slice(-8)}`
}

function number(value: number): string {
  return value.toExponential(8)
}

export function NativeFrameArtifactsPanel({ load }: NativeFrameArtifactsPanelProps): ReactElement {
  const result = load.resultIr
  const report = load.reportIr
  const unavailable = load.status !== 'ready'
    || !result
    || load.artifactStatus === 'integrity_unavailable'

  return (
    <section
      className="wb2-panel"
      aria-labelledby="wb2-native-frame-title"
      data-native-frame-artifacts={load.status}
      data-native-frame-integrity={load.artifactStatus}
    >
      <h2 id="wb2-native-frame-title" className="wb2-panel__title">Native Frame3D artifacts</h2>
      <div className="wb2-run-head">
        <StateChip state={chip(load)} srLabel="Native Frame3D artifact state" />
        <span className="wb2-run-status-label">{load.artifactStatus}</span>
      </div>

      {unavailable ? (
        <p className="wb2-unavailable" data-wb2-unavailable>
          {load.status === 'loading'
            ? 'Loading native Frame3D ResultIR/ReportIR…'
            : load.status === 'pending'
              ? `Native Frame3D job has no completed bundle yet${load.errors[0] ? ` (${load.errors[0]})` : ''}.`
            : load.status === 'unconfigured'
              ? 'No same-origin native Frame3D job, bundle or ResultIR URL is configured.'
              : `Native Frame3D artifacts are unavailable${load.errors[0] ? ` (${load.errors[0]})` : ''}.`}
          {' '}Numerical state, comparison, design and release readiness are not inferred.
        </p>
      ) : (
        <>
          <dl className="wb2-kv">
            <dt>ResultIR</dt>
            <dd
              className="wb2-mono"
              data-native-frame-result-ir={load.artifactStatus === 'integrity_unavailable' ? 'integrity_unavailable' : 'verified'}
            >
              {result.result_id} · {shortHash(result.result_hash)}
            </dd>
            <dt>ReportIR</dt>
            <dd
              className="wb2-mono"
              data-native-frame-report-ir={report
                ? load.artifactStatus === 'integrity_unavailable' ? 'integrity_unavailable' : 'verified'
                : 'not_configured'}
            >
              {report ? `${report.report_id} · ${shortHash(report.report_hash)}` : 'not configured'}
            </dd>
            <dt>Model</dt><dd>{result.bindings.model_id}</dd>
            <dt>{result.bindings.load_pattern_id ? 'Load pattern' : 'Load combination'}</dt>
            <dd>{result.bindings.load_pattern_id ?? result.bindings.load_combination_id}</dd>
            <dt>Solver</dt><dd>{result.solver.formulation} · {result.solver.backend}</dd>
            <dt>Entities</dt><dd>{result.nodes.length} nodes · {result.members.length} members</dd>
            <dt>Result authority</dt>
            <dd data-native-frame-result-authority>
              displacement={result.authority.displacement}; reaction={result.authority.reaction};
              member_force={result.authority.member_force}
            </dd>
            <dt>Comparison authority</dt>
            <dd data-native-frame-comparison-authority>{report?.authority.comparison ?? 'not_attached'}</dd>
            <dt>Release authority</dt>
            <dd data-native-frame-release-authority>{result.authority.release_readiness}</dd>
          </dl>

          <h3 className="wb2-panel__subtitle">Promotion gates</h3>
          <div className="wb2-table-scroll">
            <table className="wb2-table" data-native-frame-gates>
              <thead><tr><th>Gate</th><th>Metric</th><th>Tolerance</th></tr></thead>
              <tbody>
                <tr>
                  <td>Free residual scaled L∞</td>
                  <td className="wb2-mono">{number(result.gates.free_residual_scaled_linf)}</td>
                  <td className="wb2-mono">{number(result.gates.free_residual_scaled_linf_tolerance)}</td>
                </tr>
                <tr>
                  <td>Global force balance scaled L∞</td>
                  <td className="wb2-mono">{number(result.gates.global_force_balance_scaled_linf)}</td>
                  <td className="wb2-mono">{number(result.gates.global_force_balance_scaled_linf_tolerance)}</td>
                </tr>
                <tr>
                  <td>Global moment balance scaled L∞</td>
                  <td className="wb2-mono">{number(result.gates.global_moment_balance_scaled_linf)}</td>
                  <td className="wb2-mono">{number(result.gates.global_moment_balance_scaled_linf_tolerance)}</td>
                </tr>
                <tr>
                  <td>Independent member-force recovery replay scaled L∞</td>
                  <td className="wb2-mono">{number(result.gates.member_force_replay_scaled_linf)}</td>
                  <td className="wb2-mono">{number(result.gates.member_force_replay_scaled_linf_tolerance)}</td>
                </tr>
              </tbody>
            </table>
          </div>

          {report ? (
            <>
              <h3 className="wb2-panel__subtitle">Deterministic extrema</h3>
              <div className="wb2-table-scroll">
                <table className="wb2-table" data-native-frame-extrema>
                  <thead>
                    <tr><th>Quantity</th><th>Entity</th><th>Component</th><th>Signed value</th><th>Unit</th></tr>
                  </thead>
                  <tbody>
                    {report.extrema.map((row) => (
                      <tr key={row.quantity}>
                        <td>{row.quantity}</td><td>{row.entity_id}</td><td>{row.component}</td>
                        <td className="wb2-mono">{number(row.signed_value)}</td><td>{row.unit}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          ) : (
            <p className="wb2-unavailable" data-native-frame-report-unavailable>
              ReportIR is not configured; extrema and comparison authority remain unattached.
            </p>
          )}

          <details data-native-frame-node-results>
            <summary>Node displacement and reaction rows ({result.nodes.length})</summary>
            <div className="wb2-table-scroll">
              <table className="wb2-table">
                <thead><tr><th>Node</th><th>UX</th><th>UY</th><th>UZ</th><th>RX</th><th>RY</th><th>RZ</th><th>FX</th><th>FY</th><th>FZ</th><th>MX</th><th>MY</th><th>MZ</th></tr></thead>
                <tbody>
                  {result.nodes.map((node) => (
                    <tr key={node.node_id}>
                      <td>{node.node_id}</td>
                      {[...node.displacement_m_rad, ...node.reaction_n_nm].map((value, index) => (
                        <td className="wb2-mono" key={`${node.node_id}-${index}`}>{number(value)}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>

          <details data-native-frame-member-results>
            <summary>Member local end-force rows ({result.members.length})</summary>
            <div className="wb2-table-scroll">
              <table className="wb2-table">
                <thead><tr><th>Member</th><th>FX I</th><th>FY I</th><th>FZ I</th><th>MX I</th><th>MY I</th><th>MZ I</th><th>FX J</th><th>FY J</th><th>FZ J</th><th>MX J</th><th>MY J</th><th>MZ J</th></tr></thead>
                <tbody>
                  {result.members.map((member) => (
                    <tr key={member.member_id}>
                      <td>{member.member_id}</td>
                      {[...member.end_i_force_n_nm, ...member.end_j_force_n_nm].map((value, index) => (
                        <td className="wb2-mono" key={`${member.member_id}-${index}`}>{number(value)}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>

          <p className="wb2-muted" data-native-frame-claim-boundary>
            This is a read-only typed consumer of a bounded CPU result candidate. Workbench does not
            submit or rerun this analysis, comparison remains {report?.authority.comparison ?? 'not attached'},
            and engineering design, commercial use and release readiness remain not authoritative.
          </p>
        </>
      )}
    </section>
  )
}
