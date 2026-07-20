# Fiber-frame nonlinear terminal receipt

PR-J5 binds an actual converged Newton load path to the exact J4 scaled
execution/kinematic/material-state envelope. The receipt is authoritative only
for convergence of the bounded stateful 2D fiber-frame path. It is not a
`NonlinearNumericalResultIR`, does not emit `StateIR v1`, and grants no
displacement, reaction, member-force, recovery, design, release, or commercial
authority.

## Required source chain

Creation and full validation consume and replay all of the following objects:

```text
J1 execution topology + solver-coordinate scaling
                       |
J2 physical EquationScaling v1 binding
                       |
J3 checkpoint/kinematic state chain
                       |
PR #132 material projection chain
                       |
J4 execution/state binding
                       |
actual committed Newton load path
                       |
J5 bounded nonlinear terminal receipt
```

The load path must start at the J4 genesis checkpoint, cover every non-genesis
J4 epoch, increase load monotonically, and finish at exact load factor `1.0`.
Every step is rerun with the retained `NewtonRaphsonConfig`; the canonical hash
of the complete supplied path must equal the canonical hash of the replay.

## Residual and increment gates

The source Newton solver uses

```text
R(u) = F_internal(u) - F_external
J(u) = dF_internal/du
```

with backtracking line search. J5 does not treat the source solver's mixed-unit
relative residual as sufficient authority. For every accepted step it rebuilds
the full physical three-DOF residual from the final assembly and passes it
through the exact J2 binding.

The receipt reports separate quantities:

- translational residual norms in `N`;
- rotational residual norms in `N*m`;
- dimensionless EquationScaling residual norms;
- solver-coordinate increment norms in generalized metres;
- dimensionless increment norms using the bound characteristic length.

The v1 terminal policy fixes the dimensionless scaled residual `Linf` tolerance
at `1e-10` and the generalized-coordinate increment `Linf` tolerance at
`1e-12 m`. Both gates must pass at every accepted step. Fallback and
regularization counts must remain zero.

## Consistent Jacobian proof

Every accepted step receives a same-parent centered finite-difference audit of
the complete free-equation Jacobian. The audit fixes epsilon `1e-8 m` and a
relative infinity-norm tolerance of `5e-6`. It also verifies that the committed
parent checkpoint remains byte-identical and that the analytic tangent remains
symmetric within the bounded solver tolerance.

The terminal manifest stores canonical little-endian float64 data/content
hashes for the solution vector, physical residual, analytic Jacobian, and
finite-difference Jacobian. It does not embed those vectors, matrices,
iteration histories, or line-search histories in JSON. Histories are retained
by canonical hash only.

## Validation levels

`validate_fiber_frame_nonlinear_terminal_receipt_manifest` checks the strict
manifest shape, hashes, fixed gates, and claim boundary. A manifest by itself
does not have source-replay authority.

`validate_fiber_frame_nonlinear_terminal_receipt` replays the J1-J4 source
chain, reruns the complete Newton path, rebuilds every physical residual trace,
and repeats every Jacobian audit. Only this full validation establishes the
bounded convergence claim.

## Authority boundary

J5 establishes:

- exact J4 ancestry at every accepted Newton step;
- deterministic full-load replay for the bounded two-member 2D fiber frame;
- physical N/N*m residual observations and dimensionless convergence gates;
- same-parent consistent-Jacobian evidence for every step;
- explicit zero-fallback and zero-regularization terminal semantics.

J5 does not establish:

- general frame import, arbitrary boundary conditions, or full-building
  equilibrium;
- geometric nonlinearity, shell coupling, mesh-objective distributed
  plasticity, production sparse/HIP execution, or G1 closure;
- `StateIR v1`, reaction, member-force, or fiber-recovery authority; J5 alone
  does not issue `NonlinearNumericalResultIR` or displacement authority;
- code/design approval, release readiness, or commercial use.

The fiber-frame SolverEpisode adapter consumes the exact J5 receipt for ready
baseline/shadow observation traces, but deliberately retains
`final_authority_status=none` and no result hash. The separate result adapter in
`docs/fiber-frame-nonlinear-result-adapter.md` now independently satisfies the
state, artifact, boundary, backend, and authority requirements needed to issue
a bounded `NonlinearNumericalResultIR`. Exact engineering recovery remains a
separate step after numerical-result issuance.

## Focused verification

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest -q \
  tests/test_stateful_fiber_frame2d_nonlinear_terminal_receipt.py \
  tests/test_stateful_fiber_frame2d_nonlinear_execution_state_binding.py \
  tests/test_stateful_fiber_frame2d_physical_equation_scaling.py

python3 -m ruff check \
  src/structural_analysis/assembly/stateful_fiber_frame2d_nonlinear_terminal_receipt.py \
  tests/test_stateful_fiber_frame2d_nonlinear_terminal_receipt.py
```
