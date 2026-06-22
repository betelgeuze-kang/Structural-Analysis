# Cursor worker slice: Phase 3 expected output consumption audit

Goal:
Audit the current Phase 3 benchmark factory expected-output scorecard changes and make only small, local edits if an assertion or artifact field is missing.

Scope:
- `src/structural_analysis/benchmark/factory.py`
- `src/structural_analysis/benchmark/cli.py`
- `scripts/build_phase3_benchmark_factory_artifacts.py`
- `tests/test_build_phase3_benchmark_factory_artifacts.py`
- `tests/test_structural_analysis_benchmark_cli.py`

Criteria:
- Every scorecard row must expose `expected_output_comparisons` matching the manifest row `expected_outputs` keys.
- Every scorecard row must expose `expected_output_contract_pass is True`.
- Scorecard aggregates must expose total comparison count, pass count, and overall expected-output contract pass.
- Summary/reproducibility evidence must expose the scorecard expected-output comparison aggregate without claiming full Phase 3 closure.
- Focused tests should assert the above.

Verification:
- `python3 -m pytest -q tests/test_build_phase3_benchmark_factory_artifacts.py tests/test_structural_analysis_benchmark_cli.py`
- `python3 -m ruff check src/structural_analysis/benchmark/factory.py src/structural_analysis/benchmark/cli.py scripts/build_phase3_benchmark_factory_artifacts.py tests/test_build_phase3_benchmark_factory_artifacts.py tests/test_structural_analysis_benchmark_cli.py`

Return only:
- Changed files
- Test results
- Missing evidence/blockers
