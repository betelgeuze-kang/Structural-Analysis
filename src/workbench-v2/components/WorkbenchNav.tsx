import { useEffect, useState, type ReactElement } from 'react'
import { workbenchSections, sectionGroupLabel, type SectionGroup } from '../model/workbenchSections'
import { t, type Locale } from '../model/i18n'

/**
 * Left navigation for the commercial workbench layout. Items are in-page anchors
 * that scroll to each section; the active item is tracked with an
 * IntersectionObserver. Grouped so the model->analysis->results flow reads as the
 * primary surface and evidence/benchmarks sit in a verification layer below.
 */
export function WorkbenchNav({ locale = 'en' }: { locale?: Locale } = {}): ReactElement {
  const [active, setActive] = useState<string>(workbenchSections[0]?.id ?? '')

  useEffect(() => {
    if (typeof IntersectionObserver === 'undefined') return
    const els = workbenchSections
      .map((s) => document.getElementById(s.id))
      .filter((el): el is HTMLElement => el != null)
    if (!els.length) return

    const observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((e) => e.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)
        if (visible[0]?.target?.id) setActive(visible[0].target.id)
      },
      { rootMargin: '-20% 0px -65% 0px', threshold: [0, 0.25, 0.5, 1] },
    )
    els.forEach((el) => observer.observe(el))
    return () => observer.disconnect()
  }, [])

  const groups: SectionGroup[] = ['model', 'verification', 'decision']

  return (
    <nav className="wb2-nav" aria-label="Workbench sections" data-wb2-nav>
      {groups.map((group) => (
        <div key={group} className="wb2-nav-group">
          <p className="wb2-nav-group__label">{t(`nav.${group}`, locale)}</p>
          <ul className="wb2-nav-list">
            {workbenchSections
              .filter((s) => s.group === group)
              .map((s) => (
                <li key={s.id}>
                  <a
                    href={`#${s.id}`}
                    className={`wb2-nav-link${active === s.id ? ' is-active' : ''}`}
                    aria-current={active === s.id ? 'true' : undefined}
                    data-wb2-nav-link={s.id}
                  >
                    {t(`nav.${s.i18nKey}`, locale)}
                  </a>
                </li>
              ))}
          </ul>
        </div>
      ))}
    </nav>
  )
}
