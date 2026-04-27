# Real Project Corpus P1/P2 Closeout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the `real_project_corpus_seed_manifest` track from P1 parser/benchmark coverage through P2 refresh/redaction/release surfaces without weakening the P0 legal-provenance gate.

**Architecture:** Treat the seed manifest as the source-family contract, then add derived reports beside it: parser coverage matrix, PEER TBI benchmark metric records, row-provenance maps, crawler refresh reports, redaction reports, release package manifests, and viewer/report payloads. The pipeline must preserve provenance from official entrypoint URL to artifact row, parsed row, release package entry, and viewer/report surface.

**Tech Stack:** Python CLI tools under `implementation/phase1`, JSON Schema validation, pytest contract tests, existing release/viewer generators, signed release registry/freeze snapshot tooling.

---

## Scope And Non-Negotiable P0 Gate

This plan depends on:

- `implementation/phase1/real_project_corpus_seed_manifest.json`
- `implementation/phase1/real_project_corpus_manifest.schema.json`
- `implementation/phase1/validate_real_project_corpus_manifest.py`
- `implementation/phase1/commercialization-gap-redteam-playbook.md`
- `commercial_gap_analysis.md`

P0 remains open as a hard gate for every P1/P2 promotion:

- KONEPS public metadata and KONEPS attachments are separate assets. Public procurement metadata may be cataloged from the official API/entrypoint, but `.mgt/.ifc/.dwg/.dxf/.pdf/.xlsx/.zip` attachments stay `classification=unknown` or more restrictive until security, copyright, and redistribution review passes per artifact.
- No KONEPS attachment may be packaged, redistributed, or linked as a raw downloadable release artifact only because it appeared in public procurement metadata. Attachments require `sha256`, `bytes`, `file_inventory`, source URL, access policy, and manual review evidence before parser promotion.
- `restricted`, `unknown`, and `redacted` source/artifact rows must never set `redistribution_allowed=true`. This is already enforced by `validate_real_project_corpus_manifest.py` and must remain a P0 CI gate.
- PEER TBI starts as benchmark/citation evidence: official report or dataset URL, citation, extracted metric record, and benchmark status. Raw model/data redistribution is a separate per-document legal review and must not be bundled by default.
- P1/P2 work may add derived metadata, checksums, reports, and viewer summaries, but it must not bypass source-family `access_policy` or artifact-row redistribution policy.

Current seed baseline:

- Source families are present for `koneps_turnkey_design_docs` and `peer_tbi_tall_buildings`.
- `artifact_rows` is intentionally empty until artifact-level provenance and review evidence exist.
- P1 and P2 must be implemented as derived closeout reports first, not as blind crawler downloads.

## P1 Exit Gates

### P1-1. KONEPS Parser Coverage Matrix

**Exit Gate:** KONEPS candidates report extraction coverage for `.mgt`, `.ifc`, `.dwg`, `.dxf`, `.pdf`, and `.xlsx`, with each candidate row explicitly separating public metadata coverage from attachment coverage.

**Implementation File Candidates:**

- Create `implementation/phase1/build_real_project_corpus_coverage_matrix.py` to read the seed manifest plus artifact rows and emit `implementation/phase1/real_project_corpus_parser_coverage_report.json`.
- Modify `implementation/phase1/real_project_corpus_manifest.schema.json` only if needed to add derived coverage-report schema references, keeping source-family access policy unchanged.
- Reuse parser evidence from `implementation/phase1/generate_midas_native_corpus_manifest.py`, `implementation/phase1/collect_mgt_quality_corpus.py`, `implementation/phase1/parse_midas_binary_meb_to_json_npz.py`, and IFC/MIDAS bridge reports where available.
- Use KONEPS examples under `implementation/phase1/open_data/korea/collected/reports/*` and `implementation/phase1/open_data/korea/curated/*` only as provenance/coverage references; do not promote raw redistribution without P0 review.

**Test Candidates:**

