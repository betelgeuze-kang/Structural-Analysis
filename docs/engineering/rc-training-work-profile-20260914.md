# Original training-path work distribution

Analysis source `b56d0494c6319f0990f7894d547db3f75b79e796`.
Following the [vector fraction sensitivity study](rc-vector-fraction-steps-20260914.md),
profile all original training steps before selecting further learning targets.
This is a read-only analysis of preserved executions, not a new benchmark run.

## Scope and authentication

Freeze four training cases, reference/secant arms and a top-10-percent primary
row ranking before reading costs. There are 242 steps per path and eight paths,
1,936 authenticated original step files plus eight authenticated path files.
No validation or hold-out path is opened. Verify the original inventory SHA256,
file length/hash, step/path canonical hashes, parent identity and per-invocation
linear count; use the existing strict iteration-cost parser to distinguish
primary iterations from terminal refinement. Cross-arm parents are not assumed
to match: these are each strategy's original whole-path cost distributions.

The training source packet remains unchanged. The new [receipt](rc-training-work-profile-20260914.json)
binds the source archive, runnable profiler/auditor, detailed rows, original input
bindings and execution log. A second audit checks all aggregates and input bytes,
source extraction and the sealed output inventory. There are zero new solves or
fits, and no physical-validation or independent-performance credit.

## Secant distribution

| Case | Primary rows | Terminal linear solves | Inclusive linear solves | Primary rows in largest 25 steps |
| --- | ---: | ---: | ---: | ---: |
| train-a | 578 | 391 | 969 | 95 |
| train-b | 478 | 392 | 870 | 83 |
| train-c | 616 | 374 | 990 | 91 |
| train-d | 471 | 381 | 852 | 86 |

Across 968 secant steps the primary-row histogram is:

| Primary rows in step | Number of steps |
| --- | ---: |
| 1 | 330 |
| 2 | 156 |
| 3 | 428 |
| 4 | 53 |
| 5 | 1 |

The only five-row secant step is train-a index 7. A total of 482 steps have at
least three primary rows, while 330 already have only one. The 25 highest-ranked
steps from each case (100 of 968 steps, rounded up per case) contain 355 of
2,143 primary rows, about 16.6%. Costs are not concentrated in a tiny set of
extreme primary-iteration outliers. Ranking breaks ties by target index;
selected indices are descriptive training observations, not deployment features.

There are 1,538 terminal linear solves out of 3,681 inclusive linear solves,
about 41.8%. This fraction is a recorded work category, not an estimate of
removable overhead. Terminal refinement and verification cannot be dropped to
manufacture a warm-start speedup. Neither total assembly counts nor material
integration counts are inferred from these original histories.

The reference paths have primary totals 960/803/1,020/776 versus secant's
578/478/616/471. This is evidence that the existing deterministic baseline already
reduces much of the primary work in this training family. It does not measure
a new learned policy or establish independent-project generalization.

## Consequence for the next experiment

Do not train only on the very largest few steps and expect them to dominate
whole-path savings. A useful gate must separate the broader multi-iteration
region from already-cheap steps using information available before a solve;
actual reference cost may label training data but must never enter inference.
Evaluate retained savings after feature/proposal/fallback costs, with all original
tolerances and terminal work preserved. The inspected training paths cannot later
serve as held-out proof, and split isolation remains a separate requirement.

Profiling took 191.105317932 seconds including source-file reads, hashing and
parsing, excluding source staging/import and subsequent audit. That is analysis
cost on this storage run, not solver execution time or a production latency claim.
