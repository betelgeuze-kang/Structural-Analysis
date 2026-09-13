import { readFileSync } from 'node:fs'
import { gunzipSync } from 'node:zlib'
const packed = JSON.parse(gunzipSync(readFileSync('tests/frontend/fixtures/rc-layout-standalone.json.gz')).toString('utf8'))
export const standaloneLayouts: Record<string, Record<string, Buffer>> = Object.fromEntries(Object.entries(packed).map(([id, files]) => [id, Object.fromEntries(Object.entries(files as Record<string,string>).map(([name,raw]) => [name, Buffer.from(raw,'base64')]))]))