- Create `tests/test_build_real_project_corpus_coverage_matrix.py`.
- Extend `tests/test_real_project_corpus_manifest.py` with coverage-report validation only after the report schema exists.
- Run `python3 implementation/phase1/validate_real_project_corpus_manifest.py --schema implementation/phase1/real_project_corpus_manifest.schema.json --manifest implementation/phase1/real_project_corpus_seed_manifest.json --show-summary`.

**Pass/Fail Metric:**

- PASS if every KONEPS artifact candidate has `source_id`, `artifact_id`, `source_url`, `metadata_record_status`, `attachment_record_status`, and coverage cells for all six target formats.
- PASS if every coverage cell records one of `typed_entity`, `raw-preserved`, `excluded`, or `blocked`, plus `reason_code`, parser name/version, and source file pointer.
- PASS if public metadata rows are allowed to be `metadata_only`, while attachment rows remain blocked unless P0 security/copyright/redistribution review evidence exists.
- FAIL if any attachment inherits public metadata redistribution rights, any target extension is missing from the matrix, or any parser coverage cell has no classification.

### P1-2. PEER TBI Benchmark Metric Record

**Exit Gate:** PEER TBI candidates report benchmark/citation records for period, base shear, story drift, and nonlinear/PBD target metrics before any raw model redistribution is considered.

**Implementation File Candidates:**

- Create `implementation/phase1/build_peer_tbi_benchmark_metric_records.py` to emit `implementation/phase1/peer_tbi_benchmark_metric_records.json`.
- Reuse benchmark packaging patterns from `implementation/phase1/generate_external_benchmark_kickoff_package.py`, `implementation/phase1/run_real_accuracy_validation.py`, and `implementation/phase1/release/external_benchmark_kickoff/*peer_tbi_tall_building_ndtha*`.
- Add PEER TBI cases to benchmark reports as citation-backed records, not raw redistributed model bundles.

**Test Candidates:**

- Create `tests/test_build_peer_tbi_benchmark_metric_records.py`.
- Add a contract check to `tests/test_run_peer_blind_prediction_compare_report.py` only if PEER TBI records are surfaced through the same benchmark expansion path.
- Use a fixture record with a PEER report URL, citation, page/table locator, and four metric groups.

**Pass/Fail Metric:**

- PASS if each PEER TBI record has `source_id=peer_tbi_tall_buildings`, official URL, citation text, report/dataset identifier, metric locator, and metric values or explicit `not_available` reason for period, base shear, story drift, and nonlinear/PBD targets.
- PASS if `redistribution_allowed=false` remains the default for PEER raw materials until a per-document review record changes it.
- PASS if benchmark reports clearly mark `benchmark_status=citation_metric_recorded` or `benchmark_status=raw_review_required`.
- FAIL if a PEER raw model/archive is included in release packaging without a separate redistribution review, or if benchmark metrics are used without citation and locator evidence.

### P1-3. Real-Project Row Provenance

**Exit Gate:** Every parsed real-project row promoted beyond candidate status carries row-level provenance from source family to artifact, file inventory member, parser, and release/report surface.

**Implementation File Candidates:**

- Create `implementation/phase1/build_real_project_row_provenance.py` to emit `implementation/phase1/real_project_corpus_row_provenance_report.json`.
- Extend `implementation/phase1/generate_midas_native_corpus_manifest.py` output rows with `real_project_source_id`, `artifact_id`, `artifact_sha256`, `file_inventory_path`, `parser_name`, `parser_version`, `row_pointer`, and `access_policy`.
- Surface row provenance in `implementation/phase1/generate_structure_viewer_payloads.py` and `implementation/phase1/generate_release_gap_report.py` only as metadata labels for non-redistributable artifacts.

**Test Candidates:**

- Create `tests/test_build_real_project_row_provenance.py`.
- Extend `tests/test_generate_midas_native_corpus_manifest.py` to assert real-project rows are never emitted without provenance fields.
- Extend `tests/test_generate_structure_viewer_payloads.py` to assert viewer payloads include source/checksum/provenance labels for promoted real-project rows.

**Pass/Fail Metric:**

