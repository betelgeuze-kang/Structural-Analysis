# Goal
Expand the Phase 3 generated benchmark factory seed with a small deterministic nonlinear material-mesh axial-chain lane/case family, using existing `nonlinear_static_material_mesh` API support, without claiming full Phase 3 or commercial solver closure.

# Scope
- Add a narrow repo-generated benchmark family in `src/structural_analysis/benchmark/factory.py`.
- Reuse the existing canonical API path:
  - `AnalysisConfig(analysis_type="nonlinear_static_material_mesh", ...)`
  - cubic axial material mesh model shape already tested in `tests/test_structural_analysis_core_api.py`.
- Update manifest/scorecard handling if needed so both linear static and nonlinear material mesh benchmark cases can pass with explicit expected outputs.
- Update builder summary/claim boundary and tests to reflect the new lane/case counts.
- Keep these claims explicit:
  - repo-generated seed only
  - CPU deterministic developer-preview seed
  - no OpenSees/buildingSMART/commercial/large-model closure
  - no full Phase 2/G1 nonlinear full-mesh/full-load closure
  - no Developer Preview RC or commercial release readiness promotion

# Candidate files
- `src/structural_analysis/benchmark/factory.py`
- `src/structural_analysis/benchmark/cli.py` only if summary wording/counts require it
- `scripts/build_phase3_benchmark_factory_artifacts.py`
- `tests/test_build_phase3_benchmark_factory_artifacts.py`
- `tests/test_structural_analysis_benchmark_cli.py`
- generated productization artifacts from `python3 scripts/build_phase3_benchmark_factory_artifacts.py`

# Verification criteria
- `python3 -m pytest -q tests/test_structural_analysis_benchmark_cli.py tests/test_build_phase3_benchmark_factory_artifacts.py`
- `python3 scripts/build_phase3_benchmark_factory_artifacts.py --check`
- `python3 -m ruff check src/structural_analysis/benchmark/factory.py src/structural_analysis/benchmark/cli.py scripts/build_phase3_benchmark_factory_artifacts.py tests/test_structural_analysis_benchmark_cli.py tests/test_build_phase3_benchmark_factory_artifacts.py`
- Report changed files, new case/lane counts, tests, and blockers only.
