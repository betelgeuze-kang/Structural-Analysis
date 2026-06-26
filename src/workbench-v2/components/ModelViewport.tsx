import { useEffect, useMemo, useRef, useState, type ReactElement } from 'react'
import type { CaseModel } from '../model/caseSchema'
import type { DataMode } from '../model/workbenchState'
import { buildViewerUrl, createViewerBridge, type ViewerBridge } from '../model/viewerBridge'
import { CopyButton } from './CopyButton'

interface ModelViewportProps {
  model: CaseModel
  selectedMemberId: string | null
  onMemberSelected: (memberId: string | null) => void
  dataMode: DataMode
  sourcePath: string
  sourceCommit: string
  projectId?: string | null
}

const VIEWER_RELATIVE = 'src/structure-viewer/index.html'

export function ModelViewport({
  model,
  selectedMemberId,
  onMemberSelected,
  dataMode,
  sourcePath,
  sourceCommit,
  projectId,
}: ModelViewportProps): ReactElement {
  const base = (typeof import.meta !== 'undefined' && import.meta.env?.BASE_URL) || '/'
  const viewerSrc = useMemo(() => buildViewerUrl(`${base}${VIEWER_RELATIVE}`, { projectId }), [base, projectId])
  const deepLink = useMemo(
    () => buildViewerUrl(`${base}${VIEWER_RELATIVE}`, { projectId, memberId: selectedMemberId }),
    [base, projectId, selectedMemberId],
  )

  const bridgeRef = useRef<ViewerBridge | null>(null)
  const cbRef = useRef(onMemberSelected)
  cbRef.current = onMemberSelected
  const [memberInput, setMemberInput] = useState('')

  // Subscribe once: viewer selection -> workbench.
  useEffect(() => {
    const bridge = createViewerBridge()
    bridgeRef.current = bridge
    const unsubscribe = bridge.onSelection((id) => cbRef.current(id))
    return () => {
      unsubscribe()
      bridge.dispose()
      bridgeRef.current = null
    }
  }, [])

  // workbench selection -> viewer (the bridge guards against repeats).
  useEffect(() => {
    bridgeRef.current?.focusMember(selectedMemberId)
  }, [selectedMemberId])

  function focusFromInput(): void {
    const id = memberInput.trim()
    if (id) onMemberSelected(id)
  }

  return (
    <section className="wb2-panel wb2-viewport" aria-labelledby="wb2-viewport-title">
      <h2 id="wb2-viewport-title" className="wb2-panel__title">Model viewport</h2>

      <div className="wb2-viewport-frame">
        <iframe
          className="wb2-viewport-iframe"
          src={viewerSrc}
          title="Structural model viewer"
          sandbox="allow-scripts allow-same-origin"
          loading="lazy"
        />
      </div>

      <p className="wb2-viewport-meta">
        {model.nodeCount.toLocaleString()} nodes · {model.elementCount.toLocaleString()} elements ·{' '}
        {model.dofCount.toLocaleString()} DOF
      </p>

      {/* Selection inspector + manual focus. Selection round-trips with the
          viewer through the shared channel; this control drives and reflects it. */}
      <div className="wb2-member-inspector" data-wb2-member-inspector>
        <div className="wb2-member-current">
          <span className="wb2-member-current__label">Selected member</span>
          {selectedMemberId ? (
            <code className="wb2-mono" data-wb2-selected-member>{selectedMemberId}</code>
          ) : (
            <span className="wb2-member-none" data-wb2-selected-member="">none selected</span>
          )}
        </div>

        <form
          className="wb2-member-focus"
          onSubmit={(e) => {
            e.preventDefault()
            focusFromInput()
          }}
        >
          <label className="wb2-member-focus__field">
            <span className="wb2-member-focus__label">Focus member in viewer</span>
            <input
              type="text"
              className="wb2-review-input"
              value={memberInput}
              placeholder="member id (e.g. C12)"
              data-wb2-member-input
              onChange={(e) => setMemberInput(e.target.value)}
            />
          </label>
          <div className="wb2-member-focus__actions">
            <button type="submit" className="wb2-btn" data-wb2-member-focus disabled={!memberInput.trim()}>
              Focus
            </button>
            <button
              type="button"
              className="wb2-mode-btn"
              data-wb2-member-clear
              disabled={!selectedMemberId}
              onClick={() => onMemberSelected(null)}
            >
              Clear
            </button>
            <CopyButton value={deepLink} label="Copy viewer link" />
          </div>
        </form>
      </div>

      <dl className="wb2-kv wb2-viewport-prov">
        <dt>Analysis source</dt><dd><code className="wb2-mono">{sourcePath}</code></dd>
        <dt>Source commit</dt><dd><code className="wb2-mono">{sourceCommit.slice(0, 12)}</code></dd>
      </dl>

      <p className="wb2-note">
        Selection is synced both ways with the viewer via the shared selection channel.
        {dataMode === 'demo'
          ? ' In demo mode the viewer shows its own sample model — not the same artifact as this analysis case — so the two provenances are shown independently and never treated as matching.'
          : ' Provenance must match the analysis source before results are read as the same model.'}
      </p>
    </section>
  )
}
