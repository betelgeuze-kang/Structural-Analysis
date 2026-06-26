Goal: Add a narrow Phase 2 nonlinear mesh/load-step convergence suite artifact without claiming G1 closure.

Scope:
- Inspect existing material mesh Newton artifact patterns.
- Add or review a dedicated builder for a small 1D strain-cubic axial mesh/load-step convergence grid.
- Keep claim boundaries explicit: this may prove only a narrow 1D material mesh/load-step seed, not full-mesh/full-load G1.

Candidate files:
- scripts/build_phase2_material_mesh_newton_artifacts.py
- src/structural_analysis/assembly/nonlinear_static.py
- new scripts/build_phase2_mesh_load_step_convergence_artifacts.py
- new tests/test_build_phase2_mesh_load_step_convergence_artifacts.py
- scripts/verify_quality_gate.py and tests/test_verify_quality_gate.py if wired into full/release checks
- implementation/phase1/release_evidence/productization/phase2_mesh_load_step_convergence_*.json

Verification criteria:
- Builder and --check pass.
- Focused pytest for the new builder and verify_quality_gate if touched.
- Ruff passes on changed Python files.
- Summary keeps g1_closure_claim=false and broad blockers visible.
- Output only Changed files, Test results, Failed tests, Core diff summary, Blockers.
