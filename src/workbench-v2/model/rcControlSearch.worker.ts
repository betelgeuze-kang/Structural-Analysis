import { validateRcControlSearch, type RcSearchReview } from './rcControlSearchSchema'
import { verifiedStudyBytes, type StudyRead } from './rcControlDesignSchema'
import { readBoundedJobBytes } from './jobTransport'

let review: RcSearchReview | null = null
const originals = new Map<string, Uint8Array>()
let read: StudyRead
let initialized = false
self.onmessage = async ({ data }) => {
  const { id, type } = data
  try {
    if (type === 'initialize' && !initialized) {
      initialized = true
      const base = new URL(data.url), directory = new URL('.', base)
      if (base.origin !== self.location.origin || !/^https?:$/.test(base.protocol) || base.search || base.hash || base.username || base.password) throw new Error('invalid origin')
      const headers = new Headers(data.headers); headers.set('Accept', 'application/json')
      read = async (relative, maximum, expected) => {
        const target = new URL(relative, base)
        if (target.origin !== base.origin || !target.pathname.startsWith(directory.pathname) || target.search || target.hash || target.username || target.password) throw new Error('invalid artifact path')
        const response = await fetch(target.href, { headers, credentials: 'include', cache: 'no-store', redirect: 'error' })
        if (!response.ok) { await response.body?.cancel(); throw new Error('artifact unavailable') }
        const bytes = await readBoundedJobBytes(response, maximum, 'rc search', expected)
        if (['plan.json', 'policy.json', 'historical-training.json', 'price_order/comparison.json', 'learned_order/comparison.json', 'exhaustive_oracle/comparison.json'].includes(relative)) originals.set(relative, bytes)
        return bytes
      }
      const original = await read(base.href, 2 * 1024 ** 2)
      originals.set('result.json', original)
      review = await validateRcControlSearch(original, read)
      self.postMessage({ id, value: review })
    } else if (type === 'metadata' && review && ['result', 'plan', 'policy', 'historical-training'].includes(data.role)) {
      const bytes = originals.get(`${data.role}.json`)
      if (!bytes) throw new Error('missing original metadata')
      self.postMessage({ id, value: new Blob([bytes], { type: 'application/json' }) })
    } else if (type === 'download' && review && Object.prototype.hasOwnProperty.call(review.designs, data.arm)) {
      const design = review.designs[data.arm]
      const row = design.report.rows.find((r: any) => r.candidate_id === data.candidate)
      const bytes = data.role === 'comparison' ? originals.get(`${data.arm}/comparison.json`)
        : row ? await verifiedStudyBytes((path, max, expected) => read(`${data.arm}/${path}`, max, expected), row, data.role) : null
      if (!bytes) throw new Error('missing original artifact')
      self.postMessage({ id, value: new Blob([bytes], { type: 'application/json' }) })
    } else throw new Error('invalid operation')
  } catch {
    review = null; originals.clear()
    self.postMessage({ id, error: 'rc_search_artifacts_invalid' })
  }
}
