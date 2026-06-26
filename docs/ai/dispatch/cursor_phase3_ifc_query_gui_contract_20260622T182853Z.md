# Cursor worker task: Phase 3 IFC query/GUI readiness contract

Goal:
Strengthen the Phase 3 `ifc-query-and-gui` evidence contract without claiming the lane, Phase 3, or Developer Preview RC is closed.

Scope:
- `src/structural_analysis/benchmark/acquisition.py`
- `scripts/build_phase3_benchmark_acquisition_artifacts.py`
- `scripts/build_developer_preview_rc_status.py`
- New script/tests if needed for an IFC query/GUI task readiness receipt.
- `tests/test_build_phase3_benchmark_acquisition_artifacts.py`
- `tests/test_build_developer_preview_rc_status.py`

Requested implementation direction:
- Add a blocked IFC query/GUI readiness receipt that explicitly enumerates evidence required for this lane:
  - dataset repository URL or attached task source
  - per-file license review
  - source/file checksums
  - query/task manifest
  - expected query answers
  - GUI task runner command
  - 5-step workflow coverage: Import, Model Health, Analysis Setup, Run & Monitor, Compare & Report
  - task execution receipt with pass/fail and provenance
- Connect this receipt into the acquisition plan and RC known-limitations handoff.
- Preserve claim boundaries: query/GUI task evidence is extraction/UX/workflow evidence, not FEM numerical accuracy evidence, and cannot close Phase 3 or DP RC by itself.

Verification criteria:
- Focused tests pass for changed scripts/tests.
- `phase3_benchmark_acquisition_plan.json` remains blocked.
- `developer_preview_rc_status.json` remains blocked.
- Report changed files, tests run, remaining blockers, and any recommendations concisely.
