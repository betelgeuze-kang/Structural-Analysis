# Cursor worker task: Phase 6 RC verification sweep

Goal: Independently verify the current Phase 6 Developer Preview RC evidence slice.

Scope:
- Do not implement broad new behavior.
- Inspect only the current changed files needed to confirm Phase 3 acquisition command separation and Phase 6 RC status evidence.
- Report changed files, test results, failed test names, core diff summary, and blockers only.

Candidate files:
- `src/structural_analysis/benchmark/acquisition.py`
- `scripts/build_phase3_benchmark_acquisition_artifacts.py`
- `scripts/build_developer_preview_rc_status.py`
- `scripts/report_release_evidence_freshness.py`
- `tests/test_build_phase3_benchmark_acquisition_artifacts.py`
- `tests/test_build_developer_preview_rc_status.py`
- `implementation/phase1/release_evidence/productization/phase3_benchmark_acquisition_plan.json`
- `implementation/phase1/release_evidence/productization/developer_preview_rc_status.json`

Verification criteria:
- Phase 3 acquisition plan remains blocked for external corpus readiness.
- `sample_acquisition_command` is separately ready/pass and is explicitly no-download/no-network.
- Developer Preview RC status remains blocked but treats sample acquisition command as pass.
- Remaining blockers still expose dataset/license and final gate gaps.
- Focused tests and freshness checks pass if run locally.
