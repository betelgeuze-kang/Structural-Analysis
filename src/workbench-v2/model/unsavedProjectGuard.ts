/** A mounted editor owns its guard. Readers must return the latest local state;
 * neither result polling nor a stale component cleanup may replace another owner.
 */
const guards = new Map<symbol, () => boolean>()

function blocks(reader: () => boolean): boolean {
  try { return reader() }
  catch { return true }
}

export function registerUnsavedProjectGuard(shouldBlock: () => boolean): () => void {
  const owner = Symbol('unsaved-project')
  guards.set(owner, shouldBlock)
  const beforeUnload = (event: BeforeUnloadEvent): void => {
    if (!blocks(shouldBlock)) return
    event.preventDefault()
    // Browsers supply their own text for reload/close confirmation.
    event.returnValue = ''
  }
  window.addEventListener('beforeunload', beforeUnload)
  return () => {
    guards.delete(owner)
    window.removeEventListener('beforeunload', beforeUnload)
  }
}

/** Used only for same-document navigation that would replace the current view.
 * Downloads and links opened in another tab do not go through this guard.
 */
export function confirmUnsavedProjectNavigation(): boolean {
  if (![...guards.values()].some(blocks)) return true
  return window.confirm('This RC project has changes since its last export or open. Leave this page and discard the local changes?')
}
