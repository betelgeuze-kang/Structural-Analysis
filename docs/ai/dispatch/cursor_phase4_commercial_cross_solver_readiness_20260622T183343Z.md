# Cursor worker task: Phase 4 commercial cross-solver readiness contract

Goal:
Strengthen the commercial-cross-solver readiness evidence and Developer Preview RC handoff without claiming Phase 4, Phase 3, or DP RC is closed.

Scope:
- `src/structural_analysis/benchmark/acquisition.py`
- `scripts/build_phase3_benchmark_acquisition_artifacts.py`
- `scripts/build_developer_preview_rc_status.py`
- Existing Phase 4 scripts:
  - `scripts/build_phase4_commercial_comparison_import_template.py`
  - `scripts/build_phase4_commercial_operator_reference_contract.py`
  - `scripts/build_phase4_commercial_operator_reference_ingest_validator.py`
- New script/tests if useful for a commercial cross-solver readiness receipt.
- Relevant tests under `tests/test_build_phase3_benchmark_acquisition_artifacts.py` and `tests/test_build_developer_preview_rc_status.py`

Requested implementation direction:
- Add or propose a blocked commercial cross-solver readiness receipt that summarizes:
  - import template readiness
  - operator package missing
  - permission/customer license missing
  - raw/normalized operator file checksums missing
  - at least two independent reference solvers required/current 0
  - modeling convention declarations required
  - modeling-assumption-first diagnosis required
  - GUI story/member/mode trace rows missing for operator data
  - commercial outputs are comparison references, not absolute truth
- Connect the receipt or equivalent structured handoff into acquisition plan and RC known limitations.
- Preserve claim boundaries: no operator data, no permission, no checksums, no commercial execution, and no two-reference comparison evidence means no Phase 4/Phase 3/DP RC closure.

Verification criteria:
- Focused tests pass for changed scripts/tests.
- `phase3_benchmark_acquisition_plan.json` remains blocked.
- `developer_preview_rc_status.json` remains blocked.
- Report changed files, tests run, remaining blockers, and any recommendations concisely.
