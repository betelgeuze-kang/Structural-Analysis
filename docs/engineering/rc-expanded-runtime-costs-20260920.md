# Cost attribution for the expanded learned warm-start study

This is a post-hoc diagnostic of the [completed 54-fold study](rc-expanded-runtime-campaign-20260920.md). No solver calls or fits were executed. Its 18 case/ridge records retain all three repetitions and the exact original packet identity. It does not supply counterfactual training labels or an independent evaluation.

## Where the time went

The table reports mean **proposal minus secant** path components, in milliseconds. The original measurements charge the static model gate separately; it is excluded from this path-only decomposition. The uninstrumented remainder is retained without calling all of it serialization or I/O.

| Ridge | Middle-geometry amplitude | Solver invocations | Material capture | Proposal computation | Response recovery | Unattributed remainder |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| 10,000 | 0.5 | +149.70 | +56.05 | +23.37 | -3.23 | +0.63 |
| 10,000 | 1.0 | +40.14 | +56.81 | +23.17 | +15.62 | +0.94 |
| 10,000 | 1.5 | +47.44 | +56.81 | +23.73 | -0.71 | +3.43 |
| 1,000,000 | 0.5 | +86.04 | +56.46 | +22.94 | +31.51 | -1.50 |
| 1,000,000 | 1.0 | +61.03 | +56.68 | +23.71 | +0.68 | -10.62 |
| 1,000,000 | 1.5 | +45.18 | +56.34 | +23.59 | -1.47 | -1.20 |

Each arm's component values are nonnegative and add back exactly to its stored path wall time. A negative difference means that particular component was faster in the proposal arm, not a negative duration.

Solver invocation time increased in every middle-geometry mean, even where the Newton count decreased by one. Recorded line-search trials for the 12 controlled targets were 16/25/32 in secant; the first ridge used 19/26/33 and the second 18/26/33. These are the recorded line-search histories, not an inferred total assembly count or separately measured line-search time. They help explain why Newton count alone is an insufficient cost measure, but do not prove that line search accounts for all additional invocation time.

The consistent material-capture and proposal overhead totals about 79–81 ms per path. Eliminating that entire overhead is not demonstrated and would still leave positive mean invocation-time differences in these cases. Therefore a faster predictor alone is not an established remedy.

## Why these step comparisons are not learning labels

The two strategies share the same accepted parent for controlled targets 0 and 1. From target 2 onward the recorded parents differ in every middle-geometry case. Their full response histories pass the fixed comparison tolerances, but they are not identical native parents. Selecting whichever arm was cheaper at each later target would splice different histories together and would not represent a measured executable policy.

For example, ridge 10,000 at amplitude 1.5 changes the target-wise Newton differences in both directions: some targets save one or two iterations, while others add one. These observations can nominate a research question; they cannot be used as causal strategy labels or summed into an oracle speedup.

The next valid experiment should compare candidate seeds on the **same retained native parent and causal context**, retain unsuccessful attempts, and charge feature acquisition. Any resulting selection policy must then be reevaluated along its own complete history with geometry/project/history exclusion and original tolerances. The currently retained middle geometry alone does not establish generalization to new geometry groups.

## Integrity and verification

Diagnostic source: `2170db93a` (`scripts/diagnose_expanded_rc_runtime_costs.py`). The frozen diagnostic copies independently check each consumed original file against the original inventory and its report binding. Repetition-wise Newton counts, recorded line-search counts and parent relationships agree in all 18 records. Two focused tests verify exact additive attribution including preload, reject overlapping durations, and reject unknown work; Ruff passes.

Diagnostic packet: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-runtime-costs-6pm3z8tc`, inventory SHA-256 `701cf391c3bdc24ba6f8c8446896c5e94659b4e2fc7ab61a297a4a9fd6d4d815`. Original measurement packets were not edited. [Complete diagnostic](rc-expanded-runtime-costs-20260920.summary.json).
