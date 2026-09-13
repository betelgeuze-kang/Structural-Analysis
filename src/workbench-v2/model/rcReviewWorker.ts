import type { JobAuthorizationProvider } from './jobTransport'

export async function openRcReviewWorker(createWorker: () => Worker, url: string, signal: AbortSignal, authorize?: JobAuthorizationProvider) {
  const target = new URL(url, location.href)
  if (target.origin !== location.origin || !/^https?:$/.test(target.protocol) || target.username || target.password || target.search || target.hash) throw new Error('rc_design_endpoint_invalid')
  const headers: Record<string, string> = {}
  if (authorize) {
    let credentials
    try { credentials = await authorize({ statusUrl: target.href, signal }) } catch { throw new Error('rc_design_authorization_unavailable') }
    if (!credentials || typeof credentials.tenantId !== 'string' || typeof credentials.bearerToken !== 'string'
      || !/^[\x21-\x7e]{1,256}$/.test(credentials.tenantId) || !/^[\x21-\x7e]{1,4096}$/.test(credentials.bearerToken)) throw new Error('rc_design_authorization_invalid')
    headers['X-Structural-Tenant'] = credentials.tenantId; headers.Authorization = `Bearer ${credentials.bearerToken}`
  }
  signal.throwIfAborted()
  const worker = createWorker()
  const pending = new Map<number, { resolve: (value: any) => void; reject: (error: Error) => void; timer: ReturnType<typeof setTimeout> }>()
  const listeners = new Set<() => void>()
  let stopped = false, next = 0
  const dispose = () => {
    if (stopped) return
    stopped = true; worker.terminate(); signal.removeEventListener('abort', dispose)
    for (const item of pending.values()) { clearTimeout(item.timer); item.reject(new Error('rc_design_unavailable')) }
    pending.clear(); for (const listener of listeners) listener(); listeners.clear()
  }
  worker.onerror = dispose; worker.onmessageerror = dispose
  signal.addEventListener('abort', dispose, { once: true })
  worker.onmessage = ({ data }) => {
    const item = pending.get(data.id)
    if (!item) return
    if (data.error) { dispose(); return }
    pending.delete(data.id); clearTimeout(item.timer); item.resolve(data.value)
  }
  const call = <T>(type: string, payload: object): Promise<T> => new Promise((resolve, reject) => {
    if (stopped) { reject(new Error('rc_design_unavailable')); return }
    const id = ++next
    pending.set(id, { resolve, reject, timer: setTimeout(dispose, 60000) })
    try { worker.postMessage({ id, type, ...payload }) } catch { dispose() }
  })
  return { call, dispose, initialize: <T>() => call<T>('initialize', { url: target.href, headers }), onFailure(listener: () => void) { if (stopped) listener(); else listeners.add(listener); return () => { listeners.delete(listener) } } }
}