- PASS if `row_provenance_coverage=1.0` for every promoted parsed row in the report.
- PASS if row pointers are precise enough to audit source location: MGT table/record, IFC entity id, PDF page/table region, XLSX sheet/cell range, DWG/DXF layer/entity pointer, or `raw-preserved` byte/member pointer.
- PASS if release/report/viewer surfaces show provenance metadata without exposing restricted raw payloads.
- FAIL if any promoted row has missing `artifact_id`, missing checksum, missing parser identity, or only a human-readable source label with no artifact pointer.

### P1-4. Parser Coverage Classification

**Exit Gate:** Parser gaps are classified as `typed_entity`, `raw-preserved`, `excluded`, or `blocked`, and downstream automation treats the classification as a contract.

**Implementation File Candidates:**

- Create `implementation/phase1/validate_real_project_parser_coverage.py` to validate `implementation/phase1/real_project_corpus_parser_coverage_report.json`.
- Keep classification values aligned with `real_project_corpus_seed_manifest.json` P1 wording.
- Feed classification summaries into `implementation/phase1/generate_release_gap_report.py` and `implementation/phase1/generate_structural_optimization_visualization_viewer.py`.

**Test Candidates:**

- Create `tests/test_validate_real_project_parser_coverage.py`.
- Add negative fixtures for missing classification, invalid classification, attachment treated as redistributable, and blocked artifact appearing in release package.

**Pass/Fail Metric:**

- PASS if `typed_entity + raw-preserved + excluded + blocked == total_coverage_cells`.
- PASS if `blocked` and `excluded` cells never produce solver-ready entities or packaged raw artifacts.
- PASS if `raw-preserved` cells retain checksum/member/byte or page references for audit without claiming typed parser support.
- FAIL if an unclassified gap is allowed, if `raw-preserved` is treated as solver-ready typed geometry, or if blocked material appears in release/viewer raw links.

## P2 Exit Gates

### P2-1. Crawler Refresh

**Exit Gate:** Crawler refresh is rate-limited, terms/robots-aware, checksum-preserving, and manual-review preserving.

**Implementation File Candidates:**

- Create `implementation/phase1/refresh_real_project_corpus_candidates.py` to emit `implementation/phase1/real_project_corpus_refresh_report.json`.
- Reuse source-specific fetch patterns from `implementation/phase1/fetch_edefense_peer_blind_prediction_seed_package.py`, `implementation/phase1/fetch_peer_spd_specimen_pages.py`, and existing Korean source catalog tooling without copying their permissive assumptions.
- Add a dry-run default mode that refreshes public metadata and citation records without downloading attachments unless an explicit allowlist and P0 review state are present.

**Test Candidates:**

- Create `tests/test_refresh_real_project_corpus_candidates.py`.
- Add fixtures for unchanged ETag/checksum, changed metadata with stable attachment block, rate-limit accounting, and manual-review state preservation.

**Pass/Fail Metric:**

- PASS if refresh output includes `rate_limit_seconds`, `terms_checked`, `robots_checked` or source-specific equivalent, previous checksum, current checksum, retrieval status transition, and manual-review status for every touched artifact row.
- PASS if KONEPS metadata refresh can update notice/issuer/source URL without downloading or redistributing attachments.
- PASS if PEER TBI citation refresh can update report metadata and benchmark status without bundling raw data.
- FAIL if crawler refresh changes `redistribution_allowed` automatically, drops checksum history, downloads KONEPS attachments by default, or overwrites manual review decisions.

### P2-2. Redaction And Redistribution Policy

**Exit Gate:** Redaction policy excludes security-sensitive, restricted, unknown, or non-redistributable artifacts from release packaging while preserving auditable metadata.

**Implementation File Candidates:**

- Create `implementation/phase1/apply_real_project_corpus_redaction_policy.py` to emit `implementation/phase1/real_project_corpus_redaction_report.json`.
- Integrate redaction results into `implementation/phase1/freeze_release_snapshot.py`, `implementation/phase1/generate_signed_release_registry.py`, and `implementation/phase1/promote_release_candidate.py`.
- Preserve redacted metadata fields needed for audit: source family, official URL, jurisdiction, artifact id, checksum if allowed, review status, and reason code.

