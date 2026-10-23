import { document, validateRcJobArtifacts, type RcArtifacts, type RcObject, type RcQuantityReportSource, type RcJobSummary } from './rcJobSchema'
import { validateRcQuantityReport } from './rcQuantityReportSchema'
import { fixedRcScenarioSummary } from './rcScenarioComparison'
import type { WorkbenchJobView } from './jobSchema'
import { rcMaterialHistoryPage, rcResultGeometry, rcSectionHistoryPage } from './rcResultVisualization'

let artifacts: RcArtifacts = {}
let history: RcObject[] = []
let initialized = false
let quantitySource: RcQuantityReportSource | null = null
const quantityBytes = new Map<string, Uint8Array>()
let comparisonSource: { request: RcObject; job: WorkbenchJobView; summary: RcJobSummary } | null = null

self.onmessage = async ({ data }) => {
  const { id, type } = data
  try {
    if (type === 'initialize') {
      if (initialized) throw new Error('rc_review_already_initialized')
      const review = await validateRcJobArtifacts(data.job, data.artifacts, data.tenantId)
      artifacts = { ...data.artifacts, terminal: review.terminalBytes }
      history = review.history
      quantitySource = review.quantitySource
      comparisonSource = { request: document(data.artifacts.request).value, job: data.job, summary: review.summary }
      initialized = true
      self.postMessage({ id, value: review.summary })
      return
    }
    if (!initialized) throw new Error('rc_review_unavailable')
    if (type === 'geometry' || type === 'materialPage' || type === 'sectionPage') {
      // Optional visualization projections cannot replace or dispose the
      // original validated numerical review when a selector is unavailable.
      try {
        if (!comparisonSource) throw new Error('rc_review_unavailable')
        const value = type === 'geometry' ? rcResultGeometry(comparisonSource.request)
          : type === 'materialPage' ? rcMaterialHistoryPage(history, data.memberId, data.integrationPoint, data.fiberIndex, data.start, data.count)
            : rcSectionHistoryPage(history, data.memberId, data.integrationPoint, data.start, data.count)
        self.postMessage({ id, value })
      } catch (error) {
        const message = error instanceof Error && /^rc_review_[a-z_]+$/.test(error.message) ? error.message : 'rc_review_projection_invalid'
        self.postMessage({ id, operationError: message })
      }
      return
    }
    if (type === 'quantityReport' || type === 'quantityDownload') {
      // A failed companion is local to this RPC. It cannot dispose or replace
      // the previously validated original source and numerical review.
      try {
        if (type === 'quantityReport') {
          if (!quantitySource || !(data.bytes instanceof Uint8Array)) throw new Error('rc_review_quantity_source_unavailable')
          const review = await validateRcQuantityReport(data.bytes, quantitySource, data.reference)
          quantityBytes.delete(review.report_id)
          quantityBytes.set(review.report_id, data.bytes)
          // Bound retained exact-download bytes independently of original arrays.
          while (quantityBytes.size > 8) quantityBytes.delete(quantityBytes.keys().next().value!)
          self.postMessage({ id, value: review })
        } else {
          const bytes = quantityBytes.get(data.reportId)
          if (!bytes) throw new Error('rc_review_quantity_download_unavailable')
          self.postMessage({ id, value: new Blob([bytes], { type: 'application/json' }) })
        }
      } catch (error) {
        const message = error instanceof Error && /^rc_review_[a-z_]+$/.test(error.message)
          ? error.message : 'rc_review_quantity_contract_invalid'
        self.postMessage({ id, quantityError: message })
      }
      return
    }
    if (type === 'comparisonSummary') {
      if (!comparisonSource) throw new Error('rc_review_unavailable')
      self.postMessage({ id, value: fixedRcScenarioSummary(comparisonSource.request, comparisonSource.job, comparisonSource.summary, history) })
    } else if (type === 'epoch') {
      if (!Number.isInteger(data.index) || data.index < 0 || data.index >= history.length) throw new Error('rc_review_epoch_invalid')
      self.postMessage({ id, value: history[data.index] })
    } else if (type === 'material') {
      const { memberId, integrationPoint, fiberIndex } = data
      const rows = history.map((row) => {
        const point = row.fiber_results.find((f: RcObject) => f.member_id === memberId
          && f.integration_point_index === integrationPoint && f.fiber_index === fiberIndex)
        if (!point) throw new Error('rc_review_material_missing')
        return { epoch: row.epoch, strain: point.strain, stress_MPa: point.stress_MPa, material_state: point.material_state }
      })
      self.postMessage({ id, value: rows })
    } else if (type === 'download') {
      const bytes = artifacts[data.role]
      if (!bytes) throw new Error('rc_review_artifact_missing')
      self.postMessage({ id, value: new Blob([bytes], { type: 'application/json' }) })
    } else throw new Error('rc_review_operation_invalid')
  } catch (error) {
    artifacts = {}; history = []; initialized = false; quantitySource = null; quantityBytes.clear(); comparisonSource = null
    const message = error instanceof Error && /^rc_review_[a-z_]+$/.test(error.message)
      ? error.message : 'rc_review_contract_invalid'
    self.postMessage({ id, error: message })
  }
}
