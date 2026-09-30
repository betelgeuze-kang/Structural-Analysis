# Repeated pooled warm-start paths with immediate assembly reuse

All 90 scheduled comparisons and 360 complete paths finished with the original
acceptance tolerances. The complete audit retains **secant**: neither learned
candidate meets the predeclared 1% improvement threshold.

| Ridge | Equal-case mean learned/secant path-time ratio | Decision |
| --- | ---: | --- |
| 10,000 | 1.0165658641594375 | Reject |
| 1,000,000 | 1.020312254993227 | Reject |

These are within-run synthetic geometry/history observations. The prior
no-reuse campaign is historical and is not a contemporaneous control for an
assembly-reuse speedup. Repetitions do not create independent structural cases.

## Frozen execution and complete input audit

The numerical producer is `17c56b9997aebdc07f974d3eeb289cdab3fbd46e`.
All 803 retained source files match their committed Git blobs. The original
99- and 66-sample inventories remain unchanged; fifteen training cases form
five whole geometry/history groups. Each withheld group removes all 33 samples,
leaving 132 complementary samples for fitting. Two reserved cases remain
unexecuted. Both ridge values use three counterbalanced repetitions. The
`rc-control-immediate-line-search-reuse.v1` selection was frozen before fitting
and is bound through parent and child plans, results and comparisons.

The source-frozen auditor passed, and the later strengthened auditor passed
on the same immutable results with identical output. The latter checks each
original `request.json` against the complete comparison identity, preserving
JSON key sets and numeric/boolean types, and checks `model.json` against the
declared canonical model digest. Its bytes and software-test proof are stored
separately from the numerical producer. The scoped software suite passed 205
tests; the exact preceding auditor failed eight contradictory-type regressions.
Auditing and retained cost diagnosis perform zero new solves or fits.

The 90 comparisons include 270 full-history comparisons. There are 594 actual
proposals and 486 abstentions, 4,680 core calls, and 24,054 Newton iterations
and linear solves across all four arms. Thirty selection fits are retained;
there is no final full-pool refit or promoted policy.

## Cost and resource observations

The outer process took **1,252.138301265 seconds**, with peak child RSS
**138,416,128 bytes** and **1,588,744,681 bytes** of study output at termination.
It stayed within its declared 6,000-second, 1-GiB RSS and 4-GiB output budgets.
Selection time, driver time and process time are nested scopes and are not
added together. Earlier label-generation costs remain separate. The original
terminal process receipt is preserved; its pre-audit status is historical.

Secant used 5,412 Newton iterations; the proposal arm used 5,418. Group D saved
15 iterations across its repeats, while B added 3 and E added 18. A/C abstained
and had equal iteration work. Of 54 folds allowing actual proposals, 24 reduced
Newton work, six kept it equal and 24 increased it. A work reduction in selected
paths therefore did not establish a useful overall wall-time result.

The proposal arm's material capture component totaled 2.709350 seconds.
Proposal and feature preparation share an enclosing timer; there is no separate
feature-cost observation. Component/path sums are descriptive observations
inside their enclosing intervals and cannot be added to parent/process totals.
Later secant/proposal paths may have different accepted parents; these records
must not be promoted to same-parent causal training labels.

The [machine summary](rc-pooled-reuse-runtime-20260930.summary.json) binds result,
source, audits, retained cost diagnosis and a complete immutable payload inventory
to the retained packet. Numerical results remain bound to the frozen producer,
even after the audit-only patch is committed. This run supplies neither an
independent project split nor physical validation, hardware attestation, release
approval or net learned savings. The goal remains open. Next decisions should
use the observed proposal/capture costs and contrasting B/D/E work, preserving
reference solver authority and protected evaluation data.
