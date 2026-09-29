import { readFileSync } from 'node:fs'
import { brotliDecompressSync } from 'node:zlib'

// Byte-exact originals from the clean-source, same-family 2026-09-29 packet.
// This fixture preserves the browser's source-binding test; it does not supply
// independent physical validation or a new generalization case.
const packed: Record<string, string> = JSON.parse(brotliDecompressSync(readFileSync(
  'tests/frontend/fixtures/rc-force-floor-learned-artifacts.json.br',
)).toString('utf8'))

export function forceFloorBytes(path: string): Uint8Array {
  const source = packed[path]
  if (typeof source !== 'string') throw new Error(`missing force-floor original: ${path}`)
  return Uint8Array.from(Buffer.from(source, 'base64'))
}

export const forceFloorRead = async (path: string): Promise<Uint8Array> => forceFloorBytes(path)
