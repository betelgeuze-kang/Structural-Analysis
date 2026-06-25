// Build the public benchmark catalog for Workbench v2 from REAL repository
// metadata. We never invent checksums or URLs: every field is read from the
// collected source metadata, and anything we cannot verify is marked unknown /
// inferred rather than asserted.

import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

const rootDir = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const reportsDir = path.join(rootDir, 'implementation/phase1/open_data/irregular/collected/reports')
const peerDir = path.join(rootDir, 'implementation/phase1/open_data/pbd_hinge/peer_spd_specimens')
const outFile = path.join(rootDir, 'src/workbench-v2/model/benchmark/benchmarkCatalog.json')

// Conservative truth-class inference from source format. This is an inference
// (truth_class_verified = false), not a measured claim. Unknown -> geometry_only
// so the case is excluded from numerical-accuracy averaging by default.
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

function fromReport(raw) {
  const sourceUrls = Array.isArray(raw.source_urls) ? raw.source_urls.filter((u) => typeof u === 'string') : []
  const fmt = typeof raw.source_format === 'string' ? raw.source_format : null
  return {
    id: String(raw.source_id),
    title: typeof raw.title === 'string' ? raw.title : String(raw.source_id),
    sourceUrl: sourceUrls[0] ?? '',
    sourceVersion: 'unspecified',
    license: 'unknown',
    truthClass: (fmt && TRUTH_BY_FORMAT[fmt]) || 'geometry_only',
    structureFamily: typeof raw.family_id === 'string' ? raw.family_id : 'unspecified',
    analysisTypes: [],
    checksum: typeof raw.sha256 === 'string' ? `sha256:${raw.sha256}` : undefined,
    localAvailability: raw.source_exists === true ? 'available' : 'external',
    // honesty annotations (extensions to the base schema)
    sourceFormat: fmt,
    fileBytes: typeof raw.bytes_copied === 'number' ? raw.bytes_copied : null,
    sizeClass: sizeClassFromBytes(raw.bytes_copied),
    truthClassVerified: false,
    truthClassBasis: fmt ? `inferred from source format: ${fmt}` : 'unknown format',
    licenseVerified: false,
    referenceResultsAvailable: false,
    allSourceUrls: sourceUrls,
  }
}

function fromPeerSpecimen(raw, file) {
  return {
    id: typeof raw.seed_id === 'string' ? raw.seed_id : path.basename(file, '.specimen_page.json'),
    title: typeof raw.page_title === 'string' ? raw.page_title : `PEER SPD specimen ${raw.specimen_id ?? ''}`.trim(),
    sourceUrl: typeof raw.specimen_display_url === 'string' ? raw.specimen_display_url : '',
    sourceVersion: typeof raw.specimen_id === 'string' ? `specimen ${raw.specimen_id}` : 'unspecified',
    license: 'unknown',
    // PEER SPD is an experimental column database — this is a measured fact.
    truthClass: 'experimental',
    structureFamily: 'rc_column',
    analysisTypes: ['cyclic_quasi_static'],
    checksum: undefined,
    localAvailability: 'available',
    sourceFormat: 'peer_spd_specimen_page',
    fileBytes: null,
    sizeClass: 'small',
    truthClassVerified: true,
    truthClassBasis: 'PEER Structural Performance Database (experimental specimens)',
    licenseVerified: false,
    referenceResultsAvailable: Array.isArray(raw.hysteresis_link_candidates) && raw.hysteresis_link_candidates.length > 0,
    allSourceUrls: typeof raw.specimen_display_url === 'string' ? [raw.specimen_display_url] : [],
  }
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
      cases.push(fromPeerSpecimen(raw, file))
    }
  }

  const catalog = {
    schema_version: 'benchmark-catalog.v1',
    catalog_kind: 'candidate',
    generated_at: new Date().toISOString(),
    generated_by: 'scripts/build-benchmark-catalog.mjs',
    disclaimer:
      'Candidate benchmark catalog built from collected open-data metadata. Checksums and URLs are read from source metadata; licenses and most truth classes are UNVERIFIED (truth class is format-inferred unless marked verified). geometry_only cases must not be used for numerical-accuracy averaging.',
    accuracy_exclusion_rule:
      'geometry_only data is used only for import / topology / rendering / GUI performance / model health, never in numerical-accuracy averages.',
    cases,
  }

  fs.mkdirSync(path.dirname(outFile), { recursive: true })
  fs.writeFileSync(outFile, JSON.stringify(catalog, null, 2) + '\n')
  console.log(`Wrote ${cases.length} cases to ${path.relative(rootDir, outFile)}`)
}

main()
