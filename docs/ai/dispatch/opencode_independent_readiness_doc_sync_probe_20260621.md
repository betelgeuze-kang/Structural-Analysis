# OpenCode Slice: Independent Readiness Doc Sync Probe

Goal: Check whether README independent commercial product status matches `implementation/phase1/release/independent_product_readiness.json`.

Scope:
- Read and optionally edit:
  - `README.md`
  - `tests/test_product_readiness_snapshot_doc_sync.py`
  - `implementation/phase1/release/independent_product_readiness.json`

Desired result:
- README must not claim an independent readiness score that differs from the JSON receipt.
- Prefer a small regression test that derives the score/status from the JSON.
- Do not change readiness evidence or promote blockers.

Verification:
- `python3 -m pytest tests/test_product_readiness_snapshot_doc_sync.py -q`
- `python3 -m ruff check tests/test_product_readiness_snapshot_doc_sync.py`

Output summary only:
- Any mismatch found.
- Changed files if edited.
- Test result.
