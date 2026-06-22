# Cursor Worker Task: Phase 3 Expected Outputs Scorecard Audit

Goal:
Audit whether generated Phase 3 benchmark factory cases only declare `expected_outputs` in the manifest or whether the scorecard proves those expected outputs were consumed as comparisons.

Scope:
- Read:
  - `/home/betelgeuze/.codex/attachments/98075342-506d-4368-9755-b528a830c410/goal-objective.md`
  - `.betelgeuze/intent_spec.md`
  - `.betelgeuze/project_contract.yaml`
  - `src/structural_analysis/benchmark/factory.py`
  - `scripts/build_phase3_benchmark_factory_artifacts.py`
  - `tests/test_build_phase3_benchmark_factory_artifacts.py`
  - `tests/test_structural_analysis_benchmark_cli.py`
- Candidate edit files, only if needed:
  - `src/structural_analysis/benchmark/factory.py`
  - `scripts/build_phase3_benchmark_factory_artifacts.py`
  - `tests/test_build_phase3_benchmark_factory_artifacts.py`
  - `tests/test_structural_analysis_benchmark_cli.py`

Acceptance criteria:
- Phase 3 seed scorecard must expose machine-readable expected-output comparison rows or equivalent evidence for every case.
- Summary/reproducibility evidence must not rely only on manifest declarations for expected outputs.
- Preserve the claim boundary: seed analytic/component cases do not close full Phase 3 medium/large/IFC gates.

Verification:
- Run focused tests for changed files.
- Summarize changed files, tests, and blockers only.