**Test Candidates:**

- Create `tests/test_apply_real_project_corpus_redaction_policy.py`.
- Extend `tests/test_freeze_release_snapshot_artifact_manifest.py` and `tests/test_release_registry.py` to assert redacted/non-redistributable artifacts are excluded from package payloads.

**Pass/Fail Metric:**

- PASS if every artifact with `classification in {restricted, unknown, redacted}` or `redistribution_allowed=false` is absent from raw release package payloads.
- PASS if redacted rows still appear as metadata-only audit entries when disclosure is allowed.
- PASS if redaction report includes counts for `metadata_only`, `packaged`, `redacted`, `blocked`, and `review_required`.
- FAIL if a non-redistributable raw attachment appears in a zip/tar/release registry payload, or if redaction removes the audit trail needed to explain why it was withheld.

### P2-3. Release Packaging

**Exit Gate:** Release packaging includes only permitted derived reports, citation records, checksums, coverage summaries, and reviewed artifacts.

**Implementation File Candidates:**

- Create `implementation/phase1/package_real_project_corpus_release.py` to emit `implementation/phase1/release/real_project_corpus/real_project_corpus_release_manifest.json`.
- Integrate with `implementation/phase1/freeze_release_snapshot.py`, `implementation/phase1/generate_external_benchmark_kickoff_package.py`, `implementation/phase1/generate_release_gap_report.py`, and `implementation/phase1/generate_signed_release_registry.py`.
- Include derived P1/P2 reports: parser coverage, row provenance, PEER metric records, refresh report, redaction report, and release package manifest.

**Test Candidates:**

- Create `tests/test_package_real_project_corpus_release.py`.
- Extend `tests/test_freeze_release_snapshot_artifact_manifest.py` and `tests/test_run_nightly_release_gate_reuse.py` when the packaging path joins nightly release.

**Pass/Fail Metric:**

- PASS if the package manifest lists every included file with `sha256`, `bytes`, source report path, access policy summary, and redistribution basis.
- PASS if package contents exclude raw KONEPS attachments and PEER raw materials unless artifact-level review explicitly allows redistribution.
- PASS if signed release registry records real-project corpus package status as `metadata_only`, `citation_benchmark`, or `reviewed_artifact`.
- FAIL if package contents differ from the package manifest, if any checksum is missing, or if release packaging treats citation/metadata records as raw redistribution permission.

### P2-4. Viewer And Report Surface

**Exit Gate:** Viewer/report surfaces show corpus source, checksum, parser coverage classification, benchmark status, and redaction status in a way a reviewer can audit without opening raw restricted material.

**Implementation File Candidates:**

- Modify `implementation/phase1/generate_structure_viewer_payloads.py` to include `real_project_corpus` summary blocks.
- Modify `implementation/phase1/generate_structural_optimization_visualization_viewer.py` to display source family, checksum, parser classification, PEER benchmark status, and redaction status.
- Modify `implementation/phase1/generate_release_gap_report.py` to surface P1/P2 closeout metrics in release-consumable summary fields.
- Reuse existing viewer/report examples under `implementation/phase1/release/visualization/entries/*` as display patterns, not as legal precedent.

**Test Candidates:**

- Extend `tests/test_generate_structure_viewer_payloads.py`.
- Extend `tests/test_generate_structural_optimization_visualization_viewer.py`.
- Extend `tests/test_release_gap_report_smoke_summary.py` and `tests/test_release_gap_report_coverage_breakdown.py`.

**Pass/Fail Metric:**

- PASS if viewer/report payloads show at least source family, artifact id, checksum or checksum-withheld reason, classification, parser coverage status, redaction status, and benchmark status for every surfaced real-project entry.
- PASS if KONEPS entries visually distinguish public metadata from attachment artifacts and show P0 review state before any attachment-derived preview.
- PASS if PEER TBI entries show citation/benchmark metric status and mark raw redistribution as `separate_review_required` unless approved.
- FAIL if viewer/report links expose restricted raw artifacts, omit checksum/provenance for promoted rows, or collapse KONEPS metadata and attachments into one unrestricted source.

