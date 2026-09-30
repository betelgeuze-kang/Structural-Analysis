import { validateRcDesignStudy, verifiedStudyBytes, type RcDesignReview, type StudyRead } from './rcControlDesignSchema'
import { readBoundedJobBytes } from './jobTransport'

let review: RcDesignReview | null = null
let original: Uint8Array | null = null
let read: StudyRead
self.onmessage = async ({ data }) => {
  const { id, type } = data
  try {
    if (type === 'initialize') {
      if (review) throw new Error('already initialized')
      const base = new URL(data.url)
      if (base.origin !== self.location.origin || base.search || base.hash || base.username || base.password) throw new Error('invalid origin')
      const headers = new Headers(data.headers)
      headers.set('Accept', 'application/json')
      read = async (relative, maximum, expected) => {
        const target = new URL(relative, base)
        if (target.origin !== base.origin || !target.pathname.startsWith(new URL('.', base).pathname)) throw new Error('invalid artifact path')
        const response = await fetch(target.href, { headers, credentials: 'include', cache: 'no-store', redirect: 'error' })
        if (!response.ok) { await response.body?.cancel(); throw new Error('artifact unavailable') }
        return readBoundedJobBytes(response, maximum, 'rc study', expected)
      }
      original = await read(base.href, 2 * 1024 ** 2)
      review = await validateRcDesignStudy(original, read)
      self.postMessage({ id, value: review })
    } else if (type === 'download' && review && original) {
      const row = review.report.rows.find((r: any) => r.candidate_id === data.candidate)
      const raw = data.role === 'comparison' ? original : row ? await verifiedStudyBytes(read, row, data.role) : null
      if (!raw) throw new Error('missing artifact')
      self.postMessage({ id, value: new Blob([raw], { type: 'application/json' }) })
    } else throw new Error('invalid operation')
  } catch {
    review = null; original = null
    self.postMessage({ id, error: 'rc_design_artifacts_invalid' })
  }
}
