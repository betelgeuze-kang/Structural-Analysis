# All three reversal proposal paths complete in both execution orders

Frozen source `8d0dd66b65f17245bca08fb4fee5a284afc3631e` executes all six planned comparisons / 24 paths. Every frozen-parent-continuation proposal arm completes the original 600 kN preload and (-20,-40,+20) mm requested history: w32 cheap, w32 middle and w48 cheap, in both orders. Each model's complete accepted response history and terminal checkpoint agrees exactly between the two proposal executions.

All ordinary reference, secant and fresh-reference arms remain incomplete. Consequently every comparison against the fresh reference still fails and every qualified speed ratio remains null. Six completed proposal paths out of 24 attempted paths is not 24 successful reference comparisons, independent physical agreement, unique branch selection or design approval.

The continuation performs sixteen internal native trial solves at the reversal, all from the same original -40 mm material parent. Their returned checkpoint objects are not adopted as material-history parents. Every stage's original result artifact is retained; the outer +20 mm invocation performs the final native acceptance. No requested-history subdivision or tolerance change is introduced.

| Accounted scope | Core calls | Newton / linear solves | Newton assembly dispatches |
| --- | ---: | ---: | ---: |
| Ordinary path invocations, all arms | 102 | 588 | 1,638 |
| Additional frozen-parent proposal stages | 96 | 310 | 636 |
| Combined native work | 198 | 898 | 2,274 |

Enclosing proposal work totals 1.663392253 s, including intermediate result serialization, inside the whole path clocks. There are no SciPy optimizer callbacks in this strategy. The assembly counts cover Newton dispatches, not exhaustive outside-Newton/material evaluation work. Failed baseline/fallback work remains in these totals.

The audit checks all six report hashes, 96 intermediate artifact hashes and lengths, native acceptance gates, constant parents, declared work sums, all outcomes and repeated complete response histories/checkpoints. The 1,974-file non-cache inventory includes frozen committed source and every retained run artifact and was reread; SHA-256 `9583a3fa9292ea5f9c5746cae2d126cdccb260a729c3c6385669657a7042b104`. See the [summary](rc-frozen-continuation-path-results-20260921.summary.json) for source, roster and path clocks.

The implementation passes 102 focused tests covering warm starts, parent-step handling, initial residual observations, workflow contracts, all three actual failing-model regressions and an interrupted second continuation stage. A small-displacement test initially rejected harmless parent/target rounding; the parent consistency check now uses the already existing control tolerance. Native solver tolerances remain unchanged.

This establishes a useful numerical completion result in the bounded internal model family. The benchmark remains experimental. Before product design eligibility, preserve ordinary-reference failure and add a source-bound full-artifact replay for the proposed path, together with the required independent physical validation and broader cost/generalization checks.
