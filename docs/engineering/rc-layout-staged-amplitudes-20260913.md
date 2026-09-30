# Staged screening under changed displacement amplitudes — 2026-09-13

Initial-history screening helped one changed-amplitude condition and hurt the other.
The selected fully verified candidate was unchanged relative to cost-pruned full
analysis in every paired execution. This is evidence for conditional use of the
screen, not an argument to enable it unconditionally or a learned speedup claim.

## Frozen inputs and scope

Numerical source: `dea625b1a023954a3c2f7a39168f9f55cddcdc6a`, exported from a clean
checkout before execution. The five original models, synthetic price table and
performance limits come from the previously recorded layout cohort. All six target
displacements were multiplied by either 0.6 or 1.4. Both complete requests and their
SHA-256 were saved before the first solve. The two-target prefix and consideration
horizon were fixed. The original cohort outcomes were known; neither new-amplitude
outcome was inspected to choose the inputs or screen length.

These are two related load-amplitude variants of the same model pool, not independent
projects, structural systems or experimental specimens. No training labels, model
fits or predictions were created. The baseline always ran its full path. Prefix
passes required a fresh full execution and fresh verification; cumulative violations
could reject candidates. Cost skips retained unknown physical feasibility.

Each condition ran cost-pruned then staged, followed by staged then cost-pruned,
in separate sequential processes with one-thread BLAS settings. The machine was not
isolated. There was no automatic retry. All eight processes terminated successfully.

## Observed paired costs

| Target multiplier | Selected candidate in all runs | Pruned full rows | Staged full + prefix rows | Staged/pruned process ratios |
|---|---|---:|---:|---|
| 0.6 | small | 2 | 2 + 1 | 1.167084, 1.139559 |
| 1.4 | large | 4 | 2 + 3 | 0.823252, 0.798337 |

At 0.6, the prefix did not avoid a full path: analysis-plus-verification step count
increased from 24 to 28 per execution. At 1.4, two candidates were prefix-rejected:
step count decreased from 48 to 36, even though API invocations increased from 8 to
10. This separates API-call count from actual solver work.

The per-condition ratios of summed process times are approximately 1.153334 and 0.810666,
respectively. These are two ordered repeats per related condition, not confidence
intervals or generalized speed estimates. Pool-wide exhaustive minimum cost was not
recomputed. The selected result matches the cost-pruned strategy within each condition.

## Original-record audit

The separate audit invoked no solver. It checked the exported Git source, input
hashes, complete request bindings, quantities/common prices, result self-hashes,
checkpoint references, verification identity, response-derived screens and work.
It reconstructed cost and prefix decisions and checked no prefix-only row became
an accepted full candidate.

Across the eight executions it checked 20 full rows, eight prefix rows, 328 artifact
bindings, 40 cost decisions and eight prefix decisions. Fourteen repeated full
records matched exactly in request, response history, terminal response and checkpoint;
eight prefixes matched the corresponding full response-history prefix exactly.
These are same-solver comparisons, not independent physical verification.

The enclosing campaign lasted 91.757110393 seconds. The separate audit lasted
2.611379407 seconds. Process times include startup, execution, original writes and exit;
source/input preparation, audit and HTTP/UI review are separate and excluded. Nested
time intervals must not be summed with their parents.

Sealed packet: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-layout-staged-amplitudes-km0zu82q`.
1097 files, 143026015 bytes; inventory SHA-256:
`83f7f988d3444e616e15af20700f65eba1c34f151b947f39e101d8643b16cb63`.
The launcher, pre-execution protocol/requests, source archive, process exits, originals
and audit are retained. The accompanying summary preserves full counters and timings.

## Development implication and current integration evidence

A useful strategy selector must account for the cost of the prefix and the full work
it can avoid. These two cases are not enough to train or validate that selector.
Future geometry/history cases should be fixed before evaluation; outcomes used to
design a selector must not also serve as its held-out benefit proof. Learned benefit,
independent physical accuracy and generalization remain unproved.

At this numerical source, [Workflow Contract CI](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34723974551)
completed successfully. Both Linux and Windows build jobs in
[Native Frame Alpha Clean Install](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34723974649)
also succeeded, removing the previously observed manifest-count failure. The downstream
clean-install jobs were queued when inspected; their results and complete hosted
acceptance are not inferred from those build successes.