## Execution Order

- [ ] **Step 1:** Re-run seed manifest validation and keep P0 rules unchanged before P1 work starts.

Run:

```bash
python3 implementation/phase1/validate_real_project_corpus_manifest.py \
  --schema implementation/phase1/real_project_corpus_manifest.schema.json \
  --manifest implementation/phase1/real_project_corpus_seed_manifest.json \
  --show-summary
```

Expected: `Real project corpus manifest OK` with `p0_ready_sources=2/2`.

- [ ] **Step 2:** Implement P1 reports in this order: coverage matrix, parser classification validator, row provenance report, PEER TBI metric records.

Expected artifacts:

```text
implementation/phase1/real_project_corpus_parser_coverage_report.json
implementation/phase1/real_project_corpus_row_provenance_report.json
implementation/phase1/peer_tbi_benchmark_metric_records.json
```

- [ ] **Step 3:** Add P1 tests and fail closed on missing provenance, missing classification, and citation-free PEER metrics.

Run:

```bash
python3 -m pytest -q \
  tests/test_real_project_corpus_manifest.py \
  tests/test_build_real_project_corpus_coverage_matrix.py \
  tests/test_validate_real_project_parser_coverage.py \
  tests/test_build_real_project_row_provenance.py \
  tests/test_build_peer_tbi_benchmark_metric_records.py
```

Expected: PASS, with negative fixtures proving unsafe redistribution and unclassified parser gaps fail.

- [ ] **Step 4:** Implement P2 reports in this order: crawler refresh, redaction policy, release package manifest, viewer/report surface.

Expected artifacts:

```text
implementation/phase1/real_project_corpus_refresh_report.json
implementation/phase1/real_project_corpus_redaction_report.json
implementation/phase1/release/real_project_corpus/real_project_corpus_release_manifest.json
implementation/phase1/release/visualization/real_project_corpus_surface.json
```

- [ ] **Step 5:** Add P2 tests and fail closed on default attachment downloads, non-redistributable package contents, missing checksums, and viewer raw links.

Run:

```bash
python3 -m pytest -q \
  tests/test_refresh_real_project_corpus_candidates.py \
  tests/test_apply_real_project_corpus_redaction_policy.py \
  tests/test_package_real_project_corpus_release.py \
  tests/test_generate_structure_viewer_payloads.py \
  tests/test_generate_structural_optimization_visualization_viewer.py \
  tests/test_release_gap_report_smoke_summary.py
```

Expected: PASS, with fixtures showing metadata-only KONEPS refresh and citation-only PEER TBI packaging.

## Closeout Definition

P1 is closed only when:

- KONEPS coverage matrix covers `.mgt/.ifc/.dwg/.dxf/.pdf/.xlsx`.
- PEER TBI metric records include citation-backed period, base shear, story drift, and nonlinear/PBD benchmark fields.
- Promoted real-project rows have row-level provenance and checksum linkage.
- Parser gaps are classified and enforced by tests.

P2 is closed only when:

- Crawler refresh preserves rate limit, terms/robots evidence, checksum history, and manual-review state.
- Redaction prevents restricted/unknown/redacted/non-redistributable raw artifacts from release packages.
- Release packaging is checksum-complete and policy-aligned.
- Viewer/report surfaces expose source, checksum, parser coverage, benchmark status, and redaction status without exposing restricted raw material.

Self-review checklist for the implementing agent:

- Every KONEPS path distinguishes metadata from attachments.
- Every PEER TBI path starts from benchmark/citation evidence and treats raw redistribution as separate review.
- Every P1/P2 report is derived from manifest/source-family policy, not from crawler assumptions.
- Every release/viewer surface is audit-friendly but does not create a new redistribution channel.
- Every new gate has at least one positive fixture and one fail-closed negative fixture.
