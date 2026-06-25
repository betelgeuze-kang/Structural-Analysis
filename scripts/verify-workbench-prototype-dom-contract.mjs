// Offline DOM/logic contract for the Structural Workbench demo prototype.
// Runs in plain Node against a minimal DOM shim — no browser binaries needed.

import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

class FakeElement {
  constructor(tag) {
    this.tagName = String(tag).toUpperCase()
    this.children = []
    this.attributes = {}
    this.className = ''
    this._text = ''
    this.classList = { add() {}, remove() {}, contains: () => false }
  }
  set textContent(v) { this._text = v == null ? '' : String(v); this.children = [] }
  get textContent() { return this.children.length ? this.children.map((c) => c.textContent).join('') : this._text }
  setAttribute(k, v) { this.attributes[k] = String(v) }
  getAttribute(k) { return Object.prototype.hasOwnProperty.call(this.attributes, k) ? this.attributes[k] : null }
  appendChild(c) { this.children.push(c); return c }
  append(...n) { for (const x of n) this.children.push(x) }
  replaceChildren(...n) { this.children = n }
  addEventListener() {}
  collect(pred, acc = []) {
    if (pred(this)) acc.push(this)
    for (const c of this.children) if (c instanceof FakeElement) c.collect(pred, acc)
    return acc
  }
}

globalThis.document = {
  readyState: 'complete',
  createElement: (t) => new FakeElement(t),
  createTextNode: (t) => ({ textContent: String(t) }),
  querySelector: () => null,
  addEventListener: () => {},
  body: new FakeElement('body'),
}

let failures = 0
function check(name, cond) {
  const ok = Boolean(cond)
  console.log(`${ok ? 'PASS' : 'FAIL'} - ${name}`)
  if (!ok) failures += 1
}

async function main() {
  const app = await import('../prototype/structural-workbench/app.js')
  const demo = JSON.parse(
    fs.readFileSync(path.join(rootDir, 'prototype/structural-workbench/demo-case.json'), 'utf8'),
  )

  // data_mode mapping
  check('data_mode demo -> DEMO', app.mapDataMode('demo') === 'DEMO')
  check('data_mode live -> LIVE', app.mapDataMode('live') === 'LIVE')
  check('data_mode unknown -> UNAVAILABLE', app.mapDataMode('whatever') === 'UNAVAILABLE')

  // check-state mapping — never a positive verdict for un-evaluated values
  check('NOT_EVALUATED -> UNAVAILABLE', app.mapCheckState('NOT_EVALUATED') === 'UNAVAILABLE')
  check('NOT_CONNECTED -> MISSING', app.mapCheckState('NOT_CONNECTED') === 'MISSING')
  check('false -> BLOCKED', app.mapCheckState(false) === 'BLOCKED')
  check('null -> UNAVAILABLE', app.mapCheckState(null) === 'UNAVAILABLE')
  check('unknown token -> UNAVAILABLE (not pass)', app.mapCheckState('SOMETHING') === 'UNAVAILABLE')

  // status rows from the real demo fixture
  const rows = app.buildStatusRows(demo.status)
  const byKey = Object.fromEntries(rows.map((r) => [r.key, r.state]))
  check('solver_connected:false -> BLOCKED', byKey.solver_connected === 'BLOCKED')
  check('p0 NOT_EVALUATED -> UNAVAILABLE', byKey.p0 === 'UNAVAILABLE')
  check('p1 NOT_EVALUATED -> UNAVAILABLE', byKey.p1 === 'UNAVAILABLE')
  check('gpu NOT_CONNECTED -> MISSING', byKey.gpu === 'MISSING')
  check('no demo status row maps to LIVE/pass', !rows.some((r) => r.state === 'LIVE'))

  // chip rendering never emits the word PASS
  const chipStates = ['DEMO', 'LIVE', 'STALE', 'BLOCKED', 'MISSING', 'UNAVAILABLE']
  const chipText = chipStates.map((s) => app.createStateChip(s).textContent).join(' ')
  check('chips cover all six states', chipStates.every((s) => chipText.includes(app.STATE_META[s].label)))
  check('chips never render PASS', !/\bPASS\b/i.test(chipText))

  // rendered status panel contains no PASS and lists every gate label
  const panel = new FakeElement('div')
  // emulate renderWorkbench's status target lookup
  const root = {
    querySelector: (sel) => (sel === '[data-wb-status]' ? panel : null),
  }
  await app.renderWorkbench(root, demo)
  const panelText = panel.textContent
  check('status panel renders without PASS', !/\bPASS\b/i.test(panelText))
  check('status panel lists Solver/P0/P1/GPU', ['Solver connection', 'P0 gate', 'P1 gate', 'GPU / HIP'].every((l) => panelText.includes(l)))

  // export bundle stays demo-flagged and treats user input as inert text
  const evil = '<img src=x onerror=alert(1)>'
  const bundle = app.buildDemoBundle(demo, { reviewComment: evil, selectedFileName: evil })
  check('bundle is_demo true', bundle.is_demo === true)
  check('bundle carries claim_boundary', typeof bundle.claim_boundary === 'string' && bundle.claim_boundary.length > 0)
  check('bundle stores reviewer note as plain string', bundle.reviewer_note === evil)
  check('bundle stores file name as plain string', bundle.selected_input_file === evil)

  // static safety: the controller never uses innerHTML
  const appSource = fs.readFileSync(path.join(rootDir, 'prototype/structural-workbench/app.js'), 'utf8')
  check('app.js contains no innerHTML usage', !/\.innerHTML/.test(appSource))

  if (failures > 0) {
    console.log(`\n${failures} workbench prototype contract check(s) failed`)
    process.exitCode = 1
  } else {
    console.log('\nAll workbench prototype contract checks passed')
  }
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
