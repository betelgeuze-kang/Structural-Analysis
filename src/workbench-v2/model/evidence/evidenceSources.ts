// Registry of read-only evidence sources surfaced by the workbench.
// Paths are served as static files; the UI never writes to them.

export interface EvidenceSourceDef {
  id: string
  label: string
  path: string
}

export const EVIDENCE_SOURCES: EvidenceSourceDef[] = [
  {
    id: 'product_readiness',
    label: 'Product readiness',
    path: '/implementation/phase1/release_evidence/productization/product_readiness_snapshot.json',
  },
  {
    id: 'p1_benchmark_breadth',
    label: 'P1 benchmark breadth',
    path: '/implementation/phase1/release_evidence/productization/p1_benchmark_breadth_status.json',
  },
  {
    id: 'fresh_full_validation',
    label: 'Fresh full validation lane',
    path: '/implementation/phase1/release_evidence/productization/fresh_full_validation_lane_status.json',
  },
  {
    id: 'evidence_console_scope',
    label: 'Evidence Console scope',
    path: '/implementation/phase1/release_evidence/productization/evidence_console_scope_status.json',
  },
  {
    id: 'real_project_corpus',
    label: 'Real project corpus (measured)',
    path: '/implementation/phase1/real_project_corpus_measured_status.json',
  },
]
