# Time-benefit labels versus actual solver work

The original 660 nested sample/policy pairs have three verified comparisons
each. A read-only diagnostic at `36a143f7a1a6d65ba0b4180a91ca4cf800106f6a`
joins the original elapsed-time label with proposal-minus-secant counters.
It changes no labels, thresholds, models or policies and performs no new fit or
solve. Parent/sample/report identities remain attached to every result.

| Solver-work relation across all three repeats | Original time-positive pairs | Original time-negative pairs | Total |
| --- | ---: | ---: | ---: |
| Reduced | 32 | 23 | 55 |
| Equal | 0 | 546 | 546 |
| Increased | 0 | 59 | 59 |

Reduction means no increase in any of core calls, Newton iterations and linear
solves, with a strict decrease in at least one. There are no mixed counter
directions, unverified comparisons or changes of work category across repeats
in this particular packet. Of the 55 reductions, 51 save one Newton iteration
and linear solve, while four save two; core call counts are unchanged.

All 32 time-positive pairs also reduce actual iteration work. Thus the positive
labels in this retained dataset are not cases of faster timing with unchanged
counters. This does not prove causal timing attribution, isolated repeat
robustness or generalization. Conversely, 23 actual work reductions fail the
original time-benefit rule; all make genuine proposals and all are slower in
at least one repeat. Four of those 23 have a faster three-repeat mean. This
supports preserving the repeat-aware total-cost criterion instead of replacing
it with iteration count or mean timing alone.

The sample/policy pairs overlap in original cases and parents. These are not
660 independent structures or 32 independent successful projects. Equal work
does not mathematically imply equal elapsed time, and these three counters do
not resolve all assembly, line-search, capture or policy costs.

The [machine summary](rc-nested-work-benefit-20260920.summary.json) pins the
original audit inventory and complete diagnostic packet. All 1,373 output/source
files were checked against its final inventory. The original audit already
validated its 1,980 report comparisons; this diagnostic rechecks labels and
counter types without rerunning that numerical campaign. Observed diagnostic
time before output is 0.105161 s, not a solver benchmark.

Next learning work should distinguish whether a proposal reduces solver work
and whether that reduction survives proposal overhead and repeat variability.
The current material-input model's 2 true positives/25 false positives remains
a failed selection result. No new target, threshold or runtime promotion is
authorized by this descriptive diagnostic alone; each next experiment needs
its own excluded-group and full-cost validation.

Verification: the previous 99-test focused module run passed; the subsequently
added repeat-variation regression and all eight counter tests passed together
(9 passed, 91 deselected). Ruff and whitespace checks pass.
