# Cursor worker task: Phase 3 large model runner contract

Goal:
Strengthen the Phase 3 large-model-performance / OpenSees megatall evidence contract without claiming the large-model RC gate is closed.

Scope:
- `src/structural_analysis/benchmark/acquisition.py`
- `scripts/build_phase3_benchmark_acquisition_artifacts.py`
- `scripts/build_developer_preview_rc_status.py`
- New script/tests if needed for a large-model runner/readiness receipt.
- `tests/test_build_phase3_benchmark_acquisition_artifacts.py`
- `tests/test_build_developer_preview_rc_status.py`

Requested implementation direction:
- Add a blocked large-model runner/readiness receipt that explicitly enumerates the required evidence to close `large_models_crash_oom_free`:
  - authoritative source URL/license approval
  - source checksum
  - reference outputs
  - canonical normalization
  - nightly/workstation lane configuration
  - runner command and resource envelope
  - runtime/peak memory/crash/OOM status
  - scorecard or REVIEW decision
- Connect that receipt into the acquisition plan and RC known-limitations handoff.
- Preserve claim boundaries: policy/contract evidence is not execution evidence and must not close Phase 3 or DP RC.

Verification criteria:
- Focused tests pass for changed scripts/tests.
- `phase3_benchmark_acquisition_plan.json` remains blocked.
- `developer_preview_rc_status.json` remains blocked and the `large_models_crash_oom_free` gate remains blocked.
- Report changed files, tests run, remaining blockers, and any recommendations concisely.
