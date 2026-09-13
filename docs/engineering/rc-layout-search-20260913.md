# Full-layout candidate search with reference costs — 2026-09-13

`compare_control_layout_search` accepts a canonical baseline and 1–16 explicit
`RCControlLayoutCandidate` models. This connects the distinct layout response
policy to actual reference candidate evaluation. The old section-change search
and its serialized schemas retain their existing contracts.

## Frozen plan and accepted results

Preflight detaches input models and rejects duplicate IDs, duplicate physical
models, overlap with training models, different topology/material/control context,
invalid budgets and incomplete historical training work. Candidate IDs cannot be
paths or replace the baseline. The original layout training report must match the
policy, retain alternating analysis/verification invocations with known work, and
have valid enclosing and component costs. New training reports retain those
invocations; old reports without this cost evidence cannot enter this search.

One common material price table supplies quantities and estimates for every pool
model. Price order and learned order are both frozen and saved before numerical
evaluation. The learned order uses the existing cheaper-boundary heuristic;
prediction and feature-bound status remain non-authoritative and uncalibrated.
Each arm's budget includes a fresh baseline. Every shortlisted model receives its
full control path and fresh verification, retaining original model/result/
checkpoint/verification and invocation artifacts. Optional terminal screens apply
to both predictions and actual results alongside complete-history/material screens.

Only verified candidates passing all requested screens can be selected. Numerical
work becoming unknown or an interruption stops before subsequent arms or the
oracle, preserving partial rows and an outcome. A separately charged complete-pool
oracle runs only after both online arms. Shared coverage and cost-optimality audits
separate missed feasible models from missed cheaper feasible models. Without the
oracle, whole-pool optimality remains unknown.

The enclosing search time includes preflight, ranking, both reference arms,
optional oracle and intermediate IO, excluding the final report write. Arm and
ranking times are components of this interval. Historical training is retained
once outside the online interval. This fixed execution order alone cannot prove
runtime advantage; matched standalone/reversed repeated runs remain necessary.

Geometry changes can change architectural function and envelope. Same material
prices and solver screens do not establish equivalent building function. Reports
therefore keep `functional_equivalence_verified=false` and do not claim real
currency savings or global design optimality.

## Focused verification

78 tests passed: 17 new layout-search tests, 22 layout-learning tests, 23 common
candidate-cost tests and 16 workflow contracts. The actual search fixture executes
seven model rows (two baseline-plus-small arms and a later three-model oracle),
with fresh full verification for every row. Both arms select the same small model;
the oracle confirms zero finite-pool estimated-cost gap. The unselected larger
feasible model is counted as missed feasible, but not as a cheaper missed choice.
Original artifact bytes, quantities, estimates and terminal screens are checked.

Control-flow-only retained-row doubles test missing-oracle accounting without
claiming new numerical evidence. Other cases cover preflight rejection, invalid
historical training phases/costs, unknown work, interruption and path-like IDs.
Ruff, focused mypy and whitespace checks passed. Development CI now selects 35
modules; local focused checks do not establish hosted full-suite completion.

## Separate exploratory budget-two observation

Committed source `218a4c052c350de4f274cb0e387975349b7bfad6` executed one new fit
from four training geometries. The fixed six-target history, four candidate
geometries, synthetic price table, strain limit 2e-6 and budget two (baseline plus
one alternative per arm) were recorded before this run. The setup was chosen
with knowledge of the earlier layout pilot; it is exploratory, not blind or
independent validation. Numerical holdout paths remained unexecuted.

| Strategy | Shortlist after baseline | Verified selected model | Declared material estimate |
| --- | --- | --- | --- |
| Price order | small | none within the budget | unavailable |
| Learned order | large | large | 289.8216 |
| Later complete-pool comparison | all four alternatives | middle | 246.34836 |

The learned arm found an admissible model within this budget, while price order
did not. It nevertheless missed the cheaper admissible `middle` model, leaving a
finite-pool estimated-cost gap of 43.47324. This is a synthetic quantity/price
comparison, not a construction quote or monetary saving. The two online outcomes
have different feasibility quality, so their small timing difference is not an
AI speedup ratio.

For `middle`, predicted peak strain was 2.133260162678327e-6 (above the declared
2e-6 screen), while the separately verified response was 1.7257126522790234e-6
(below it). The false-negative prediction delayed a cheaper feasible candidate.
The `outside` model was unpredicted due to feature bounds and remained in the
pool; the complete comparison later found it feasible. No outcome or failed
prediction was removed from the denominator.

Training including all labels and fresh verification took 13.289224020 s.
Search including both arms, ranking, complete-pool comparison and intermediate IO
took 29.938792399 s; their disjoint sum is 43.228016419 s, excluding campaign
preparation and final inventory audit. Within the search interval, price order
took 6.650750124 s, learned order 6.617442238 s, and the later complete comparison
16.630834455 s. Those component times must not be added to the enclosing interval.
There was one fit, 13 reference result rows including repeated baselines/candidates,
26 analysis/verification invocations and 156 attempted control steps. All 13 rows
passed fresh full verification; this does not mean every model passed the caller's
performance limits.

The original packet has 163 files / 22,272,327 bytes at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-layout-search-pttzyatg`.
The adjacent inventory SHA-256 is
`94cb286e2b12987d19b2e5c95db854f2de1b286bbd49f10795fd9fd96a62b2b4`.
The [machine-readable summary](rc-layout-search-20260913.summary.json) retains
predictions, plans, selected outcomes, work and cost-optimality details. Inventory
verification checks existing bytes and performs no extra numerical replay.

## Integration boundaries

The new report and plan schemas are explicitly layout-specific. They have not yet
been admitted by the portable search-artifact reader or Workbench reviewer, and
`workbench_search_review_integrated` remains false. That graph/reader/review path,
matched repeated total-cost measurements, joint project/geometry/history splits,
independent physical verification and the broader planar/material/3D requirements
remain open. This implementation adds no second solver or new acceptance tolerance.
