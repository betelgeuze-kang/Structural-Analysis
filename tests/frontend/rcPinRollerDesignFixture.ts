import { readFileSync } from 'node:fs'
import { gunzipSync } from 'node:zlib'
import { createHash } from 'node:crypto'

// One packet of exact producer originals, including the direct preload study.
// The synthetic model/prices are software controls, not physical validation.
const packet = JSON.parse(gunzipSync(readFileSync('tests/frontend/fixtures/rc-pin-roller-design-artifacts.json.gz')).toString('utf8'))
if (packet.schema_version !== 'rc-pin-roller-design-original-fixture.v1') throw new Error('pin/roller fixture schema')
export type PinRollerStudy = 'no-preload' | 'preload' | 'fixed-control' | 'support-preload'
export function pinRollerDesignBytes(path: string, study: PinRollerStudy = 'no-preload'): Uint8Array {
  const row = packet.files[`${study}/${path}`]
  if (!row) throw new Error(`missing original pin/roller study artifact: ${study}/${path}`)
  const bytes = Buffer.from(row.base64, 'base64')
  if (bytes.length !== row.bytes || createHash('sha256').update(bytes).digest('hex') !== row.sha256) throw new Error('pin/roller fixture bytes')
  return new Uint8Array(bytes)
}
export const pinRollerDesignRead = (study: PinRollerStudy = 'no-preload') => async (path: string): Promise<Uint8Array> => pinRollerDesignBytes(path, study)
export const pinRollerProducerProof = packet.producer_proof
