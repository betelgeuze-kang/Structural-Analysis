#!/usr/bin/env node
import { existsSync, readFileSync } from 'node:fs'
import path from 'node:path'
import { fileURLToPath, pathToFileURL } from 'node:url'
import {
  DEFAULT_STRUCTURE_VIEWER_PROJECT_MANIFEST,
  PROJECT_WORKSPACE_STATUS_ORDER,
  normalizeProjectManifest,
  summarizeProjectManifest,
} from '../src/structure-viewer/viewer-project-workspace.js'

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const viewerDir = path.join(rootDir, 'src', 'structure-viewer')
const schemaVersion = 'structure-viewer-project-manifest.v1'

function parseArgs(argv = process.argv.slice(2)) {
  const args = {
    json: false,
    minProjects: 3,
    minDrawings: 11,
    minVariants: 32,
    minReleaseTriples: 8,
  }
  for (let index = 0; index < argv.length; index += 1) {
    const arg = argv[index]
    if (arg === '--json') args.json = true
    else if (arg === '--min-projects') args.minProjects = Number(argv[++index])
    else if (arg === '--min-drawings') args.minDrawings = Number(argv[++index])
    else if (arg === '--min-variants') args.minVariants = Number(argv[++index])
    else if (arg === '--min-release-triples') args.minReleaseTriples = Number(argv[++index])
    else throw new Error(`Unknown argument: ${arg}`)
  }
  return args
}

function normalizeText(value) {
  return String(value ?? '').trim()
}

function isExternalOrPrivatePath(value) {
  const text = normalizeText(value)
  return !text || text.startsWith('private ') || /^https?:\/\//i.test(text) || /^data:/i.test(text)
}

function resolveRepoPath(relativePath = '') {
  const text = normalizeText(relativePath)
  if (isExternalOrPrivatePath(text)) return { skipped: true, path: text, candidates: [] }
  const candidates = [
    path.resolve(rootDir, text),
    path.resolve(viewerDir, text),
  ]
  const resolved = candidates.find((candidate) => existsSync(candidate)) || ''
  return {
    skipped: false,
    path: text,
    exists: Boolean(resolved),
    resolved,
    candidates,
  }
}

function isGeneratedReleasePath(value) {
  // implementation/phase1/release/ is gitignored generated release output (see
  // .gitignore). These artifacts are absent on clean checkouts (CI) by design.
  // Note: this intentionally does not match the committed release_evidence/ tree.
  return normalizeText(value).includes('implementation/phase1/release/')
}

function addPathCheck(checks, errors, warnings, label, relativePath, { required = true } = {}) {
  const result = resolveRepoPath(relativePath)
  checks.push({ label, ...result })
  if (required && !result.skipped && !result.exists) {
    if (isGeneratedReleasePath(relativePath)) {
      result.optional = true
      warnings.push(`${label} missing (generated release artifact): ${relativePath}`)
    } else {
      errors.push(`${label} missing: ${relativePath}`)
    }
  }
}

function validateVariantTriangle(drawing) {
  const variants = Array.isArray(drawing.variants) ? drawing.variants : []
  const names = new Set(variants.map((variant) => variant.variant))
  return ['baseline', 'optimized', 'compare'].every((name) => names.has(name))
}

function safeNumber(value) {
  const number = Number(value)
  return Number.isFinite(number) ? number : NaN
}

function readJsonFile(absolutePath) {
  try {
    return JSON.parse(readFileSync(absolutePath, 'utf8'))
  } catch (error) {
    return { __read_error: String(error?.message || error) }
  }
}

function extractInteractiveComparisonCounts(payload = {}) {
  const interactive = payload?.interactive_3d && typeof payload.interactive_3d === 'object'
    ? payload.interactive_3d
    : {}
  const baseline = safeNumber(
    interactive.baseline_segment_count
      ?? (Array.isArray(interactive.baseline_segments) ? interactive.baseline_segments.length : NaN),
  )
  const optimized = safeNumber(
    interactive.after_segment_count
      ?? (Array.isArray(interactive.after_segments) ? interactive.after_segments.length : NaN),
  )
  return { baseline, optimized }
}

function addArtifactCountCheck(checks, errors, warnings, label, drawing = {}) {
  const summary = drawing.optimization_summary && typeof drawing.optimization_summary === 'object'
    ? drawing.optimization_summary
    : {}
  const sourcePath = normalizeText(summary.artifact_count_source)
  if (!sourcePath) return
  const resolved = resolveRepoPath(sourcePath)
  const check = {
    label,
    sourcePath,
    exists: Boolean(resolved.exists),
    baselineManifest: safeNumber(summary.baseline_member_count),
    optimizedManifest: safeNumber(summary.optimized_member_count),
    baselineArtifact: NaN,
    optimizedArtifact: NaN,
    ok: false,
  }
  if (!resolved.exists) {
    // Generated release artifacts are intentionally gitignored and absent on clean
    // checkouts (CI). Treat their absence as a warning, but still validate counts
    // whenever the artifact is present locally.
    if (isGeneratedReleasePath(sourcePath)) {
      check.optional = true
      warnings.push(`${label} artifact count source missing (generated release artifact): ${sourcePath}`)
    } else {
      errors.push(`${label} artifact count source missing: ${sourcePath}`)
    }
    checks.push(check)
    return
  }
  const payload = readJsonFile(resolved.resolved)
  if (payload.__read_error) {
    errors.push(`${label} artifact count source unreadable: ${payload.__read_error}`)
    checks.push(check)
    return
  }
  const counts = extractInteractiveComparisonCounts(payload)
  check.baselineArtifact = counts.baseline
  check.optimizedArtifact = counts.optimized
  const baselineOk = Number.isFinite(check.baselineManifest) && check.baselineManifest === counts.baseline
  const optimizedOk = Number.isFinite(check.optimizedManifest) && check.optimizedManifest === counts.optimized
  check.ok = baselineOk && optimizedOk
  if (!check.ok) {
    errors.push(`${label} artifact count mismatch: manifest ${check.baselineManifest}->${check.optimizedManifest}, artifact ${counts.baseline}->${counts.optimized}`)
  }
  checks.push(check)
}

