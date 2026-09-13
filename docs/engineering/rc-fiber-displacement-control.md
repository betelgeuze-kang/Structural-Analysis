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

## Canonical-model API and strict request

The separate experimental API in
`structural_analysis.api.rc_fiber_frame_direct_control` accepts the existing
canonical RC model through `analyze_bounded_rc_fiber_direct_control(model,
targets_m, *, control_global_dof, config, allow_reversals, maximum_reversals,
maximum_targets, restart)`. The optional settings retain the core defaults.
It does not use the original public monotonic-load result schema or its J1–J5
authority.

The result exposes `to_dict()`, `status`, `contract_pass`, `result_hash`,
`result_artifact_bytes()` and `checkpoint_artifact_bytes()`. Its schema is
`bounded-rc-fiber-direct-control-result.v1`. Accepted responses are reassembled
from each actual previous checkpoint, original augmented Newton coordinates
and solved load factor. The full original assembly and accepted native material
bytes must match before response export. History covers the **whole accepted
prefix**, including accepted epochs recovered by restart replay; a failed trial
is retained in path accounting, not promoted to an accepted response.

The response arrays declare displacements in m/rad, forces and moments in N/Nm,
fiber stress in MPa, material energy density in MJ/m³, section energy per length
in MJ/m, and member dissipated energy in MJ. Native plastic and damage memory
is retained with the original checkpoint/parent bindings. These source checks
are internal consistency checks, not independent material or physical validation.

The [strict request example](../../examples/bounded_rc_fiber_direct_control_l_frame_cyclic.request.v1.json)
uses the unchanged
[original L-frame model](../../examples/public_rc_fiber_frame_l_frame_material_history.json).
Its 242 target numeric tokens are copied verbatim from the fixed observation's
`protocol.json` (`925b3810720c71243e4178e77dc9d2925df954836e7a35aa694da8d11a79e67a`);
they were not rounded or regenerated. The model byte SHA256 is
`9f2a66f86fd5443574032ff4a55f3de09995094808f20c1b7f34ac403de6b59d`.
Control DOF 7 is N3 UY in this compiled model. The request explicitly retains
40 Newton iterations, residual tolerance `1e-10`, increment/control tolerances
`1e-12 m`, load-factor coordinate scale `0.001 m`, the original six line-search
alphas, dense backend, and disabled terminal polishing. Two reversals and a
cumulative maximum of 255 targets are declared.

`decode_bounded_rc_fiber_direct_control_request(bytes_or_dict)` returns an
immutable `BoundedRCFiberDirectControlRequest`; `.targets_m` and `.api_kwargs()`
provide the API arguments. `bounded_rc_fiber_direct_control_request_payload()`
exports all settings, including all six `NewtonRaphsonConfig` fields. Its schema
is `bounded-rc-fiber-direct-control-request.v1`. Unknown nested fields, duplicate
JSON keys, nonfinite/unsafe numbers and boolean/count confusion are rejected.
Targets remain metres; the decoder does not authorize a fixed or rotational DOF.
The compiled model and complete prefix/suffix still enforce the control and
cumulative budgets. Restart bytes are supplied separately, never regenerated
from the result's physical displacement rows.

## Run and verify CLI

From the repository root, run the explicit request with:

```bash
PYTHONPATH=src python3 -m structural_analysis.api.rc_fiber_frame_direct_control_cli run \
  --model examples/public_rc_fiber_frame_l_frame_material_history.json \
  --request examples/bounded_rc_fiber_direct_control_l_frame_cyclic.request.v1.json \
  --output /tmp/rc-control-example/result.json \
  --report /tmp/rc-control-example/run-report.json \
  --checkpoint-output /tmp/rc-control-example/checkpoint.json
```

The installed console entry point is `bounded-rc-fiber-direct-control`, with
the same `run` and `verify` subcommands. This example is a full nonlinear
execution command, not a cheap schema check. `run` performs the original API
analysis and then **mandatory fresh source verification**, which executes the
same request again and independently reassembles its accepted transitions.
If all 242 targets complete without a restart, that is two 242-step paths.
`analysis_control_work`, `analysis_metrics`, the nested `verification` report,
`analysis_api_timing` and `verification_api_timing` preserve the original and
verification costs separately. Reported wall/process CPU intervals cover those
functions; input parsing, report formatting and output writes are excluded.
Serialization has its own interval. These are correctness costs, not speedup
evidence.

Verify the saved original bytes in a separate invocation with:

