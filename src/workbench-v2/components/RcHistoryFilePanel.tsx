import { useEffect, useState, type ReactElement } from 'react'
import { loadRcHistoryFileReview } from '../model/rcHistoryFileReview'
import type { RcJobReview } from '../model/rcJobReview'
import { RcJobResultPanel } from './RcJobResultPanel'

export function RcHistoryFilePanel(): ReactElement {
  const [file, setFile] = useState<File | null>(null)
  const [review, setReview] = useState<RcJobReview | null>(null)
  const [state, setState] = useState('idle'), [count, setCount] = useState(0)
  useEffect(() => {
    if (!file) return
    const controller = new AbortController()
    let loaded: RcJobReview | null = null
    setReview(null); setState('loading'); setCount(0)
    loadRcHistoryFileReview(file, controller.signal, n => { if (!controller.signal.aborted) setCount(n) }).then(value => {
      loaded = value
      if (controller.signal.aborted) { value.dispose(); return }
      value.onFailure(() => { if (!controller.signal.aborted) { setReview(null); setState('invalid') } })
      setReview(value); setState('verified')
    }).catch(() => { if (!controller.signal.aborted) { setReview(null); setState('invalid') } })
    return () => { controller.abort(); loaded?.dispose() }
  }, [file])
  return <details className="wb2-panel" data-rc-history-file={state} style={{ minWidth: 0, maxWidth: '100%' }}>
    <summary>Open RC history file</summary>
    <p>Inspect a saved authored RC history, including constant-load preload, displacements, forces and material states. The file stays on this device.</p>
    <label>RC history file (.ndjson, up to 512 MiB){' '}
      <input type="file" accept=".ndjson" onChange={event => {
        const selected = event.target.files?.[0] ?? null
        setReview(null); setState(selected ? 'loading' : 'idle'); setFile(selected); event.target.value = ''
      }} style={{ maxWidth: '100%' }} />
    </label>
    {file ? <p style={{ overflowWrap: 'anywhere' }}>{file.name}</p> : null}
    {state === 'loading' ? <p role="status">Checking stored history: {count} steps…</p> : null}
    {state === 'invalid' ? <p role="alert">RC history unavailable. The file is incomplete, unsupported or its stored bindings could not be verified.</p> : null}
    {review ? <RcJobResultPanel key={review.summary.resultHash} jobId="local-history" review={review} /> : null}
  </details>
}
