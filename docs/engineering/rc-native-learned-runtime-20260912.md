# Learned runtime selection with native assembly reuse

At source `9374eb140725a67edfd7cca3c04a4febe3f3fbeb`, native assembly reuse
does not make the existing learned warm start preferable to secant in this
authored four-case cohort. The reconstructed mean of case mean learned/secant
scored path-time ratios is **1.0185773190436491**. The selector keeps secant;
no selected full-training refit or policy promotion occurs.

## Fixed experiment and observed result

The previous counterbalanced study's original models, 242-target cyclic requests,
964 original training rows and integrated policy are reused without changes.
Four withheld-case SVD fits use ridge 10,000 and the retained twofold arithmetic
profile. Each fit is reused across three prescribed arm orders. Native assembly
reuse and dispatch recording are enabled equally for reference, secant, proposal
and fresh-reference paths. Static rejection still falls back to secant.

| Authored case | Mean scored proposal/secant ratio | Secant / proposal Newton counts across three repeats |
| --- | ---: | ---: |
| train-a | 0.9957215516360819 | 2,907 / 2,907 |
| train-b | 1.0824775527878507 | 2,610 / 2,901 |
| train-c | 0.9974182661111134 | 2,970 / 2,970 |
| train-d | 0.9986919056395501 | 2,556 / 2,556 |

Only train-b makes actual learned proposals: 723 across three repeats. Its
ratios are 1.077635, 1.086887 and 1.082911, each slower than secant. Small
differences in the other cases occur on secant-abstention paths and are not
learned acceleration. The score includes static policy-gate setup and proposal
path time; fit cost is reported separately. It is not total lifecycle cost or
an isolated numerical-kernel timing.

The execution completes 12 folds / 48 paths, 11,616 core calls and 52,779
inclusive Newton iterations and linear solves. All 36 full-history comparisons
pass at unchanged absolute 1e-10 / relative 1e-8 tolerances. All 12 reference
repeats are exact; this does not mean every seeded terminal checkpoint is
byte-identical to the reference. Actual dispatch sidecars count 74,475 calls
and 22,956 reuse hits. A hit is not a saved Newton iteration, and these totals
are not an observed off-cache comparison within this experiment.

## Costs and source audit

Numerical parent wall time is 3,430.746125155 s after preparation. The four fits
total 0.326183887 s within the run; original label-generation costs are not
charged again or treated as free training. Successful source/record auditing
takes a separate 1,632.271805463 s, with no fits or Newton path replays. It does
perform 11,616 same-solver response reconstructions and 975,744 recovery material
integrations, reopens 48 native terminals and reconstructs 2,904 stored proposals.

The first audit stops because its new reuse counter check incorrectly requires
a field that the recorder omits when the hit count is zero. The second audit
uses that documented zero default; the failed script and traceback are retained.
Its partial cost was not separately metered and remains unknown. No numerical
experiment is retried and no tolerance is changed.

The completed audit verifies all 447 frozen Git-bound source files and the
original input inventory, withheld-case partitions, preprocessing and ridge
stationarity; reconstructs all histories, work and candidate scores; and confirms
the final selection. This is internal record verification, not independent
physical validation. The four geometries belong to the same authored structural
family. No measured training rows or new independent campaign are admitted;
validation and holdout cases are not executed.

The host is not isolated. BLAS/OMP/MKL are single-threaded with Haswell OpenBLAS;
package versions are retained. Earlier off-cache timings are historical rather
than contemporaneous controls, so differences between study scores do not prove
an acceleration attributable to reuse. The independent non-AI reuse study remains
[separately reported](rc-full-cycle-native-reuse-20260912.md).

The [machine summary](rc-native-learned-runtime-20260912.summary.json) binds the sealed packet and records the full
case repeat ratios. Preserve the original records and failed audit alongside the
successful audit. No external reference, protected qualification receipt, solver
or product policy default changes in this observation.

## Same-source hosted checks

Run [34696092738](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34696092738)
tests this source through merge `6b2e3e3acd7ac9ea2b5a09e131a06bb1cf83311b`.
Its independent development JUnit confirms 562 passes in 26 modules, no failures,
errors or skips, in 699.379 s. All four full shards fail materialization and skip
their actual full-suite pytest; the required aggregate fails. Their retained
receipts have the same two reaction mismatches as the
[hosted diagnosis](ci-hosted-materialization-20260912.md). Green development
coverage does not close full-suite or external verification requirements.
