import { expect, test } from '@playwright/test'
import { readFileSync } from 'node:fs'
import { gunzipSync } from 'node:zlib'
import { createHash } from 'node:crypto'
import { scanRcHistoryFile, readRcHistoryRecord, RC_HISTORY_FILE_LIMIT } from '../../src/workbench-v2/model/rcHistoryFile'
import { fields } from '../../src/workbench-v2/model/rcJobSchema'

const raw = gunzipSync(readFileSync('tests/frontend/fixtures/rc-fiber-history-stream/history.ndjson.gz'))
const originals = raw.toString().trimEnd().split('\n')
const digest = (s: string | Uint8Array) => `sha256:${createHash('sha256').update(s).digest('hex')}`
function prefix(count = 3): Blob { return new Blob([originals.slice(0, count).join('\n') + '\n']) }
function changeField(raw: string, key: string, value: string): string {
  return `{${[...fields(raw)].map(([k, v]) => k === key ? `${JSON.stringify(k)}:${value}` : v.member).join(',')}}`
}
function reseal(raw: string): string {
  const unsigned = `{${[...fields(raw)].filter(([k]) => k !== 'record_hash').map(([, v]) => v.member).join(',')}}`
  return changeField(raw, 'record_hash', JSON.stringify(digest(unsigned)))
}
function changedResponse(edit: (row: any) => void): Blob {
  const row = JSON.parse(originals[2]).response
  edit(row)
  const changed = reseal(changeField(originals[2], 'response', JSON.stringify(row)))
  return new Blob([originals[0] + '\n' + originals[1] + '\n' + changed + '\n'])
}
test('history file indexes 1010 original targets and reads bounded slices without retaining responses', async () => {
  test.setTimeout(60000)
  const reads: number[] = []
  class SlicedOnly extends Blob {
    override arrayBuffer(): Promise<ArrayBuffer> { throw new Error('whole file read forbidden') }
    override slice(start = 0, end = this.size, type = ''): Blob {
      reads.push(end - start)
      return super.slice(start, end, type)
    }
  }
  const file = new SlicedOnly([raw]), index = await scanRcHistoryFile(file)
  expect(index.status).toBe('complete')
  expect(index.acceptedCount).toBe(1011)
  expect(index.records).toHaveLength(1012)
  expect(index.knownCalls).toBe(1011)
  expect(index.knownNewton).toBe(2022)
  expect(index.unknownCalls).toBe(0)
  expect(index.control).toEqual({ node_id: 'N2', component: 'UY', unit: 'm' })
  expect(index.records.every(r => Object.keys(r).sort().join(',') === 'end,hash,start')).toBe(true)
  expect(Math.max(...reads)).toBeLessThanOrEqual(256 * 1024)
  for (const n of [0, 1, 255, 256, 1011]) {
    expect(Buffer.from(await readRcHistoryRecord(file, index, n)).toString()).toBe(originals[n])
  }
})
test('history file preserves a valid prefix without claiming completion', async () => {
  const index = await scanRcHistoryFile(prefix())
  expect(index.status).toBe('prefix')
  expect(index.acceptedCount).toBe(2)
  expect(index.header.request.targets_m).toHaveLength(1010)
})
for (const [name, build] of [
  ['truncated last record', () => new Blob([originals[0] + '\n' + originals[1].slice(0, -1)])],
  ['missing newline', () => new Blob([originals[0] + '\n' + originals[1]])],
  ['blank record', () => new Blob([originals[0] + '\n\n'])],
  ['reordered records', () => new Blob([originals[0] + '\n' + originals[2] + '\n'])],
  ['repeated record', () => new Blob([originals[0] + '\n' + originals[1] + '\n' + originals[1] + '\n'])],
  ['duplicate key', () => new Blob([originals[0].replace('"claims":', '"claims":{},"claims":') + '\n' + originals[1] + '\n'])],
  ['header authority promotion', () => new Blob([originals[0].replace('"design_authority":false', '"design_authority":true') + '\n' + originals[1] + '\n'])],
] as const) {
  test(`history file rejects ${name}`, async () => { await expect(scanRcHistoryFile(build())).rejects.toThrow() })
}
for (const [name, edit] of [
  ['displacement', (r: any) => { r.node_displacements[1].UX_m += 1 }],
  ['support reaction', (r: any) => { r.support_reactions[0].value_si += 1 }],
  ['member force', (r: any) => { r.member_end_forces[0].local_end_i.FX_N += 1 }],
  ['section curvature', (r: any) => { r.section_results[0].curvature_z_per_m += 1 }],
  ['fiber stress', (r: any) => { r.fiber_results[0].stress_MPa += 1 }],
  ['material state', (r: any) => { r.fiber_results[0].material_state.tensile_damage += 0.1 }],
  ['fiber area identity', (r: any) => { r.fiber_results[0].area_m2 += 1 }],
  ['checkpoint binding', (r: any) => { r.checkpoint_hash = 'sha256:' + '0'.repeat(64) }],
] as const) {
  test(`history file rejects resealed ${name} inconsistent with original source`, async () => {
    await expect(scanRcHistoryFile(changedResponse(edit))).rejects.toThrow('rc_review_')
  })
}
test('history file rejects stored bytes changed after indexing', async () => {
  const source = Buffer.from(originals.slice(0, 3).join('\n') + '\n')
  let changed = false
  class ChangingFile extends Blob {
    override slice(start = 0, end = this.size): Blob {
      const bytes = Buffer.from(source.subarray(start, end))
      if (changed && bytes.length > 30) bytes[20] ^= 1
      return new Blob([bytes])
    }
  }
  const file = new ChangingFile([source]), index = await scanRcHistoryFile(file)
  changed = true
  await expect(readRcHistoryRecord(file, index, 2)).rejects.toThrow('history_record_changed')
})
test('history file bounds total size before reading data', async () => {
  class TooLarge extends Blob {
    override get size(): number { return RC_HISTORY_FILE_LIMIT + 1 }
    override slice(): Blob { throw new Error('must reject before reading') }
  }
  await expect(scanRcHistoryFile(new TooLarge())).rejects.toThrow('history_file_size_invalid')
})
