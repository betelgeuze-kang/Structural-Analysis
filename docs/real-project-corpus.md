# Real Project Corpus Closeout Guide

This guide defines how we close the real-project corpus track for KONEPS and PEER TBI. The goal is not to mass-download or indiscriminately redistribute source material. The goal is to keep provenance, row-level provenance, coverage, and release eligibility explicit as the corpus moves through P0, P1, P1-3, and P2.

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
| P1-3 | row provenance gate | source family, access policy, checksum-or-withheld reason, file inventory status, parser contract, stable row pointer, manual review status, release-surface eligibility | row-level eligibility for P2 |
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

## P1-3: Real-Project Row Provenance

P1-3 closes the handoff from parsed rows to P2 release/report surfaces.

| Required signal | What it means |
| --- | --- |
| source family | The row is tied back to a concrete KONEPS or PEER TBI source family entry. |
| access policy | The row keeps public, restricted, and redistributable access rules explicit. |
| checksum or withheld reason | The row carries a checksum when allowed, or an explicit reason when it is withheld. |
| file inventory status | The row records whether the source file is retrieved, referenced, excluded, blocked, or missing. |
| parser contract | The parser identity, parser version, and row classification remain auditable. |
| stable row pointer | The row keeps a stable page/table/entity/cell/member locator back to source. |
| manual review status | The row says whether artifact-level or document-level review is complete, pending, or blocked. |
| release-surface eligibility | The row states clearly whether it may move to P2. |

- KONEPS public metadata/announcement/attachment access is tracked separately from redistributable artifacts.
- PEER TBI records now include the official Task 12 period locator and local measured-run KPI bridge rows, but raw model/input deck release stays blocked until document-level review is complete.
- Generate the current report with `implementation/phase1/build_real_project_row_provenance_report.py`; the tracked `implementation/phase1/real_project_row_provenance_report.json` now includes measured local KR artifact rows in addition to seed/source-family rows.
- Check the measured exit status without touching tracked evidence with `python3 implementation/phase1/check_real_project_corpus_measured_status.py --no-write --json`. Release evidence refreshes should write explicitly to `implementation/phase1/real_project_corpus_measured_status.json`. Current status passes the initial metadata/value gate with all five PEER metric groups carrying values, while separately reporting official reference-truth groups and measured-run KPI bridge groups so the result is not treated as external V&V closure.

## Customer Shadow Evidence

Customer completed-project shadow evidence must not put customer raw data into Git. Use `implementation/phase1/customer_shadow_evidence.schema.json` and validate a filled evidence file with `implementation/phase1/validate_customer_shadow_evidence.py`.

Generate the owner handoff packet with `python3 scripts/build_customer_shadow_evidence_intake_packet.py --json`. The tracked packet fixes five owner-input slots and per-slot validation commands, but it only prepares intake; it does not create customer shadow evidence, ingest customer raw data, or close the 3/5 completed-project target.

Required evidence fields include `case_id`, `project_status=completed`, structure family, reference solver/version, reference output checksum, our engine commit, delta metrics, residual metrics, reviewer decision, limitations, and reproduce bundle id. The validator requires `raw_data_retained_by_customer=true` and `redistribution_allowed=false`, rejects placeholders, and only accepts reviewer decisions `PASS`, `REVIEW`, or `FAIL`.

Track the 3-5 completed-project shadow-case target with `python3 scripts/check_customer_shadow_evidence_status.py --out implementation/phase1/customer_shadow_evidence_status.json`. Verification-only checks should pass `--no-write` instead of writing the tracked status path. The current tracked status is intentionally blocked at `0/3` because no real customer-retained evidence files are attached under `implementation/phase1/customer_shadow_evidence/`; synthetic or placeholder cases must not be used to close this gate.

## P2: Crawler Automation / Redaction / Release Viewer / Report Surfacing

P2 turns the vetted corpus into a repeatable operating surface.

- Automate refresh with rate-limit handling, robots and terms checks, and checksum preservation.
- Apply redaction before packaging anything that contains restricted content or non-redistributable attachments.
- Publish only redistributable artifacts into the release view.
- Surface corpus status in the viewer and report layer so provenance, coverage, benchmark status, and redaction state are visible together.
- Keep a clear split between source ingestion, redacted release assets, and user-facing reporting.
