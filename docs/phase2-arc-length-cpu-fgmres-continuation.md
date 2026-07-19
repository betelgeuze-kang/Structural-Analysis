# Phase 2 complete short-path CPU FGMRES arc-length integration

This slice runs the accepted/trial/rollback vector spherical arc-length loop
with Engine v2 deterministic CPU FGMRES for every predictor and Schur-corrector
tangent solve. The external tangent solver profile and its ExecutionPlan,
EquationScaling, recurrence, and tolerance binding are included in the path
contract hash, so a checkpoint cannot be resumed under a different backend
contract.

The coupled two-DOF shallow-arch path starts at zero load, crosses the first
limit point, follows the descending branch, and reaches a negative load factor.
The run records:

- 6 accepted steps and one rejected step with exact rollback;
- 57 bound tangent solves, each converging in at most two FGMRES iterations;
- explicit unscaled residual checks for every tangent solve;
- bit-identical deterministic replay and midpoint checkpoint restart;
- the same checkpoint count and at most `1e-12` deviation from the dense
  augmented reference path;
- exact coupled-potential reduction checks;
- zero fallback and zero regularization.

Artifacts:

- `implementation/phase1/release_evidence/productization/phase2_arc_length_cpu_fgmres_continuation_result.json`
- `implementation/phase1/release_evidence/productization/phase2_arc_length_cpu_fgmres_continuation_summary.json`
- `src/structural_analysis/schemas/arc_length_cpu_fgmres_continuation_v1.schema.json`

Run:

```bash
python3 scripts/build_phase2_arc_length_cpu_fgmres_continuation_artifacts.py
python3 scripts/build_phase2_arc_length_cpu_fgmres_continuation_artifacts.py --check
PYTHONPATH=src python3 -m pytest -q \
  tests/test_nonlinear_vector_arc_length.py \
  tests/test_engine_v2_cpu_fgmres_tangent.py \
  tests/test_arc_length_cpu_fgmres_continuation.py \
  tests/test_build_phase2_arc_length_cpu_fgmres_continuation_artifacts.py
```

This closes only a complete short analytic path integration. It does not connect
a frame/shell consistent residual, verify a production-scale sparse
preconditioner, establish ROCm/HIP nonlinear parity, close full-load/full-mesh
G1, or provide release-readiness evidence.

The follow-up `phase2_sparse_chain_cpu_fgmres_arc_length_result.json` removes
the dense-tangent materialization requirement and exercises a state-bound sparse
CSR solver on a 12-equation analytic chain. That follow-up still does not supply
frame/shell assembly, production scale, HIP parity, or G1 closure.

The later `phase2_load_coupled_sparse_chain_arc_length_result.json` replaces
the fixed `P_ref` load direction with the state-consistent `-∂R/∂λ` contract and
verifies both load and displacement derivatives on an analytic sparse chain.
It likewise does not provide an MGT/G1 adapter or production evidence.
