# Envelope-admission campaign: audited results — 2026-09-13

The frozen manual envelope rule did **not** establish learned net benefit.
All nine scheduled comparisons completed and their original records were
reconstructed successfully. The tuning case was slower despite one fewer Newton
iteration per proposal path; validation used more iterations and was slower.
Holdout rejected the learned policy at the static model gate and used fallback
throughout. The default secant policy remains unchanged; no policy was promoted.

## Scope and results

Numerical source: `c72ff7b0012d1c4a4287bde82ec1a51dbc876fb2`.
The original train-b diagnostic informed the manual rule, so train-b is a tuning
case. Validation and holdout are authored cases with declared split identities,
not blind external experiments or authenticated independent projects. Three
counterbalanced orders per case retain all 242 original targets and execute
reference, secant, proposal, and a fresh reference. Repetitions are not additional
independent physical cases; the host was not isolated.

The proposal callback consults the existing learned policy only when the next
absolute control target exceeds the complete accepted prefix's absolute maximum.
Existing static model and policy guards still apply, and final acceptance remains
with the reference solver. This experiment changes admission, not fitted weights.

| Case | Mean proposal/secant path ratio | Observed range | Newton iterations, secant → proposal per path | Proposed targets across 3 runs |
| --- | ---: | ---: | ---: | ---: |
| train-b, tuning | 1.02451604235 | 1.022057–1.026213 | 870 → 869 | 147 / 726 |
| validation | 1.07000310247 | 1.068288–1.070989 | 912 → 992 | 147 / 726 |
| holdout, static rejection | 1.00397094520 | 0.998496–1.012845 | 790 → 790 | 0 / 726 |

The iteration counts were identical across the three orders within each case.
Ratios include proposal setup and whole online paths: input capture, inference,
numerical attempts, recovery and step I/O; the final path-file write is excluded.
Historical data generation/training and the post-run audit are not charged in
these online ratios. A slightly faster single holdout order is not learned
acceleration: no learned proposal was used there. Different policies and
tuning/evaluation roles are not pooled into a single performance score.

Train-b uses a withheld SVD fit at ridge `10000`; validation and holdout reuse the
original integrated SVD fit at ridge `1e-6`. The latter is not the later
nested-selection refit. See [policy identities and historical costs](rc-envelope-historical-costs-20260913.md).

## Original-record reconstruction

The audit checked all 638 frozen source-manifest files against Git, original
inputs and policy compositions, accepted-prefix contexts, gate decisions,
proposal/fallback vectors, self-hashed invocation records, rollback and acceptance
contracts, material snapshots, full histories and timing/work summaries.

- Nine comparisons / 36 complete paths, with 27 full-history comparisons passing
  and nine exact reference/fresh-reference repeats.
- 8,712 core calls and 36,615 Newton iterations / linear solves; no unknown work.
- 8,712 same-solver assembly/response reconstructions, 731,808 associated material
  integrations, 36 terminal checkpoint reopens and 1,452 material snapshots.
- 2,178 proposal decisions reconstructed. Envelope permission occurred 516 times;
  only 300 calls passed the static model gate and consulted the policy. The policy
  produced 294 proposals. Permission, consultation and proposal are distinct.
- The numerical campaign generated no new labels or fits. The audit performed no
  Newton solves or fits. Same-solver reconstruction is not independent physical
  validation, measured-test agreement or design authority.

## Costs, including the preserved failure

| Non-overlapping parent interval | Seconds |
| --- | ---: |
| Original numerical parent, failed after first completed slot | 269.484319911 |
| Continuation, remaining eight slots | 2,106.268096198 |
| Post-run audit parent | 1,217.231818576 |
| Sum of these three intervals | 3,592.984234685 |

The first completed slot was retained, not rerun or counted twice. The audit's
internal 1,215.800404332 s is inside its parent and is not added again. Sealing
took a separate 3.643975561 s. Historical training generation, earlier research,
finalization work outside sealing and remote CI are outside this sum. A complete
research-lifecycle total remains unknown. Shared historical generation records
1,045.632468841 s of reference/secant/fresh-reference paths and must be retained
without multiplying it by policy count or repetition count.

An accounting bound from the three audited train-b runs and validation's first
run removes **all** material-capture time, including captures needed by real
proposals, while leaving other intervals fixed. Even that optimistic subtraction
leaves ratios above one. It is not a measured optimized implementation, and does
not predict timing interactions; it shows why capture overhead alone cannot
explain away the observed deficit. Validation's first proposal path also spent
2.621558360 s more in numerical work. No further timing campaign was launched.

## Preservation and CI boundary

The original failed packet remains preserved as described in the
[continuation record](rc-envelope-continuation-20260913.md). The completed
continuation, audit and audit parent are now read-only, with verified inventories:

| Packet suffix under the retained experiment volume | Files | Bytes | Inventory SHA-256 |
| --- | ---: | ---: | --- |
| `structural-rc-envelope-resume-f0nrbjdg` | 47,453 | 2,679,121,607 | `114b540066af399cc6588af8a40df0c75a25edb7b1720f27196835cc26bf73da` |
| `structural-rc-envelope-audit-cqsa_xrd` | 42 | 504,728 | `ad73bc202b7a8d898da377ca0dfb6d217a250428c3fa264c186dc77921896e26` |
| `structural-rc-envelope-audit-parent-10guf078` | 6 | 26,085 | `429d31e95b0f17ce4b39b0e796f1bef5f8043febe163c41d6ce52bd85e22cd98` |

The [machine-readable result](rc-envelope-results-20260913.summary.json) gives
absolute packet paths, cost scopes, support bindings and explicit unproved claims.
The audit packet retains reconstruction/finalization scripts, historical-cost
provenance, preliminary records marked as such, CI diagnostic ZIPs and JUnit data.

For development head `e9241dd5801144bc1690e9f26ca6fb47c5292e23`, hosted Python
[run 34714939922](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34714939922)
tested PR merge checkout `d5b19e0b759dcbf7ffab85ebc1b599170515cede`.
The selected development contracts passed **777 tests, zero failures/errors/skips**
in 905.66 s. Collection passed. All four full-suite shards failed evidence
materialization and skipped their repository tests; the aggregate failed.
Frontend runs 34714939945 and 34714936994 and Issue State Current 34714940028
completed successfully. These are scoped results for that head, not blanket
qualification of a later commit or the full repository.

The inspected shard-3 diagnostic identifies two failing horizontal-reaction
comparisons against reused OpenSees values: member-feature absolute error
`4.96424095305589e-7 N` and prescribed-settlement error `3.631256504377234e-7 N`.
The receipt explicitly reports no fresh external-runtime execution. Preparation
stopped at internal due diligence after the product replay failed. Other shards
are confirmed to fail the same preparation step; their detailed root causes were
not separately asserted. No tolerance or readiness gate was relaxed.

This campaign closes its scheduled execution and original-record audit. Learned
net benefit, independent project/physical validation, full repository integration
and the overall roadmap remain unclosed.