```bash
PYTHONPATH=src python3 -m structural_analysis.api.rc_fiber_frame_direct_control_cli verify \
  --model examples/public_rc_fiber_frame_l_frame_material_history.json \
  --request examples/bounded_rc_fiber_direct_control_l_frame_cyclic.request.v1.json \
  --result /tmp/rc-control-example/result.json \
  --checkpoint /tmp/rc-control-example/checkpoint.json \
  --report /tmp/rc-control-example/verify-report.json
```

`verify` calls `validate_bounded_rc_fiber_direct_control_artifacts` on the supplied
model, complete request, original result bytes and original checkpoint bytes.
It performs another full fresh API execution; it is not hash-only validation.
There is no skip-replay mode. To verify a resumed run, also pass its **original
restart input** with `--restart`; this differs from the resulting
`--checkpoint`. A resumed `run` likewise uses `--restart` with a request containing
only the new suffix and identical configuration/control/budgets. Both original
and validation executions replay the entire accepted prefix before the suffix.

`run` exits 0 only for a ready result with complete physical and validation
contracts; other results exit 2. `verify` exits 0 for
`artifact_contract_pass=True`, even when a consistently reproduced blocked
result has `contract_pass=False` and `physical_path_complete=False`. Thus a
successful verification command does not prove that the requested path finished.
The verification report separates a fresh API invocation from actual solver
attempts; unsupported and empty-genesis cases do not claim numerical replay or
positive accepted history. Actual failures and unavailable work remain visible.

The CLI reads and binds the same immutable model/request/restart bytes, applies
strict JSON checks before canonical-model loading, and rechecks inputs and output
path bindings before publication. Outputs must not alias or nest with each other
or any protected input, including `verify`'s result and checkpoint. Requested
checkpoint output is preserved only when an available artifact passes validation;
otherwise a stale requested checkpoint is cleared on normal result publication.
The shared writers stage files and roll back caught replacement failures; they
do not claim crash-safe atomic publication of the whole bundle.

Limits are 128 KiB for the request, 16 MiB for the model, 8 MiB for restart/
checkpoint bytes and 512 MiB for result input/output. An API export failure or
an oversized serialized result preserves completed execution metrics in a
failure report, does not relabel the computed physical outcome, and leaves
existing result/checkpoint outputs intact. Validation and result export authority
remain unavailable in that case.

Durable job submission/resume and Workbench execution/review for this profile
are not implemented. This API, request format and CLI add source-bound local
research access; they do not grant original public J1–J5, independent physical,
general cyclic, design, capacity, production or release authority.

The two core-focused test files are registered in the core CI boundary, PR
quality gate and existing fiber execution workflow. They cover original elastic
parity, augmented finite differences, actual committed steel plasticity and
unloading, rollback, numeric bounds, source/metadata mutation, strict restart,
complete prefix replay and replay/suffix failure accounting. This is local
implementation verification; independent material benchmarks, published cyclic
acceptance, public J1–J5 authority, durable jobs and Workbench integration for
this profile remain separate work.

Three API/request/CLI test files are also registered in those same lanes. They
cover actual transition recovery, cumulative restart history, source replay,
rehashed artifact substitution, strict inputs, output protection and retained
unknown execution work. A missing iteration count remains unknown even when
the configured iteration budget is zero.

The [fixed-source 242-target observation](rc-fiber-control-restart-observation-20260909.md)
records retained coarse failures, accepted plastic/damage history, a separate
full-prefix restart execution, exact original-state comparisons and all measured
correctness costs. Its observed success does not extend this profile's authority.

The [API/CLI observation](rc-fiber-control-api-cli-observation-20260909.md) records
the seven fresh API invocations, full response recovery, strict CLI transport,
separate verification costs and exact saved-history audit for the same targets.

## Durable fixed-chunk execution

The canonical RC API now connects to a distinct v3 single-host durable job
profile. Each immutable chunk receives original execution and mandatory fresh
source verification, with separate reservations, full-prefix replay costs,
retained failures and unknown abandoned work. Compact checkpoint receipts bind
the stored invocation pair; the final result contains the latest cumulative API
history once. The local three-target reversal matches across service reopen and
resume. See [the durable job record](rc-fiber-durable-jobs-20260909.md) for request,
lifecycle, limits and verification. The earlier 242-target API/CLI observation
has not yet been repeated through this service; verified RC Workbench review,
study integration and independent validation remain open.
