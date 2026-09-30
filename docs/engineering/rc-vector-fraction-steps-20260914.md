# Vector correction fractions: training-parent cost sensitivity

Numerical source `58f6f2eb75dfa25ba98e4f8072b52c6a8319a029`.
The [accepted-answer seed diagnostic](rc-answer-seed-parent-steps-20260914.md)
showed work headroom at the stored answer. This follow-up measures three fixed
fractions of that correction before deciding whether coordinate regression is
an attractive next target.

## Frozen protocol

Use the same twenty known training parents: four cases, indices 1, 61, 121,
181, 241. Before execution, freeze fractions 0.5, 0.9 and 0.99. Propose
`secant + fraction * (accepted_high - secant)` using the existing binary64
augmented-coordinate seed interface. Retained compensation is recorded and
omitted. Every fraction uses target answers and therefore has answer leakage.
No fit, held-out case or executable learned policy is produced.

Run reference/secant/proposal in alternating orders and a fresh reference after
each group, retaining original native parent, request, arithmetic profile and
response tolerances. Fractions run in fixed ascending blocks. Baselines are
rerun for each fraction, but this is not a randomized repeated runtime campaign.
Prefixes are reused, not newly executed. Each callback has zero extra assembly
calls; its event serialization is charged in the arm interval.

## Measured work

| Fraction of answer correction | Primary rows, secant / proposal | Newton assemblies, secant / proposal | Inclusive linear solves, secant / proposal | Parents with fewer primary rows |
| --- | ---: | ---: | ---: | ---: |
| 0.50 | 46 / 45 | 132 / 130 | 78 / 75 | 1 of 20 |
| 0.90 | 46 / 44 | 132 / 128 | 78 / 75 | 2 of 20 |
| 0.99 | 46 / 38 | 132 / 116 | 78 / 68 | 8 of 20 |

The other parents tie in primary rows and assemblies. Inclusive linear solves
increase in 2, 3 and 2 parents respectively; terminal refinement is included.
Thus even an almost complete correction along the exact answer direction does
not save primary work everywhere. These artificial errors have an unusually
favorable direction: they cannot establish a universal prediction-accuracy
threshold for arbitrary model errors. Fractions describe correction recovery,
not classification accuracy or empirical model RMSE.

Recorded secant/proposal arm interval sums are 5.442426683/5.525987805 seconds
at 0.5, 5.477991514/5.430131603 at 0.9, and 5.403861504/5.124137055 at 0.99.
Proposal intervals are higher in 17, 15 and 11 individual comparisons. These
single instrumented intervals exclude the original answer-generation cost and
cannot prove learned net savings or a full-path speedup.

All 180 fresh-reference response comparisons pass the unchanged absolute 1e-10
and relative 1e-8 tolerances. All 60 reference/fresh-reference checkpoints match
exactly. There are 240 core calls, 1,112 inclusive linear solves and 2,006 Newton
assembly dispatches. Total element integrations remain unknown. The campaign
loop takes 82.078495959 seconds, excluding source staging/import and later audit.
The sixty comparisons repeat twenty parents, not sixty independent structures.

## Audit and next decision

The [receipt](rc-vector-fraction-steps-20260914.json) binds the protocol, source
archive, original input hashes, runnable experiment/auditor, original execution
log, all step/path reports and callback events. The audit reconstructs every
fraction seed, checks step/path/report hashes, actual work, parent identities,
response comparisons and exact reference repeats. All 2,642 sealed inventory
entries were reread for SHA256 and byte length without additional solves.

These observations do not justify another coordinate regressor merely because
its average error is lower. Before spending on a new fit, identify training
contexts where secant has substantial primary work to save, and assess candidate
predictions by actual work and full inference cost on those contexts. Any policy
selected from this diagnostic must later be frozen and tested on independent
geometry/load-history splits; these inspected parents cannot become hold-out
proof. Neither independent physical verification nor roadmap completion follows
from this study.
