# Cursor worker task: Developer Preview dataset/license manifest split audit

Goal: Audit whether the current dataset/license manifest should separate Developer Preview seed-bundle readiness from blocked external Phase 3 corpus readiness.

Scope:
- Do not perform broad refactors.
- Inspect only the manifest builder, RC status builder, tests, and generated manifest/RC receipts.
- If making edits, keep unsupported external corpus blockers visible and non-promoting.

Candidate files:
- `scripts/build_developer_preview_readiness.py`
- `scripts/build_developer_preview_rc_status.py`
- `tests/test_build_developer_preview_readiness.py`
- `tests/test_build_developer_preview_rc_status.py`
- `implementation/phase1/release_evidence/productization/developer_preview_dataset_license_manifest.json`
- `implementation/phase1/release_evidence/productization/developer_preview_rc_status.json`

Verification criteria:
- Developer Preview seed dataset/license manifest may pass only if repo-generated bundled sources have license/checksum/expected-output coverage.
- External OpenSees, buildingSMART, IFC query, and commercial/operator sources must remain non-bundled and blocked for Phase 3/full corpus readiness.
- RC status must not claim full Phase 3 corpus readiness.
- Any remaining blockers must be visible as external corpus/final-gate blockers, not hidden.
- Report changed files, test results, failed test names, core diff summary, and blockers only.
