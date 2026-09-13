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
        if (/^(price_order|learned_order)\/prefix\/[A-Za-z0-9_-]+\/(decision|request|row)\.json$/.test(relative) || ['price-table.json', 'plan.json', 'policy.json', 'historical-training.json', 'price_order/comparison.json', 'learned_order/comparison.json', 'exhaustive_oracle/comparison.json'].includes(relative) || /^pool\/[A-Za-z0-9_-]+\.json$/.test(relative) || /^(price_order|learned_order)\/decisions\/[0-9]{2}\.json$/.test(relative)) originals.set(relative, bytes)
        return bytes
      }
      const original = await read(base.href, 2 * 1024 ** 2)
      originals.set('result.json', original)
      review = await validateRcControlSearch(original, read)
      self.postMessage({ id, value: review })
    } else if (type === 'metadata' && review && ['result', 'plan', 'policy', 'historical-training', 'price-table'].includes(data.role)) {
      const bytes = originals.get(`${data.role}.json`)
      if (!bytes) throw new Error('missing original metadata')
      self.postMessage({ id, value: new Blob([bytes], { type: 'application/json' }) })
    } else if (type === 'pruningDownload' && review && ['experimental-rc-control-layout-cost-pruned-strategy.v1', 'experimental-rc-control-layout-staged-strategy.v1'].includes(review.report.schema_version)) {
      const pool = review.plan.pool.find((p: any) => p.candidate_id === data.candidate)
      const arm = review.report.arms[review.report.strategy]
      const decision = arm.cost_pruning.decisions.find((d: any) => d.candidate_id === data.candidate)
      const path = data.role === 'model' ? pool?.model_artifact.path : data.role === 'decision' && decision ? `${review.report.strategy}/${decision.artifact.path}` : null
      const bytes = path ? originals.get(path) : null
      if (!bytes) throw new Error('missing original pruning artifact')
      self.postMessage({ id, value: new Blob([bytes], { type: 'application/json' }) })
    } else if (type === 'prefixDownload' && review?.prefixes && Object.prototype.hasOwnProperty.call(review.prefixes, data.candidate)) {
      const prefix = review.prefixes[data.candidate], folder = `${review.report.strategy}/prefix/${data.candidate}`
      const bytes = ['decision', 'request', 'row'].includes(data.role) ? originals.get(`${folder}/${data.role}.json`)
        : ['model', 'result', 'checkpoint', 'verification'].includes(data.role) ? await verifiedStudyBytes((path, max, expected) => read(`${folder}/${path}`, max, expected), prefix.row, data.role) : null
      if (!bytes) throw new Error('missing original prefix artifact')
      self.postMessage({ id, value: new Blob([bytes], { type: 'application/json' }) })
    } else if (type === 'download' && review && Object.prototype.hasOwnProperty.call(review.designs, data.arm)) {
      const design = review.designs[data.arm]
      const row = design.report.rows.find((r: any) => r.candidate_id === data.candidate)
      const bytes = data.role === 'comparison' ? originals.get(`${data.arm}/comparison.json`)
        : row ? await verifiedStudyBytes((path, max, expected) => read(`${data.arm}/${path}`, max, expected), row, data.role, ['experimental-rc-control-layout-comparison.v1', 'experimental-rc-control-layout-cost-pruned-comparison.v1', 'experimental-rc-control-layout-staged-comparison.v1'].includes(design.report.schema_version) ? 'layout' : 'section') : null
      if (!bytes) throw new Error('missing original artifact')
      self.postMessage({ id, value: new Blob([bytes], { type: 'application/json' }) })
    } else throw new Error('invalid operation')
  } catch {
    review = null; originals.clear()
    self.postMessage({ id, error: 'rc_search_artifacts_invalid' })
  }
}
