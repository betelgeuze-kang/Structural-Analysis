# Shadow-only solver controller

## Purpose

This module is the first executable AI control-plane boundary built on
`SolverEpisodeIR`. It records policy proposals beside deterministic baseline
actions without allowing the proposal to alter the solver.

```text
solver observation
  ├─ deterministic baseline action   executed
  └─ shadow policy proposal          recorded only
```

The controller always emits a `shadow` episode and validates that:

- `ai_action_executed` is false;
- every executed action is the deterministic baseline action;
- every policy proposal retains stable policy ID, version, artifact hash,
  uncertainty, OOD disposition, reason code, and action-payload hash;
- a third-party policy cannot substitute an unrelated artifact hash or action
  scalar after the proposal is formed;
- unsupported model families fail closed as OOD;
- rollback observations deterministically shrink the next baseline step.

## Reference policy

`DeterministicResidualStepPolicy` is a bounded reference rule used to test the
controller wiring. It is not a trained AI model and does not claim learned
performance.

The reference proposal may suggest a larger, retained, or reduced next step from
residual ratio and rollback state. The proposal is still never executed in this
PR.

## Identity binding

A selected policy exposes:

```text
policy_id
policy_version
policy_artifact_hash
minimum_step_size
maximum_step_size
```

The controller requires the returned decision to repeat the selected policy
identity and recomputes:

```text
action_payload_hash = hash(
  action_kind,
  proposed_step_size,
  step_unit,
  policy_artifact_hash
)
```

Out-of-range step sizes, mismatched artifact hashes, mismatched payload hashes,
non-finite uncertainty, or inconsistent OOD disposition are rejected before an
episode is produced.

## Fiber-frame integration

`fiber_frame_solver_episode_adapter.py` now applies this controller to the
actual stateful fiber-frame load path. It emits genesis plus accepted-step
observations, or a final rollback observation for a blocked path, and binds
each observation to its exact J4 execution-state epoch and J2 physical
residual trace. A ready path must also replay an exact J5 receipt.

The adapter passes only action-source observations to the controller: one row
for each attempted transition. It then places the resulting proposals beside
the complete observation sequence. This preserves one proposal per attempted
step without inventing an action after the terminal observation.

## Authority boundary

A shadow episode is observation/replay data only. It cannot grant convergence,
numerical-result, reaction/member-force, design/code, release, or commercial
authority. The controller does not correct residuals, Jacobians, material laws,
or final results.

Guarded execution and learned checkpoints remain later reviewed contracts. The
fiber-frame adapter is still non-authoritative: it observes the merged J1–J5
chain but does not mint or modify topology, scaling, kinematic, material-state,
convergence, or result authority.
