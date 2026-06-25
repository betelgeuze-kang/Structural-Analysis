// Structural Workbench — safe demo prototype controller.
//
// Safety contract (priority 2):
// - All shown values come from demo-case.json; nothing is hardcoded in markup.
// - There is no automated PASS anywhere. "NOT_EVALUATED" / "NOT_CONNECTED" map
//   to explicit UNAVAILABLE / MISSING states, never to a positive verdict.
// - Every node is built with createElement/textContent. innerHTML is never
//   used, so a user-supplied file name or review comment cannot execute as
//   HTML.
// - Six data states (DEMO / LIVE / STALE / BLOCKED / MISSING / UNAVAILABLE)
//   are distinguished by colour and label.

const CASE_URL = './demo-case.json'

/** The six canonical data states, with display label and CSS modifier. */
export const STATE_META = {
  DEMO: { label: 'DEMO', mod: 'is-demo', hint: 'Demonstration data' },
  LIVE: { label: 'LIVE', mod: 'is-live', hint: 'Live evidence attached' },
  STALE: { label: 'STALE', mod: 'is-stale', hint: 'Evidence is out of date' },
  BLOCKED: { label: 'BLOCKED', mod: 'is-blocked', hint: 'Gated / not connected' },
  MISSING: { label: 'MISSING', mod: 'is-missing', hint: 'Not present' },
  UNAVAILABLE: { label: 'UNAVAILABLE', mod: 'is-unavailable', hint: 'No value' },
}

export function hasValue(value) {
  if (value == null) return false
  if (typeof value === 'string') return value.trim() !== ''
  if (Array.isArray(value)) return value.length > 0
  return true
}

/** Map the top-level data_mode to a state. Unknown/empty -> UNAVAILABLE. */
export function mapDataMode(mode) {
  switch (String(mode || '').toLowerCase()) {
    case 'demo':
      return 'DEMO'
    case 'live':
      return 'LIVE'
    case 'stale':
      return 'STALE'
    default:
      return 'UNAVAILABLE'
  }
}

/**
 * Map an individual status/check value to one of the six states.
 * Critically, this never turns an un-evaluated value into a positive verdict.
 */
export function mapCheckState(value) {
  if (value === true) return 'LIVE'
  if (value === false) return 'BLOCKED'
  const token = String(value == null ? '' : value).trim().toUpperCase()
  switch (token) {
    case 'NOT_CONNECTED':
    case 'DISCONNECTED':
      return 'MISSING'
    case 'NOT_EVALUATED':
    case 'PENDING':
    case '':
      return 'UNAVAILABLE'
    case 'BLOCKED':
      return 'BLOCKED'
    case 'STALE':
      return 'STALE'
    case 'CONNECTED':
    case 'READY':
    case 'CONVERGED':
      return 'LIVE'
    default:
      // Unknown tokens are surfaced as UNAVAILABLE, never as a pass.
      return 'UNAVAILABLE'
  }
}

/** Build the rows rendered in the readiness/status panel. */
export function buildStatusRows(status) {
  const s = status && typeof status === 'object' ? status : {}
  return [
    { key: 'solver_connected', label: 'Solver connection', state: mapCheckState(s.solver_connected), raw: String(s.solver_connected) },
    { key: 'p0', label: 'P0 gate', state: mapCheckState(s.p0), raw: hasValue(s.p0) ? String(s.p0) : '—' },
    { key: 'p1', label: 'P1 gate', state: mapCheckState(s.p1), raw: hasValue(s.p1) ? String(s.p1) : '—' },
    { key: 'gpu', label: 'GPU / HIP', state: mapCheckState(s.gpu), raw: hasValue(s.gpu) ? String(s.gpu) : '—' },
  ]
}

/** Build the demo export bundle (kept demo-flagged, never a validated artifact). */
export function buildDemoBundle(model, { reviewComment, selectedFileName } = {}) {
  return {
    schema_version: 'workbench-demo-export.v1',
    data_mode: model && model.data_mode ? model.data_mode : 'demo',
    is_demo: (model && String(model.data_mode).toLowerCase() === 'demo') || true,
    claim_boundary: model && model.claim_boundary ? model.claim_boundary : null,
    exported_at: new Date().toISOString(),
    project: (model && model.project) || null,
    case: (model && model.case) || null,
    status: (model && model.status) || null,
    reviewer_note: hasValue(reviewComment) ? String(reviewComment) : null,
    selected_input_file: hasValue(selectedFileName) ? String(selectedFileName) : null,
  }
}

/* ---------- DOM helpers (no innerHTML) ---------- */

function el(tag, { className, text, attrs } = {}) {
  const node = document.createElement(tag)
  if (className) node.className = className
  if (text != null) node.textContent = String(text)
  if (attrs) {
    for (const [k, v] of Object.entries(attrs)) {
      if (v != null) node.setAttribute(k, String(v))
    }
  }
  return node
}

/** Render a coloured + labelled state chip. */
export function createStateChip(state, { srLabel } = {}) {
  const meta = STATE_META[state] || STATE_META.UNAVAILABLE
  const chip = el('span', {
    className: `wb-chip wb-chip--${meta.mod}`,
    text: meta.label,
    attrs: { 'data-state': state, title: meta.hint },
  })
  if (srLabel) chip.setAttribute('aria-label', `${srLabel}: ${meta.label} — ${meta.hint}`)
  else chip.setAttribute('aria-label', `${meta.label} — ${meta.hint}`)
  return chip
}

