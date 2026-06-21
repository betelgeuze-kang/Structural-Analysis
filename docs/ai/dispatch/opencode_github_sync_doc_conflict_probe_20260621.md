# OpenCode Slice: GitHub Sync Doc Conflict Probe

Goal: Check whether user-facing docs conflict with canonical product readiness when `product_readiness_snapshot.json` contains `pm_release::github_sync::*` blockers.

Scope:
- Read:
  - `README.md`
  - `docs/commercialization-gap-current-state.md`
  - `implementation/phase1/release_evidence/productization/product_readiness_snapshot.json`
  - `tests/test_product_readiness_snapshot_doc_sync.py`
- Do not push or mutate remote state.

Desired result:
- If GitHub sync blockers exist in the snapshot, docs must not say GitHub development sync is complete.
- Prefer a small regression test and a narrow doc wording fix if needed.

Verification:
- `python3 -m pytest tests/test_product_readiness_snapshot_doc_sync.py -q`

Output summary only:
- Any mismatch found.
- Changed files if edited.
- Test result.
