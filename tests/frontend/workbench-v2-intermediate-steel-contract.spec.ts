import { test, expect } from '@playwright/test'
import { intermediateSteelBarCount } from '../../src/workbench-v2/model/rcSteelLayers'

test('intermediate steel quantity retains authored layers', () => {
  const section = { depth_m: 0.4, cover_m: 0.04 }
  expect(intermediateSteelBarCount(section)).toBe(0)
  expect(intermediateSteelBarCount({ ...section, intermediate_steel_layers: [
    { y_m: -0.05, bar_count: 2 }, { y_m: 0.05, bar_count: 2 },
  ] })).toBe(4)
})
for (const [name, layers] of Object.entries({
  null: null, empty: [], boolean: [{ y_m: 0, bar_count: true }],
  duplicate: [{ y_m: 0, bar_count: 2 }, { y_m: 0, bar_count: 2 }],
  outside: [{ y_m: 0.18, bar_count: 2 }], reverse: [{ y_m: 0.05, bar_count: 2 }, { y_m: -0.05, bar_count: 2 }],
  unknown: [{ y_m: 0, bar_count: 2, area: 1 }],
})) test(`intermediate steel rejects ${name}`, () => {
  expect(() => intermediateSteelBarCount({ depth_m: 0.4, cover_m: 0.04, intermediate_steel_layers: layers })).toThrow()
})
