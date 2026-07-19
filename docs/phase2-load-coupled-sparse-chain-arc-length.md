# Phase 2 load-coupled sparse-chain arc-length

This slice closes one contract gap between the analytic vector arc-length kernel
and the G1 physical residual. The original proportional-load contract assumes

`R(u, λ) = F_int(u) - λ F_ref`

and therefore uses `F_ref` as `-∂R/∂λ`. The real G1 assembly also changes
load-dependent geometric terms with `λ`, so that shortcut is not generally a
consistent load derivative.

## Contract

The state-bound path now supports a fail-closed load-coupled mode with three
problem operations:

- `residual_kn(u, λ)` evaluates the full physical residual;
- `consistent_state_tangent_action_kn_per_m(u, λ, v)` evaluates `J_u v`;
- `negative_load_derivative_kn(u, λ)` evaluates `-∂R/∂λ`.

The predictor solves `J_u du/dλ = -∂R/∂λ`. Each Schur corrector solves one
residual direction and one load-linearization direction at the same trial
`(u, λ)` state. The independently recomputed tangent-action residual gate still
applies to every external solve. A checkpoint hash binds the equilibrium mode,
solver profile, solver contract, and numerical path settings. Partial
load-coupled implementations fail closed, and this mode requires a state-bound
tangent solver.

## Analytic verification

The verification problem is the existing 12-equation tridiagonal shallow-arch
chain plus the load-dependent primary force `λ β u0`, with `β = 2 kN/m`. Its
primary equilibrium has the exact reduction

`λ = F_arch(u0) / (1 - β u0)`.

The production path uses the same 72-global-DOF ExecutionPlan, 12 free
equations, 94 global CSR nonzeros, and 34 reduced CSR nonzeros. It never
materializes the tangent as a dense matrix. A separate verification-only dense
state solver follows the identical coupled residual and derivative contract.

The committed receipt records:

- 6 accepted and 1 rejected arc-length steps;
- 61 Engine v2 CPU FGMRES tangent solves, maximum 12 iterations;
- maximum independently recomputed tangent residual `8.53e-14 kN`;
- displacement-Jacobian finite-difference error `7.27e-8 kN`;
- negative load-derivative finite-difference error `5.76e-9 kN`;
- 33 distinct operator numeric-value hashes;
- final primary displacement `0.2223913323 m` and load factor
  `-15.4610973011`;
- exact replay, exact midpoint restart, exact rollback, negative-load branch,
  analytic reduction, and dense-reference equivalence;
- zero fallback and zero regularization.

The result and compact summary are
`phase2_load_coupled_sparse_chain_arc_length_result.json` and
`phase2_load_coupled_sparse_chain_arc_length_summary.json` under
`implementation/phase1/release_evidence/productization/`.

## Claim boundary

This remains an analytic 12-equation CPU verification with identity
preconditioning. A separate
`g1_mgt_load_coupled_arc_length_adapter_receipt.json` now connects the same
residual/derivative shape to the actual-MGT frame/shell/spring assembly using
authoritative per-element CSR connectivity and a complete supported authored
`LIVE` vector: six nodal rows plus 3,644 uniform unprojected global-Z plate-face
pressure rows in the preserved `KN/M` unit system. The benchmark gravity and
unit-pressure proxy vector is disabled. Its zero-state, no-regularization
component sparse predictor passes the linear solve and residual-floor-subtracted
remainder gates through load factor `1.0`. That one full-unit free-DOF predictor
is persisted as a deterministic 70,560-value little-endian binary64 vector and
bound to its direction hash. It is explicitly not a continuation trace or an
accepted nonlinear checkpoint. The retained load-`0.656` checkpoint, however,
was generated with the former incorrect frame binding and a different load
contract, so it fails the corrected LIVE physical-residual gate. The receipt also
keeps the current-source/stored-receipt mismatch visible. Neither artifact runs a
full corrector/continuation path, connects material-state commit/rollback, proves
production-scale preconditioning or ROCm/HIP parity, creates an accepted
load-scale-1.0 G1 checkpoint, or closes G1.
