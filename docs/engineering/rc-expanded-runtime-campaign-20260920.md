# Grouped runtime follow-up from 99 retained labels

Execution source: `fa2af8cbdd976e84d96d21b4e10e5b77d9f7efac`.
Driver: `scripts/run_expanded_rc_runtime_campaign.py`.
The source packet contains 467 committed files. Execution uses one OpenBLAS/OMP thread and the retained twofold arithmetic profile.

## Protocol and separation

This follows the separately audited label recovery in [the diagnostic correction](rc-diagnostic-label-correction-20260920.md). The original label process's post-fit diagnostic failure remains a failure; its completed numerical labels are reused under their original inventory identity. No labels are regenerated to make the original process appear successful.

Nine training cases cover three geometries and three amplitudes each. Each withheld case excludes its entire three-case geometry group, leaving exactly 66 complementary samples. Two ridge values (10,000 and 1,000,000), three counterbalanced repetitions and nine cases yield 54 folds. Each fold includes reference, secant, proposal and a fresh reference full path. The two reserved cases remain unexecuted. This is training-only strategy selection, not independent evaluation.

Extended line-search candidates down to 1/4096 are explicit in every request. The solver acceptance tolerances and full-history comparison tolerances remain unchanged. The public solver default is not changed. A candidate needs actual proposals, complete comparisons and at least the predeclared one-percent improvement to displace secant.

The separately incurred label-study cost is 134.743465748 seconds, 351 core calls and 1,894 Newton iterations/linear solves. Runtime-selection costs include its fitting, all four path arms, comparisons and intermediate output. Driver wall time also includes retained-input validation and preparation; imports, the final outcome write and subsequent auditing are excluded. These scopes must not be reported as end-to-end independent-case net savings.

## Terminal outcome

The original process exited **0**. All **54 folds / 216 full paths** completed and all full-history comparisons passed. There were **198 learned proposals and 450 abstentions**, 18 fits, **2,808 core calls and 14,679 Newton iterations/linear solves**, with no unknown work. Each fit contained exactly the 66 complementary-group samples.

| Ridge | Equal-case mean proposal/secant time | Learned proposals | Decision |
| --- | ---: | ---: | --- |
| 10,000 | 1.0142941048810143 | 99 | Reject; 1.43% slower |
| 1,000,000 | 1.0132257932504385 | 99 | Reject; 1.32% slower |

The final strategy remains **secant**, with no winning-policy refit or promotion. The selector took 1,016.628100486 seconds; the enclosing driver took 1,016.765035116 seconds. The earlier label cost remains separate. This experiment establishes successful learned proposals within the expanded training coverage, but no overall acceleration.

The static model gate rejected all 36 extreme-geometry folds; the 18 middle-geometry folds used 11 learned proposals each. In every middle-geometry case and both ridge choices, the three-repeat mean time was slower than secant:

| Middle-geometry amplitude | Secant Newton iterations | Learned at ridge 10,000 | Mean time ratio | Learned at ridge 1,000,000 | Mean time ratio |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0.5 | 51 | 56 | 1.068453 | 53 | 1.058755 |
| 1.0 | 63 | 62 | 1.035862 | 64 | 1.034754 |
| 1.5 | 69 | 68 | 1.031333 | 68 | 1.029544 |

Iteration counts include preload and were identical across each case's three repetitions. Small one-iteration reductions do not offset total proposal-path overhead. Some fallback-only folds had ratios below one; these are not evidence of learned acceleration. The equal-case overall score mixes proposal-using and fallback-only cases, so the middle-geometry table is necessary to interpret it.

The next useful learning question is which specific steps can save enough solver work to cover inference and state-capture costs. More amplitude coverage alone has now been tested and is insufficient to make this warm-start policy beneficial. No broader geometry, physical validation, candidate-search benefit, or reserved-case result follows from this experiment.

## Evidence

Original labels: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-history-coverage-extended-a784lw9c`, inventory SHA-256 `f850f7e65670bf4d6254039da2aca35269cbd1840b645d82308c2402017849f0`.

Runtime packet: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-expanded-runtime-hny1qlu6`. The checked-in summary is generated only after all predeclared folds have terminated. An independent receipt auditor checks input hashes, complete fold roster, group exclusion, original comparison reports, per-invocation costs, timing ratios and the final selection rule without fitting or solving again.

The terminal inventory contains **18,189 files / 956,068,912 bytes** (excluding interpreter caches and the inventory itself), SHA-256 `d5e1d9d6727a827ba8f4011b9a52e9ca66be417bd927cae9dceb450e96a1aba2`. All 467 frozen source files match their recorded hashes and original Git blobs. Auditor revision: `cf07a25f17fa83787e09a7e7bbbc6f9ea7ee0605`. The stored report is [the complete receipt summary](rc-expanded-runtime-campaign-20260920.summary.json).

Audit rejection checks used separate temporary files: removing a fold while recomputing summary hashes was rejected for an incomplete roster; changing the source inventory identity was rejected before receipt processing. Original packets were not modified. The audit does not repeat numerical solves or provide an independent physical reference.
