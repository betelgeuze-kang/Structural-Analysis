# Training-history coverage experiment: predeclared scope

The [completed grouped runtime experiment](rc-grouped-runtime-campaign-20260920.md)
produced no learned corrections. For the interior geometry, 21 distinct input
features violated the training envelopes across the original contexts. Those
features are concrete dissipated energy, concrete compressive history and one
steel plastic-strain coordinate. Four concrete energy coordinates violated the
range on all 11 noninitial targets, with identical exclusions at both ridge values.

The next bounded question is whether additional **training histories within each
geometry family** improve input coverage without mixing that family into its
own withheld statistics. It is not a new timing or predictive-accuracy claim.

`scripts/run_grouped_rc_history_coverage.py` fixes the following before numerical
execution:

- Keep the three existing training geometries and all existing material, load,
  integration, arithmetic, tolerance and four-reversal settings.
- For each training geometry, run the original 12-target history at multipliers
  0.5, 1.0 and 1.5. This creates nine training cases in three connected groups.
- Preserve the two reserved evaluation models and requests exactly, with evaluation
  explicitly deferred. No reserved label, response or metric enters this stage.
- Generate all original reference/secant/fresh-reference labels. If any required
  labels are incomplete, retain failures and do not issue a coverage conclusion.
- Withhold every case of one connected geometry family when calculating feature
  minima/maxima. Retain the existing 0.1 range margin and 1e-12 minimum slack.
- Report per-label range eligibility and offending feature names from original
  accepted reference-parent inputs. No runtime proposal is executed by this audit;
  in-range inputs alone do not establish good predictions or safe acceleration.

Expected complete label count is 99 (9 × 11), with 66 fitting samples per excluded
family. Repetitions or amplitude variants are not new independent projects.
The ordinary original-label study still performs its initial fit, and that cost
remains charged even though this diagnostic uses only the feature envelope.

This stage deliberately precedes another full repeated runtime campaign. Its
outcome can guide further **training-only** development while the existing
reserved evaluation paths remain unexecuted. It does not restore an untouched
status to any previously observed training fold or waive physical verification.

## Terminal outcome: incomplete labels, no coverage conclusion

The frozen `1cb62a5964ed0bac2cc0c97233ace5b3860f983b` execution is terminal.
Seven cases qualified their original labels; two A-family variants did not.
Only 77 of the expected 99 labels were retained. The run intentionally emitted
`incomplete_labels`, performed no fit, and produced no range-eligibility result.
Both reserved evaluation solver paths remain unexecuted. Their canonical models
and full requests were compared exactly with the prior campaign and are unchanged.

| Variant | Blocked reference target | Relative equilibrium residual | Control error | Secant path |
| --- | ---: | ---: | ---: | --- |
| A × 0.5 | +2 mm (index 6) | 0.09973544 | -0.861328125 mm | All 12 targets complete |
| A × 1.5 | -4.5 mm (index 2) | 0.19662428 | +1.384277344 mm | All 12 targets complete |

Both original reference paths stop with `line_search_failed_to_reduce_residual`;
rollback remains exact. These are substantial unsatisfied equilibrium/control
conditions, not tiny terminal-rounding differences. A completed secant path does
not satisfy the existing requirement for a completed independent fresh-reference
comparison. No failed sample was relabelled as valid, and acceptance tolerances
were not relaxed. The next numerical investigation should preserve these exact
parents/targets and examine globalization before expanding the learning study.

Known work was 323 core calls and 1,670 Newton iterations/linear solves, with no
unknown execution work. The label-study wall time was 117.067 s and enclosing
campaign time 117.192 s before final outcome write. No runtime selection or
reserved-case performance measurement followed.

Packet: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-history-coverage-37l21wi_`.
All 466 frozen source files match their SHA-256 manifest and exact Git blobs.
Inventory: 2,513 files / 129,504,366 bytes, excluding regenerable `__pycache__`;
SHA-256 `cffefc0082c58e75d07f6e7df712bea1e8eaab9b66ceb368990fd00b633e4f70`.
[Retained outcome](rc-training-history-coverage-20260920.summary.json) includes
all nine cases and the original blocked-step metrics.
