import { document, check, type RcJobSummary, type RcObject } from './rcJobSchema'
import { scanRcHistoryFile, readRcHistoryRecord, type RcHistoryIndex } from './rcHistoryFile'

let file: Blob | null = null, index: RcHistoryIndex | null = null
let queue = Promise.resolve()
async function row(epoch: number): Promise<RcObject> {
  check(file && index && Number.isInteger(epoch) && epoch >= 0 && epoch < index.acceptedCount, 'history_epoch_invalid')
  return document(await readRcHistoryRecord(file, index, epoch + 1)).value.response
}
async function handle(data: any): Promise<void> {
  const { id, type } = data
  try {
    if (type === 'initialize') {
      check(!file && data.file instanceof Blob, 'history_initialize_invalid')
      file = data.file
      index = await scanRcHistoryFile(data.file, count => self.postMessage({ id, progress: count }))
      const request = index.header.request
      const summary: RcJobSummary = {
        resultHash: index.lastRecordHash, sourceRevision: index.header.canonical_model_checksum,
        targets: request.targets_m.slice(0, index.acceptedCount - Number(index.hasPreload)),
        hasPreload: index.hasPreload, constantLoads: request.constant_nodal_loads ?? [], control: index.control,
        reservedInvocations: 0, confirmedInvocations: 0, knownCoreCalls: index.knownCalls,
        knownNewtonIterations: index.knownNewton, unknownWork: true, artifactRoles: ['history'],
        historyFile: { status: index.status, declaredTargets: request.targets_m.length, bytes: data.file.size, unknownCalls: index.unknownCalls },
      }
      self.postMessage({ id, value: summary })
      return
    }
    check(file && index, 'history_unavailable')
    if (type === 'epoch') self.postMessage({ id, value: await row(data.index) })
    else if (type === 'materialPage') {
      check(Number.isInteger(data.start) && data.start >= 0 && data.start < index.acceptedCount
        && Number.isInteger(data.count) && data.count > 0 && data.count <= 20, 'history_page_invalid')
      const rows = []
      for (let i = data.start; i < Math.min(index.acceptedCount, data.start + data.count); i += 1) {
        const response = await row(i)
        const point = response.fiber_results.find((f: RcObject) => f.member_id === data.memberId
          && f.integration_point_index === data.integrationPoint && f.fiber_index === data.fiberIndex)
        check(point, 'history_material_missing')
        rows.push({ epoch: response.epoch, strain: point.strain, stress_MPa: point.stress_MPa, material_state: point.material_state })
      }
      self.postMessage({ id, value: rows })
    } else if (type === 'download') {
      check(data.role === 'history' && file.size === index.records[index.records.length - 1].end + 1, 'history_download_invalid')
      // Recheck original slices before returning the browser's immutable Blob.
      for (let i = 0; i < index.records.length; i += 1) await readRcHistoryRecord(file, index, i)
      self.postMessage({ id, value: new Blob([file], { type: 'application/x-ndjson' }) })
    } else throw new Error('rc_review_history_operation_invalid')
  } catch (error) {
    file = null; index = null
    self.postMessage({ id, error: error instanceof Error && /^rc_review_[a-z_]+$/.test(error.message)
      ? error.message : 'rc_review_history_invalid' })
  }
}
self.onmessage = ({ data }) => { queue = queue.then(() => handle(data)) }
