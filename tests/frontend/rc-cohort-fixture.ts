import { readFileSync } from 'node:fs'
export const cohortRoot = 'tests/frontend/fixtures/rc-strategy-cohort-control/'
export function cohortBytes(path: string): Uint8Array {
  if (path === 'cohort.json') return new Uint8Array(readFileSync(cohortRoot + path))
  const match = /^pairs\/0\/(price_order|learned_order)\/(.+)$/.exec(path)
  if (!match) throw Error('unregistered fixture path')
  return new Uint8Array(readFileSync(['result.json', 'plan.json', 'strategy-runtime.json'].includes(match[2])
    ? cohortRoot + path : 'tests/frontend/fixtures/rc-control-search-cost-no-oracle/' + match[2]))
}
