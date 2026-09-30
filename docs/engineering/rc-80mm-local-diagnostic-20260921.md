# Local residual and line-search diagnosis at the 80 mm witness

Frozen source `a94d82d1ed60317d36bce7f5af67730576f9ff61` reconstructs the final binary64 failed recovery trial from both original orderings. The parent, model and target are hash-checked against the original packet. Residual vectors and Newton directions match the original records exactly. The 84 noncommitting residual/tangent observations produce identical results across the two repeated states; the parent remains unchanged.

The residual infinity norm is 2.022516977339119e-05 kN. The augmented Jacobian has raw 2-norm condition number 6291.26379901; this is coordinate/units dependent, not a physical stability criterion. Solving its Newton equation leaves infinity-norm error 1.321371397716709e-19 kN. This small linear-system error does not establish a globally valid tangent or a converged nonlinear solution.

The original six trial fractions, 1 through 1/32, all increase the residual at this state. The first smaller sampled fraction, 1/64, decreases it to 2.016535255888764e-5 kN. At 1/128 it decreases to 2.0067151333433584e-5 kN. These observations establish local descent outside the original grid; they do not establish whole-step convergence or full-path completion.

## Actual native follow-up

Six native solves use the same original material parent and original trial initial coordinates, reversing profile order on the second repeat. The original profile reproduces its entire native trial solution exactly. Residual/control/increment tolerances remain unchanged.

| Profile | Maximum iterations | Smallest alpha | Actual Newton iterations per run | Final relative residual | Committed |
| --- | ---: | ---: | ---: | ---: | --- |
| Original | 25 | 1/32 | 8 | 1.348344651559413e-7 | No |
| Fine grid | 25 | 1/65536 | 19 | 1.3345627671204146e-7 | No |
| Fine grid, larger limit | 100 | 1/65536 | 19 | 1.3345627671204146e-7 | No |

Both repetitions agree in each profile. All six return `line_search_failed_to_reduce_residual`, with 92 total Newton iterations and linear solves, and no adopted checkpoint. The larger iteration limit is not reached. A finer grid finds initial descent but is insufficient to meet the original residual gate. Alongside the retained-arithmetic comparison, this narrows the next investigation to residual/tangent behavior near a material transition or a different path-following method; neither explanation is yet established. No default, tolerance, recovery budget or learned policy changes.

## Evidence

Direction packet: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-80mm-direction-10ghwgfw`; inventory SHA-256 `971a6013549ce55e2bc2336b1cafe715a11867e492405014ac3102d7dd934e55`. Local-search packet: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-80mm-local-search-1_byxzj0`; inventory SHA-256 `fb4fe6cdc180aa2a2ead1bc6ed3b093b7b508acf2f6d977854e4c52c40a1abe4`. Each preserves its pre-execution plan, driver, numeric observations/results and hash inventory, with every entry reread. The two studies' work is separate: 84 observations without solving, then six native solves. Neither is a fresh complete-history replay, external physical validation, speedup, or release approval.

[Machine-readable evidence](rc-80mm-local-diagnostic-20260921.summary.json).
