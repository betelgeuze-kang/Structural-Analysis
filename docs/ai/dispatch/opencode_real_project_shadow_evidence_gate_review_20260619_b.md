# OpenCode Slice: Real-Project Measured Gate Claim Review

## Goal

Review the current Codex WIP for real-project corpus measured status and customer shadow evidence gating. Do not make broad edits.

## Scope

- `implementation/phase1/build_real_project_row_provenance_report.py`
- `implementation/phase1/check_real_project_corpus_measured_status.py`
- `implementation/phase1/customer_shadow_evidence.schema.json`
- `implementation/phase1/validate_customer_shadow_evidence.py`
- `tests/test_build_real_project_row_provenance_report.py`
- `tests/test_check_real_project_corpus_measured_status.py`
- `tests/test_validate_customer_shadow_evidence.py`
- `README.md`
- `docs/real-project-corpus.md`
- `docs/commercialization-gap-current-state.md`
- `docs/github-documentation-status.md`

## Review Criteria

- Real-project corpus must not be represented as closed while PEER metric-bearing values are incomplete.
- Measured KR artifact rows must keep checksum-or-withheld reason, stable row pointer, manual review status, release eligibility, and `release_surface_allowed=false`.
- Customer shadow evidence must reject placeholders, missing or empty required fields, raw redistribution, and non-`sha256:` reference output checksums.
- Docs must state the blocked claim boundary clearly.

## Verification

Run focused tests only:

```bash
python3 -m pytest -q tests/test_build_real_project_row_provenance_report.py tests/test_check_real_project_corpus_measured_status.py tests/test_validate_customer_shadow_evidence.py
```

## Output Rules

Return only:

- changed files, if any
- test command and pass/fail result
- concise blocker or risk summary

Do not include full logs, JSON bodies, or diffs. Keep the final output under 120 lines.
