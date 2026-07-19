# Phase 2 adaptive consistent-Newton continuation

This slice adds an accepted-state load-continuation contract around the existing vector Newton solver. A failed trial never mutates the accepted checkpoint: the step is rolled back exactly, the load increment is reduced, and only a solver receipt with both residual and increment gates may be committed.

The analytic evidence case is a two-element 1D strain-cubic axial chain. Its first `0.5` trial is deliberately rejected by the configured iteration budget, then the controller reduces the increment and reaches absolute load factor `1.0` through committed steps. A checkpoint at `0.5` restarts to the exact same final state hash as the one-shot run.

Evidence includes:

- canonical residual formula hash for `F_internal_minus_F_external`;
- finite-difference assembled Jacobian agreement;
- local quadratic convergence order from full Newton steps;
- complete line-search histories;
- fail-closed scalar/vector probes proving a non-descending line search cannot
  be accepted merely because its unchanged state has a zero applied increment;
- exact rollback hashes for rejected trials;
- residual and increment gates for every committed step;
- fallback and regularization counts equal to zero;
- deterministic checkpoint/restart equality.

Artifacts:

- `implementation/phase1/release_evidence/productization/phase2_adaptive_newton_continuation_result.json`
- `implementation/phase1/release_evidence/productization/phase2_adaptive_newton_continuation_summary.json`
- `src/structural_analysis/schemas/adaptive_newton_continuation_v1.schema.json`

Run:

```bash
python3 scripts/build_phase2_adaptive_newton_continuation_artifacts.py
python3 scripts/build_phase2_adaptive_newton_continuation_artifacts.py --check
python3 -m pytest -q tests/test_nonlinear_adaptive_continuation.py \
  tests/test_build_phase2_adaptive_newton_continuation_artifacts.py
```

This closes only the narrow analytic continuation contract. It does not promote the repository’s G1 row: full-building load factor `1.0`, general frame/shell consistent Jacobians, state-updated material breadth, arc-length snap-through, and production ROCm/HIP parity remain open.

Fully constrained stateful prescribed-displacement fixtures are governed by a
separate `no_solve_reaction_only` contract. They do not run this Newton
recurrence and are not counted as convergence evidence. The generic adaptive
controller can advance empty-vector load checkpoints under that disposition,
but records residual/increment gates as `null`, `solver_executed=false`, and
`convergence_claim=false`; an invalid zero-equation assembly rolls back and
fails closed. The analytic receipt above remains an active-free-equation
Newton receipt and records zero no-solve steps.

The shared Newton configuration rejects non-finite/non-positive gates and
invalid backtracking sequences before any active-equation solver invocation,
so continuation cannot convert an infinite-tolerance configuration into a
convergence receipt.

The installable `AnalysisConfig` boundary now applies the same fail-closed
policy before the public linear-static and axial material-mesh paths consume
their numerical controls. Boolean, non-numeric, non-finite, zero, and negative
tolerances are blocked; the material-mesh path also blocks boolean,
fractional, string, and negative iteration limits while retaining `0` as its
documented bounded-default selector. Invalid Python API and CLI requests emit
schema-valid, strict-JSON-serializable blocked envelopes with
`solver_executed=false`, `convergence_claim=false`, and no fallback or
regularization. This input guard is not nonlinear solution evidence.
