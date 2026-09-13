# RC warm-start diagnosis using only the original training cases

Source `e9dd26ed8d85795c74153eac2df6626b2cc1a148` adds
[case-withheld training diagnostics](../../src/structural_analysis/benchmark/rc_control_training_diagnostics.py).
The utility takes original training samples and their frozen policy, checks every
sample hash and the exact ordered policy sample list, and rejects validation or
holdout rows before fitting. Each fold excludes one complete training case.
Weights, means, standard deviations and feature bounds are fitted from the other
cases only. The original fixed ridge and range margin are retained; the original
policy's weights/scales/bounds are not used by the fold predictors.

The report retains each fitted policy and its train/withheld sample identities,
per-coordinate correction RMSE against the zero-correction secant baseline,
feature range violations, empty eligible subsets as unavailable metrics, and
fit/prediction costs. Ungated predictions remain diagnostics. Range eligibility
does not certify the other runtime conditions, accepted structural results or
speedup. Runtime rounding when adding the correction to a secant seed is not
measured by this correction-only diagnostic. The prescribed-coordinate correction
is zeroed consistently with the runtime's target reset.

## Original 964-pair observation

Only `study/training-samples.json` and `study/policy.json` are read from the
[sealed expanded training study](rc-training-expansion-completed-20260910.md).
Their original bytes match the hashes in that study's retained local inventory.
This verifies content consistency; independent provenance remains unestablished.
The validation/holdout data and original source packet remain untouched. All 596
selected current source/test files match Git and remain unchanged during execution.

The four fixed folds each fit **723 pairs** and withhold **241 pairs**, using
ridge `1e-6` and range margin `0.1`. All folds belong to the same authored training
project. This is a development case-transfer diagnostic, not an independent
project/campaign split or a new blind evaluation.

| Withheld training case | Within fitted feature ranges | Outside ranges | Learned/secant correction-RMSE ratio across six non-controlled augmented coordinates |
| --- | ---: | ---: | ---: |
| train-a | 0 / 241 | 241 | 0.67-1.88, ungated only |
| train-b | 241 / 241 | 0 | 1.03-1.55 |
| train-c | 0 / 241 | 241 | 0.77-1.47, ungated only |
| train-d | 0 / 241 | 241 | 1.93-6.16, ungated only |

Each ratio compares the same coordinate's RMSE; values above one are worse than
zero learned correction. Coordinates retain their original solver scaling,
including the augmented load-factor coordinate. This table is not an aggregate
of different physical units. The prescribed coordinate is excluded from the
range above; its retained near-roundoff label residual has ratio one.

For train-a, `rotation_coordinate_scale_m` alone excludes all 241 samples.
Train-c and train-d also violate geometry/length bounds; train-c has additional
accepted-coordinate and previous-increment violations. The complete feature
counts and all per-coordinate errors are retained in the original fold report.
For the sole range-eligible case, train-b, all six non-controlled coordinate
correction errors increase. These findings demonstrate a training-case transfer
and feature-coverage limitation before any new structural solve. They do not
prove a unique cause of the earlier slower runtime result.

The next learner change needs training-only evidence for improved feature
normalization/history representation or model capacity, followed by a frozen
full-path comparison with complete costs. This observation supplies no reason
to promote the current policy, relax its range checks, or repeat the same
unchanged expanded training run. Public experiment reconstruction and independent
campaign coverage remain required.

## Costs, verification and retained outputs

There are **four actual refits and zero structural solver calls**. Individual
fits take 0.007317439, 0.006477713, 0.006073514 and 0.006289924 seconds, nested in
the 0.406709568-second diagnostic. The worker interval through report writing is
0.416051169 seconds; the parent process interval is 2.164532493 seconds and
includes interpreter/import/input-reading overhead. Source preparation, hashing,
the separate final audit, GitHub retrieval and sealing are outside these intervals.
Peak worker RSS is 198,460 KiB. No runtime speed comparison is performed.

Eight focused tests pass in 1.58 seconds. A withheld case's features and labels
can change without changing that fold's weights, scales or bounds. Invalid source
hashes, reordered/duplicate rows, evaluation rows, nonfinite values and one-case
data reject before diagnostic fitting. The first mypy run finds one missing
collection annotation; the corrected module passes mypy, Ruff, formatting and
diff checks. That annotation does not alter numerical behavior.

The observer and worker are confirmed absent before sealing. The packet at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-train-folds-h7tzgfkb`
contains **18 files / 22,478,923 bytes**, inventory SHA-256
`6f7d8655d7dcf86cab42086bd063030cc8f0b978faaf002f7648d3e63b986259`.
It retains the predeclared inputs, original sample/policy copies, worker/observer,
all four fitted policies, reports and process outcomes. The
[machine summary](rc-training-case-folds-20260910.summary.json) records the source
and observation identities. Neither the original policy nor production proposer
behavior is changed.

The same packet separately retains original completed logs for CI runs
[34385591191](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34385591191)
and [34385597715](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34385597715)
at preceding published head `e3476809ccf16b1b803bf1d20db2d52bdbe380d6`.
Both browser installation steps pass, then materialization fails with
`external_code_to_code_product_replay_not_passed` and
`external_code_to_code_technical_receipt_not_ready`. Downstream skipped checks
receive no pass credit. The full roadmap and these external verification
requirements remain open.
