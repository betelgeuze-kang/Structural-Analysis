# Matched process costs for staged RC layout selection

Frozen numerical source: `af3793dd3a8a34891ea81c8b76a4428c1a7ae790`.

Four independent worker processes executed the existing cost-pruned scheduler and
the new prefix-staged scheduler on identical original inputs. The order was frozen
as pruned → staged, then staged → pruned. Each process ran one complete strategy;
no automatic retry occurred. This is a deterministic scheduling comparison with
no learned policy, fit or new training labels.

## Scope and results

The pool contains the same known baseline, small, middle, large and outside models
used in the prior prefix pilot. Both strategies consider all five with a frozen
budget of five including baseline, the same six-target cyclic request, material
properties, tolerances, performance limits and common synthetic material prices.
The staged strategy uses the two-target prefix selected after the known-pool pilot.
This is exploratory reuse, not an independent held-out benchmark. There is no
constant preload in this particular measured request.

| Pair | Cost-pruned process | Staged process | Staged / pruned |
|---|---:|---:|---:|
| pruned then staged | 11.840332758 s | 11.078261884 s | 0.935637715 |
| staged then pruned | 11.781439755 s | 11.047367919 s | 0.937692519 |
| Sum | 23.621772513 s | 22.125629803 s | 0.936662555 |

The observed reduction is 6.33% by ratio of process-time sums. Two ordered repeats
on one non-isolated host do not establish a stable distribution, confidence bound,
other-problem speedup, or a general product performance claim. The executable
strategy-call intervals are nested in those process intervals: pruned 10.030929389
and 9.985271155 s; staged 9.292191011 and 9.269992728 s.

Every run selects `middle` with original synthetic estimate
`246.34835999999999` (rounded display 246.34836). This is not a quote or verified
currency saving. The incumbent cost rule skips large and outside in both methods.
The staged run rejects small after a verified prefix strain-limit violation;
middle passes the prefix and is accepted only after a new full-reference path.
The baseline always receives its complete path.

| Per run | Cost-pruned | Staged |
|---|---:|---:|
| Full reference rows | 3 | 2 |
| Prefix reference rows | 0 | 2 |
| API calls including verification | 6 | 8 |
| Attempted steps including verification | 36 | 32 |
| Newton iterations / linear solves | 72 / 72 | 64 / 64 |

The prefix increases invocation and serialization overhead while avoiding one
full path. Across all four runs the accounting is 10 full rows, 4 prefix rows,
28 API calls, 136 steps and 272 Newton iterations / linear solves. The work is
known; there are no hidden failed-path retries. Different models or limit settings
may produce no rejection and increase total cost.

## Audit and preserved originals

A separate audit checked 643 frozen source files against the Git archive,
input identities, 164 artifact hash/length bindings, 20 cost decisions and four
prefix decisions. It recomputed quantities, estimates, performance screens,
incumbent selection and the prefix violations from original records. Prefix
requests match the full request with only the suffix removed. All seven repeated
full-response comparisons and all four prefix/full-history comparisons are exact.
Full and prefix paths each retain their fresh same-solver verification. This does
not constitute external physical verification.

The enclosing four-process campaign took 45.747992795 s. Individual process and
strategy-call intervals are nested components; do not add them to the campaign.
Audit took 2.217164085 s and performed no solver calls. Source preparation,
packet sealing, historical research and future HTTP/browser review costs are
outside these measured intervals and are not all timed.

Read-only packet:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-layout-staged-costs-_dieg276`.
876 files, 123,155,181 bytes. Inventory SHA-256:
`9a192b671d0d4c128cd6fc970d9b16ab5c9cd97a1d97ba772c7b9c4c9ebf16ea`.
It contains the launcher, frozen source, input bindings, pre-execution protocol,
process outcomes, original solver/verification artifacts and the completed audit.
All worker processes are terminal. Prior sealed packets remain unchanged.

## Next gate

The measured staged artifacts still require HTTP graph admission and Workbench
review. That integration must validate original prefix request/model/result/
checkpoint/verification identities, reproduce cumulative-limit rejection, preserve
complete costs, and distinguish it from cost skipping and full acceptance.
No staged HTTP or browser acceptance is claimed here. Broader independent cases,
external verification, learned net benefit and full hosted qualification remain
open; the roadmap is not complete.
