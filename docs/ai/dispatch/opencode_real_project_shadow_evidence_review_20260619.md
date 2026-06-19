# OpenCode Slice: Real-Project Corpus + Customer Shadow Evidence Review

## Goal

Review the local plan for advancing the real-project corpus from planned-only rows toward measured evidence and adding a customer shadow evidence schema.

## Scope

- `implementation/phase1/build_real_project_row_provenance_report.py`
- `implementation/phase1/build_peer_tbi_benchmark_metric_records.py`
- tests for those scripts
- any new customer shadow evidence schema/validator files if Codex adds them
- docs touching `docs/real-project-corpus.md` or README status

## Context

Do not promote raw redistribution or autonomous/commercial replacement claims. Real-project rows may count measured local artifacts only if they have checksum or withheld reason, stable row pointer, manual review status, and release eligibility explicitly stated. PEER metric rows must distinguish measured run evidence from external reference benchmark truth.

## Verification

Run focused tests for changed scripts. If customer shadow schema is added, run its validator tests too.

## Output Rules

Return only:

- changed files
- test commands and pass/fail result
- concise risk or blocker summary

Do not include full logs, full JSON bodies, or diffs.
