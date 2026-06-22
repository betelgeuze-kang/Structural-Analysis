# Cursor worker slice: G1 HIP lane source commit refresh

Goal:
- Diagnose whether `implementation/phase1/release_evidence/productization/g1_full_load_hip_newton_lane_report.json`
  can be safely regenerated at current `HEAD` to remove only stale source-commit mismatch blockers.

Context:
- Current `HEAD` is `c7dea7e22b3ba69d9d46b9fb11901ed85f2c5978`.
- `g1_full_load_hip_newton_lane_report.json` still records `source_commit_sha=d33a7132976afce8a56aa4cc8e10d26b7285010b`.
- Do not close or hide real blockers such as missing `/dev/kfd`, missing `/dev/dri`, non-full-load scale, full-mesh nonlinear/material Newton gaps, or production HIP residency gaps.

Scope:
- Candidate files:
  - `scripts/run_g1_full_load_hip_newton_lane.py`
  - `tests/test_run_g1_full_load_hip_newton_lane.py`
  - `implementation/phase1/release_evidence/productization/g1_full_load_hip_newton_lane_report.json`
  - downstream readiness snapshots only if regeneration is required

Tasks:
- Find the supported command to refresh/check the G1 lane report.
- If the report can be regenerated locally without requiring unavailable HIP hardware, do so in a way that preserves all true blockers.
- If code/test expectations need adjustment for current-HEAD regeneration semantics, make the smallest safe change.
- Do not fabricate any pass/ready claim.

Verification:
- Run the focused test for `run_g1_full_load_hip_newton_lane`.
- Run the G1 lane check/build command if one exists.
- Summarize changed files, command results, and whether the source-commit mismatch was removed while runtime HIP blockers stayed visible.
