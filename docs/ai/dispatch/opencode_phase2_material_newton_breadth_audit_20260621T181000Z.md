# Worker Slice: Phase 2 Material Newton Breadth Audit

Goal:
Audit the existing Phase 2 material-Newton breadth seed implementation for claim-boundary correctness and missing verification before Codex regenerates artifacts.

Scope:
- Inspect only these files unless needed for direct imports:
  - src/structural_analysis/solvers/nonlinear/newton.py
  - src/structural_analysis/solvers/nonlinear/__init__.py
  - scripts/build_phase2_material_newton_breadth_artifacts.py
  - tests/test_build_phase2_material_newton_breadth_artifacts.py
  - scripts/verify_quality_gate.py
- Do not edit files.

Questions:
- Does the implementation cover at least two scalar constitutive/nonlinear laws?
- Does every law use explicit F_internal - F_external residual, consistent tangent, finite-difference tangent check, residual gate, increment gate, and no regularization/fallback pass?
- Are G1/material Newton closure claims explicitly false with remaining blockers preserved?
- What focused commands should Codex run after artifact generation?

Output summary only:
- Pass/fail assessment
- Any claim-boundary risks
- Any missing tests or artifacts
- Suggested focused commands
