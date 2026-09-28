import { readFileSync } from 'node:fs'
import { gunzipSync } from 'node:zlib'

// Original bytes from a two-design, synthetic-price study produced by
// compare_rc_control_designs with the v4 pin/roller direct-control request.
const packed: Record<string, string> = JSON.parse(gunzipSync(readFileSync(
  'tests/frontend/fixtures/rc-pin-roller-design-artifacts.json.gz',
)).toString('utf8'))

export function pinRollerDesignBytes(path: string): Uint8Array {
  const value = packed[path]
  if (typeof value !== 'string') throw new Error(`missing original pin/roller design artifact: ${path}`)
  return Uint8Array.from(Buffer.from(value, 'base64'))
}

export const pinRollerDesignRead = async (path: string): Promise<Uint8Array> => pinRollerDesignBytes(path)
