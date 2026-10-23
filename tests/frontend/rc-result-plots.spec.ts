import { expect, test } from '@playwright/test'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { resolve } from 'node:path'
import ts from 'typescript'

// Playwright rewrites imported TSX into component-test descriptors. Compile
// this actual source with React's JSX runtime for numerical SVG output checks.
// Browser integration tests independently exercise the production Vite build.
const componentFile = resolve('src/workbench-v2/components/RcResultVisualization.tsx')
const compiled = ts.transpileModule(readFileSync(componentFile, 'utf8'), {
  compilerOptions: { jsx: ts.JsxEmit.ReactJSX, module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText
const componentExports = {} as typeof import('../../src/workbench-v2/components/RcResultVisualization')
new Function('require', 'exports', compiled)(createRequire(componentFile), componentExports)
const { RcDeformedShape, RcHistoryPlot } = componentExports

const geometry = {
  nodes: [{ id: 'A', x: 0, y: 0 }, { id: 'B', x: 2, y: 0 }, { id: 'C', x: 2, y: 2 }],
  members: [{ id: 'H', nodeI: 'A', nodeJ: 'B' }, { id: 'V', nodeI: 'B', nodeJ: 'C' }],
}
const movements = [{ nodeId: 'A', ux: 0, uy: 0 }, { nodeId: 'B', ux: 0, uy: 0 }, { nodeId: 'C', ux: 0.1, uy: -0.2 }]
const shape = (scale: string, displacements = movements) => renderToStaticMarkup(createElement(RcDeformedShape, {
  geometry, displacements, scale, selectedMember: 'V', onSelectMember: () => {},
}))
const attr = (raw: string, name: string) => Number(new RegExp(`\\b${name}="([^"]+)"`).exec(raw)![1])

test('deformation plot preserves a physical aspect ratio, global Y direction and the explicit scale', () => {
  const markup = shape('10')
  const groups = [...markup.matchAll(/<g[^>]*data-rc-member="([^"]+)"[^>]*>([\s\S]*?)<\/g>/g)]
  expect(groups.map(match => match[1])).toEqual(['H', 'V'])
  const lines = groups.map(match => /<line[^>]+>/.exec(match[2])![0])
  expect(attr(lines[0], 'x2') - attr(lines[0], 'x1')).toBeCloseTo(attr(lines[1], 'y1') - attr(lines[1], 'y2'), 12)
  expect(markup).toContain('data-rc-deformed-x2="3" data-rc-deformed-y2="0"')
  expect(markup).toContain('Global XY (m)')
  expect(markup).toContain('deformation ×10')
})

for (const scale of ['', 'NaN', '-1', 'Infinity', '1e309']) test(`invalid deformation scale ${JSON.stringify(scale)} hides the plot instead of changing result values`, () => {
  const markup = shape(scale)
  expect(markup).toContain('data-rc-shape-unavailable')
  expect(markup).not.toContain('<svg')
  expect(movements[2]).toEqual({ nodeId: 'C', ux: 0.1, uy: -0.2 })
})

test('missing translations and arithmetic overflow do not become a zero-displacement shape', () => {
  expect(shape('1', movements.slice(0, 2))).not.toContain('<svg')
  expect(shape('2', movements.map(row => row.nodeId === 'C' ? { ...row, ux: Number.MAX_VALUE } : row))).not.toContain('<svg')
})

test('history plots preserve reversal order and repeated coordinates as separate stored states', () => {
  const points = [{ state: 20, x: 0.2, y: 5 }, { state: 21, x: -0.1, y: -3 }, { state: 22, x: 0.2, y: 4 }, { state: 23, x: 0.2, y: 5 }]
  const markup = renderToStaticMarkup(createElement(RcHistoryPlot, { label: 'History', xLabel: 'Strain (dimensionless)', yLabel: 'Stress (MPa)', points, selectedState: 22 }))
  expect([...markup.matchAll(/data-rc-history-point="(\d+)"/g)].map(match => Number(match[1]))).toEqual([20, 21, 22, 23])
  const plotted = /<polyline[^>]*points="([^"]+)"/.exec(markup)![1].split(' ').map(pair => pair.split(',').map(Number))
  expect(plotted[0][0]).toBeGreaterThan(plotted[1][0])
  expect(plotted[2][0]).toBeGreaterThan(plotted[1][0])
  expect(plotted[0]).toEqual(plotted[3])
  expect(markup).toContain('data-rc-x="-0.1" data-rc-y="-3"')
  expect(markup).toContain('Stress (MPa)')
})

test('finite extreme and constant histories produce finite SVG coordinates', () => {
  for (const points of [
    [{ state: 0, x: -Number.MAX_VALUE, y: Number.MAX_VALUE }, { state: 1, x: Number.MAX_VALUE, y: -Number.MAX_VALUE }],
    [{ state: 0, x: 0, y: 5 }, { state: 1, x: 0, y: 5 }],
  ]) {
    const markup = renderToStaticMarkup(createElement(RcHistoryPlot, { label: 'History', xLabel: 'x', yLabel: 'y', points }))
    const plotted = /<polyline[^>]*points="([^"]+)"/.exec(markup)![1].split(/[ ,]/).map(Number)
    expect(plotted.every(Number.isFinite)).toBe(true)
  }
})
