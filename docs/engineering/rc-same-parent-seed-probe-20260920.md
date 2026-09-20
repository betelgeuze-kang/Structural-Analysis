# Matched-parent secant and learned-seed comparison

This post-hoc experiment follows the [path-cost attribution](rc-expanded-runtime-costs-20260920.md). It compares existing policies on the same retained native parents to distinguish local seed effects from differences accumulated along separate histories. It does not fit a selector, execute reserved cases, or demonstrate full-path acceleration.

## Predeclared scope

All 33 noninitial reference parents from the three middle-geometry amplitude histories were included, each with both previously fitted ridge policies. Each policy retains exactly 66 complementary training samples, excluding the complete middle-geometry family. The 66 parent/policy pairs each use three counterbalanced repetitions. Every comparison executes reference, secant, proposal and fresh reference from the same parent, without repeating preload. Material capture is charged to the proposal path; arithmetic and acceptance tolerances remain unchanged.

Initial driver revision: `c5f83e1ae1ec325cb51df2d83550e2b1c2f48f9d`. A progress-file write failed after the first two completed comparisons because the artifact writer correctly refuses overwrites. The original process exited 1 and remains preserved. The corrected driver uses one immutable receipt per repetition and binds the retained prefix to its exact inventory. Revision `9ba612f5d3c9eaf6e78f730c1ab439cd1c893513` reused those two reports and executed only the remaining 196 comparisons, then exited 0. A focused regression verifies distinct repeat receipts and rejection of overwrite attempts.

## Result

- **198 comparisons / 792 single-target paths** completed; all 198 step-response comparisons passed at the original tolerances. These are not 792 full loading histories.
- All 198 proposal decisions actually proposed a seed. All four arms in every comparison have the declared identical native-parent hash.
- Total numerical work, including the two retained reports: **792 core calls and 4,233 Newton iterations/linear solves**, with no unknown work. The resumed process makes 784 of those calls.
- The resumed driver wall time is **293.084741252 seconds**. It excludes the original failed driver's elapsed time, which is not reconstructed. Prior label generation and policy-fitting costs remain separate.
- Only **3/66 pair means** are faster. Only **one pair is faster in all three repetitions**. Seven pairs reduce Newton iterations in at least one repetition, so iteration savings alone are again insufficient.

| Case / ridge / target index | Mean proposal/secant path ratio | Three ratios | Secant → proposal Newton |
| --- | ---: | --- | --- |
| B amplitude 0.5 / 1,000,000 / 10 | 0.990832 | 0.878126, 1.067182, 1.027186 | 4 → 4 throughout |
| B amplitude 1.5 / 10,000 / 10 | 0.877490 | 0.877792, 0.874985, 0.879691 | 5 → 4 throughout |
| B amplitude 1.5 / 1,000,000 / 4 | 0.976828 | 0.882741, 1.022105, 1.025638 | 4 → 4 throughout |

The consistent local benefit is the amplitude-1.5 target at **−6 mm**, zero-based index 10: about 12.25% lower measured single-step path time in this run, including feature capture. It is one specific retained parent under one policy. The other two faster means mix one faster repetition with two slower repetitions and do not reduce Newton work. They should not be promoted as useful selection targets on this evidence.

## Consequence for learning

This experiment demonstrates one reproducible local seed benefit under the measured conditions; it does not establish a useful switching model. Training a classifier from this one favorable combination, selecting by its target index, or summing the best observed step times into a claimed oracle path speedup would overstate the evidence. A policy changes its subsequent parents and must be evaluated along its own complete history.

The next data expansion needs independent geometry/history families with both beneficial and harmful matched-parent cases, a low-cost causal gate whose feature cost is charged, and complete-path reevaluation with the established exclusion rules. The existing full-path selector continues to retain secant. No held-out, independent physical, candidate-search, or release qualification is added here.

## Receipt integrity

Auditor revision `c349c523916662ebb8d403787482423e9d5007ac` verifies all 198 immutable receipts, original report hashes, source revisions, native parents, policy identities, target indices, counterbalanced orders, capture scope, fixed tolerances, work and declared budget. The initial audit's full-history field assumption was corrected to the single-step report's `step_response_pass`; no numerical rerun was performed. All 467 source files in each execution packet were compared with both recorded hashes and their original Git blobs.

Initial packet: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-same-parent-qt7f3k_1`, 537 files / 12,039,383 bytes; inventory SHA-256 `90528a26fce7f06f6a768766120b14e0c6063e2a9aed07393a50c422a7688f13`.

Resumed packet: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-same-parent-resumed-nw_z5hvi`, 7,141 files / 299,893,139 bytes; inventory SHA-256 `6f3ef02af2107f745f8bce34ea3da725e827ad2041c28d2bd46c3935aa1ca84f`. Counts exclude interpreter caches and the inventories themselves. [Complete receipt summary](rc-same-parent-seed-probe-20260920.summary.json).
