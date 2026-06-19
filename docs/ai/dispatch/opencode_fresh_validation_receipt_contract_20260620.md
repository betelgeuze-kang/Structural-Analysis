# Fresh Full-Validation Receipt Contract Slice

Goal: make fresh full-validation lane receipts explicit, validated artifacts instead of ad hoc JSON metadata.

Scope:
- Add a fresh validation receipt schema under `implementation/phase1/`.
- Add a validator CLI under `implementation/phase1/`.
- Add a template under `docs/templates/`.
- Update `scripts/build_fresh_full_validation_lane_status.py` so an existing receipt must pass the validator contract.
- Update focused tests for the validator and lane status.

Candidate files:
- `implementation/phase1/fresh_validation_receipt.schema.json`
- `implementation/phase1/validate_fresh_validation_receipt.py`
- `docs/templates/fresh_validation_receipt.template.json`
- `scripts/build_fresh_full_validation_lane_status.py`
- `tests/test_validate_fresh_validation_receipt.py`
- `tests/test_build_fresh_full_validation_lane_status.py`

Verification criteria:
- Missing receipts stay blocked as `fresh_validation_receipt_missing`.
- Existing invalid receipts become `fresh_validation_receipt_invalid`.
- Existing reused receipts stay blocked with `fresh_validation_receipt_reuses_evidence`.
- A valid receipt requires at least `schema_version`, `lane_id`, `runner`, `generated_at`, `source_commit_sha`, `engine_version`, nonempty `input_checksums`, `reused_evidence=false`, `contract_pass=true`, `reason_code=PASS`, `validation_command`, `receipt_artifacts`, `summary`, and `claim_boundary`.
- Run `pytest tests/test_validate_fresh_validation_receipt.py tests/test_build_fresh_full_validation_lane_status.py`.

Do not:
- Run git commit, git push, merge, or modify `.env*`.
- Mark any fresh lane as closed without a real receipt.
- Read full raw worker logs or huge generated evidence.
