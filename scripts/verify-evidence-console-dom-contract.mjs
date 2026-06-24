// DOM contract test for the Evidence Console (no browser required).
//
// This exercises the real rendering/normalization logic against a minimal,
// self-contained DOM shim so the rendering contract can be checked in plain
// Node (CI does not need browser binaries for this layer). The browser-level
// behavior (full page, downloads, screenshots) is covered separately by the
// Playwright smoke spec.

import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

/* ---------- Minimal DOM shim ---------- */

class FakeElement {
  constructor(tagName) {
    this.tagName = String(tagName).toUpperCase()
    this.children = []
    this.attributes = {}
    this.className = ''
    this._text = ''
    this.eventListeners = {}
  }

  set textContent(value) {
    this._text = value == null ? '' : String(value)
    this.children = []
  }

  get textContent() {
    if (this.children.length) return this.children.map((c) => c.textContent).join('')
    return this._text
  }

  setAttribute(key, value) {
    this.attributes[key] = String(value)
  }

  getAttribute(key) {
    return Object.prototype.hasOwnProperty.call(this.attributes, key) ? this.attributes[key] : null
  }

  appendChild(child) {
    this.children.push(child)
    return child
  }

  append(...nodes) {
    for (const node of nodes) this.children.push(node)
  }

  replaceChildren(...nodes) {
    this.children = nodes
  }

  addEventListener(type, handler) {
    ;(this.eventListeners[type] ||= []).push(handler)
  }

  // Test helpers (not part of the real DOM API).
  collect(predicate, acc = []) {
    if (predicate(this)) acc.push(this)
    for (const child of this.children) {
      if (child instanceof FakeElement) child.collect(predicate, acc)
    }
    return acc
  }
}

globalThis.CSS = { escape: (value) => String(value) }
globalThis.document = {
  readyState: 'complete',
  createElement: (tag) => new FakeElement(tag),
  querySelector: () => null, // makes module init() exit early
  addEventListener: () => {},
  body: new FakeElement('body'),
}

/* ---------- Test harness ---------- */

let failures = 0
function check(name, condition) {
  const ok = Boolean(condition)
  console.log(`${ok ? 'PASS' : 'FAIL'} - ${name}`)
  if (!ok) failures += 1
}

async function main() {
  const ec = await import('../src/evidence-console/evidence-console.js')
  const adapter = await import('../src/evidence-console/readiness-adapter.js')

  // ----- Pure verdict / evidence contract -----
  check('null reviewer decision never normalizes to PASS', ec.normalizeDecision(null) === null)
  check('unknown reviewer decision never normalizes to PASS', ec.normalizeDecision('approved') === null)
  check('explicit PASS recognized only when present', ec.normalizeDecision('pass') === 'PASS')
  check('empty array treated as no evidence', ec.hasValue([]) === false)
  check('numeric zero treated as real evidence', ec.hasValue(0) === true)

  const bundle = ec.buildReproduceBundle({ id: 'demo-x' }, { is_demo: true, claim_boundary: 'DEMO' })
  check('reproduce bundle carries demo flag + claim boundary', bundle.is_demo === true && bundle.claim_boundary === 'DEMO')

  // ----- Readiness rendering contract against the REAL artifact -----
  const artifactPath = path.join(
    rootDir,
    'implementation/phase1/release_evidence/productization/evidence_console_scope_status.json',
  )
  const raw = JSON.parse(fs.readFileSync(artifactPath, 'utf8'))
  const now = Date.parse(raw.generated_at) + 3 * 24 * 60 * 60 * 1000
  const readiness = adapter.normalizeReadiness(raw, { now })

  const readyContainer = new FakeElement('section')
  ec.renderReadiness(readyContainer, readiness)
  const readyText = readyContainer.textContent
  check('readiness panel shows BLOCKED gate', readyText.includes('BLOCKED'))
  check('readiness panel shows the source commit', readyText.includes('b883c03e'))
  check('readiness panel renders blocker entries', readyContainer.collect((n) => n.className === 'ec-blocker-list').length === 1)
  check('readiness panel renders the claim boundary text', readyText.includes('Evidence Console'))
  const commitNodes = readyContainer.collect((n) => n.getAttribute('data-ec-source-commit') != null)
  check('source commit exposes full sha via data attribute', commitNodes.length === 1 && commitNodes[0].getAttribute('data-ec-source-commit') === raw.source_commit_sha)
  const gateNodes = readyContainer.collect((n) => n.getAttribute('data-ec-gate') === 'BLOCKED')
  check('gate pill marked data-ec-gate=BLOCKED', gateNodes.length === 1)

  // ----- Missing readiness must render as unavailable, never READY -----
  const missing = adapter.normalizeReadiness(null, { now })
  const missingContainer = new FakeElement('section')
  ec.renderReadiness(missingContainer, missing)
  const missingText = missingContainer.textContent
  check('missing readiness shows unavailable state', missingText.toLowerCase().includes('unavailable'))
  check('missing readiness never shows READY/PASS', !missingText.includes('READY') && !missingText.includes('Launch: READY'))
  check('missing readiness marks gate=missing', missingContainer.collect((n) => n.getAttribute('data-ec-gate') === 'missing').length === 1)

  // ----- Stale readiness surfaces a stale freshness pill -----
  const staleNow = Date.parse(raw.generated_at) + 60 * 24 * 60 * 60 * 1000
  const stale = adapter.normalizeReadiness(raw, { now: staleNow })
  const staleContainer = new FakeElement('section')
  ec.renderReadiness(staleContainer, stale)
  check('stale readiness marks freshness=stale', staleContainer.collect((n) => n.getAttribute('data-ec-freshness') === 'stale').length === 1)

  if (failures > 0) {
    console.log(`\n${failures} DOM contract check(s) failed`)
    process.exitCode = 1
  } else {
    console.log('\nAll DOM contract checks passed')
  }
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
