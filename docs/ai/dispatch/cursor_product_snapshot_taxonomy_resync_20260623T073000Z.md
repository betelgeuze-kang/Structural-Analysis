Goal: Review the product readiness snapshot taxonomy and resync gap for the active Codex goal.

Scope:
- Inspect `scripts/build_product_readiness_snapshot.py`.
- Inspect `tests/test_build_product_readiness_snapshot.py`.
- Inspect `tests/test_product_readiness_snapshot_doc_sync.py`.
- Inspect `implementation/phase1/release_evidence/productization/product_readiness_snapshot.json`.
- Inspect `README.md` and `docs/commercialization-gap-current-state.md` only for canonical snapshot summary lines.

Candidate issue:
- `python3 scripts/build_product_readiness_snapshot.py --check --fail-blocked` currently reports semantic mismatch.
- The generated snapshot reports blocker_count 84 while the stored snapshot/docs still report 81.
- `independent_product::...residual_holdout_closure_pending` is currently classified under `release freshness/sync`; decide whether it should remain there or map to a solver/numerical stream based on existing contract language.

Verification criteria:
- Report the minimal code/docs/tests changes needed.
- Do not push, commit, revert unrelated work, or rewrite broad generated evidence outside the snapshot/doc sync.
- Keep assisted_service_pilot and solver_product gates separate.
- Do not promote readiness; blocked/stale states must stay visible.
