Goal: Audit the Phase 1/2 axial linear-static core slice for false closure claims and solver boundary correctness.

Scope:
- `src/structural_analysis/elements/axial.py`
- `src/structural_analysis/assembly/linear_static.py`
- `src/structural_analysis/solvers/linear/static.py`
- `src/structural_analysis/api/core.py`
- `tests/test_structural_analysis_core_api.py`

Check:
- Element stiffness, global assembly, and linear solve are separated and all consume the canonical model.
- The implemented `linear_static` path should only pass the narrow axial/truss preview case.
- Unsupported frame/IFC/general solver cases must remain blocked and must not imply commercial linear solver closure.
- Result metrics/convergence history should retain provenance and tolerance/residual evidence.

Please return only:
- changed files, if any
- test commands/results, if run
- core findings
- blockers
