import type { ReactElement } from 'react'
import type { ResidualStep } from '../model/caseSchema'

function fmt(value: number): string {
  if (value !== 0 && (Math.abs(value) < 1e-3 || Math.abs(value) >= 1e6)) return value.toExponential(3)
  return Number.isInteger(value) ? String(value) : value.toFixed(4).replace(/0+$/, '').replace(/\.$/, '')
}

interface ResidualAuditPanelProps {
  residualHistory: ResidualStep[]
  sourceLabel: string
  residualTolerance?: number
}

const CHART_W = 460
const CHART_H = 150
const PAD_L = 44
const PAD_R = 12
const PAD_T = 12
const PAD_B = 26

/**
 * Log-scale residual chart. Plots the recorded residual per iteration on a
 * base-10 log axis and, when a tolerance is provided, draws the tolerance line
 * so a reviewer can see how close the run came. Pure SVG, no animation; renders
 * only when residual history exists (never fabricated).
 */
function ResidualChart({ history, tolerance }: { history: ResidualStep[]; tolerance?: number }): ReactElement {
  const positive = history.filter((s) => s.residual > 0)
  const residualValues = positive.map((s) => s.residual)
  const candidates = [...residualValues]
  if (tolerance != null && tolerance > 0) candidates.push(tolerance)

  const minLog = Math.floor(Math.log10(Math.min(...candidates)))
  const maxLog = Math.ceil(Math.log10(Math.max(...candidates)))
  const logSpan = Math.max(1, maxLog - minLog)

  const iters = positive.map((s) => s.iteration)
  const minIter = Math.min(...iters)
  const maxIter = Math.max(...iters)
  const iterSpan = Math.max(1, maxIter - minIter)

  const x = (iter: number): number => PAD_L + ((iter - minIter) / iterSpan) * (CHART_W - PAD_L - PAD_R)
  const y = (residual: number): number => {
    const t = (Math.log10(residual) - minLog) / logSpan
    return CHART_H - PAD_B - t * (CHART_H - PAD_T - PAD_B)
  }

  const points = positive.map((s) => `${x(s.iteration).toFixed(1)},${y(s.residual).toFixed(1)}`).join(' ')
  const tolY = tolerance != null && tolerance > 0 ? y(tolerance) : null

  const gridLogs: number[] = []
  for (let l = minLog; l <= maxLog; l += 1) gridLogs.push(l)

  return (
    <svg
      className="wb2-residual-chart"
      viewBox={`0 0 ${CHART_W} ${CHART_H}`}
      role="img"
      aria-label="Residual versus iteration on a base-10 log scale"
      data-wb2-residual-chart
      preserveAspectRatio="xMidYMid meet"
    >
      {gridLogs.map((l) => {
        const gy = y(Math.pow(10, l))
        return (
          <g key={l}>
            <line x1={PAD_L} y1={gy} x2={CHART_W - PAD_R} y2={gy} className="wb2-chart-grid" />
            <text x={PAD_L - 6} y={gy + 3} className="wb2-chart-axis" textAnchor="end">{`1e${l}`}</text>
          </g>
        )
      })}
      {tolY != null ? (
        <g>
          <line x1={PAD_L} y1={tolY} x2={CHART_W - PAD_R} y2={tolY} className="wb2-chart-tol" data-wb2-tol-line />
          <text x={CHART_W - PAD_R} y={tolY - 4} className="wb2-chart-tol-label" textAnchor="end">tolerance</text>
        </g>
      ) : null}
      <polyline points={points} className="wb2-chart-line" fill="none" />
      {positive.map((s) => (
        <circle key={s.iteration} cx={x(s.iteration)} cy={y(s.residual)} r={2.6} className="wb2-chart-dot" />
      ))}
      <text x={(CHART_W + PAD_L) / 2} y={CHART_H - 6} className="wb2-chart-axis" textAnchor="middle">iteration</text>
    </svg>
  )
}

export function ResidualAuditPanel({ residualHistory, sourceLabel, residualTolerance }: ResidualAuditPanelProps): ReactElement {
  const hasPositive = residualHistory.some((s) => s.residual > 0)
  return (
    <section className="wb2-panel" aria-labelledby="wb2-residual-title">
      <h2 id="wb2-residual-title" className="wb2-panel__title">Residual audit</h2>
      {residualHistory.length ? (
        <>
          {hasPositive ? <ResidualChart history={residualHistory} tolerance={residualTolerance} /> : null}
          <div className="wb2-table-scroll" role="region" aria-label="Residual history table" tabIndex={0}>
            <table className="wb2-table">
              <thead>
                <tr>
                  <th className="wb2-num">Iter</th>
                  <th className="wb2-num">Residual</th>
                  <th className="wb2-num">Rel. increment</th>
                  <th className="wb2-num">Alpha</th>
                </tr>
              </thead>
              <tbody>
                {residualHistory.map((step) => (
                  <tr key={step.iteration}>
                    <td className="wb2-num">{step.iteration}</td>
                    <td className="wb2-num">{fmt(step.residual)}</td>
                    <td className="wb2-num">{fmt(step.relativeIncrement)}</td>
                    <td className="wb2-num">{fmt(step.alpha)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="wb2-provenance" data-wb2-provenance>Source: {sourceLabel}</p>
        </>
      ) : (
        <p className="wb2-unavailable" data-wb2-unavailable>
          No residual history attached. Convergence trace cannot be shown for this case.
        </p>
      )}
    </section>
  )
}
