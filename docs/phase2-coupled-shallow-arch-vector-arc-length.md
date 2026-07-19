# Phase 2 coupled shallow-arch vector arc-length continuation

This slice generalizes the scalar spherical arc-length contract to a dense
multi-DOF residual and consistent tangent. The predictor solves
`K du/dlambda = P_ref`; the corrector solves equilibrium and the weighted
spherical constraint together in one augmented Newton system.

The verification problem is a conservative two-DOF potential. Its primary DOF
uses the exact finite-rotation two-bar shallow arch, while a non-diagonal
symmetric coupling term adds a second equilibrium equation. The exact reduction
is `u1 = 0.35 u0` and `lambda = F_arch(u0)`, so every accepted vector checkpoint
can be checked independently against the scalar closed-form path.

The committed receipt records:

- 28 accepted path steps and one rejected large step;
- exact accepted-state hash retention and arc-length reduction on rejection;
- first-limit accepted-path load error below 1%;
- descending, negative-load, and rehardening path branches;
- six full-matrix tangent, symmetry, and strain-energy-gradient checks;
- configuration-bound checkpoint hashes and bit-identical midpoint restart;
- deterministic replay with zero fallback and zero regularization.

The separate `phase2_arc_length_cpu_fgmres_tangent_bridge_result.json` receipt
shows that each augmented corrector increment can be recovered from two bound
Engine v2 CPU FGMRES tangent solves through a Schur reduction. A further
`phase2_arc_length_cpu_fgmres_continuation_result.json` receipt runs that adapter
through a complete short analytic path and compares it with this dense path.
The later `phase2_sparse_chain_cpu_fgmres_arc_length_result.json` receipt also
removes dense tangent materialization from the production path on a 12-equation
analytic sparse chain.

Artifacts:

- `implementation/phase1/release_evidence/productization/phase2_coupled_shallow_arch_vector_arc_length_result.json`
- `implementation/phase1/release_evidence/productization/phase2_coupled_shallow_arch_vector_arc_length_summary.json`
- `src/structural_analysis/schemas/coupled_shallow_arch_vector_arc_length_v1.schema.json`

Run:

```bash
python3 scripts/build_phase2_coupled_shallow_arch_vector_arc_length_artifacts.py
python3 scripts/build_phase2_coupled_shallow_arch_vector_arc_length_artifacts.py --check
PYTHONPATH=src python3 -m pytest -q \
  tests/test_nonlinear_vector_arc_length.py \
  tests/test_coupled_shallow_arch_vector_arc_length_benchmark.py \
  tests/test_build_phase2_coupled_shallow_arch_vector_arc_length_artifacts.py
```

This remains a narrow dense two-DOF analytic seed. It is not a frame or shell
formulation, Lee-frame evidence, material-geometric coupling, published or
experimental validation, a sparse production solver, ROCm/HIP parity, a
full-building solve, G1 closure, or release-readiness evidence.
