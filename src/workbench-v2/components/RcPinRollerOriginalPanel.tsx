import { useRef, useState, type ReactElement } from 'react'
import {
  RC_PIN_ROLLER_FILE_LIMITS, reviewRcPinRollerOriginals,
  type RcPinRollerOriginals, type RcPinRollerReview, type RcPinRollerRole,
} from '../model/rcPinRollerOriginal'

const roles = ['model', 'request', 'result', 'checkpoint', 'verification'] as const
const labels: Record<RcPinRollerRole, string> = {
  model: 'Original neutral model', request: 'Original v4 request',
  result: 'Original API result', checkpoint: 'Original checkpoint',
  verification: 'CLI verify report',
}
const sizeLabel = (bytes: number) => bytes < 1024 * 1024
  ? `${bytes / 1024} KiB` : `${bytes / 1024 / 1024} MiB`

export function RcPinRollerOriginalPanel(): ReactElement {
  const [selected, setSelected] = useState<Partial<Record<RcPinRollerRole, File>>>({})
  const [review, setReview] = useState<RcPinRollerReview | null>(null)
  const [state, setState] = useState<'idle' | 'loading' | 'verified' | 'invalid'>('idle')
  const [error, setError] = useState('')
  const [step, setStep] = useState(0)
  const generation = useRef(0)

  async function checkFiles() {
    const ticket = ++generation.current
    setReview(null); setState('loading'); setError('')
    try {
      const files = {} as RcPinRollerOriginals
      for (const role of roles) {
        const file = selected[role]
        if (!file || file.size < 1 || file.size > RC_PIN_ROLLER_FILE_LIMITS[role]) throw new Error(`${role}_size_invalid`)
        files[role] = new Uint8Array(await file.arrayBuffer())
        if (ticket !== generation.current) return
      }
      const next = await reviewRcPinRollerOriginals(files)
      if (ticket !== generation.current) return
      setReview(next); setStep(next.preload ? -1 : 0); setState('verified')
    } catch (caught) {
      if (ticket !== generation.current) return
      setReview(null); setError(caught instanceof Error ? caught.message : 'invalid_original_bundle'); setState('invalid')
    }
  }
  function download(role: RcPinRollerRole) {
    if (!review) return
    const blob = new Blob([review.files[role]], { type: 'application/json' })
    const url = URL.createObjectURL(blob), anchor = document.createElement('a')
    anchor.href = url; anchor.download = selected[role]?.name || `${role}.json`
    document.body.append(anchor); anchor.click(); anchor.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  const response = review ? step === -1 ? review.preload : review.history[step] : null
  return <main className="wb2-section" style={{ maxWidth: 1100, margin: '0 auto', padding: '1rem', overflowWrap: 'anywhere' }}>
    <p><a href="#/workbench-v2">← Workbench v2</a></p>
    <section className="wb2-panel" data-rc-pin-roller-original={state}>
      <h1>RC pin/roller original bundle</h1>
      <p>Open five files from one initial, no-restart, experimental pin/roller direct-control bundle. The request must be the full typed v4 <code>to_dict()</code> JSON, including defaults. Files stay in this browser. The supplied <code>verify</code> report must bind their exact bytes and record a fresh Python source replay.</p>
      <p>This local reviewer caps result files at 8 MiB and verify reports at 1 MiB; the CLI result contract allows a larger result.</p>
      <p data-rc-pin-roller-authority>The CLI receipt is unsigned local consistency evidence. This browser checks its contents and byte bindings; it does not run the solver, independently validate the physics, or grant design approval.</p>
      <div style={{ display: 'grid', gap: '.75rem' }}>
        {roles.map(role => <label key={role}>{labels[role]} (.json, up to {sizeLabel(RC_PIN_ROLLER_FILE_LIMITS[role])})<br />
          <input type="file" accept=".json,application/json" data-rc-pin-roller-file={role} onChange={event => {
            const file = event.target.files?.[0]
            generation.current += 1; setReview(null); setState('idle'); setError('')
            setSelected(current => { const next = { ...current }; if (file) next[role] = file; else delete next[role]; return next })
          }} />
          {selected[role] ? <span> {selected[role]?.name}</span> : null}
        </label>)}
      </div>
      <p><button type="button" disabled={roles.some(role => !selected[role]) || state === 'loading'} onClick={checkFiles}>Review original bundle</button></p>
      {state === 'loading' ? <p role="status">Checking original bytes and supplied verification receipt…</p> : null}
      {state === 'invalid' ? <p role="alert">Original bundle unavailable: {error}</p> : null}
      {review ? <div data-rc-pin-roller-review>
        <h2>{review.status === 'ready' ? 'Complete original path' : 'Verified original prefix; path blocked'}</h2>
        <p>Pin <strong>{review.pin}</strong> restrains UX/UY; roller <strong>{review.roller}</strong> restrains UY. Exactly three reaction rows were checked in every accepted response{review.preload ? ' and the preload' : ''}.</p>
        <p>{review.history.length}/{review.targets.length} targets accepted · supplied verification replay: {review.verificationWork.attempted_step_count} attempted step(s), {review.verificationWork.known_newton_iteration_count} known Newton iteration(s).</p>
        <p data-rc-pin-roller-cost>Original run wall time, CPU time, and monetary cost: <strong>unknown</strong>. This verify-only receipt times verification separately; it has no original run timing.</p>
        <p>Result hash <code>{review.resultHash}</code><br />Verify report hash <code>{review.reportHash}</code></p>
        <label>Response to inspect{' '}
          <select value={step} onChange={event => setStep(Number(event.target.value))}>
            {review.preload ? <option value={-1}>Preload</option> : null}
            {review.history.map((row, i) => <option key={i} value={i}>Accepted step {i + 1} · target {review.targets[i]} m · epoch {row.epoch}</option>)}
          </select>
        </label>
        {response ? <table data-rc-pin-roller-reactions><caption>Original support reactions · N</caption>
          <thead><tr><th scope="col">Node</th><th scope="col">DOF</th><th scope="col">Reaction (N)</th></tr></thead>
          <tbody>{response.support_reactions.map((row: { node_id: string; dof: string; value_si: number }, i: number) => <tr key={i}><td>{row.node_id}</td><td>{row.dof}</td><td>{String(row.value_si)}</td></tr>)}</tbody>
        </table> : null}
        <h3>Original downloads</h3>
        <p>Each download uses the bytes checked above.</p>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '.5rem' }}>{roles.map(role => <button type="button" key={role} onClick={() => download(role)}>Download {labels[role].toLowerCase()}</button>)}</div>
      </div> : null}
    </section>
  </main>
}
