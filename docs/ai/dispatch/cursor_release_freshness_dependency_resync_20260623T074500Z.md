Goal: Diagnose and confirm the minimal resync sequence for release freshness blockers.

Scope:
- Inspect `scripts/build_fresh_full_validation_lane_status.py`.
- Inspect `scripts/build_evidence_console_scope_status.py`.
- Inspect `scripts/report_release_evidence_freshness.py`.
- Inspect `implementation/phase1/release_evidence/productization/release_evidence_freshness_report.json`.
- Inspect `README.md` and `docs/commercialization-gap-current-state.md` only as input dependencies for those status artifacts.

Current issue:
- `release_evidence_freshness_report.json` is blocked with:
  - `fresh_full_validation_lane_status::input_dependency_newer_than_artifact`
  - `evidence_console_scope_status::input_dependency_newer_than_artifact`
- The underlying readiness blockers must remain visible. Do not promote fresh validation, Evidence Console launch, customer shadow, G1, or release readiness.

Expected output:
- Report the exact commands that should rebuild the stale status artifacts and freshness report.
- Report whether any code changes are needed.
- Do not commit, push, revert unrelated work, or claim readiness promotion.
