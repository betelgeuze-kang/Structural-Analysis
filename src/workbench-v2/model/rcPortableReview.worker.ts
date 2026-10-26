import { parseRcPortableReview, type RcPortableReviewDocument } from './rcPortableReviewSchema'
import { corotationalDetailMember, corotationalDetailSection, corotationalDetailFiber, corotationalDetailSectionPage, corotationalDetailFiberPage } from './rcCorotationalDetailReport'
import { rcResultGeometry } from './rcResultVisualization'

let current: RcPortableReviewDocument | null = null, initializing = false
const safe = (error: unknown) => error instanceof Error && /^(rc_portable_review_|rc_corotational_report_detail_)[a-z_]+$/.test(error.message)
  ? error.message : 'rc_portable_review_contract_invalid'
self.onmessage = async ({ data }) => {
  const { id, type } = data
  try {
    if (type === 'initialize') {
      if (current || initializing) throw new Error('rc_portable_review_already_initialized')
      initializing = true
      current = await parseRcPortableReview(data.bytes)
      self.postMessage({ id, value: { summary: current.summary, detailSummary: current.detailSummary } })
      return
    }
    if (!current) throw new Error('rc_portable_review_unavailable')
    const report = current.report
    let value: unknown
    if (type === 'state') {
      if (!Number.isSafeInteger(data.index) || data.index < 0 || data.index >= report.responses.length) throw new Error('rc_portable_review_state_invalid')
      value = report.responses[data.index]
    } else if (type === 'statePage') {
      if (!Number.isSafeInteger(data.start) || data.start < 0 || data.start >= report.responses.length
        || !Number.isSafeInteger(data.count) || data.count < 1 || data.count > 50) throw new Error('rc_portable_review_page_invalid')
      value = report.responses.slice(data.start, data.start + data.count).map(row => ({
        state_index: row.state_index, phase: row.phase, control_displacement_m: row.control_displacement_m,
        load_factor: row.load_factor, checkpoint_hash: row.checkpoint_hash,
      }))
    } else if (type === 'openDetails' || typeof type === 'string' && type.startsWith('detail')) {
      const detail = current.detail, original = current.detailReport
      if (!detail || !original || !current.detailSummary) throw new Error('rc_corotational_report_detail_unavailable')
      if (type === 'openDetails') value = current.detailSummary
      else if (type === 'detailMember') value = corotationalDetailMember(detail, data.state, data.member)
      else if (type === 'detailSection') value = corotationalDetailSection(detail, data.state, data.member, data.point)
      else if (type === 'detailFiber') value = corotationalDetailFiber(detail, data.state, data.member, data.point, data.fiber)
      else if (type === 'detailSectionPage') value = corotationalDetailSectionPage(detail, data.member, data.point, data.start, data.count)
      else if (type === 'detailFiberPage') value = corotationalDetailFiberPage(detail, data.member, data.point, data.fiber, data.start, data.count)
      else if (type === 'detailDownload') value = new Blob([original.bytes], { type: 'application/json' })
      else throw new Error('rc_corotational_report_detail_operation_invalid')
    } else if (type === 'geometry') value = rcResultGeometry(current.request)
    else if (type === 'requestDownload') value = new Blob([current.requestBytes], { type: 'application/json' })
    else if (type === 'reportDownload') value = new Blob([current.reportBytes], { type: 'application/json' })
    else throw new Error('rc_portable_review_operation_invalid')
    self.postMessage({ id, value })
  } catch (error) {
    if (type === 'initialize') { current = null; self.postMessage({ id, error: safe(error) }) }
    else self.postMessage({ id, operationError: safe(error) })
  }
}
