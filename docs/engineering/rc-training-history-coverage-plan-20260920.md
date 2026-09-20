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
