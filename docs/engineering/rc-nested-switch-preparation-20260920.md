# Nested group provenance for switching-label preparation

Ten seed policies are fitted and audited using exact 99-sample complements.
There are **no switching labels, trained gates, new structural solves or reserved
evaluations** yet. This is preparation for a leakage-resistant development study,
not evidence of full-path acceleration or independent generalization.

The completed B/D/E probe excluded the label case's whole group when fitting each
seed policy. That is appropriate to its original same-parent diagnostic. For a
new outer-group evaluation of a switching rule, the policies used to create the
rule's training labels must also exclude the outer evaluation group. Otherwise,
its training labels indirectly depend on the group it purports to exclude.

The new planner starts from the existing connected project/geometry/history
groups and the source-validated 165 labels. For every outer group and different
inner label group, seed fitting uses only the other three groups: 99 samples.
Overlapping groups, duplicate sample hashes, reserved samples and incomplete
case rosters are rejected. Group/sample order does not change the plan.

| Preparation item | Completed or planned count |
| --- | ---: |
| Original connected training groups | 5 |
| Original training samples | 165 |
| Directed outer/inner label tasks | 20 planned |
| Unique two-group-complement seed fits | 10 completed |
| Samples per seed fit | 99 |
| Retained parent/seed pairs | 660 planned |
| Counterbalanced comparisons | 1,980 planned |
| Single-target paths | 7,920 planned |
| Switching labels / trained gates | 0 / 0 |

Identical two-group complements share a fit across the two directed tasks.
Future cost reporting must charge those ten fits once and retain all label
construction costs; reuse is not a reason to hide preparation cost. Ridge 10,000
is fixed from the prior development diagnostics, so this preparation does not
claim independent hyperparameter selection. An untouched evaluation remains
necessary. No existing favorable target or case is promoted into a rule.

## Actual fitting and rejection checks

Source: `cdd78f326de82253877f2250d811a42aae22da17`.
All ten SVD fits complete in a combined **0.213587213 s**. The seed-stage interval
through the result write starts at source verification and includes input
preparation and old-policy rejection checks: **1.446685703 s**, excluding later
normalization audit/inventory. No structural solve runs.

For all twenty directed tasks, the old single-exclusion policy contains all
**33 samples from the newly designated outer group**. The new exact-complement
validator rejects every such reuse. This does not invalidate the old diagnostic;
it prevents reusing its policies under a stronger nested-evaluation claim.

The fitted policies' training hashes, feature means/minima/maxima and both
feature/target standard-deviation scales are verified against the declared
99-sample subsets. Every zero scale uses the original unit-scale convention.
No fit is rerun for this separate audit. The focused diagnostic suite passes
26 tests, including an old 132-sample policy rejected by the new 99-sample rule,
ambiguous groups, duplicate labels, reserved labels and missing cases. Ruff passes.

All **966 payload files / 19,300,076 bytes** are hash/length verified in
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-nested-switch-9o6ul5ja`.
Inventory SHA-256:
`547112b912e6ff77fc43e755daa8ce12467d7a72766ec2ada3875e4c40263c49`.
The immutable pre-fit plan's zero-execution fields describe preparation time;
`seed-stage-result.json` and the fit receipts record the subsequent ten fits.
[Machine-readable summary](rc-nested-switch-preparation-20260920.summary.json)
preserves fit costs, source hashes, normalization checks and all twenty rejected
old-policy uses.

## Implementation required before useful switching

The current runtime captures committed material state before invoking the
proposal callback. A cheap switch must be able to decide before that capture,
otherwise declining a learned seed still pays the capture cost. Add a timed,
explicit pre-capture decision that preserves default behavior, solver validation,
known work and the declared secant fallback. Charge both accepted and declined
selection decisions. Only then evaluate a trained switch on its own complete
paths; do not combine best retained-parent times into an oracle speedup.
