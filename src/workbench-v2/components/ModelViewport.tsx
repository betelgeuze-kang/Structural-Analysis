import { useEffect, useMemo, useRef, type ReactElement } from 'react'
import type { CaseModel } from '../model/caseSchema'
import type { DataMode } from '../model/workbenchState'
import { buildViewerUrl, createViewerBridge, type ViewerBridge } from '../model/viewerBridge'

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

  const bridgeRef = useRef<ViewerBridge | null>(null)
  const cbRef = useRef(onMemberSelected)
  cbRef.current = onMemberSelected

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
        {model.dofCount.toLocaleString()} DOF · {selectedMemberId ? `selected: ${selectedMemberId}` : 'no member selected'}
      </p>

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
