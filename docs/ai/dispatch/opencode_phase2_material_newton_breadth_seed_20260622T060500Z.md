# Worker Slice: Phase 2 Material Newton Breadth Seed

Goal:
Add a narrow deterministic Phase 2 material-Newton breadth seed that proves more than one scalar constitutive/nonlinear material law can be solved with the same explicit `F_internal - F_external` residual contract, consistent tangent, residual gate, increment gate, and no regularization/fallback false PASS.

Scope:
- Prefer small additions under `src/structural_analysis/solvers/nonlinear/`.
- Add a builder under `scripts/` for `phase2_material_newton_breadth_*` productization artifacts.
- Add focused pytest coverage under `tests/`.
- If needed, add the new artifact check to `scripts/verify_quality_gate.py --mode release` without weakening existing checks.

Candidate files:
- `src/structural_analysis/solvers/nonlinear/newton.py`
- `src/structural_analysis/solvers/nonlinear/__init__.py`
- `scripts/build_phase2_material_newton_breadth_artifacts.py`
- `tests/test_build_phase2_material_newton_breadth_artifacts.py`
- `scripts/verify_quality_gate.py`
- `implementation/phase1/release_evidence/productization/phase2_material_newton_breadth_*.json`

Requirements:
- Cover at least two material/nonlinear laws, for example cubic hardening and bilinear/softening/hardening scalar axial laws.
- Use explicit residual `F_internal - F_external`.
- Record consistent tangent/Jacobian and a finite-difference tangent check for each law.
- Require both residual and increment gates.
- Record `regularization_used=false`, `fallback_used=false`; any regularized/degraded path must not pass as ready.
- Keep `g1_closure_claim=false` and `material_newton_closure_claim=false`.
- Preserve blockers for full mesh/full load, frame/shell/material coupling, sparse production backend, and GPU/HIP parity.
- Do not modify unrelated docs or ledgers.

Verification criteria:
- `python3 scripts/build_phase2_material_newton_breadth_artifacts.py`
- `python3 scripts/build_phase2_material_newton_breadth_artifacts.py --check`
- `python3 -m pytest -q tests/test_build_phase2_material_newton_breadth_artifacts.py tests/test_build_phase2_newton_globalization_artifacts.py tests/test_build_phase2_nonlinear_load_step_artifacts.py`
- `python3 -m ruff check src/structural_analysis/solvers/nonlinear/newton.py scripts/build_phase2_material_newton_breadth_artifacts.py tests/test_build_phase2_material_newton_breadth_artifacts.py scripts/verify_quality_gate.py`

Output summary only:
- Changed files
- Tests run and result
- Core implementation summary
- Any blockers
