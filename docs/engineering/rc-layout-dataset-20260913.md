# Train-only fixed-history layout preparation — 2026-09-13

Source `c2a824af848d27c2b9b6640b701c5cf8ca43c486` adds `prepare_control_layout_dataset` for the
separate fixed-topology layout descriptor. It prepares inputs/statistics only;
there are no response labels, fitted candidate policies or accepted physical results.

## Contract and scope

The function takes a bounded tuple of 4–32 existing immutable
`RCControlLearningCase` objects. It requires at least two training cases in two
distinct geometry groups, plus validation and holdout cases. All cases must share
the descriptor's fixed topology/material/request context and one honestly declared
fixed-history label. External measured sources require a separate admission
contract and are not accepted here.

Physical model duplicates reject even within a split. Cross-split overlap in
project labels, geometry-family labels or conservative normalized geometry rejects.
The geometry comparator is shared with the existing warm-start split screen; its
1e-10 relative / 1e-12 absolute comparison tolerances are unchanged and apply only
to split grouping. Connected shape groups are retained in the report. Caller project
labels are screened for overlap but are not authenticated project provenance.

Cases are sorted before computing mean, population standard deviation and feature
bounds using **training rows only**. Constant training columns use scale 1 and are
marked explicitly. Weighting is one row per case; geometry group counts remain
visible. Each case lists features outside the training min/max, without using
validation/holdout rows to enlarge those bounds. The resulting report is hash-bound.

This contract is explicitly geometry/project-group separation **under one fixed
history**. It declares `independent_load_history_split=false`,
`joint_geometry_history_split=false` and `project_provenance_authenticated=false`.
The existing joint warm-start split validator still rejects the shared history in
this roster. Its gate was not weakened or replaced.

## Verification

54 tests passed: 10 dataset tests, 10 descriptor tests, 18 existing split tests and
16 workflow-contract tests. Ruff, focused mypy and whitespace checks passed. The
independent development CI list now contains 32 modules. Tests prove that changing
holdout geometry leaves preprocessing unchanged, input permutation preserves the
report, and scaled aliases, duplicate models/cases, shared projects/families,
misdeclared histories and incomplete splits reject. Scaled training aliases cannot
supply the required two distinct geometry groups.

A controlled four-case example produced 2 train / 1 validation / 1 holdout rows and
four geometry groups. Of 163 feature columns, 156 were constant in its two training
rows. The validation row stayed inside all training feature bounds; the holdout row
exceeded seven geometry-related bounds. This small fixture demonstrates the data
contract and its diagnostics, not a sufficient training set or an independently
preregistered research holdout. New response-policy fits and numerical solves: zero.

The initial standalone observer invocation could not import the test helper because
only `src` was on PYTHONPATH. It failed before constructing cases. The successful
reproduction uses `PYTHONPATH=.:src python3 observe.py`; source contracts were not
changed for that environment correction.

## Evidence and next step

Packet `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-layout-dataset-7eplwl7u` contains 11 files / 78,625 bytes and sibling
inventory SHA-256 `5604ef23457dc9b99c83ac333641211baa3529a848979682f8c893adcd4f3aef`. It preserves the four input models,
requests, full dataset/statistics, observer, source delta and test logs. Dataset hash:
`sha256:d4e8f32f4dcd1d46b8da3b287f2f932ed43a7c16df914fd97510686a462be30e`. Previous sealed packets remain unchanged.

Next work must generate full-reference labels from an explicitly chosen training
roster, fit a separately versioned layout policy with these training-only statistics,
and evaluate unseen shape groups while retaining OOD abstention and total costs.
Joint history transfer remains outside this feature profile. Existing old-policy
weights, Workbench result authority, independent physical qualification, full hosted
CI, licensing, owner/administrator and hardware dependencies remain unchanged.
