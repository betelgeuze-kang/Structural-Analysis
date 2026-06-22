# Worker Slice: Phase 2 Material Mesh Newton Assembly Seed

Goal:
Add a narrow deterministic Phase 2 seed proving scalar material laws are consumed by a tiny global axial mesh assembly/Newton path, not only solved as standalone scalar springs.

Scope:
- Keep the slice small and local.
- Prefer adding a small module under `src/structural_analysis/assembly/` or `src/structural_analysis/solvers/nonlinear/`.
- Add a builder under `scripts/` for `phase2_material_mesh_newton_*` productization artifacts.
- Add focused pytest coverage under `tests/`.
- If appropriate, add the new artifact check to `scripts/verify_quality_gate.py --mode release`.

Candidate files:
- `src/structural_analysis/solvers/nonlinear/newton.py`
- `src/structural_analysis/assembly/nonlinear_static.py`
- `src/structural_analysis/assembly/__init__.py`
- `scripts/build_phase2_material_mesh_newton_artifacts.py`
- `tests/test_build_phase2_material_mesh_newton_artifacts.py`
- `scripts/verify_quality_gate.py`
- `implementation/phase1/release_evidence/productization/phase2_material_mesh_newton_*.json`

Requirements:
- Build a deterministic 1D axial chain with at least 2 elements and 3 nodes.
- Use at least one material law from the existing Phase 2 material breadth seed.
- Assemble global residual as `F_internal(u) - F_external`.
- Assemble a consistent global tangent/Jacobian from element/material tangents.
- Solve with Newton residual+increment gates, no regularization/fallback false PASS.
- Include a finite-difference check proving assembled tangent matches dR/du on free DOFs.
- Include a mesh/load-step or mesh partition consistency check if it can stay small.
- Record reactions/internal/external forces and convergence history.
- Keep `g1_closure_claim=false`, `material_newton_closure_claim=false`, and `full_mesh_closure_claim=false`.
- Preserve blockers for full mesh/full load, frame/shell/material coupling, sparse production backend, broad material Newton breadth, and GPU/HIP parity.
- Do not modify docs/ledgers or unrelated UI.

Verification criteria:
- `python3 scripts/build_phase2_material_mesh_newton_artifacts.py`
- `python3 scripts/build_phase2_material_mesh_newton_artifacts.py --check`
- `python3 -m pytest -q tests/test_build_phase2_material_mesh_newton_artifacts.py tests/test_build_phase2_material_newton_breadth_artifacts.py tests/test_build_phase2_nonlinear_load_step_artifacts.py`
- `python3 -m ruff check src/structural_analysis/assembly/nonlinear_static.py src/structural_analysis/solvers/nonlinear/newton.py scripts/build_phase2_material_mesh_newton_artifacts.py tests/test_build_phase2_material_mesh_newton_artifacts.py scripts/verify_quality_gate.py`

Output summary only:
- Changed files
- Tests run and result
- Core implementation summary
- Any blockers
