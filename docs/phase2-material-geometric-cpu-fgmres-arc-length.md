# Phase 2 material-geometric CPU FGMRES arc-length integration

This slice connects the bounded state-updated two-bar material-geometric
arc-length path to Engine v2 CPU FGMRES for every predictor and
Schur-corrector tangent solve.

## Implemented contract

- The physical residual and tangent still use exact current-chord two-bar
  kinematics, combined-hardening steel, and separate material and
  initial-stress tangent terms.
- Every physical attempt remains bound to one immutable accepted material
  parent. A converged step commits displacement, load factor, and both material
  states atomically; a failed step rolls back the exact parent bytes.
- The continuation API accepts a bound state-tangent solver. Its profile and
  contract hash are included in the path and checkpoint identities, so a
  checkpoint cannot be resumed under a different linear-solver contract.
- The dedicated solver binds a three-node, 18-global-DOF ExecutionPlan, its
  EquationScaling, and an exact two-equation reduced CSR operator to Engine v2
  CPU FGMRES. The adapter explicitly converts physical kN and kN/m values to
  the Engine v2 SI N and N/m inputs before each solve.
- The default dense 2x2 solver remains available and retains its existing path
  profile and hash behavior.

## Deterministic verification

The integration receipt is built by
`build_material_geometric_cpu_fgmres_arc_length_benchmark()` and records:

- 12 accepted steps and one rejected step with exact rollback and arc reduction;
- 117 external state-tangent solves, all through Engine v2 CPU FGMRES;
- maximum tangent-solve explicit residual of approximately `1.42e-14 kN`;
- at most one FGMRES iteration and three matrix-vector products per solve for
  this two-equation operator;
- zero fallback and zero regularization;
- deterministic replay and exact restart from the rejected-attempt boundary;
- the same accepted-state count as the dense reference path;
- maximum dense-reference displacement error of approximately `8.67e-19 m`;
- maximum dense-reference load-factor error of approximately `2.22e-16`;
- zero final material-state field error;
- the same limit-point crossing and descending branch as the dense path.

Run the focused checks with:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest -p no:cacheprovider -q \
  tests/test_material_geometric_fgmres_arc_length.py \
  tests/test_material_geometric_truss_arc_length.py
```

## Claim boundary

The reduced operator contains only two physical equations. Although it uses
the real Engine v2 reduced-CSR and CPU FGMRES contracts, it does not establish
production-scale sparsity or preconditioner effectiveness.

This slice also does not validate a general 2D/3D truss, frame, or shell
adapter; finite-strain constitutive behavior; ROCm/HIP nonlinear parity;
durable serialized checkpoints; external code-to-code, published, or
experimental evidence; full-building equilibrium; or G1 closure. Those claims
remain explicitly false in the receipt.
