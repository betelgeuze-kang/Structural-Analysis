import { validateRcStrategyCohort, type RcCohortReview } from './rcStrategyCohortSchema'
import { readBoundedJobBytes } from './jobTransport'

let review: RcCohortReview | null = null
let initialized = false
const originals = new Map<string, Uint8Array>()
self.onmessage = async ({ data }) => {
  const { id, type } = data
  try {
    if (type === 'initialize' && !initialized) {
      initialized = true
      const base = new URL(data.url), directory = new URL('.', base)
      if (base.origin !== self.location.origin || !/^https?:$/.test(base.protocol) || base.search || base.hash || base.username || base.password) throw new Error('invalid origin')
      const headers = new Headers(data.headers); headers.set('Accept', 'application/json')
      const read = async (path: string, maximum: number, expected?: number) => {
        const target = new URL(path, base)
        if (target.origin !== base.origin || !target.pathname.startsWith(directory.pathname) || target.search || target.hash || target.username || target.password) throw new Error('invalid path')
        const response = await fetch(target.href, { headers, credentials: 'include', cache: 'no-store', redirect: 'error' })
        if (!response.ok) { await response.body?.cancel(); throw new Error('artifact unavailable') }
        const bytes = await readBoundedJobBytes(response, maximum, 'rc cohort', expected)
        if (path === 'cohort.json' || path === 'process-observations.json' || path.endsWith('/strategy-runtime.json')) originals.set(path, bytes)
        return bytes
      }
      const raw = await read(base.href, 2 * 1024 ** 2)
      originals.set('cohort.json', raw)
      review = await validateRcStrategyCohort(raw, read)
      self.postMessage({ id, value: review })
    } else if (type === 'download' && review && (data.path === 'cohort.json' || (data.path === 'process-observations.json' && review.processCost) || review.executions.some(e => e.runtimePath === data.path))) {
      const raw = originals.get(data.path)
      if (!raw) throw new Error('missing original')
      self.postMessage({ id, value: new Blob([raw], { type: 'application/json' }) })
    } else throw new Error('request unavailable')
  } catch { originals.clear(); review = null; self.postMessage({ id, error: 'rc_cohort_unavailable' }) }
}
