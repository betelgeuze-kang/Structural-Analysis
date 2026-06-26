import type { ReactElement, ReactNode } from 'react'
import type { DataMode } from '../model/workbenchState'
import type { ProviderMode } from '../model/evidenceAdapter'
import { StateChip, dataModeChipState } from './StateChip'

interface WorkbenchShellProps {
  dataMode: DataMode
  providerMode: ProviderMode
  sourceLabel: string
  claimBoundary: string | null
  onProviderModeChange: (mode: ProviderMode) => void
  nav?: ReactNode
  children: ReactNode
}

export function WorkbenchShell({
  dataMode,
  providerMode,
  sourceLabel,
  claimBoundary,
  onProviderModeChange,
  nav,
  children,
}: WorkbenchShellProps): ReactElement {
  const claimText =
    claimBoundary ??
    'Demo prototype. No solver evidence attached; values are illustrative and are not a verdict.'

  return (
    <div className="wb2-root" data-wb2-root>
      <a className="wb2-skip-link" href="#wb2-main">Skip to workbench</a>

      <header className="wb2-header">
        <div>
          <p className="wb2-eyebrow">Structural Optimization Workbench</p>
          <div className="wb2-title-row">
            <h1>Workbench v2</h1>
            <StateChip state={dataModeChipState(dataMode)} srLabel="Data mode" />
          </div>
        </div>
        <div className="wb2-mode-switch" role="group" aria-label="Data provider">
          <span className="wb2-mode-label">Provider</span>
          {(['demo', 'live'] as ProviderMode[]).map((m) => (
            <button
              key={m}
              type="button"
              className={`wb2-mode-btn${providerMode === m ? ' is-active' : ''}`}
              aria-pressed={providerMode === m}
              data-wb2-provider={m}
              onClick={() => onProviderModeChange(m)}
            >
              {m === 'demo' ? 'Demo' : 'Live'}
            </button>
          ))}
        </div>
      </header>

      <p className="wb2-claim" role="note" aria-label="Claim boundary" data-wb2-claim>
        <strong>Claim boundary: </strong>
        {claimText}
      </p>
      <p className="wb2-provenance" data-wb2-source>Source: {sourceLabel}</p>

      <div className={`wb2-layout${nav ? ' has-nav' : ''}`}>
        {nav ? (
          <aside className="wb2-nav-col" aria-label="Workbench navigation">
            {nav}
          </aside>
        ) : null}
        <main id="wb2-main" className="wb2-main" tabIndex={-1} aria-label="Workbench content">
          {children}
        </main>
      </div>
    </div>
  )
}
