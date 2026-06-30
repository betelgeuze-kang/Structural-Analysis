import type { ReactElement } from 'react'
import type { Locale } from '../model/i18n'

interface LocaleToggleProps {
  locale: Locale
  onChange: (locale: Locale) => void
}

/**
 * Simple locale toggle for the header. Two buttons: EN / 한국어.
 */
export function LocaleToggle({ locale, onChange }: LocaleToggleProps): ReactElement {
  return (
    <div className="wb2-locale-toggle" role="group" aria-label="Language" data-wb2-locale>
      <button
        type="button"
        className={`wb2-locale-btn${locale === 'en' ? ' is-active' : ''}`}
        aria-pressed={locale === 'en'}
        data-locale="en"
        onClick={() => onChange('en')}
      >
        EN
      </button>
      <button
        type="button"
        className={`wb2-locale-btn${locale === 'ko' ? ' is-active' : ''}`}
        aria-pressed={locale === 'ko'}
        data-locale="ko"
        onClick={() => onChange('ko')}
      >
        한국어
      </button>
    </div>
  )
}
