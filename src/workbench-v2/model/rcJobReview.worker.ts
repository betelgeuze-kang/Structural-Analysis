import { validateRcJobArtifacts, type RcArtifacts, type RcObject } from './rcJobSchema'

let artifacts: RcArtifacts = {}
let history: RcObject[] = []
let initialized = false

self.onmessage = async ({ data }) => {
  const { id, type } = data
  try {
    if (type === 'initialize') {
      if (initialized) throw new Error('rc_review_already_initialized')
      const review = await validateRcJobArtifacts(data.job, data.artifacts)
      artifacts = { ...data.artifacts, terminal: review.terminalBytes }
      history = review.history
      initialized = true
      self.postMessage({ id, value: review.summary })
      return
    }
    if (!initialized) throw new Error('rc_review_unavailable')
    if (type === 'epoch') {
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
    artifacts = {}; history = []; initialized = false
    const message = error instanceof Error && /^rc_review_[a-z_]+$/.test(error.message)
      ? error.message : 'rc_review_contract_invalid'
    self.postMessage({ id, error: message })
  }
}
