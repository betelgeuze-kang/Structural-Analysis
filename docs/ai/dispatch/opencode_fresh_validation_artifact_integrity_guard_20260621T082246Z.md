# OpenCode task: fresh validation artifact integrity guard

## Goal
Check whether fresh validation lane status should reject receipts whose `receipt_artifacts[].path` or `input_checksums` entries do not exist or whose recorded `sha256:` digest does not match the actual file.

## Scope
- Inspect only:
  - `scripts/build_fresh_full_validation_lane_status.py`
  - `tests/test_build_fresh_full_validation_lane_status.py`
  - `implementation/phase1/validate_fresh_validation_receipt.py` only for schema/validator shape

## Constraints
- Do not create or modify fresh validation receipts.
- Do not synthesize validation evidence.
- Do not mark any lane ready.
- Preserve existing missing-receipt blockers.

## Candidate improvement
In lane status, after schema validation passes, compute SHA-256 for receipt artifact paths and input checksum paths that resolve to files. Block if referenced files are missing or if recorded digests differ.

## Verification
- Focused pytest for `tests/test_build_fresh_full_validation_lane_status.py`.
- Ruff/diff check for touched Python files.

## Output
Concise summary only: changed files, tests, blockers, concerns. No full unified diff.
