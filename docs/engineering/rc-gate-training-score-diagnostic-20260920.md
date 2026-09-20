# The fixed gate also declines every training row

The [complete guarded runtime result](rc-guarded-runtime-results-20260920.md) declines all 540 online decisions. Its diagnostic attributes 222 decisions to individual-feature bounds and 318 to scores below the fixed threshold. A subsequent read-only training diagnostic shows that distribution shift is not the only limitation: **all five original gates decline every one of their own 132 training rows** at the unchanged 0.75 threshold.

| Excluded outer group | Positive / negative rows | Largest positive score | Training true positives | Training false positives | Training pairwise AUC |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0 | 5 / 127 | 0.232254 | 0 | 0 | 0.921260 |
| 1 | 6 / 126 | 0.445152 | 0 | 0 | 0.943122 |
| 2 | 7 / 125 | 0.304023 | 0 | 0 | 0.898286 |
| 3 | 6 / 126 | 0.159425 | 0 | 0 | 0.899471 |
| 4 | 8 / 124 | 0.294653 | 0 | 0 | 0.919355 |

These are five overlapping complement fits, not 660 independent physical cases. All 32 positive label rows are false negatives under the fixed training decision rule. The training ranking measures show some ordering within the fitted data, but they are not held-out performance, calibrated probabilities or evidence of runtime savings. Regression scores must not be interpreted as probabilities merely because their targets are binary. Training MSE is below each constant-prevalence baseline, yet the resulting decisions still select nothing.

The diagnostic reassembles every original training table from the pinned nested label and seed inventories, checks equality to the retained fit tables and their policy training hashes, loads each strict original gate, and verifies that direct score comparisons agree with the gate's actual decision method. No policy, threshold, bounds or labels are modified. No threshold sweep, fit, structural solve or reserved evaluation is performed.

## Next decision

Do not repeat another complete-path timing campaign with the unchanged gate expecting useful proposals. Before that expense, a new development protocol must specify a decision objective and score interpretation consistent with rare measured benefits, and inspect its training decision behavior. Any revised loss, feature representation or threshold is a new development candidate informed by these observed failures, not an untouched confirmation of the old result. Outer-group exclusion and the untouched reserved cases must remain intact; training classification or ranking improvement cannot substitute for actual full-path net savings.

This finding does not identify one uniquely correct replacement model or prove that lowering a threshold will accelerate the solver. False proposals can cost more than missed opportunities, and local labels do not establish full-path benefit. Secant remains the supported selection while a useful alternative remains unproved.

## Evidence

Observer revision: `2f5d5d6dc671ae6e09d16ca87d5297155de02b24`. The diagnostic uses the original fixed gate-fit, nested-label and nested-seed inventory pins retained in the [machine summary](rc-gate-training-score-diagnostic-20260920.summary.json). Elapsed diagnostic time before writing is 0.269069 s; this is not a benchmark speed claim.

Packet: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-gate-training-score-diagnostic-qn5qg4ft`. Both payload files verify against inventory SHA-256 `4e82ce2fea25fa137ce689133eb34bbf2d4ecc4ec69e4b5fa156fe0a7b06bb3c`. The packet retains the exact diagnostic program, per-gate score ranges/counts and original policy/training hashes.
