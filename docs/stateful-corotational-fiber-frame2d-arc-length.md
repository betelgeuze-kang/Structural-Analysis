# Stateful corotational fiber-frame arc-length continuation

## Implemented boundary

`stateful_corotational_fiber_frame2d_arc_length_continuation` follows a
proportional reference-load path with a spherical displacement/load constraint.
It composes the existing dense vector arc-length kernel with the actual
`StatefulCorotationalFiberFrame2DProblem` assembly and provides:

- predictor and augmented-Newton corrector solves using the assembled
  material-plus-geometric consistent tangent;
- trial section and material integration from one immutable accepted parent;
- atomic commit of displacement, load factor, corotational state, section
  state, and every supported steel/concrete fiber state;
- exact full-checkpoint rollback and deterministic radius reduction after a
  rejected attempt;
- continuation-orientation persistence across limit points;
- cumulative attempt-budget enforcement across restarts; and
- canonical source- and path-bound persisted restart artifacts.

The bridge executes exactly one generic vector-kernel attempt for each physical
material parent. After a successful vector correction it performs a terminal
frame reassembly from that same parent. Only that terminal assembly may supply
the next accepted material state.

## Equilibrium and path constraint

For free generalized coordinates `q`, load factor `lambda`, reference load
`p`, accepted coordinates `q_n`, and accepted factor `lambda_n`, the corrected
system is

```text
r(q, lambda) = f_internal(q; accepted material parent) - lambda p = 0
g(q, lambda) = (q-q_n)^T W (q-q_n)
             + (s_lambda (lambda-lambda_n))^2 - ds^2 = 0
```

Every corrector uses

```text
[ K_material + K_geometric    -p ] [delta_q     ] = [-r]
[ 2 W (q-q_n)^T       2 s_lambda^2 delta_lambda] [delta_lambda]   [-g]
```

The predictor solves the same current consistent tangent against `p`, scales
the combined displacement/load direction to unit arc length, and selects its
sign by the previous accepted tangent. No regularization or fallback is
authorized by this boundary.

## Transaction and restart rules

An accepted attempt must pass all of the following independently reassembled
gates:

- residual infinity norm;
- spherical-constraint residual;
- monitored-coordinate direction;
- exact section/element parent hashes;
- unchanged parent canonical bytes; and
- zero fallback and regularization counts.

A failure retains the exact accepted object and nested element-state bytes,
then multiplies the radius by `failed_step_reduction`. The persisted boundary
stores the full accepted frame checkpoint, current radius, previous normalized
displacement/load tangent, cumulative progress, and the latest attempt outcome.
Restart cannot reset the attempt budget or lose the branch orientation.

Artifacts are bounded, closed-schema canonical UTF-8 JSON. Loading fails
closed on duplicate keys, non-finite numbers, noncanonical encoding, source or
path mismatch, checkpoint hash mismatch, nested-state mismatch, tangent
dimension/norm mismatch, or configuration mismatch. File creation is
non-overwriting.

## Focused verification

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest -q \
  tests/test_stateful_corotational_fiber_frame2d_arc_length.py \
  tests/test_stateful_corotational_fiber_frame2d_adaptive.py \
  tests/test_stateful_corotational_fiber_frame2d_solver.py \
  tests/test_stateful_corotational_fiber_frame2d.py
```

The bounded reference test is a two-member shallow corotational fiber arch.
Its material parameters remain elastic over the tested range so the test
isolates geometric path following while still exercising the complete
stateful fiber checkpoint graph. The path crosses the first load maximum,
follows a descending branch through negative load, reaches a second minimum,
and rehardens. Separate tests verify same-parent finite-difference displacement
and load derivatives, deterministic replay, persisted mid-path restart,
tamper rejection, actual corrector failure with four radius reductions, and
byte-exact rollback.

This is an internal deterministic verification case, not an externally
accepted shallow-arch or Lee-frame benchmark receipt.

## Claim boundary

This slice closes the optional dense spherical arc-length branch for the
bounded stateful corotational 2D fiber-frame assembly and its built-in material
state codec. The lower-level contract still does not claim checkpoint-chain
replay by itself. The unified `analyze_nonlinear_frame` adapter now adds exact
terminal engineering recovery and a composite artifact that binds the complete
committed frame ancestry to the source/path-bound continuation checkpoint, then
requires deterministic genesis replay. Follower loads, a general
section/material codec registry, sparse production execution, ROCm/HIP parity,
and an externally accepted nonlinear benchmark remain open.

Fully constrained `F=0` models remain reaction-only outcomes and cannot enter
this displacement-monitored arc-length branch or make a convergence claim.
Authoritative G1, full-building equilibrium, external acceptance, and
commercial readiness remain open; protected readiness evidence is unchanged.
