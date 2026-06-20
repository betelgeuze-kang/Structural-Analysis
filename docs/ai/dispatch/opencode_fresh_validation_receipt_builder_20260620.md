# OpenCode Slice: Fresh Validation Receipt Builder

Goal: Add a small, safe CLI helper that can run a real fresh full-validation lane command and build a schema-valid receipt from the resulting artifacts.

Scope:
- Candidate new script: `scripts/build_fresh_validation_receipt.py`.
- Candidate tests: `tests/test_build_fresh_validation_receipt.py`.
- Reuse existing receipt contract:
  - `implementation/phase1/fresh_validation_receipt.schema.json`
  - `implementation/phase1/validate_fresh_validation_receipt.py`
  - `scripts/build_fresh_full_validation_lane_status.py`
- Do not create any tracked `implementation/phase1/release_evidence/full_validation/*.fresh_validation_receipt.json` receipt unless a real command is run in the test tmpdir.
- Do not fake or close any fresh full-validation lane.

Required behavior:
- CLI accepts lane id, runner name, validation command, one or more input paths, one or more receipt artifact paths, output receipt path, optional case counts/duration.
- CLI runs the supplied validation command for every passing receipt. Metadata-only receipt construction must be blocked because `reused_evidence=false` must mean a command actually ran.
- If the validation command exits nonzero, write no passing receipt and return nonzero with a concise blocker/result payload if an `--out-result` option exists.
- For successful command runs, compute SHA256 for input paths and receipt artifact paths, set `reused_evidence=false`, `contract_pass=true`, `reason_code=PASS`, current git HEAD, engine version matching existing metadata, and a clear claim boundary.
- Validate the built receipt using `validate_fresh_validation_receipt.validate_payload` before success.
- Keep all output concise. No secrets, no `.env*`.

Verification:
- Run focused pytest for the new tests plus:
  - `tests/test_validate_fresh_validation_receipt.py`
  - `tests/test_build_fresh_full_validation_lane_status.py`
- Report changed files, test commands/results, blockers only.
