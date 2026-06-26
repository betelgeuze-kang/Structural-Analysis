import type { ReactElement, ReactNode } from 'react'
import type { DataMode } from '../model/workbenchState'
import type { ProviderMode } from '../model/evidenceAdapter'
import { t, type Locale } from '../model/i18n'
import { StateChip, dataModeChipState } from './StateChip'
import { LocaleToggle } from './LocaleToggle'

interface WorkbenchShellProps {
  dataMode: DataMode
  providerMode: ProviderMode
  sourceLabel: string
  claimBoundary: string | null
  onProviderModeChange: (mode: ProviderMode) => void
  locale: Locale
  onLocaleChange: (locale: Locale) => void
  nav?: ReactNode
  children: ReactNode
}

export function WorkbenchShell({
  dataMode,
  providerMode,
  sourceLabel,
  claimBoundary,
  onProviderModeChange,
  locale,
  onLocaleChange,
  nav,
  children,
}: WorkbenchShellProps): ReactElement {
  const claimText =
    claimBoundary ??
    'Demo prototype. No solver evidence attached; values are illustrative and are not a verdict.'

  return (
    <div className="wb2-root" data-wb2-root data-locale={locale}>
      <a className="wb2-skip-link" href="#wb2-main">{t('shell.skip', locale)}</a>

      <header className="wb2-header">
        <div>
          <p className="wb2-eyebrow">{t('shell.eyebrow', locale)}</p>
          <div className="wb2-title-row">
            <h1>{t('shell.title', locale)}</h1>
            <StateChip state={dataModeChipState(dataMode)} srLabel="Data mode" />
          </div>
        </div>
        <div className="wb2-header-controls">
          <div className="wb2-mode-switch" role="group" aria-label={t('shell.provider', locale)}>
            <span className="wb2-mode-label">{t('shell.provider', locale)}</span>
            {(['demo', 'live'] as ProviderMode[]).map((m) => (
              <button
                key={m}
                type="button"
                className={`wb2-mode-btn${providerMode === m ? ' is-active' : ''}`}
                aria-pressed={providerMode === m}
                data-wb2-provider={m}
                onClick={() => onProviderModeChange(m)}
              >
                {m === 'demo' ? t('shell.demo', locale) : t('shell.live', locale)}
              </button>
            ))}
          </div>
          <LocaleToggle locale={locale} onChange={onLocaleChange} />
        </div>
      </header>

      <p className="wb2-claim" role="note" aria-label="Claim boundary" data-wb2-claim>
        <strong>{t('shell.claim_prefix', locale)}</strong>
        {claimText}
      </p>
      <p className="wb2-provenance" data-wb2-source>{t('shell.source', locale)}: {sourceLabel}</p>

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
