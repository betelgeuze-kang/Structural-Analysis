# OpenCode audit: Phase 3 analytic-small 20-case seed

Goal: audit the Phase 3 benchmark factory expansion from 6 to 20 generated analytic/component cases.

Scope:
- `src/structural_analysis/benchmark/factory.py`
- `scripts/build_phase3_benchmark_factory_artifacts.py`
- `tests/test_build_phase3_benchmark_factory_artifacts.py`
- generated `implementation/phase1/release_evidence/productization/phase3_benchmark_factory_seed_*.json`

Check:
- Manifest has exactly 20 generated analytic-small cases with checksum, truth class, license, expected outputs, modeling assumptions, and selected lane.
- Scorecard is produced by canonical API execution for all 20 cases, not by copying expected values.
- Summary sets `analytic_component_quantity_gate_met=true` but keeps `phase3_closure_claim=false` and `full_phase3_quantity_gates_met=false`.
- Remaining medium/large/IFC/OpenSees/buildingSMART/commercial-cross-solver gaps remain visible.
- `--check` still detects stale artifacts.

Verification to run:
- `python3 scripts/build_phase3_benchmark_factory_artifacts.py --check`
- `python3 -m pytest -q tests/test_build_phase3_benchmark_factory_artifacts.py`
- `python3 -m ruff check src/structural_analysis/benchmark/factory.py scripts/build_phase3_benchmark_factory_artifacts.py tests/test_build_phase3_benchmark_factory_artifacts.py`

Return only:
- changed files inspected
- test results
- failed test names, if any
- core findings or blockers