function renderModeBadge(container, model) {
  if (!container) return
  container.replaceChildren()
  const state = mapDataMode(model && model.data_mode)
  const badge = createStateChip(state, { srLabel: 'Data mode' })
  badge.classList.add('wb-mode-badge')
  badge.setAttribute('data-wb-mode-badge', '')
  container.appendChild(badge)
}

function renderClaimBoundary(container, model) {
  if (!container) return
  container.replaceChildren()
  const text = model && hasValue(model.claim_boundary)
    ? model.claim_boundary
    : 'Demo prototype. No solver evidence attached; values are illustrative and are not a verdict.'
  container.appendChild(el('strong', { text: 'Claim boundary: ' }))
  container.appendChild(document.createTextNode(text))
}

function renderProject(container, model) {
  if (!container) return
  container.replaceChildren()
  const project = (model && model.project) || {}
  const kase = (model && model.case) || {}
  container.appendChild(el('h2', { className: 'wb-project-name', text: hasValue(project.name) ? project.name : 'Untitled project' }))
  const meta = [kase.label, kase.structure_family, kase.load_combination].filter((v) => hasValue(v))
  container.appendChild(el('p', { className: 'wb-project-meta', text: meta.length ? meta.join(' · ') : 'No case metadata' }))
}

function renderStatusPanel(container, model) {
  if (!container) return
  container.replaceChildren()
  const rows = buildStatusRows(model && model.status)
  const list = el('ul', { className: 'wb-status-list', attrs: { 'aria-label': 'Readiness status' } })
  rows.forEach((row) => {
    const li = el('li', { className: 'wb-status-row' })
    li.appendChild(el('span', { className: 'wb-status-label', text: row.label }))
    li.appendChild(el('span', { className: 'wb-status-raw', text: row.raw }))
    li.appendChild(createStateChip(row.state, { srLabel: row.label }))
    list.appendChild(li)
  })
  container.appendChild(list)
}

function renderReviewDecision(container) {
  if (!container) return
  container.replaceChildren()
  // There is intentionally no automated verdict in demo mode.
  container.appendChild(createStateChip('UNAVAILABLE', { srLabel: 'Automated verdict' }))
  container.appendChild(el('p', {
    className: 'wb-note',
    text: 'No automated reviewer result is inferred from demo data without solver evidence.',
  }))
}

function wireReviewInputs({ fileInput, fileNameOut, commentInput, commentOut }) {
  if (fileInput && fileNameOut) {
    fileInput.addEventListener('change', () => {
      const file = fileInput.files && fileInput.files[0]
      // Display the chosen name as text only — never as markup.
      fileNameOut.textContent = file ? file.name : 'No file selected'
    })
  }
  if (commentInput && commentOut) {
    const update = () => {
      // textContent assignment ensures any HTML/script in the comment is inert.
      commentOut.textContent = hasValue(commentInput.value) ? commentInput.value : 'No reviewer note entered.'
    }
    commentInput.addEventListener('input', update)
    update()
  }
}

function wireExport(button, getModel, getInputs) {
  if (!button) return
  button.addEventListener('click', () => {
    const bundle = buildDemoBundle(getModel(), getInputs())
    const blob = new Blob([JSON.stringify(bundle, null, 2)], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const link = el('a', { attrs: { href: url, download: 'workbench_demo_bundle.json' } })
    document.body.appendChild(link)
    link.click()
    link.remove()
    URL.revokeObjectURL(url)
  })
}

/* ---------- Bootstrap ---------- */

export async function renderWorkbench(root, model) {
  renderModeBadge(root.querySelector('[data-wb-mode]'), model)
  renderClaimBoundary(root.querySelector('[data-wb-claim]'), model)
  renderProject(root.querySelector('[data-wb-project]'), model)
  renderStatusPanel(root.querySelector('[data-wb-status]'), model)
  renderReviewDecision(root.querySelector('[data-wb-verdict]'))
}

async function init() {
  const root = document.querySelector('[data-wb-root]')
  if (!root) return

  let model = null
  try {
    const response = await fetch(CASE_URL, { cache: 'no-store' })
    if (!response.ok) throw new Error(`HTTP ${response.status}`)
    model = await response.json()
  } catch (error) {
    const claim = root.querySelector('[data-wb-claim]')
    if (claim) {
      claim.replaceChildren()
      claim.appendChild(el('strong', { text: 'Demo data unavailable: ' }))
      claim.appendChild(document.createTextNode(String((error && error.message) || error)))
    }
    const mode = root.querySelector('[data-wb-mode]')
    if (mode) {
      mode.replaceChildren()
      mode.appendChild(createStateChip('MISSING', { srLabel: 'Data mode' }))
    }
    return
  }

  await renderWorkbench(root, model)

  wireReviewInputs({
    fileInput: root.querySelector('[data-wb-file]'),
    fileNameOut: root.querySelector('[data-wb-file-name]'),
    commentInput: root.querySelector('[data-wb-comment]'),
    commentOut: root.querySelector('[data-wb-comment-preview]'),
  })

  wireExport(
    root.querySelector('[data-wb-export]'),
    () => model,
    () => ({
      reviewComment: (root.querySelector('[data-wb-comment]') || {}).value,
      selectedFileName: (root.querySelector('[data-wb-file-name]') || {}).textContent,
    }),
  )
}

if (typeof document !== 'undefined') {
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init)
  } else {
    init()
  }
}
