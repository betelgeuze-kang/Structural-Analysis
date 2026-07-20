# Fiber-frame SolverEpisode adapter

The fiber-frame SolverEpisode adapter converts one exact stateful 2D
fiber-frame Newton load path into a replayable baseline or shadow
`SolverEpisodeIR`. It is an observation and control-plane artifact only. It
does not grant convergence, displacement, reaction, member-force, recovery,
design, release, or commercial authority.

## Source chain

Creation and full validation require the same J1-J4 source objects used by the
nonlinear terminal receipt:

```text
J1 nonlinear execution topology + solver-coordinate scaling
                              |
J2 physical EquationScaling + residual trace
                              |
J3 checkpoint/kinematic/material projection chains
                              |
J4 combined execution-state binding
                              |
actual Newton load path ──────┼──── ready path: exact J5 receipt required
                              |
                              └──── blocked path: one exact rollback required
```

A ready path is replayed and validated against its full J5 terminal receipt.
A blocked path cannot attach a J5 receipt. Its last step must be the only
non-committed step, and the returned checkpoint must be the identical parent
object with the same state hash and canonical bytes.

## Observation mapping

The episode contains one observation for genesis and one for every attempted
source load step. A successful path therefore has genesis plus all accepted
steps. A blocked path additionally retains its terminal rollback observation.

Each observation binds:

- the exact J4 epoch-binding hash as the generic episode `state_hash`;
- checkpoint, topology-plan, topology, solver-coordinate-scaling, and physical
  equation-scaling hashes;
- a replayed J2 physical-residual-trace hash;
- translational residual `Linf` in `N` and rotational residual `Linf` in
  `N*m`;
- dimensionless scaled residual `L2`/`Linf` and dimensionless increment
  `Linf`;
- cumulative Newton iteration count, load factor, and accepted/rollback
  disposition.

The generic `residual_linf` field carries the dimensionless J2-scaled `Linf`.
Runtime is exact zero under
`source-runtime-not-captured.report-zero.v1`; the source solver does not retain
authoritative timing data, so the adapter does not invent it.

For a rollback observation, the J4 state hash and checkpoint hash remain those
of the preceding accepted observation. The failed trial residual and scalar
increment remain visible, while no trial state becomes accepted.

## Baseline and shadow transitions

Every attempted load step has one deterministic baseline `step_size` action.
The canonical payload binds the positive load-factor increment, unit, and
`deterministic-baseline-step-policy.v1` source profile.

Baseline mode records no proposal. Shadow mode invokes the selected
`ShadowStepPolicy`, retains its policy ID/version/artifact hash and complete
scalar decision, then records the proposal as `shadow_only` or `rejected`.
Every executed action remains `source=baseline`; no proposal index or guard
receipt is attached to an executed action.

The transition envelope independently binds:

- source-step replay hash;
- parent and outcome checkpoint hashes;
- source and target observation indices;
- baseline action payload hash;
- commit or exact-rollback outcome;
- shadow decision and action hashes when shadow mode is selected.

Full validation rebuilds these rows from the actual source path. Rehashing a
coherently modified manifest cannot substitute another source step.

## Data-use boundary

Training eligibility defaults to false. Setting it true requires explicit
lowercase SHA-256 license and privacy receipt hashes and switches
`evaluation_only` to false. This records eligibility metadata only; it does not
move or embed customer data.

The manifest stores hashes and scalar diagnostics. It does not store raw model,
displacement, residual-vector, Jacobian, material-constituent, or checkpoint
bytes. `raw_customer_payload_included` is always false in both the episode and
adapter boundary.

## Validation levels

`validate_fiber_frame_solver_episode_adapter_manifest` checks strict JSON
shape, all canonical hashes, episode/action/proposal references, data and claim
boundaries, exact rollback linkage, and the permanent no-authority rule. A
manifest-only check does not establish source replay.

`validate_fiber_frame_solver_episode_adapter` additionally replays J1-J4, the
complete Newton path, every physical residual observation, the selected shadow
policy, and J5 for ready paths. The rebuilt manifest must be identical.

## Authority boundary

Even for a converged J5-backed path, the episode terminal is:

```text
reason                 converged
converged              true
final_state_hash       last accepted J4 epoch-binding hash
final_authority_status none
final_result_hash      null
```

This episode adapter itself cannot turn the J5 convergence receipt into a
numerical result. The separate adapter documented in
`docs/fiber-frame-nonlinear-result-adapter.md` now satisfies
`NonlinearNumericalResultIR`, binds the terminal displacement artifact and
boundary/backend receipts, and preserves the narrower J5 authority limits.
The episode remains non-authoritative and does not inherit that result hash.

## Focused verification

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest -q \
  tests/test_fiber_frame_solver_episode_adapter.py \
  tests/test_shadow_solver_controller.py \
  tests/test_engine_v2_solver_episode_v1.py

python3 -m ruff check \
  src/structural_analysis/ai/fiber_frame_solver_episode_adapter.py \
  src/structural_analysis/ai/shadow_solver_controller.py \
  tests/test_fiber_frame_solver_episode_adapter.py
```
