# OpenCode Slice: G1 Load-Path Provenance Gate

Goal: Inspect whether `scripts/run_g1_full_load_hip_newton_lane.py` can cheaply strengthen the G1 full-load checkpoint input gate by requiring load-path provenance, not only a numeric `load_scale`.

Scope:
- Read and optionally edit:
  - `scripts/run_g1_full_load_hip_newton_lane.py`
  - `tests/test_run_g1_full_load_hip_newton_lane.py`

Desired behavior:
- Do not promote G1 readiness.
- Keep `load_scale < 1.0` blocked as today.
- If a checkpoint claims `load_scale >= 1.0` but metadata shows an accepted frontier below required full load or a failed bracket below full load, block the lane with an explicit load-path provenance blocker.
- Preserve existing successful unit-test fixtures by updating helper metadata if needed.

Verification:
- `python3 -m pytest tests/test_run_g1_full_load_hip_newton_lane.py -q`
- `python3 -m ruff check scripts/run_g1_full_load_hip_newton_lane.py tests/test_run_g1_full_load_hip_newton_lane.py`

Output summary only:
- Changed files.
- Tests run and result.
- Any blocker.
