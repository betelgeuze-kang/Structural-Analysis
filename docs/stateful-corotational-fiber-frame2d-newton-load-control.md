# Stateful corotational fiber-frame Newton load control

## Implemented boundary

`solve_stateful_corotational_fiber_frame2d_load_step` composes the dense
`StatefulCorotationalFiberFrame2D` assembly with the existing deterministic
vector Newton solver. Each call owns one prescribed reference-load factor and
one immutable accepted checkpoint.

The bounded load-step contract provides:

- the accepted checkpoint displacement as the initial generalized coordinate;
- the exact assembled material-plus-geometric tangent at every Newton trial;
- deterministic backtracking line search without regularization or fallback;
- residual and increment convergence gates;
- exact solver-coordinate and terminal-residual binding to the final assembly;
- positive-epoch checkpoint creation only after every solver, parent, and
  immutability gate passes;
- identity-preserving rollback to the accepted checkpoint after any failed
  iteration, singular tangent, unsupported backend, or line-search failure;
- a reaction-only terminal path when the free-equation space is empty.

`run_stateful_corotational_fiber_frame2d_load_path` applies an explicit sequence
of load factors. It stops at the first blocked target and returns the last
successfully committed checkpoint.

## Trial and commit lifecycle

For an accepted checkpoint `C_n`, every residual and tangent evaluation in one
load step uses the same parent state:

```text
(r_i, K_i, E_i_trial) = assemble(C_n, lambda_target, q_i)
K_i delta_q_i = -r_i
q_i+1 = q_i + alpha_i delta_q_i
```

Line-search candidates are therefore sibling trials. They do not become the
parent of later candidates and cannot mutate `C_n`.

After residual and increment convergence, the solver reassembles the terminal
coordinate and verifies:

```text
solution q bytes == terminal assembly free-coordinate bytes
solution residual bytes == terminal assembly residual bytes
every element response parent hash == C_n element-state hash
C_n canonical bytes and state hash are unchanged
```

Only then is `C_n+1` created with `epoch = step_index = n + 1`, the target load
factor, `C_n.state_hash` as its parent, the terminal global displacements, and
the terminal trial element states. A blocked step returns the original `C_n`
object and records `rollback_exact=true`.

## Coordinate and equilibrium convention

The load-step adapter retains the assembly convention

```text
u_physical = S q_generalized
r_generalized = S_free^T (f_internal - lambda f_reference)_free
K_generalized = S_free^T (K_material + K_geometric)_free S_free
```

The residual norm is scaled by the generalized reference-force infinity norm.
The increment norm is evaluated in the length-valued generalized coordinates,
including scaled rotational coordinates.

## Focused verification

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest -q \
  tests/test_stateful_corotational_fiber_frame2d_solver.py \
  tests/test_stateful_corotational_fiber_frame2d.py \
  tests/test_stateful_corotational_fiber_beam2d.py
```

The solver tests cover a converged two-member frame, deterministic replay of a
four-step RC damage path, exact failed-step rollback, stop-at-first-failure load
paths, and the zero-free-equation reaction-only disposition.

## Claim boundary

This slice implements dense, fixed-target load control only. It does not add
adaptive increment selection, automatic cutback or retry, displacement control,
arc length, follower loads, sparse production assembly, corotational checkpoint
persistence, checkpoint-chain replay, external benchmark acceptance, or a
full-building solve path.

No P-Delta portal, Euler-column, cyclic member, snap-through, restart, or
customer-shadow acceptance receipt is supplied here. G1 and commercial
readiness remain open, and no protected evidence claim is promoted.
