# Experimental small-displacement RC displacement control

The internal RC path can prescribe one free horizontal or vertical displacement
and solve for its proportional reference-load factor. It reuses the original
`StatefulFiberFrame2DProblem`, fixed-chord fiber assembler, steel/concrete laws,
checkpoint codec and vector Newton solver. The new adapter adds the control
equation; it does not change the original public monotonic-load profile.

This supports bounded research into accepted steel plasticity, concrete damage
and reversal history. It carries no public J1–J5, independent physical,
general cyclic, capacity, design, performance or release authority. Existing
corotational and 3D paths retain their separate mechanics and contracts.

## Equations and acceptance

The augmented unknown is `[q_free, s * lambda]`, with default `s = 0.001 m`.
The original physical equilibrium residual uses the solved load factor. Its
new load column is `-S_free * F_reference_free / s`; the control row is the
prescribed translation error multiplied by
`F_reference_scale * residual_tolerance / control_tolerance_m`.
This scaling ties the unchanged Newton residual gate to the control tolerance.

Each attempt starts from the last accepted displacement and load factor. All
Newton trials use the same accepted constitutive parent. Commit requires the
original solver contract and residual/increment gates, independent terminal
equilibrium and control checks, matching actual solver coordinates and residual,
and original element/checkpoint ancestry. There is no final coordinate snapping,
regularization, fallback, target seeding or automatic cutback/retry. Ordinary
nonconvergence returns the exact original parent and retains the failed trial.

The default control tolerance is `1e-12 m`; Newton defaults remain those of
`NewtonRaphsonConfig`. The load-factor correction bound is explicitly
`increment_tolerance / s`. Bounds and equation weights must remain finite and
positive. The experimental model is a connected graph with at most 48 global
degrees of freedom and 64 members, dense CPU Newton with at most 200 iterations,
one free UX/UY control, original zero fixed supports and nonzero free reference
loading. Geometry remains small-displacement. Unsupported requests are rejected.

## Authored paths and restart

Given an existing original compiled `problem`, the internal entry point is:

```python
from structural_analysis.assembly.stateful_fiber_frame2d_control_path import (
    run_stateful_fiber_frame2d_control_path,
)

prefix = run_stateful_fiber_frame2d_control_path(
    problem, [-0.0004, -0.0008], control_global_dof=7,
    allow_reversals=True, maximum_reversals=2, maximum_targets=255,
)
restart_bytes = prefix.restart_artifact()
resumed = run_stateful_fiber_frame2d_control_path(
    problem, [-0.0012], control_global_dof=7,
    allow_reversals=True, maximum_reversals=2, maximum_targets=255,
    restart=restart_bytes,
)
```

This illustrates the interface; convergence depends on the actual model and
authored path. Targets are metres. Consecutive targets must differ, and reversals
require explicit opt-in and a budget. The combined accepted prefix and requested
suffix may contain at most 255 targets. All combined target/direction/budget
checks run before numerical replay. Empty suffixes are allowed only to verify
an explicit restart. A failed target remains in attempted accounting and is not
added to the accepted restart prefix.

The bounded canonical UTF-8 JSON restart binds the problem, exact configuration,
DOF, units, budgets, accepted targets, directions, every step binding and original
checkpoint bytes. Loading performs real numerical replay of the **whole prefix
from the unloaded state**, comparing all accepted step bindings and terminal
checkpoint bytes before any new suffix. Rehashing a plausible but altered
material history does not establish reachability. These unsigned hashes provide
consistency checks, not authentication.

Results separate new requested/attempted/accepted/failed/unattempted targets from
prefix replay work and retain their total. Solver exceptions retain attempted
work as unknown when exact counts are unavailable. Source mutation or an invalid
returned step raises a structured execution error with prior/current attempts;
it cannot export an accepted result or restart. Rejected restart replay retains
its own attempted work. Result export also checks unchanged checkpoint, source
and individual replay/suffix step groups against execution snapshots. Exported
step dictionaries detach nested metadata from the original step.

The two new focused test files are registered in the core CI boundary, PR
quality gate and existing fiber execution workflow. They cover original elastic
parity, augmented finite differences, actual committed steel plasticity and
unloading, rollback, numeric bounds, source/metadata mutation, strict restart,
complete prefix replay and replay/suffix failure accounting. This is local
implementation verification; independent material benchmarks, published cyclic
acceptance, public recovery/authority, durable jobs and Workbench integration for
this profile remain separate work.
