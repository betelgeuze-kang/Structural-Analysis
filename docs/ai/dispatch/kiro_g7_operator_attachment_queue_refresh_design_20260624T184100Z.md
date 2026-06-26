# Kiro Design Slice: G7 Operator Attachment Queue Refresh

You are Kiro running as a design-only architect on model `opus-4.8`. Codex owns the active goal, acceptance criteria, verification planning, claim-boundary review, and final acceptance. Cursor `composer-2.5` may implement the approved scoped slice if implementation is needed.

Do not edit files. Do not claim readiness closure. Do not produce a long design document.

## Task

Goal: Design a bounded G7 evidence refresh that regenerates the operator attachment manifest queue and direct-download review from the current Korean medium/large ingest receipt without downloading files, confirming rights, or promoting G7.

Current blocker: G7 remains partial because benchmark-bridge MGTs, metadata-only sources, source-mapping gaps, and rights-blocked private candidate actions cannot count as operator-attached real-project corpus closure. Current commercial status reports G7 blockers: `repo_benchmark_bridge_mgt_present`, `metadata_only_sources_present`, `operator_attached_real_mgt_header_ok_below_target`, `operator_source_mapping_blocked_actions_present`, and `operator_rights_blocked_private_candidate_actions_present`.

Scope: Refresh only local queue/review evidence and the derived ledger/status receipts. Do not perform network downloads, do not create or alter real operator attachment manifests, do not set `rights_confirmed=true`, and do not claim G7 closure. If validation is run against a queue/template rather than a true operator overlay, keep any rejection or pending status visible.

Candidate files:

- `scripts/build_korean_operator_attachment_manifest_queue.py`
- `scripts/build_korean_operator_direct_download_review.py`
- `scripts/validate_korean_operator_attachment_manifest.py`
- `implementation/phase1/open_data/korea/korean_medium_large_ingest_receipt.json`
- `implementation/phase1/open_data/korea/operator_attachment_manifest.queue.json`
- `implementation/phase1/open_data/korea/operator_attachment_direct_download_review.json`
- `implementation/phase1/open_data/korea/operator_attachment_manifest.queue.validation_report.json`
- `implementation/phase1/release_evidence/productization/commercial_gap_ledger_status.json`
- `docs/commercial-structural-solver-product-gap-ledger.md`

Verification criteria:

- Kiro wrapper receipt confirms `opus-4.8`, no-edit, and no-readiness-closure prompt boundaries.
- Queue refresh records attachment count, auto-promotable candidate count, source-mapping blocked action count, rights-blocked action count, and claim boundary.
- Direct-download review records direct/portal action counts and continues to forbid automatic raw downloads or rights claims.
- Commercial status remains `open`; G7 remains `partial` unless accepted operator-attached real MGT/IFC/PDF-derived evidence is actually present.
- Focused tests and readiness/freshness checks continue to pass.

## Return Format

Return only these sections:

- Design summary
- Implementation order
- Candidate files
- Verification plan
- Risks and claim boundary
- Cursor handoff prompt
