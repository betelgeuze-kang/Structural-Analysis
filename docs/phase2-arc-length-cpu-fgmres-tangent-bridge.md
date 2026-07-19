# Phase 2 arc-length CPU FGMRES tangent bridge

This slice binds one nonlinear tangent system at a time to the existing Engine
v2 `ExecutionPlan`, `EquationScaling`, reduced-CSR identity, and deterministic
CPU FGMRES recurrence. Each solve emits a compact descriptor-only receipt with
an explicit unscaled residual gate and no fallback or regularization.

For an arc-length correction, the augmented system can be reduced to two
consistent-tangent solves:

```text
K z = -R
K q = P_ref
delta_lambda = (-g - a^T z) / (a^T q + b)
delta_u = z + q delta_lambda
```

The benchmark evaluates this Schur form at pre-limit, negative-tangent
descending, and positive-tangent rehardening states of the coupled two-DOF
shallow arch. Six CPU FGMRES solves converge in two iterations each. The Schur
correction is compared against the direct dense augmented solve, and the whole
receipt is replayed exactly.

Artifacts:

- `implementation/phase1/release_evidence/productization/phase2_arc_length_cpu_fgmres_tangent_bridge_result.json`
- `implementation/phase1/release_evidence/productization/phase2_arc_length_cpu_fgmres_tangent_bridge_summary.json`
- `src/structural_analysis/schemas/arc_length_cpu_fgmres_tangent_bridge_v1.schema.json`

Run:

```bash
python3 scripts/build_phase2_arc_length_cpu_fgmres_tangent_bridge_artifacts.py
python3 scripts/build_phase2_arc_length_cpu_fgmres_tangent_bridge_artifacts.py --check
PYTHONPATH=src python3 -m pytest -q \
  tests/test_engine_v2_cpu_fgmres_tangent.py \
  tests/test_arc_length_cpu_fgmres_tangent_bridge.py \
  tests/test_build_phase2_arc_length_cpu_fgmres_tangent_bridge_artifacts.py
```

This artifact remains a one-correction tangent-solve bridge. The separate
`phase2_arc_length_cpu_fgmres_continuation_result.json` artifact now exercises
the adapter through one complete short analytic continuation path. The further
`phase2_sparse_chain_cpu_fgmres_arc_length_result.json` artifact removes dense
tangent materialization on a 12-equation analytic sparse chain. The subsequent
`phase2_load_coupled_sparse_chain_arc_length_result.json` also generalizes the
load direction from fixed `P_ref` to state-consistent `-∂R/∂λ`. None of these
artifacts connects the real frame/shell/material residual adapter,
production-scale sparse preconditioning, HIP parity, full-building G1 closure,
or release readiness.
