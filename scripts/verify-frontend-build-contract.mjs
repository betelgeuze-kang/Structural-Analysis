import { existsSync, lstatSync, readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

function readJson(relativePath) {
  const absolutePath = path.join(rootDir, relativePath)
  return JSON.parse(readFileSync(absolutePath, 'utf8'))
}

function fail(message) {
  throw new Error(message)
}

function pathLexists(absolutePath) {
  try {
    lstatSync(absolutePath)
    return true
  } catch (error) {
    if (error?.code === 'ENOENT') {
      return false
    }
    throw error
  }
}

const packageJson = readJson('package.json')
const packageLock = readJson('package-lock.json')

const requiredFiles = [
  'index.html',
  'tsconfig.json',
  'vite.config.ts',
  'src/main.tsx',
  'src/App.tsx',
  'scripts/verify-frontend-build-contract.mjs',
  'scripts/verify-frontend-smoke.mjs',
  'scripts/verify-frontend-browser-smoke.mjs',
  'scripts/verify-workbench-viewer-delivery.mjs',
  'scripts/verify-structure-viewer-project-manifest.mjs',
  'scripts/verify-structure-viewer-callout-docking.mjs',
  'scripts/verify-structure-viewer-critical-callout-focus.mjs',
  'scripts/verify-structure-viewer-drawing-handoff-preview.mjs',
  'scripts/verify-structure-viewer-multi-selection-hud.mjs',
  'scripts/verify-workstation-delivery-viewer-smoke.mjs',
  'scripts/export-structure-viewer-report-pdf.mjs',
  'scripts/verify-structure-viewer-report-pdf.mjs',
  'scripts/measure-structure-viewer-performance.mjs',
  'scripts/measure-structure-viewer-visual-regression.mjs',
  'src/structure-viewer/design-tokens.css',
  'src/structure-viewer/viewer-visual-identity.css',
  'src/structure-viewer/viewer-visual-scene.js',
  'src/structure-viewer/viewer-viewport-hud.js',
  'src/structure-viewer/viewer-callout-layout.js',
  'src/structure-viewer/commercial-cockpit-polish.css',
  'src/structure-viewer/viewer-drawing-handoff-panel-renderer.js',
  'src/structure-viewer/viewer-drawing-review-model.js',
  'src/structure-viewer/viewer-member-comparison-model.js',
  'src/structure-viewer/viewer-optimization-comparison-model.js',
  'src/structure-viewer/viewer-project-workspace-renderer.js',
  'src/structure-viewer/viewer-report-panel-renderer.js',
  'src/structure-viewer/viewer-runtime-ingest-payload-storage.js',
  'src/structure-viewer/viewer-selection-inspector-renderer.js',
  'src/structure-viewer/viewer-stage-result-callouts-renderer.js',
  'tests/frontend/structure-viewer-smoke.spec.ts',
  'docs/frontend-build-reproducibility.md',
]

for (const relativePath of requiredFiles) {
  if (!existsSync(path.join(rootDir, relativePath))) {
    fail(`Missing required frontend file: ${relativePath}`)
  }
}

if (existsSync(path.join(rootDir, 'pakage.json'))) {
  fail('Stale typo manifest pakage.json must be removed.')
}

if (existsSync(path.join(rootDir, 'src/app.tsx'))) {
  fail('Stale lowercase src/app.tsx must be removed; src/main.tsx imports src/App.tsx.')
}

if (packageJson.name !== 'structural-analysis') {
  fail(`Unexpected package name: ${packageJson.name}`)
}

if ((packageJson.description || '').toLowerCase().includes('monet')) {
  fail('package.json description still contains stale Monet metadata.')
}

if (packageJson.packageManager !== 'npm@11.19.0') {
  fail(`Unexpected package manager pin: ${packageJson.packageManager}`)
}

if (JSON.stringify(packageJson.engines) !== JSON.stringify({ node: '24.20.0', npm: '11.19.0' })) {
  fail(`Unexpected engine pins: ${JSON.stringify(packageJson.engines)}`)
}

for (const field of ['bundleDependencies', 'bundledDependencies', 'devEngines', 'overrides', 'workspaces']) {
  if (Object.hasOwn(packageJson, field)) {
    fail(`Unsupported package manifest field: ${field}`)
  }
}

for (const relativePath of [
  '.npmrc',
  '.pnpmfile.cjs',
  '.yarn',
  '.yarnrc',
  '.yarnrc.yml',
  'bun.lock',
  'bun.lockb',
  'bunfig.toml',
  'npm-shrinkwrap.json',
  'pnpm-lock.yaml',
  'pnpm-workspace.yaml',
  'yarn.lock',
]) {
  if (pathLexists(path.join(rootDir, relativePath))) {
    fail(`Forbidden alternate dependency surface: ${relativePath}`)
  }
}

for (let ancestor = path.dirname(rootDir); ; ancestor = path.dirname(ancestor)) {
  if (pathLexists(path.join(ancestor, '.npmrc'))) {
    fail('Ancestor .npmrc is forbidden for the exact frontend build contract.')
  }
  if (path.dirname(ancestor) === ancestor) {
    break
  }
}

const expectedScripts = {
  dev: 'vite',
  build: 'tsc --noEmit && vite build && node ./scripts/verify-workbench-viewer-delivery.mjs',
  preview: 'vite preview',
  'verify:frontend-contract': 'node ./scripts/verify-frontend-build-contract.mjs',
  'verify:frontend-smoke': 'node ./scripts/verify-frontend-smoke.mjs',
  'verify:viewer-manifest': 'node ./scripts/verify-structure-viewer-project-manifest.mjs',
  'verify:frontend-browser-smoke': 'node ./scripts/verify-frontend-browser-smoke.mjs',
  'verify:workbench-viewer-delivery': 'node ./scripts/verify-workbench-viewer-delivery.mjs',
  'export:viewer-report-pdf': 'node ./scripts/export-structure-viewer-report-pdf.mjs',
  'verify:viewer-report-pdf': 'node ./scripts/verify-structure-viewer-report-pdf.mjs',
  'verify:viewer-performance-probe': 'node ./scripts/measure-structure-viewer-performance.mjs --verify --fail-blocked',
  'verify:viewer-visual-regression': 'node ./scripts/measure-structure-viewer-visual-regression.mjs --verify --fail-blocked',
}

for (const [name, command] of Object.entries(expectedScripts)) {
  if (packageJson.scripts?.[name] !== command) {
    fail(`Unexpected script for ${name}: ${packageJson.scripts?.[name]}`)
  }
}

const expectedDependencies = {
  ajv: '8.20.0',
  react: '18.2.0',
  'react-dom': '18.2.0',
}

const expectedDevDependencies = {
  '@playwright/test': '1.56.1',
  '@types/react': '18.2.15',
  '@types/react-dom': '18.2.7',
  '@vitejs/plugin-react': '6.0.1',
  postcss: '8.5.26',
  typescript: '5.0.2',
  vite: '8.0.16',
}

function assertExactDependencies(groupName, actualGroup, expectedGroup) {
  const actualKeys = Object.keys(actualGroup || {}).sort()
  const expectedKeys = Object.keys(expectedGroup).sort()

  if (JSON.stringify(actualKeys) !== JSON.stringify(expectedKeys)) {
    fail(`Unexpected ${groupName} keys: ${actualKeys.join(', ')}`)
  }

  for (const [name, version] of Object.entries(expectedGroup)) {
    const actualVersion = actualGroup?.[name]
    if (actualVersion !== version) {
      fail(`Unexpected ${groupName} version for ${name}: ${actualVersion}`)
    }
    if (/^[~^]/.test(actualVersion)) {
      fail(`${groupName} ${name} must be pinned exactly, found ${actualVersion}`)
    }
  }
}

assertExactDependencies('dependencies', packageJson.dependencies, expectedDependencies)
assertExactDependencies('devDependencies', packageJson.devDependencies, expectedDevDependencies)

if (packageLock.name !== packageJson.name) {
  fail(`package-lock.json name mismatch: ${packageLock.name}`)
}

if (packageLock.version !== packageJson.version) {
  fail(`package-lock.json version mismatch: ${packageLock.version}`)
}

if (packageLock.lockfileVersion !== 3 || packageLock.requires !== true) {
  fail(`Expected npm lockfileVersion 3 with requires=true, found ${packageLock.lockfileVersion}/${packageLock.requires}`)
}

const rootPackage = packageLock.packages?.['']

if (!rootPackage) {
  fail('package-lock.json is missing the root package entry.')
}

if (rootPackage.name !== packageJson.name || rootPackage.version !== packageJson.version) {
  fail('package-lock.json root package metadata does not match package.json.')
}

if (JSON.stringify(rootPackage.engines) !== JSON.stringify(packageJson.engines)) {
  fail('package-lock.json root engines do not match package.json.')
}

assertExactDependencies('lockfile root dependencies', rootPackage.dependencies, expectedDependencies)
assertExactDependencies('lockfile root devDependencies', rootPackage.devDependencies, expectedDevDependencies)

console.log('Frontend build contract OK')
if (existsSync(path.join(rootDir, 'node_modules'))) {
  console.log('node_modules present: launch scripts/verify-frontend-smoke.mjs with the hash-verified absolute Node 24.20.0 executable under env -i for authoritative reinstall and build verification.')
} else {
  console.log('node_modules missing: contract-only verification passed without installed packages.')
  console.log('Launch scripts/verify-frontend-smoke.mjs with the hash-verified absolute Node 24.20.0 executable under env -i to install from package-lock.json and build.')
}
