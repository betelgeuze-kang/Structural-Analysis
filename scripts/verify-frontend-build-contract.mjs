import { existsSync, readFileSync } from 'node:fs'
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
  'src/structure-viewer/commercial-cockpit-polish.css',
  'src/structure-viewer/viewer-drawing-handoff-panel-renderer.js',
  'src/structure-viewer/viewer-drawing-review-model.js',
  'src/structure-viewer/viewer-member-comparison-model.js',
  'src/structure-viewer/viewer-optimization-comparison-model.js',
  'src/structure-viewer/viewer-project-workspace-renderer.js',
  'src/structure-viewer/viewer-report-panel-renderer.js',
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

if (packageJson.name !== 'structural-optimization-workbench') {
  fail(`Unexpected package name: ${packageJson.name}`)
}

if ((packageJson.description || '').toLowerCase().includes('monet')) {
  fail('package.json description still contains stale Monet metadata.')
}

if (packageJson.packageManager !== 'npm@10.8.2') {
  fail(`Unexpected package manager pin: ${packageJson.packageManager}`)
}

const expectedScripts = {
  dev: 'vite',
  build: 'tsc --noEmit && vite build',
  preview: 'vite preview',
  'verify:frontend-contract': 'node ./scripts/verify-frontend-build-contract.mjs',
  'verify:frontend-smoke': 'node ./scripts/verify-frontend-smoke.mjs',
  'verify:viewer-manifest': 'node ./scripts/verify-structure-viewer-project-manifest.mjs',
  'verify:frontend-browser-smoke': 'node ./scripts/verify-frontend-browser-smoke.mjs',
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
  react: '18.2.0',
  'react-dom': '18.2.0',
}

const expectedDevDependencies = {
  '@playwright/test': '1.56.1',
  '@types/react': '18.2.15',
  '@types/react-dom': '18.2.7',
  '@vitejs/plugin-react': '6.0.1',
  typescript: '5.0.2',
  vite: '8.0.8',
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

if (packageLock.lockfileVersion < 3) {
  fail(`Expected npm lockfileVersion >= 3, found ${packageLock.lockfileVersion}`)
}

const rootPackage = packageLock.packages?.['']

if (!rootPackage) {
  fail('package-lock.json is missing the root package entry.')
}

if (rootPackage.name !== packageJson.name || rootPackage.version !== packageJson.version) {
  fail('package-lock.json root package metadata does not match package.json.')
}

assertExactDependencies('lockfile root dependencies', rootPackage.dependencies, expectedDependencies)
assertExactDependencies('lockfile root devDependencies', rootPackage.devDependencies, expectedDevDependencies)

console.log('Frontend build contract OK')
if (existsSync(path.join(rootDir, 'node_modules'))) {
  console.log('node_modules present: run `npm run verify:frontend-smoke` to reinstall and rebuild deterministically.')
} else {
  console.log('node_modules missing: contract-only verification passed without installed packages.')
  console.log('Run `npm run verify:frontend-smoke` to install from package-lock.json and build.')
}
