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

## Authority boundary

A shadow episode is observation/replay data only. It cannot grant convergence,
numerical-result, reaction/member-force, design/code, release, or commercial
authority. The controller does not correct residuals, Jacobians, material laws,
or final results.

Guarded execution, learned checkpoints, and an adapter from the actual
fiber-frame solve path remain later reviewed contracts. The merged J1–J4
fiber-frame topology, physical scaling, kinematic history, and combined
execution-state contracts are inherited from main but are not minted by this
controller.
