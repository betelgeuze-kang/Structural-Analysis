# Stateful corotational fiber-frame adaptive continuation

## Implemented boundary

`adaptive_stateful_corotational_fiber_frame2d_continuation` advances one
`StatefulCorotationalFiberFrame2DCheckpoint` toward a prescribed load factor by
composing the existing fixed-target Newton transaction. It provides:

- deterministic load-increment cutback after a blocked Newton attempt;
- retry from the exact last accepted checkpoint, never from a failed trial;
- bounded growth after a quickly converged accepted step;
- minimum/maximum increment and cumulative attempt-budget enforcement;
- exact commit ancestry and failed-attempt rollback checks;
- persisted full corotational frame state and adaptive progress;
- source-, path-, problem-, state-hash-, and canonical-byte-bound restart;
- equilibrium revalidation before a persisted checkpoint may resume; and
- a reaction-only terminal disposition for an empty free-equation space.

Every nonlinear attempt is delegated to
`solve_stateful_corotational_fiber_frame2d_load_step`. The adaptive controller
does not duplicate or weaken the Newton solver's convergence, terminal
reassembly, parent-state, or commit gates.

## Transaction and step-size rules

For accepted boundary `C_n`, current factor `lambda_n`, and proposed increment
`d_lambda`, one attempt targets

```text
lambda_trial = min(lambda_target, lambda_n + d_lambda)
attempt = fixed_target_newton(C_n, lambda_trial)
```

If the attempt commits, the returned checkpoint becomes `C_n+1`. A fast
convergence may multiply the next increment by the configured growth factor,
bounded by the maximum increment and remaining distance. If the attempt is
blocked, the controller verifies both object identity and canonical bytes of
`C_n`, increments the failed-attempt counters, and multiplies the proposed
increment by the reduction factor. It stops without mutation when the next
increment would be below the configured minimum or the cumulative attempt
budget is exhausted.

Attempt, accepted-step, failure, reduction, growth, Newton-iteration,
line-search, fallback, regularization, yielding, damage, residual, ancestry,
immutability, and rollback facts are cumulative. Restart does not reset these
counters or make a previously exhausted budget available again.

## Persisted restart boundary

The base checkpoint codec stores the complete nested state of the global
corotational frame, each basic fiber beam, every section integration point, and
the supported steel/concrete material states. The adaptive artifact additionally
stores the next proposed increment and cumulative progress.

Artifacts are bounded, closed-schema, canonical UTF-8 JSON. Loading fails
closed on duplicate keys, non-finite numbers, signed-zero loss, noncanonical
encoding, source/path/problem mismatch, hash mismatch, nested-state mismatch,
or accepted-state equilibrium mismatch. File creation is non-overwriting.

This is a persisted single accepted-boundary restart contract. It is not a
multi-file checkpoint-chain protocol and does not claim arbitrary material
plugin serialization.

## Focused verification

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m pytest -q \
  tests/test_stateful_corotational_fiber_frame2d_adaptive.py \
  tests/test_stateful_corotational_fiber_frame2d_solver.py \
  tests/test_stateful_corotational_fiber_frame2d.py \
  tests/test_stateful_corotational_fiber_beam2d.py
```

The nonlinear reference case deliberately blocks a direct `0 -> 1.0` attempt,
cuts back to `0.5`, commits it, grows the increment, and then commits the full
target. Tests verify deterministic replay, exact failed-boundary rollback,
equivalent one-shot and persisted-restart terminal state, attempt-budget
continuity, minimum-step exhaustion, fully constrained reaction-only behavior,
tamper rejection, source/problem binding, and non-overwriting writes.

## Claim boundary

This slice closes adaptive load stepping, automatic cutback/retry, exact
failed-step rollback, and persisted restart from one accepted corotational
frame boundary for the supported built-in fiber material state graph. It does
not provide displacement control, arc length, follower loads, sparse/HIP
execution, a general material-codec registry, checkpoint-chain replay, external
benchmark acceptance, or a full-building solve path.

No authoritative P-Delta portal, Euler-column, external cyclic-member,
snap-through, or customer-shadow acceptance receipt is supplied. G1 and
commercial readiness remain open, and protected readiness evidence is not
promoted.
