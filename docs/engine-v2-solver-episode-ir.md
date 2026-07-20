# Engine v2 SolverEpisodeIR v1

## Purpose

`SolverEpisodeIR` is the common data contract for solver trajectories used by
baseline diagnostics, shadow AI evaluation, and guarded AI solver control. It
records what the solver observed, what a policy proposed, what action actually
executed, whether a rollback occurred, and how the episode terminated.

It is **not** a result type. The episode remains non-authoritative even when it
references a separately validated `NumericalResultIR` or `EngineeringResultIR`.

## Bound identities

Every episode binds:

- ModelIR content hash;
- ExecutionPlan hash;
- initial StateIR hash;
- analysis profile;
- backend profile and backend receipt hash;
- ordered observations, proposals, and executed actions;
- terminal state/result references;
- license/privacy evidence for training eligibility.

The contract contains hashes and scalar observations only. It does not embed a
model, customer payload, solution vector, material-state artifact, or free-form
exception text.

## Episode modes

### `baseline`

No AI proposals are permitted. Executed actions must come from the deterministic
baseline or a declared human override.

### `shadow`

AI proposals may be recorded, but they must remain `shadow_only` or `rejected`.
An AI proposal cannot execute in this mode.

### `guarded`

An AI action may execute only when:

- it references an existing proposal and observation;
- action kind and payload hash match exactly;
- the proposal is `eligible` and not OOD;
- a deterministic guard receipt hash is attached.

Baseline and human actions cannot claim an AI proposal or guard receipt.

## Recorded actions

The bounded v1 action set is:

- step size;
- solver routing;
- Krylov restart length;
- preconditioner selection;
- warm start;
- checkpoint recovery.

Response correction, residual replacement, learned material laws, design
promotion, and code-compliance decisions are intentionally absent from v1.

## Authority boundary

The terminal row may reference a final state and result hash after another
contract grants authority. `SolverEpisodeIR` itself never grants:

- convergence authority;
- displacement, reaction, or member-force authority;
- design or code-compliance authority;
- release readiness or commercial authority.

A non-converged episode cannot reference numerical or engineering authority.
`final_authority_status=none` cannot attach a final result hash.

## Data-use boundary

`training_eligible=true` requires:

- `evaluation_only=false`;
- a source-license receipt hash;
- a privacy receipt hash;
- `raw_customer_payload_included=false`.

This flag records eligibility; it does not train a model or authenticate the
external receipts.

## Fail-closed checks

The implementation rejects:

- unknown manifest fields and non-exact JSON scalar types;
- non-contiguous indices or out-of-range references;
- accepted and rollback on the same observation;
- AI proposals in baseline mode;
- eligible proposals in shadow mode;
- eligible OOD proposals;
- executed AI actions without an exact matching proposal and guard receipt;
- terminal convergence/authority mismatch;
- training eligibility without license/privacy evidence;
- raw customer payload claims;
- authority-profile or canonical episode-hash tamper.

## Current boundary

This PR adds the contract, schema, and focused tests only. It does not yet adapt
CPU FGMRES, Newton, arc-length, HIP, Workbench, or optimization receipts into
episodes. It also does not include a policy model or shadow controller. The next
stacked PR adds a deterministic shadow controller that produces proposals but
cannot execute them.

## Focused validation

```bash
PYTHONPATH=src python3 -m pytest -q \
  tests/test_engine_v2_solver_episode_v1.py
python3 -m ruff check \
  src/structural_analysis/engine_v2/contracts/solver_episode.py \
  tests/test_engine_v2_solver_episode_v1.py
```
