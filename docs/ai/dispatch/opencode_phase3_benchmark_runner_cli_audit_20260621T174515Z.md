# OpenCode slice: Phase 3 benchmark runner CLI audit

Goal: Audit the smallest gap between the existing Phase 3 benchmark factory seed and the Developer Preview RC deliverable "benchmark runner".

Scope:
- Read only:
  - `src/structural_analysis/benchmark/factory.py`
  - `src/structural_analysis/benchmark/__init__.py`
  - `scripts/build_phase3_benchmark_factory_artifacts.py`
  - `tests/test_build_phase3_benchmark_factory_artifacts.py`
  - `pyproject.toml`
  - `setup.cfg`
- Do not edit files.

Question:
- Does the repo currently expose a package-level benchmark runner CLI, or only script-local artifact builders?
- Identify the smallest entrypoint/test/artifact fields needed to prove a user can run the generated benchmark seed from the installed package without claiming full Phase 3 closure.

Return only:
- Candidate files to edit.
- Missing/weak runner evidence fields.
- Suggested test names/commands.
- Blockers, if any.
