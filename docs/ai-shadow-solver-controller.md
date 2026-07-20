# Shadow AI solver controller v1

## Purpose

This slice adds the first executable AI-control-plane boundary on top of
`SolverEpisodeIR`: a **shadow-only step-size proposal runner**.

The controller observes an already executed deterministic solver trajectory,
asks a policy for a next-step proposal, records that proposal, and records the
actual deterministic baseline action separately. It never executes the
proposal and never modifies solver, state, result, design, release, or
commercial authority.

## Reference policy

`DeterministicResidualStepPolicy` is included to verify the plumbing. It is a
fixed rule policy, not a learned model and not production AI.

Its bounded action is the next load-factor increment:

- strong residual reduction: propose growth;
- weak residual reduction: propose shrink;
- moderate reduction: propose hold;
- rollback: propose shrink;
- insufficient history: propose hold;
- unsupported model family: mark OOD and reject.

All proposed steps are clamped to the declared minimum and maximum.

## Shadow execution contract

For every retained observation the runner creates:

1. one policy proposal in `SolverEpisodeIR.proposals`;
2. one deterministic baseline action in `executed_actions`;
3. no `source=ai_proposal` action;
4. a canonical action-payload hash for the proposal and the baseline action.

The resulting episode mode is always `shadow`. `SolverEpisodeIR` independently
rejects any policy that attempts to mark a shadow proposal `eligible` for
execution.

## OOD and authority boundary

An unsupported model family is recorded as:

```text
ood=true
disposition=rejected
reason_code=ood_model_family
```

The baseline action is still recorded. The runner does not silently reinterpret
or repair the model.

The controller output fixes:

```text
ai_action_executed=false
result_authority=false
```

A terminal episode may reference an independently authoritative result, but the
controller and episode do not create that authority.

## Extensibility

Future learned policies may implement `ShadowStepPolicy` with:

- stable policy ID and version;
- immutable model/checkpoint artifact hash;
- deterministic proposal payload hash;
- explicit uncertainty, OOD, and disposition.

Moving from shadow to guarded execution requires a separate PR and an exact
physics/rollback guard receipt. This v1 runner cannot be configured into guarded
mode.

## Current exclusions

- no trained checkpoint or inference runtime;
- no actual step-size override;
- no solver-route, preconditioner, warm-start, or checkpoint action runner;
- no customer data ingestion;
- no response/residual correction;
- no design or code-check decision;
- no production performance claim.

## Focused validation

```bash
PYTHONPATH=src python3 -m pytest -q \
  tests/test_engine_v2_solver_episode_v1.py \
  tests/test_shadow_solver_controller.py
python3 -m ruff check \
  src/structural_analysis/engine_v2/contracts/solver_episode.py \
  src/structural_analysis/ai/shadow_solver_controller.py \
  tests/test_engine_v2_solver_episode_v1.py \
  tests/test_shadow_solver_controller.py
```
