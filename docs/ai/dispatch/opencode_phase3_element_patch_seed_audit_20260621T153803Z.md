# OpenCode audit: Phase 3 element-patch seed

Goal: audit the Phase 3 benchmark factory expansion that adds generated `element-patch` cases.

Scope:
- `src/structural_analysis/benchmark/factory.py`
- `scripts/build_phase3_benchmark_factory_artifacts.py`
- `tests/test_build_phase3_benchmark_factory_artifacts.py`
- generated `implementation/phase1/release_evidence/productization/phase3_benchmark_factory_seed_*.json`

Check:
- Manifest contains 20 `analytic-small` cases and 6 `element-patch` cases.
- `element-patch` cases exercise X/Y/Z axis-aligned element patch behavior and translated coordinates.
- Scorecard compares the correct displacement/reaction DOF from canonical API metrics for each case.
- Summary reports `element-patch` as `seed_ready`, while OpenSees, buildingSMART IFC, commercial-cross-solver, and large-model lanes remain open.
- `phase3_closure_claim=false` and `full_phase3_quantity_gates_met=false` remain true.

Verification to run:
- `python3 scripts/build_phase3_benchmark_factory_artifacts.py --check`
- `python3 -m pytest -q tests/test_build_phase3_benchmark_factory_artifacts.py`
- `python3 -m ruff check src/structural_analysis/benchmark/factory.py scripts/build_phase3_benchmark_factory_artifacts.py tests/test_build_phase3_benchmark_factory_artifacts.py`

Return only:
- changed files inspected
- test results
- failed test names, if any
- core findings or blockers
