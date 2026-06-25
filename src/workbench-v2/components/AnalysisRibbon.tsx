import type { ReactElement } from 'react'
import type { RunStatus } from '../model/workbenchState'

const STAGES: { key: RunStatus; label: string }[] = [
  { key: 'idle', label: 'Idle' },
  { key: 'validating', label: 'Validating' },
  { key: 'running', label: 'Running' },
  { key: 'converged', label: 'Converged' },
]

export function AnalysisRibbon({ runStatus }: { runStatus: RunStatus }): ReactElement {
  const activeIndex = STAGES.findIndex((s) => s.key === runStatus)
  const failed = runStatus === 'failed'

  return (
    <section className="wb2-panel wb2-ribbon" aria-labelledby="wb2-ribbon-title">
      <h2 id="wb2-ribbon-title" className="wb2-panel__title">Analysis</h2>
      <ol className="wb2-ribbon-steps" aria-label="Analysis stages">
        {STAGES.map((stage, index) => {
          const isActive = !failed && index <= activeIndex && activeIndex >= 0
          const isCurrent = !failed && index === activeIndex
          return (
            <li
              key={stage.key}
              className={`wb2-ribbon-step${isActive ? ' is-active' : ''}${isCurrent ? ' is-current' : ''}`}
              aria-current={isCurrent ? 'step' : undefined}
            >
              <span className="wb2-ribbon-dot" aria-hidden="true" />
              {stage.label}
            </li>
          )
        })}
      </ol>
      {failed ? <p className="wb2-note wb2-note--warn">Run failed — see warnings.</p> : null}
    </section>
  )
}
