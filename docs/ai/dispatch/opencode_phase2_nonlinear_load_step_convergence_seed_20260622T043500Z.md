# Goal
Add a narrow Phase 2 nonlinear load-step convergence seed for the existing scalar cubic-spring Newton reference without claiming G1/full nonlinear closure.

# Scope
- Implement a deterministic load-step partition convergence artifact for the existing scalar nonlinear axial/cubic spring reference.
- Compare final load factor 1.0 solutions for partitions such as 1, 2, 4, and 8 steps.
- Use the existing `newton_raphson_scalar`, residual contract `F_internal_minus_F_external`, consistent tangent, and residual+increment gates.
- Continue each partition from the previous accepted step displacement.
- Record per-step residual gate, increment gate, iteration count, line search usage, final displacement, expected analytic displacement, and no regularization/fallback.
- Keep claim boundaries explicit:
  - `g1_closure_claim=false`
  - `nonlinear_newton_closure_claim=false`
  - this is scalar load-step convergence only, not full mesh/material/frame/shell nonlinear convergence.

# Candidate files
- `scripts/build_phase2_nonlinear_load_step_artifacts.py` (new)
- `tests/test_build_phase2_nonlinear_load_step_artifacts.py` (new)
- `scripts/verify_quality_gate.py`
- optionally `scripts/build_phase2_newton_globalization_artifacts.py` if it should reference the new artifact path, but do not merge broad closure claims.

# Verification criteria
- `python3 scripts/build_phase2_nonlinear_load_step_artifacts.py`
- `python3 scripts/build_phase2_nonlinear_load_step_artifacts.py --check`
- `python3 -m pytest -q tests/test_build_phase2_nonlinear_load_step_artifacts.py tests/test_build_phase2_newton_globalization_artifacts.py`
- `python3 -m ruff check scripts/build_phase2_nonlinear_load_step_artifacts.py tests/test_build_phase2_nonlinear_load_step_artifacts.py`
- Worker summary must list changed files, test commands/results, key diff points, and blockers only.
