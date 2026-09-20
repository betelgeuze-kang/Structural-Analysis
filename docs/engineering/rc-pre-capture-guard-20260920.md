# Timed pre-capture decision for learned seed experiments

An opt-in guard now runs before committed material state is captured for the
proposal arm. It sees only the accepted prefix, current requested target and
compiled problem identity; its context contains no material snapshot. This is
execution infrastructure, not a trained switching model or demonstrated speedup.

`benchmark_rc_control_seed_paths` accepts `proposal_guard` and a declared SHA-256
`proposal_guard_identity` alongside the existing proposer. Guard use requires
secant abstention. With no guard, the existing path and report shape are retained.

- Exact `True`: capture material state if requested, then call and validate the
  proposer through the existing seed adapter and solver path.
- Exact `False`: skip both material capture and the proposer. Use the existing
  secant fallback, which uses the reference start when the prefix cannot yet
  define a secant.
- An exception or any non-boolean return: record the failed guard and stop that
  proposal path before a numerical attempt. The full-path score stays null;
  failures cannot earn a favorable timing ratio.

The callback has a separate wall/CPU timer and immutable input/start/outcome
receipts. The whole arm interval includes context construction, guard I/O,
callback, subsequent capture/inference and solver work. The timing decomposition
reports guard callback cost separately; its context and I/O remain in the
explicit residual category. Neither accepted nor declined decisions are free.
Reference, secant and fresh-reference arms do not invoke the guard.

## Behavioral verification

The focused diagnostic suite passes 36 tests. Actual four-target cyclic runs
verify that an always-declining guard never calls material capture or the proposer,
and every resulting numerical step file exactly matches the secant arm. An
always-accepting guard runs before each capture, supplies material state to the
proposer and passes the original full-history comparison. Invalid/raising guards
produce incomplete paths and no speed score. Unbound/invalid guard configuration
is rejected before output creation. Additive timing retains the decision cost.
These are behavioral tests using a fixed test revision marker, not independent
physics or performance evidence.

The combined diagnostic, learning, runtime-selection and iteration-cost suite
passes **166 tests in 266.91 s**; Ruff passes. No trained guard or reserved evaluation has been executed. The existing
full-path selector continues to retain secant. The nested seed complements and
all 1,980 planned label comparisons remain a separate unfinished study.
