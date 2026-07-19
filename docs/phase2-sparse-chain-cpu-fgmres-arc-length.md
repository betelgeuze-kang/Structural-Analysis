# Phase 2 sparse state-operator CPU FGMRES arc-length path

This slice removes the dense-tangent materialization requirement from the
vector spherical arc-length loop. A state-bound tangent solver receives the
accepted or trial displacement state and right-hand side, while the equilibrium
problem independently exposes a consistent tangent action for the explicit
linear-residual gate. The solver profile, state-operator mode, and contract hash
are bound into the checkpoint path contract.

The verification problem is a conservative 12-equation tridiagonal chain whose
first equation is the exact finite-rotation two-bar shallow arch. Each chain
link enforces `u_i = 0.65 u_(i-1)` on the exact equilibrium path, so all 12
displacements and the load factor have an independent scalar reduction. The
production-path problem does not expose a dense tangent method at all.

The Engine v2 binding uses 72 global DOF with 12 free equations, a 94-entry
global CSR pattern, and a 34-entry reduced CSR pattern instead of a 144-entry
dense free matrix. The receipt records:

- 5 accepted steps and one rejected step with exact rollback;
- 52 state-bound CPU FGMRES tangent solves, each taking at most 12 iterations;
- an independently recomputed explicit tangent-action residual for every solve;
- a negative-load branch after the first limit point;
- exact replay and midpoint checkpoint restart;
- agreement with a separate verification-only dense path;
- zero fallback and zero regularization.

Artifacts:

- `implementation/phase1/release_evidence/productization/phase2_sparse_chain_cpu_fgmres_arc_length_result.json`
- `implementation/phase1/release_evidence/productization/phase2_sparse_chain_cpu_fgmres_arc_length_summary.json`
- `src/structural_analysis/schemas/sparse_chain_cpu_fgmres_arc_length_v1.schema.json`

Run:

```bash
PYTHONPATH=src python3 scripts/build_phase2_sparse_chain_cpu_fgmres_arc_length_artifacts.py
PYTHONPATH=src python3 scripts/build_phase2_sparse_chain_cpu_fgmres_arc_length_artifacts.py --check
PYTHONPATH=src python3 -m pytest -q \
  tests/test_sparse_chain_cpu_fgmres_arc_length.py \
  tests/test_build_phase2_sparse_chain_cpu_fgmres_arc_length_artifacts.py
```

This closes the state-operator/sparse-CSR integration contract on one short
analytic path only. Twelve equations are not production scale, identity
preconditioning is not production preconditioner evidence, and the problem is
not a frame or shell assembly. No ROCm/HIP nonlinear parity, G1 full-load or
full-mesh closure, independent verification, or release-readiness claim is
made.

The follow-up
`phase2_load_coupled_sparse_chain_arc_length_result.json` generalizes the
state-bound contract to a residual and displacement tangent that both depend on
load factor, and independently verifies `-∂R/∂λ`. That is still an analytic
chain; it does not connect the real MGT frame/shell/material adapter or close
G1.
