import type { ReactElement } from 'react'
import registryRaw from '../model/generatedCapabilities.json'

interface CapabilityRow {
  id: string
  title: string
  category: string
  status: 'supported' | 'bounded_public' | 'experimental' | 'shadow_only' | 'blocked'
  representable: boolean
  implemented: boolean
  executable: boolean
  public: boolean
  numerical_authority: string
  recovery_authority: string
  external_vv_level: number
  release_eligible: boolean
  interfaces: string[]
  profile: string
  limitations: string[]
}

interface CapabilityRegistry {
  schemaVersion: string
  authorityRules: {
    solver_truth_owner: string
    workbench_truth_owner: string
    ai_truth_owner: string
    fallback_promotion_allowed: boolean
  }
  capabilities: CapabilityRow[]
}

const registry = registryRaw as CapabilityRegistry

export function CapabilitySupportPanel(): ReactElement {
  return (
    <section className="wb2-panel wb2-capabilities" aria-labelledby="wb2-capabilities-title">
      <div className="wb2-panel__heading">
        <div>
          <p className="wb2-kicker">Generated support registry</p>
          <h2 id="wb2-capabilities-title" className="wb2-panel__title">Capabilities</h2>
        </div>
        <span className="wb2-capabilities__schema">{registry.schemaVersion}</span>
      </div>
      <p className="wb2-note">
        Solver truth owner: {registry.authorityRules.solver_truth_owner}. Workbench authority:
        {' '}{registry.authorityRules.workbench_truth_owner}; AI authority:
        {' '}{registry.authorityRules.ai_truth_owner}; fallback promotion is
        {registry.authorityRules.fallback_promotion_allowed ? ' enabled' : ' disabled'}.
        {' '}Representable, implemented, executable, public, numerical/recovery,
        external-V&amp;V, and release axes are independent.
      </p>
      <div className="wb2-table-wrap">
        <table className="wb2-table" data-wb2-capability-table>
          <thead>
            <tr>
              <th scope="col">Capability</th>
              <th scope="col">Status</th>
              <th scope="col">R/I/E/P</th>
              <th scope="col">Numerical authority</th>
              <th scope="col">Recovery authority</th>
              <th scope="col">External V&amp;V</th>
              <th scope="col">Release</th>
              <th scope="col">Boundary</th>
            </tr>
          </thead>
          <tbody>
            {registry.capabilities.map((row) => (
              <tr key={row.id} data-capability-id={row.id} data-capability-status={row.status}>
                <th scope="row">{row.title}</th>
                <td>{row.status}</td>
                <td>
                  {row.representable ? 'Y' : 'N'}/
                  {row.implemented ? 'Y' : 'N'}/
                  {row.executable ? 'Y' : 'N'}/
                  {row.public ? 'Y' : 'N'}
                </td>
                <td>{row.numerical_authority}</td>
                <td>{row.recovery_authority}</td>
                <td>{row.external_vv_level}</td>
                <td>{row.release_eligible ? 'yes' : 'no'}</td>
                <td>{row.profile}; {row.limitations[0]}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  )
}
