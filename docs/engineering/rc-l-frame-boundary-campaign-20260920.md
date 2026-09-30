# Repeated L-frame design selection with a rejected cheaper candidate

The prior [plastic L-frame study](rc-l-frame-cost-campaign-20260920.md) used broad
synthetic limits under which every candidate passed. This separate campaign uses
a maximum steel accumulated plastic strain of **8e-5**, chosen post-hoc from
those same-model observations. It tests actual limit rejection and baseline
retention with cost exclusion. It is not an independent evaluation or an
engineering acceptance limit. Prices remain synthetic.

Only the experiment driver changes from the preceding frozen source: all other
466 archived files, including every numerical source, are identical. The new
source is `ae3eef1fd116700c43dec642ec7e633122010942`. The original two-member
geometry, constant 20 kN vertical load, twelve reversing targets, reinforcement
candidates, material laws and solver tolerances remain fixed. No training or AI
is involved. The four full result hashes match the prior broad-screen study
exactly, even though the stricter caller limit changes eligibility.

| Design | Observed steel accumulated plastic strain | Synthetic limit result | Declared material estimate |
| --- | ---: | --- | ---: |
| baseline | 7.878049781739804e-5 | pass | 254.1252 USD |
| cheap | 8.77808609403411e-5 | fail | 237.86 USD |
| middle | 7.564745076645051e-5 | pass in full comparison | 259.84 USD |
| costly | 6.380519357565963e-5 | pass in full comparison | 281.82 USD |

Every full and pruned process selects baseline. Cheap undergoes its complete
analysis and fresh verification, then is rejected by its actual limit violation.
The pruned process excludes middle and costly only because they cost more than
the verified eligible baseline; their performance and eligibility remain unknown
in that pruned report. The separate full comparison establishes their actual
screen results. No requested-limit failure is reclassified as a solver failure,
and no unanalysed candidate is represented as having passed its limits.

## Four counterbalanced pairs

All eight public CLI processes exit successfully. The auditor reconstructs all
four pair receipts, checks the exact full/pruned order and eight-process
denominator, and verifies repeated and retained numerical result hashes.

| Pair | Full process seconds | Pruned process seconds | Pruned / full |
| --- | ---: | ---: | ---: |
| 0 | 39.367537315 | 20.306694948 | 0.515823 |
| 1 | 40.079188699 | 20.351260142 | 0.507776 |
| 2 | 39.666749053 | 20.359289974 | 0.513258 |
| 3 | 39.825766851 | 20.441089394 | 0.513263 |

Summed process time is 158.939241918 versus 81.458334458 seconds, a ratio of
0.5125124134 (48.75% lower in this observation). Full runs total 32 API
invocations, 416 attempted steps and 2,536 Newton iterations/linear solves;
pruned runs total 16, 208 and 1,264 respectively. Each invocation count includes
fresh full-path verification. No unknown numerical work was accepted.

These enclosing process clocks include interpreter startup, input, all analyses,
fresh verification and output. They exclude parent setup/audit and browser or
transport time. The host was not isolated; ordinary development activity was
possible, and browser execution was deferred until the numerical campaign
finished. This is a bounded same-model cost-exclusion observation, not a general
speedup, AI benefit or whole-user-flow time reduction.

The source, process receipts, original artifacts and read-only audit are retained
at `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-l-frame-boundary-8bbvizfi`.
The companion summary preserves all pair costs, work counts and full-model
observations. Independent physics, engineering-limit authority and commercial
price validation remain separate requirements.

## Original-artifact Workbench review

The repetition-0 pruned report and all 21 referenced JSON artifacts are packed
byte-exactly in the [boundary fixture](../../tests/frontend/fixtures/l-frame-boundary.md).
At 1440px and 390px, the browser verifies the complete artifact set, shows
baseline as selected, disables cheap after its verified limit failure, and
distinguishes middle's unanalysed cost exclusion. It exposes the exact observed
value and caller limit and downloads the rejected cheap result byte-for-byte.
The viewport bounds pass, and the retained mobile screenshot was inspected.

The original and new L-frame tests initially pass five checks locally. After
the separate [90cc hosted screenshot timeouts](hosted-90cc-terminal-20260920.md),
the four browser cases receive a 60-second budget. Both repetitions with two
workers then pass: **10 tests in 1.2 minutes**. All semantic assertions and final
screenshots remain. TypeScript and the unchanged offline source inventory pass.
This local run does not turn the failed 90cc CI into a success.

Audit/browser revision: `d76e45c1197c9d4891c5eaf223c00ff304263dc5`.
The preserved packet has 735 payload files, 100,543,328 bytes, excluding Python
cache files. All listed byte lengths and SHA-256 hashes were checked. Inventory
SHA-256: `5553e5ff042ccdd414c9e7b4372aae1b481af774d13b9435d392815676c2b4c2`.
The packet includes the two browser screenshots and source-bound auditor/test
copies. Audit and browser review perform no new structural solves.
