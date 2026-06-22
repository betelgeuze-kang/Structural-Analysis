# Cursor worker slice: Phase 2 deterministic-core artifact freshness

Goal:
- Audit and refresh Phase 2 deterministic-core evidence artifacts so they match the current HEAD without promoting G1/full commercial closure.

Scope:
- Candidate builders:
  - `scripts/build_phase2_linear_reference_artifacts.py`
  - other `scripts/build_phase2_*` builders if their summary artifacts are stale.
- Candidate artifacts:
  - `implementation/phase1/release_evidence/productization/phase2_*`
- Candidate tests:
  - `tests/test_build_phase2_linear_reference_artifacts.py`
  - any focused `tests/test_build_phase2_*` tests discovered by `rg`.

Constraints:
- Preserve claim boundaries: Phase 2 artifacts may prove narrow axial/scalar/material/coupling seeds, not G1 full-mesh/full-load closure.
- Keep `g1_closure_claim=false`, no regularization/fallback false PASS, and blockers visible.
- Do not run long CPU diagnostic G1 continuation probes.

Verification:
- Run relevant `--check` commands for Phase 2 builders.
- Run focused pytest for changed Phase 2 builders/tests.
- Report changed files, tests, failed checks, and remaining blockers.
