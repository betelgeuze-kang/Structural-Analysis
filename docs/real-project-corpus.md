# Real Project Corpus Closeout Guide

This guide defines how we close the real-project corpus track for KONEPS and PEER TBI. The goal is not to mass-download or indiscriminately redistribute source material. The goal is to keep provenance, coverage, and release eligibility explicit as the corpus moves through P0, P1, and P2.

## Corpus Families

### KONEPS

KONEPS is handled as a public procurement source family. We can access and catalog:

- procurement metadata
- announcement or notice pages
- attachment discovery and retrieval paths

Those inputs are not the same as a redistributable artifact. Each retrieved item must be classified separately as one of the following:

- metadata only
- attachment reference
- locally retrieved file
- redistributable artifact

Only the last class may move toward release packaging, and only after the P0 gate passes. Public access to a notice or attachment is not enough to assume redistribution rights.

### PEER TBI

PEER TBI is handled as a citation-first benchmark family. The first durable record is not the raw model package; it is the citation-backed benchmark metric record that makes the comparison reproducible.

Raw model, input deck, and companion file redistribution is not allowed until document-level review has been completed for the specific document. Public availability does not imply redistribution rights.

Benchmark metric groups are kept as machine-readable records:

| Group | What it captures |
| --- | --- |
| `citation` | citation text, official URL, report/dataset identifier, page/table locator, access note, and redistribution status |
| `period` | modal or response period values and the source locator for the cited comparison |
| `base_shear` | global base shear results, including direction and load-case tags |
| `story_drift` | interstory drift or drift-ratio results by story, direction, and load case |
| `nonlinear_response` | nonlinear or PBD response quantities, envelope checks, residual response, convergence notes, and limit-state targets |

## Closeout Sequence

| Phase | Goal | Required Evidence | Output |
| --- | --- | --- | --- |
| P0 | provenance, license, security, checksum, manual-review | official entrypoint, jurisdiction, access policy, file inventory, checksums, reviewer signoff | accept/reject decision and redistributability flag |
| P1 | parser coverage matrix and benchmark metric record | file-type coverage, typed/raw-preserved/excluded/blocked status, metric rows, citation linkage | corpus coverage report and benchmark table |
| P2 | crawler automation, redaction, release viewer, report surfacing | refresh schedule, robots and rate-limit handling, redaction policy, release manifest | repeatable refresh and surfaced reports/releases |

## P0: Provenance / License / Security / Checksum / Manual-Review

P0 blocks anything that cannot prove its origin or redistribution status.

- Record the official entrypoint, jurisdiction, access policy, source family, and target file type.
- Capture retrieval timestamp, source URL or notice ID, and the downloaded file inventory.
- Verify checksums for every retrieved file and retain them alongside the manifest.
- Run security review for archives, macro-enabled documents, and any file that could carry active content.
- Complete manual review before any item is marked redistributable.
- If provenance or license is unclear, mark the item blocked rather than assume release eligibility.

## P1: Parser Coverage Matrix / Benchmark Metric Record

P1 proves that the corpus can support repeatable extraction and comparison.

- Build a coverage matrix for candidate KONEPS files across `mgt`, `ifc`, `dwg`, `dxf`, `pdf`, and `xlsx`.
- Record parser outcome per row as `typed`, `raw-preserved`, `excluded`, or `blocked`.
- Attach provenance to each matrix row so a parsed value can be traced back to the source item.
- For PEER TBI, store benchmark metric records that start with `citation` metadata and then capture `period`, `base_shear`, `story_drift`, and `nonlinear_response` fields.
- Generate the current PEER TBI seed records with `implementation/phase1/build_peer_tbi_benchmark_metric_records.py`; the deterministic output is `implementation/phase1/peer_tbi_benchmark_metric_records.json`.
- Keep raw model/input deck redistribution blocked until the relevant document-level review is complete.
- Keep the benchmark record machine-readable so report generation and regression checks can reuse it.

## P2: Crawler Automation / Redaction / Release Viewer / Report Surfacing

P2 turns the vetted corpus into a repeatable operating surface.

- Automate refresh with rate-limit handling, robots and terms checks, and checksum preservation.
- Apply redaction before packaging anything that contains restricted content or non-redistributable attachments.
- Publish only redistributable artifacts into the release view.
- Surface corpus status in the viewer and report layer so provenance, coverage, benchmark status, and redaction state are visible together.
- Keep a clear split between source ingestion, redacted release assets, and user-facing reporting.
