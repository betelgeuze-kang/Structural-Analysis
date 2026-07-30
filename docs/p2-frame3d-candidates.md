# P2 bounded Frame3D candidates

The internal stateful Frame3D path remains an experimental bounded candidate.
It is executable from Python but is not public, independently verified, or
release eligible. The capability registry is the authority for that boundary.

## Native sparse convergence contract

`StatefulCorotationalFrame3DSparseConfig` binds the following evidence to its
solver-contract hash:

- model-derived characteristic length and reference force;
- six-DOF force/moment equation scaling;
- relative and absolute residual tolerances;
- relative and absolute Newton-increment tolerances;
- an ordered backtracking-alpha set;
- bounded adaptive cutback ratio, per-parent cutback depth, accepted-substep
  limit, minimum load-factor increment, and explicit convergence-only retry
  classification;
- fail-closed sparse factorization limits with no regularization or fallback.

For node-major `[UX, UY, UZ, RX, RY, RZ]`, translational residuals retain force
units while rotational residuals retain moment units. A characteristic length
`L` converts moments to equivalent forces and rotations to equivalent
translations:

```text
R_equivalent = [Fx, Fy, Fz, Mx/L, My/L, Mz/L]
dq_equivalent = [dux, duy, duz, L*dRx, L*dRy, L*dRz]
```

The same row and column equilibration is applied to the sparse tangent before
factorization, so its reported condition number belongs to the scaled 6DOF
system rather than the mixed-unit raw matrix.

A checkpoint is committed only after:

- the dimensionless scaled residual gate passes;
- the dimensionless scaled Newton-increment gate passes;
- every applied update came from an admissible, strictly
  residual-decreasing line-search trial;
- material integration remains admissible from the unchanged parent, and every
  point or distributed-member response reports that exact accepted-parent state
  hash and an exact-family trial-state type;
- the final equilibrium and material state are reassembled identically;
- every scaled sparse diagnostic passes without fallback or regularization.

Checkpoint validation fixes a single deterministic genesis: step zero has no
parent, zero load/displacement, zero converged iterations, and the material
state/residual produced by the same unloaded zero-state assembly used by the
creator. Every later step requires a nonzero parent hash, and its reported
iteration count cannot exceed the bound in the checkpoint's solver contract. A
zero-update child is valid when the changed load acts only on restrained
equations and material replay, factorization, final-reassembly, and equilibrium
gates pass. A syntactic solver-contract hash is required even for
config-independent assembly replay. Displacement scalars cannot change
type/value during binary64 normalization, and material state must replay
idempotently at the checkpoint displacement before either dense or sparse trial
assembly consumes it.

The step receipt keeps raw translational and rotational residuals and
increments, scaled norms and tolerances, the selected alpha or `null` when no
line search was required, scaled condition number, scaling hash, and full
convergence/line-search histories. No absent alpha is replaced by a numeric
default.

The bounded direct-control configuration cannot outlive the sparse Frame3D
iteration budget bound into its checkpoint contract. Its checkpoint iteration
field counts applied Newton/line-search updates and excludes the final
gate-evaluation row, preventing a bound-edge convergence from producing a
self-invalid checkpoint.

If a requested load target exhausts Newton iterations or cannot find an
admissible residual-decreasing line-search trial, the solver retries a smaller
load-factor increment only when the terminal error is explicitly classified as
a pure convergence failure. Any material or contract inadmissibility observed
anywhere in the failed step makes it non-retryable; it cannot be relabeled as a
line-search or maximum-iteration failure. Material path errors, response-parent
lineage mismatches, and sparse factorization failures are not hidden by cutback.
Every rejected target records its stable reason, parent checkpoint hash,
proposed cutback target, and parent-immutability result. Only accepted substeps
create checkpoints. After each accepted substep the original requested target
is tried again, so the remaining path depends only on the accepted checkpoint,
target, and solver contract; resume reproduces the uninterrupted suffix exactly.

## Bounded direct displacement control

The separately registered
`stateful_corotational_frame3d_sparse_direct_displacement_control.v1` profile
solves one free translational or rotational coordinate together with the
proportional reference-load factor. It uses the same source-bound 6DOF scaling,
sparse factorization diagnostics, immutable-parent material trials, strict
merit-decreasing backtracking, residual and increment gates, final reassembly,
and accepted-checkpoint lineage as the load-control candidate. The monotonic v1
resume receipt binds one direction, while the opt-in exact combined-hardening
steel reversal path uses a v2 last-leg/cumulative-count/rolling-target-chain
receipt. A prefix run resumed with both the checkpoint and matching receipt
reproduces the uninterrupted checkpoint, material state, and final lineage;
a bare equilibrium checkpoint is explicitly labeled an unbound restart. These
are unsigned internal consistency receipts, not adversarial authentication.
Persisted API artifacts additionally reject duplicate keys, non-finite JSON,
coercive integer/float checkpoint, resume-binding, and top-level envelope hash
domains, and non-canonical bytes before typed reconstruction or equilibrium
validation.

This is an internal bounded candidate, not a public or release-eligible
capability. Its exact equations and unsupported cases are documented in
`docs/p2-frame3d-direct-displacement-control.md`.

## Remaining boundary

This change does not add multi-DOF direct control, arc-length continuation,
general material/shear/torsion coupling, member
releases, rigid offsets, distributed member loads, production-scale authority,
or independent external 3D validation. Bounded target cutback plus same-operator
OpenSees monotonic axial-yield UX, one five-target exact-Hardening axial reversal,
and pure-axis elastic RX/RY/RZ comparisons now exist. Other cyclic materials and
histories, coupled multi-axis/multi-control behavior, general direct-control, and
formal Level 2 evidence remain open.

Focused verification:

```bash
python -m pytest -q \
  tests/test_stateful_corotational_frame3d_displacement_control.py \
  tests/test_stateful_corotational_frame3d_sparse.py \
  tests/test_stateful_corotational_frame3d_materials.py \
  tests/test_stateful_corotational_fiber_frame3d.py \
  tests/test_stateful_corotational_partial_composite_frame3d.py \
  tests/test_corotational_frame3d_scalable_graph.py
```
