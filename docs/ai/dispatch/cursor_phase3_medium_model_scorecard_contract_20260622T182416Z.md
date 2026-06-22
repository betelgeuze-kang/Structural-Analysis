# Cursor worker task: Phase 3 medium model scorecard contract

Goal:
Strengthen the Phase 3 OpenSees medium-model evidence contract without claiming the medium-model RC gate is closed.

Scope:
- `src/structural_analysis/benchmark/acquisition.py`
- `scripts/build_phase3_benchmark_acquisition_artifacts.py`
- `scripts/build_developer_preview_rc_status.py`
- New script/tests if needed for an OpenSees medium scorecard/readiness receipt.
- `tests/test_build_phase3_benchmark_acquisition_artifacts.py`
- `tests/test_build_developer_preview_rc_status.py`

Requested implementation direction:
- Add a blocked OpenSees medium scorecard/readiness receipt that explicitly enumerates evidence required for `selected_medium_models_pass_or_approved_review`:
  - authoritative source URL and license approval
  - local candidate checksum/topology evidence boundary
  - reference outputs
  - canonical normalization
  - runner command
  - scorecard execution
  - pass or approved REVIEW decision
  - required count 5/current count 0
- Connect this receipt into the acquisition plan and RC known-limitations handoff.
- Preserve claim boundaries: topology/parser/local candidate evidence is not benchmark pass evidence and cannot close Phase 3 or DP RC.

Verification criteria:
- Focused tests pass for changed scripts/tests.
- `phase3_benchmark_acquisition_plan.json` remains blocked.
- `developer_preview_rc_status.json` remains blocked and the `selected_medium_models_pass_or_approved_review` gate remains blocked.
- Report changed files, tests run, remaining blockers, and any recommendations concisely.