function buildReport(args = parseArgs()) {
  const manifest = normalizeProjectManifest(DEFAULT_STRUCTURE_VIEWER_PROJECT_MANIFEST)
  const summary = summarizeProjectManifest(manifest)
  const errors = []
  const warnings = []
  const pathChecks = []
  const artifactCountChecks = []
  const releaseProject = manifest.projects.find((project) => project.project_id === 'release_visualization')
  let releaseTripleCount = 0

  if (manifest.schema_version !== schemaVersion) {
    errors.push(`schema_version mismatch: ${manifest.schema_version}`)
  }
  if (summary.projectCount < args.minProjects) errors.push(`project count below minimum: ${summary.projectCount}`)
  if (summary.drawingCount < args.minDrawings) errors.push(`drawing count below minimum: ${summary.drawingCount}`)
  if (summary.variantCount < args.minVariants) errors.push(`variant count below minimum: ${summary.variantCount}`)

  for (const project of manifest.projects) {
    if (!project.project_id) errors.push('project missing project_id')
    if (!project.project_title) errors.push(`${project.project_id} missing project_title`)
    if (!project.drawings.length) errors.push(`${project.project_id} has no drawings`)

    for (const drawing of project.drawings) {
      const label = `${project.project_id}/${drawing.drawing_id}`
      if (!drawing.drawing_id) errors.push(`${label} missing drawing_id`)
      if (!drawing.drawing_title) errors.push(`${label} missing drawing_title`)
      if (!PROJECT_WORKSPACE_STATUS_ORDER.includes(drawing.commercial_review_status)) {
        errors.push(`${label} has invalid commercial_review_status=${drawing.commercial_review_status}`)
      }
      if (!drawing.variants.length) errors.push(`${label} has no variants`)
      if (!drawing.viewer_preset && !drawing.artifact_path && !drawing.variants.some((variant) => variant.viewer_preset || variant.artifact_path)) {
        errors.push(`${label} has no viewer_preset or artifact path`)
      }

      addPathCheck(pathChecks, errors, warnings, `${label} drawing artifact`, drawing.artifact_path, {
        required: Boolean(drawing.artifact_path && !drawing.viewer_preset),
      })
      if (drawing.provenance?.source_path) {
        addPathCheck(pathChecks, errors, warnings, `${label} provenance source`, drawing.provenance.source_path)
      } else {
        warnings.push(`${label} has no provenance source_path`)
      }
      if (drawing.provenance?.report_path) {
        addPathCheck(pathChecks, errors, warnings, `${label} provenance report`, drawing.provenance.report_path)
      }
      addArtifactCountCheck(artifactCountChecks, errors, warnings, label, drawing)

      for (const variant of drawing.variants) {
        if (!variant.variant) errors.push(`${label} variant missing name`)
        if (!variant.viewer_preset && !variant.artifact_path) errors.push(`${label}/${variant.variant} has no preset or artifact`)
        if (variant.artifact_path) {
          addPathCheck(pathChecks, errors, warnings, `${label}/${variant.variant} artifact`, variant.artifact_path, {
            required: !variant.viewer_preset,
          })
        }
      }

      if (project.project_id === 'release_visualization') {
        if (validateVariantTriangle(drawing)) releaseTripleCount += 1
        else errors.push(`${label} does not expose baseline/optimized/compare variants`)
        if (!drawing.quality_flags.includes('external_receipt_pending')) {
          warnings.push(`${label} should remain claim-limited without external receipt`)
        }
      }
    }
  }

  if (!releaseProject) errors.push('release_visualization project missing')
  if (releaseTripleCount < args.minReleaseTriples) {
    errors.push(`release visualization triple count below minimum: ${releaseTripleCount}`)
  }

  return {
    schema_version: 'structure-viewer-project-manifest-verification.v1',
    contract_pass: errors.length === 0,
    reason_code: errors.length ? 'FAIL' : 'PASS',
    manifest_schema_version: manifest.schema_version,
    summary,
    releaseTripleCount,
    pathCheckCount: pathChecks.length,
    missingPathCount: pathChecks.filter((check) => !check.skipped && !check.exists).length,
    artifactCountCheckCount: artifactCountChecks.length,
    artifactCountMismatchCount: artifactCountChecks.filter((check) => !check.ok).length,
    artifactCountChecks,
    warnings,
    errors,
  }
}

function main() {
  const args = parseArgs()
  const report = buildReport(args)
  if (args.json) {
    console.log(JSON.stringify(report, null, 2))
  } else if (report.contract_pass) {
    console.log(`Structure viewer project manifest OK: projects=${report.summary.projectCount} drawings=${report.summary.drawingCount} variants=${report.summary.variantCount} release_triples=${report.releaseTripleCount} artifact_count_checks=${report.artifactCountCheckCount}`)
  } else {
    console.error('Structure viewer project manifest FAILED')
    report.errors.forEach((error) => console.error(`- ${error}`))
  }
  return report.contract_pass ? 0 : 1
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  process.exitCode = main()
}
