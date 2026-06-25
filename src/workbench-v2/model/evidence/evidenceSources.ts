// The workbench reads evidence from a published, read-only bundle (built by
// scripts/build-workbench-evidence-bundle.mjs) rather than fetching repository
// internals directly. URLs resolve against import.meta.env.BASE_URL so the app
// works under a GitHub Pages subpath.

export interface EvidenceManifestArtifact {
  id: string
  label: string
  /** Path of the copy, relative to the bundle directory. */
  path: string
  /** Original read-only source path in the repository. */
  source_path: string
  sha256: string
  read_only: boolean
}

export interface EvidenceManifest {
  schema_version: string
  generated_at: string
  source_commit_sha: string
  artifacts: EvidenceManifestArtifact[]
}

export const EVIDENCE_BUNDLE_DIR = 'evidence'
export const EVIDENCE_MANIFEST_FILE = 'manifest.json'

function withBase(baseUrl: string): string {
  return baseUrl.endsWith('/') ? baseUrl : `${baseUrl}/`
}

export function evidenceManifestUrl(baseUrl: string): string {
  return `${withBase(baseUrl)}${EVIDENCE_BUNDLE_DIR}/${EVIDENCE_MANIFEST_FILE}`
}

export function evidenceArtifactUrl(baseUrl: string, artifactPath: string): string {
  return `${withBase(baseUrl)}${EVIDENCE_BUNDLE_DIR}/${artifactPath}`
}
