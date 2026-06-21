# OpenCode Slice: Fresh Validation Runner Command Guard

Goal:
Tighten `scripts/build_fresh_validation_receipt.py` so a fresh validation
receipt cannot be generated from arbitrary commands such as `python3 -c "pass"`.

Scope:
- Inspect `scripts/build_fresh_validation_receipt.py`.
- Add a small runner-command policy that requires `--validation-command` to
  match a registered runner prefix before subprocess execution.
- Keep metadata-only, missing artifact, command failure, and schema validation
  blockers explicit.
- Update `tests/test_build_fresh_validation_receipt.py` with focused coverage.

Candidate files:
- `scripts/build_fresh_validation_receipt.py`
- `tests/test_build_fresh_validation_receipt.py`

Verification:
- `python3 -m pytest tests/test_build_fresh_validation_receipt.py -q`
- `python3 -m ruff check scripts/build_fresh_validation_receipt.py tests/test_build_fresh_validation_receipt.py`

Claim boundary:
This is evidence-boundary hardening only. Do not generate fresh validation
receipts, do not promote any lane, and do not mark external/customer/fresh
validation evidence as closed.
