import { existsSync, mkdtempSync, readFileSync, rmSync, statSync } from 'node:fs'
import os from 'node:os'
import path from 'node:path'
import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')

function readArg(name, fallback = '') {
  const index = process.argv.indexOf(name)
  return index >= 0 ? process.argv[index + 1] || fallback : fallback
}

function hasFlag(name) {
  return process.argv.includes(name)
}

function fail(message) {
  throw new Error(message)
}

function commandExists(command) {
  const result = spawnSync(command, ['-v'], { encoding: 'utf8' })
  return !result.error || result.error.code !== 'ENOENT'
}

const query = readArg('--query', 'project=midas33_release&drawing=midas33_optimized&variant=optimized')
const minBytes = Number(readArg('--min-bytes', '12000'))
const explicitOut = readArg('--out', '')
const dryRun = hasFlag('--dry-run')
const keep = hasFlag('--keep') || Boolean(explicitOut)
const workDir = explicitOut || dryRun ? '' : mkdtempSync(path.join(os.tmpdir(), 'structure-viewer-pdf-'))
const out = explicitOut || path.join(workDir, 'structure_viewer_report.pdf')
const htmlOut = dryRun
  ? ''
  : explicitOut
    ? `${out}.html`
    : path.join(workDir, 'structure_viewer_report.html')
const command = [
  process.execPath,
  'scripts/export-structure-viewer-report-pdf.mjs',
  '--query',
  query,
  '--out',
  out,
  ...(htmlOut ? ['--html-out', htmlOut] : []),
]

try {
  if (dryRun) {
    console.log(command.join(' '))
  } else {
    const result = spawnSync(command[0], command.slice(1), {
      cwd: rootDir,
      encoding: 'utf8',
    })
    if (result.status !== 0) {
      process.stderr.write(result.stdout || '')
      process.stderr.write(result.stderr || '')
      fail(`PDF export command failed with exit code ${result.status || 1}`)
    }
    if (!existsSync(out)) fail(`PDF was not written: ${out}`)
    const size = statSync(out).size
    if (!Number.isFinite(minBytes) || minBytes <= 0) fail(`Invalid --min-bytes value: ${minBytes}`)
    if (size < minBytes) fail(`PDF is unexpectedly small: ${size} bytes < ${minBytes} bytes`)
    const header = readFileSync(out).subarray(0, 5).toString('utf8')
    if (!header.startsWith('%PDF-')) fail(`PDF header is missing: ${out}`)
    if (!existsSync(htmlOut)) fail(`HTML report mirror was not written: ${htmlOut}`)
    const html = readFileSync(htmlOut, 'utf8')
    for (const snippet of [
      'Drawing Review',
      'Before / After Member Comparison',
      'viewer screenshot marker',
      'Engineer-in-loop Checklist',
      '상용 검토 가능',
    ]) {
      if (!html.includes(snippet)) fail(`HTML report mirror is missing required snippet: ${snippet}`)
    }
    if (commandExists('pdftotext')) {
      const textResult = spawnSync('pdftotext', [out, '-'], {
        cwd: rootDir,
        encoding: 'utf8',
      })
      if (textResult.status !== 0) {
        process.stderr.write(textResult.stdout || '')
        process.stderr.write(textResult.stderr || '')
        fail(`pdftotext failed with exit code ${textResult.status || 1}`)
      }
      for (const snippet of ['Drawing Review', 'Before / After Member Comparison', 'Engineer-in-loop Checklist']) {
        if (!textResult.stdout.includes(snippet)) fail(`PDF text is missing required snippet: ${snippet}`)
      }
    }
    console.log(`Structure viewer PDF export OK: ${out} (${size} bytes)`)
  }
} finally {
  if (workDir && !keep) {
    rmSync(workDir, { recursive: true, force: true })
  }
}
