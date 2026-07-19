# G1 actual-MGT state-updated matrix-free Newton diagnostic

This non-promoting diagnostic starts from the actual semantic `LIVE` full-unit
zero-state linear predictor and evaluates at most two full Newton corrections at
`lambda=1.0`. Every tangent action is evaluated at the current state by composing
the analytic reference contribution with the exact finite-chord axial correction.
The nonlinear solve residual uses the same reference CSR, load-frame delta, and
finite-chord correction parents; the component-force sum is retained only as an
audited diagnostic. That formula is bound by canonical hash
`sha256:2da9d3377eaf3cd9b196e82535c3a3593502079652306bc5705e13d910cca62f`.
A centered residual difference is available only as an independent audit and is
not the solver callback.

The zero-state reference CSR is factored once with `splu(COLAMD)` and used only as
a fixed right preconditioner. It is neither the current Jacobian nor a production
preconditioner claim. The raw current-tangent residual is replayed independently
after every FGMRES solve. The host recurrence now uses the Engine v2
`ascending_index_python_fsum_fp64.v1` accumulation order for dot products,
norms, projected back-substitution, and basis updates. The actual free-equation
order, residual formula, reference load, current-tangent action, and reference
preconditioner are hash-bound and rechecked at solve time. The current-tangent
formula and its 12 immutable little-endian parent arrays are now separately
bound by contract hash
`sha256:56fdb87292249c79557198159590710394f0b0482acf5552d55d7888cd730177`.
The NumPy callback evaluation order and SciPy SuperLU output remain outside the
cross-platform deterministic recurrence claim.

## Actual-model result

- actual uncoarsened MGT: 70,560 free equations and semantic `LIVE` load factor
  `1.0`;
- frame property coverage: 5,572/5,572 through exact source-derived DGN aliases,
  with fallback count zero and engineer review still required;
- cancellation-stable finite-chord extension and second-order axial correction;
- Newton attempts: `2`, accepted/rejected `2/0`;
- total FGMRES iterations/current-tangent actions: `5/10`;
- maximum independently replayed tangent residual:
  `4.116211867882802e-10 kN`;
- first full correction: `3823.8140951064206 N -> 0.002323337105281098 N`,
  accepted only as an in-memory diagnostic state;
- second full correction: `0.002323337105281098 N ->
  1.1767242540372536e-6 N`, accepted in memory;
- final accepted residual gate: `1.1767242540372536e-6 N <= 0.0005 N` is true;
- fallback, regularization, and line search: `0`, `0`, and not executed.

Both tangent systems pass their explicit linear residual contract. The first step
reduces the nonlinear residual by approximately 1.65 million times, the second by
approximately 1,974 times, and the overall reduction is approximately
`3.25e9`. The earlier `0.05 N` residual floor was therefore numerical
counterevidence from cancellation-prone chord-length and axial-force
subtractions, not a need for line search on this bounded local path.

## Evidence and verification

- receipt:
  `implementation/phase1/release_evidence/productization/g1_mgt_state_updated_matrix_free_newton_diagnostic_receipt.json`;
- schema:
  `src/structural_analysis/schemas/g1_mgt_state_updated_matrix_free_newton_diagnostic_v1.schema.json`;
- builder:
  `scripts/build_g1_mgt_state_updated_matrix_free_newton_diagnostic_receipt.py`;
- matrix-free solver:
  `src/structural_analysis/solvers/nonlinear/matrix_free_fgmres.py`;
- backend-neutral current tangent:
  `docs/engine-v2-current-tangent-operator.md`.

```bash
python3 scripts/build_g1_mgt_state_updated_matrix_free_newton_diagnostic_receipt.py --check
python3 -m pytest -q \
  tests/test_matrix_free_cpu_fgmres_state_tangent.py \
  tests/test_build_g1_mgt_state_updated_matrix_free_newton_diagnostic_receipt.py
```

## Claim boundary

This receipt proves two descending bounded local CPU current-tangent solves and a
local residual-gate-passing in-memory state. It does not itself prove
load-controlled nonlinear continuation, rollback, a persisted load-`1.0`
checkpoint, full corotational bending/torsion, material state commit/rollback,
scalable production preconditioning, end-to-end cross-platform deterministic
Engine v2 operator/preconditioner execution, ROCm/HIP parity, or G1 closure. In
particular, the operator formula/parent contract does not make its NumPy
evaluation or the SuperLU preconditioner an end-to-end cross-platform
determinism claim.
