// Build the public benchmark catalog for Workbench v2 from REAL repository
// metadata. We never invent checksums, URLs, licenses, reference results, or
// runners: every verified field must come from real metadata, and anything we
// cannot verify is recorded as unverified / null, not asserted.

import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const reportsDir = path.join(rootDir, 'implementation/phase1/open_data/irregular/collected/reports')
const peerDir = path.join(rootDir, 'implementation/phase1/open_data/pbd_hinge/peer_spd_specimens')
const outFile = path.join(rootDir, 'src/workbench-v2/model/benchmark/benchmarkCatalog.json')

const TRUTH_BY_FORMAT = {
  ifc: 'geometry_only',
  tcl: 'independent_solver',
  json_graph: 'independent_solver',
  mgt: 'commercial_reference',
  mcb: 'commercial_reference',
  meb: 'commercial_reference',
  report_pdf: 'geometry_only',
  csv_tables: 'geometry_only',
}

function sizeClassFromBytes(bytes) {
  if (typeof bytes !== 'number' || bytes <= 0) return 'unknown'
  if (bytes < 100 * 1024) return 'small'
  if (bytes < 2 * 1024 * 1024) return 'medium'
  return 'large'
}

// Verification block: everything starts UNVERIFIED. No runner is registered, so
// no run command will be offered until one is added.
function baseVerification(extra = {}) {
  return {
    licenseId: null,
    licenseUrl: null,
    licenseVerified: false,
    truthClassVerified: false,
    truthEvidencePath: null,
    referenceResultsAvailable: false,
    referenceResultsPath: null,
    referenceSolver: null,
    referenceSolverVersion: null,
    acquisitionCommand: null,
    runnerId: null,
    ...extra,
  }
}

function fromReport(raw) {
  const sourceUrls = Array.isArray(raw.source_urls) ? raw.source_urls.filter((u) => typeof u === 'string') : []
  const fmt = typeof raw.source_format === 'string' ? raw.source_format : null
  const id = String(raw.source_id)
  return {
    id,
    title: typeof raw.title === 'string' ? raw.title : id,
    sourceUrl: sourceUrls[0] ?? '',
    sourceVersion: 'unspecified',
    license: 'unknown',
    truthClass: (fmt && TRUTH_BY_FORMAT[fmt]) || 'geometry_only',
    structureFamily: typeof raw.family_id === 'string' ? raw.family_id : 'unspecified',
    analysisTypes: [],
    checksum: typeof raw.sha256 === 'string' ? `sha256:${raw.sha256}` : undefined,
    localAvailability: raw.source_exists === true ? 'available' : 'external',
    sourceFormat: fmt,
    fileBytes: typeof raw.bytes_copied === 'number' ? raw.bytes_copied : null,
    sizeClass: sizeClassFromBytes(raw.bytes_copied),
    truthClassBasis: fmt ? `inferred from source format: ${fmt}` : 'unknown format',
    allSourceUrls: sourceUrls,
    firstValidationTarget: false,
    verification: baseVerification({
      acquisitionCommand: sourceUrls[0] ? `# obtain manually from ${sourceUrls[0]}` : null,
    }),
  }
}

function fromPeerSpecimen(raw, file, sourceRel) {
  const id = typeof raw.seed_id === 'string' ? raw.seed_id : path.basename(file, '.specimen_page.json')
  const hasRef = Array.isArray(raw.hysteresis_link_candidates) && raw.hysteresis_link_candidates.length > 0
  const url = typeof raw.specimen_display_url === 'string' ? raw.specimen_display_url : ''
  return {
    id,
    title: typeof raw.page_title === 'string' ? raw.page_title : `PEER SPD specimen ${raw.specimen_id ?? ''}`.trim(),
    sourceUrl: url,
    sourceVersion: typeof raw.specimen_id === 'string' ? `specimen ${raw.specimen_id}` : 'unspecified',
    license: 'unknown',
    truthClass: 'experimental',
    structureFamily: 'rc_column',
    analysisTypes: ['cyclic_quasi_static'],
    checksum: undefined,
    localAvailability: 'available',
    sourceFormat: 'peer_spd_specimen_page',
    fileBytes: null,
    sizeClass: 'small',
    truthClassBasis: 'PEER Structural Performance Database (experimental specimens)',
    allSourceUrls: url ? [url] : [],
    firstValidationTarget: false,
    // PEER SPD is a verified experimental truth class; the specimen page is the
    // truth evidence. Reference results availability mirrors hysteresis links.
    verification: baseVerification({
      truthClassVerified: true,
      truthEvidencePath: sourceRel,
      referenceResultsAvailable: hasRef,
      acquisitionCommand: url ? `# PEER SPD specimen ${raw.specimen_id ?? ''} from ${url}` : null,
    }),
  }
}

// First validation targets (priority candidates, NOT validated yet).
function markFirstValidationTargets(cases) {
  const pick = (predicate) => {
    const hit = cases.find((c) => !c.firstValidationTarget && predicate(c))
    if (hit) hit.firstValidationTarget = true
  }
  pick((c) => c.id === 'luxinzheng_megatall_tcl_model1_local') // OpenSees Mega-Tall
  pick((c) => c.id.startsWith('peer_spd_rc_column_rectangular')) // PEER/SPD experimental
  pick((c) => c.id === 'midas_multifamily_building_meb_local') // mid-size MIDAS
  pick((c) => c.sourceFormat === 'ifc') // buildingSMART IFC geometry-only
}

function main() {
  const cases = []
  for (const file of fs.readdirSync(reportsDir).filter((f) => f.endsWith('.json')).sort()) {
    const raw = JSON.parse(fs.readFileSync(path.join(reportsDir, file), 'utf8'))
    if (raw && raw.source_id) cases.push(fromReport(raw))
  }
  if (fs.existsSync(peerDir)) {
    for (const file of fs.readdirSync(peerDir).filter((f) => f.endsWith('.specimen_page.json')).sort()) {
      const raw = JSON.parse(fs.readFileSync(path.join(peerDir, file), 'utf8'))
      const sourceRel = path.relative(rootDir, path.join(peerDir, file))
      cases.push(fromPeerSpecimen(raw, file, sourceRel))
    }
  }
  markFirstValidationTargets(cases)

  const catalog = {
    schema_version: 'benchmark-catalog.v2',
    catalog_kind: 'candidate',
    generated_at: new Date().toISOString(),
    generated_by: 'scripts/build-benchmark-catalog.mjs',
    disclaimer:
      'Candidate benchmark catalog built from collected open-data metadata. Checksums and URLs are read from source metadata; licenses, most truth classes, reference results, and runners are UNVERIFIED. A run command is only offered for cases with a registered runnerId. geometry_only cases must not be used for numerical-accuracy averaging.',
    accuracy_exclusion_rule:
      'geometry_only data is used only for import / topology / rendering / GUI performance / model health, never in numerical-accuracy averages.',
    lifecycle_states: ['DISCOVERED', 'ACQUIRED', 'NORMALIZED', 'REFERENCE_ATTACHED', 'RUNNABLE', 'VALIDATED'],
    cases,
  }

  fs.mkdirSync(path.dirname(outFile), { recursive: true })
  fs.writeFileSync(outFile, JSON.stringify(catalog, null, 2) + '\n')
  const targets = cases.filter((c) => c.firstValidationTarget).map((c) => c.id)
  console.log(`Wrote ${cases.length} cases. First validation targets: ${targets.join(', ')}`)
}

main()
