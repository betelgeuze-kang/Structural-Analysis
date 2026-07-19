import { existsSync, readFileSync, statSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const distDir = path.join(rootDir, 'dist')
const workbenchEntry = path.join(distDir, 'index.html')
const viewerEntry = path.join(distDir, 'src', 'structure-viewer', 'index.html')
const legacySentinels = [
  'Structural Signal Desk',
  'native-authoring-controls',
  'release-gap-review-state',
]

function fail(message) {
  throw new Error(`Workbench/Viewer delivery contract failed: ${message}`)
}

function readRequiredFile(absolutePath, label) {
  if (!existsSync(absolutePath) || !statSync(absolutePath).isFile()) {
    fail(`${label} is missing: ${path.relative(rootDir, absolutePath)}`)
  }
  const text = readFileSync(absolutePath, 'utf8')
  if (!text.trim()) fail(`${label} is empty`)
  return text
}

function emittedAssetPath(reference) {
  const cleanReference = reference.split(/[?#]/, 1)[0]
  const match = cleanReference.match(/(?:^|\/)(assets\/[^"']+)$/)
  return match ? path.join(distDir, ...match[1].split('/')) : null
}

function emittedAssetReferences(html) {
  return [...html.matchAll(/(?:src|href)="([^"]+)"/g)]
    .map((match) => match[1])
    .map((reference) => ({ reference, absolutePath: emittedAssetPath(reference) }))
    .filter((entry) => entry.absolutePath !== null)
}

function verifyAssetReferences(html, label) {
  const references = emittedAssetReferences(html)
  if (!references.length) fail(`${label} has no emitted asset references`)
  for (const { reference, absolutePath } of references) {
    if (!existsSync(absolutePath) || !statSync(absolutePath).isFile()) {
      fail(`${label} references a missing emitted asset: ${reference}`)
    }
  }
  return references
}

const workbenchHtml = readRequiredFile(workbenchEntry, 'Workbench entry')
const viewerHtml = readRequiredFile(viewerEntry, 'Viewer entry')

if (!workbenchHtml.includes('<div id="root"></div>')) {
  fail('Workbench entry does not contain the React product-shell root')
}
if (workbenchHtml.includes('data-si-shell="product"')) {
  fail('Workbench entry was replaced by the Viewer entry')
}
if (!viewerHtml.includes('data-si-shell="product"')) {
  fail('Viewer entry does not contain the Viewer product-shell marker')
}
if (!viewerHtml.includes('data-viewer-workflow="model"')) {
  fail('Viewer entry does not contain the Viewer workflow marker')
}
if (viewerHtml.includes('data-wb2-root')) {
  fail('Viewer entry resolved to the Workbench SPA fallback')
}

const workbenchAssets = verifyAssetReferences(workbenchHtml, 'Workbench entry')
const viewerAssets = verifyAssetReferences(viewerHtml, 'Viewer entry')
const workbenchScripts = workbenchAssets
  .filter(({ reference }) => reference.split(/[?#]/, 1)[0].endsWith('.js'))
  .map(({ absolutePath }) => readRequiredFile(absolutePath, 'Workbench JavaScript asset'))

if (!workbenchScripts.some((source) => source.includes('src/structure-viewer/index.html'))) {
  fail('Workbench JavaScript does not target the emitted Viewer entry')
}

for (const sentinel of legacySentinels) {
  if (workbenchScripts.some((source) => source.includes(sentinel))) {
    fail(`Legacy App code leaked into the eager Workbench graph: ${sentinel}`)
  }
}

const legacyChunkNames = new Set(
  workbenchScripts.flatMap((source) => [...source.matchAll(/(?:assets\/|\.\/)(App-[^"'`]+\.js)/g)]
    .map((match) => match[1])),
)
if (legacyChunkNames.size !== 1) {
  fail(`Workbench must reference exactly one lazy legacy App chunk; found ${legacyChunkNames.size}`)
}
const legacyChunkName = [...legacyChunkNames][0]
const legacyChunkPath = path.join(distDir, 'assets', legacyChunkName)
const legacyChunkSource = readRequiredFile(legacyChunkPath, 'Legacy App JavaScript asset')
for (const sentinel of legacySentinels) {
  if (!legacyChunkSource.includes(sentinel)) {
    fail(`Lazy legacy App chunk is missing its ownership marker: ${sentinel}`)
  }
}

console.log(JSON.stringify({
  contract: 'workbench_viewer_production_delivery_v1',
  status: 'ready',
  workbench_entry: path.relative(rootDir, workbenchEntry),
  viewer_entry: path.relative(rootDir, viewerEntry),
  legacy_chunk: path.relative(rootDir, legacyChunkPath),
  workbench_asset_count: workbenchAssets.length,
  viewer_asset_count: viewerAssets.length,
  legacy_marker_count: legacySentinels.length,
}))
