// Bridge to the existing structure viewer, reusing its published selection
// contract so the viewer needs no changes:
// - shared key `structural-viewer-selection-v1` (BroadcastChannel + localStorage);
// - deep-link query params `member` / `member_set`;
// - the viewer, on a channel message, re-reads localStorage and selects the
//   member, and on its own selection it posts to the channel + writes storage.
//
// Same-origin only (the viewer is served from our own origin).

export const VIEWER_SELECTION_KEY = 'structural-viewer-selection-v1'

export interface ViewerSelectionPayload {
  memberId: string
  memberIds: string[]
  memberSet: string[]
  selectionSetCount: number
  source: string
  viewerFamily: string
  updatedAt: string
}

export function buildSelectionPayload(memberId: string | null): ViewerSelectionPayload {
  const id = (memberId ?? '').trim()
  const ids = id ? [id] : []
  return {
    memberId: id,
    memberIds: ids,
    memberSet: ids,
    selectionSetCount: ids.length,
    source: 'workbench-v2',
    viewerFamily: 'workbench_v2',
    updatedAt: new Date().toISOString(),
  }
}

/** Extract a member id from a channel/storage payload (defensive). */
export function extractMemberId(data: unknown): string | null {
  if (!data || typeof data !== 'object') return null
  const r = data as Record<string, unknown>
  if (typeof r.memberId === 'string' && r.memberId.trim()) return r.memberId.trim()
  if (Array.isArray(r.memberIds)) {
    const first = r.memberIds.find((v) => typeof v === 'string' && v.trim())
    if (typeof first === 'string') return first.trim()
  }
  return null
}

/** Build the viewer iframe URL with a deep-link selection + optional project. */
export function buildViewerUrl(
  viewerPath: string,
  options: { projectId?: string | null; memberId?: string | null } = {},
): string {
  // Use a dummy base only to manipulate query params for a possibly-relative path.
  const url = new URL(viewerPath, 'https://local.invalid')
  if (options.projectId) url.searchParams.set('project', options.projectId)
  if (options.memberId) {
    url.searchParams.set('member', options.memberId)
    url.searchParams.set('member_set', options.memberId)
  }
  const qs = url.searchParams.toString()
  return qs ? `${viewerPath}?${qs}` : viewerPath
}

export interface ViewerBridge {
  /** Tell the viewer to focus/select a member (no-op for a repeat value). */
  focusMember(memberId: string | null): void
  /** Subscribe to selections coming from the viewer. Returns an unsubscribe fn. */
  onSelection(cb: (memberId: string | null) => void): () => void
  dispose(): void
}

/**
 * Create a viewer bridge. In a non-browser context (or when BroadcastChannel /
 * localStorage are unavailable) this degrades to a no-op bridge.
 */
export function createViewerBridge(): ViewerBridge {
  const hasWindow = typeof window !== 'undefined'
  const channel =
    hasWindow && typeof BroadcastChannel === 'function' ? new BroadcastChannel(VIEWER_SELECTION_KEY) : null
  let lastFocused: string | null = null
  const listeners = new Set<(memberId: string | null) => void>()

  const onChannel = (event: MessageEvent) => {
    const id = extractMemberId(event.data)
    listeners.forEach((cb) => cb(id))
  }
  const onStorage = (event: StorageEvent) => {
    if (event.key !== VIEWER_SELECTION_KEY || !event.newValue) return
    try {
      const id = extractMemberId(JSON.parse(event.newValue))
      listeners.forEach((cb) => cb(id))
    } catch {
      /* ignore malformed payloads */
    }
  }

  channel?.addEventListener('message', onChannel)
  if (hasWindow) window.addEventListener('storage', onStorage)

  return {
    focusMember(memberId) {
      const id = (memberId ?? '').trim() || null
      if (id === lastFocused) return
      lastFocused = id
      const payload = buildSelectionPayload(id)
      try {
        if (hasWindow) window.localStorage.setItem(VIEWER_SELECTION_KEY, JSON.stringify(payload))
      } catch {
        /* storage may be unavailable; channel still notifies */
      }
      channel?.postMessage(payload)
    },
    onSelection(cb) {
      listeners.add(cb)
      return () => listeners.delete(cb)
    },
    dispose() {
      channel?.removeEventListener('message', onChannel)
      if (hasWindow) window.removeEventListener('storage', onStorage)
      channel?.close()
      listeners.clear()
    },
  }
}
