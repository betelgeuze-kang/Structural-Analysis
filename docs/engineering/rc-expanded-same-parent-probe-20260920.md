# Expanded retained-parent diagnostic preparation

Status: prepared; numerical execution has not started.

The previous matched-parent study covered only the original B geometry family
and older complementary policies. The new diagnostic includes **all B/D/E cases**
(three amplitudes per family), both original ridge settings and every noninitial
reference parent. It does not select the favorable D-amp150 result or a favorable
target from the full-path study.

The latest retained policies come from the policy-reuse runtime packet, whose
inventory SHA-256 is
`e47a96cf34c52b3a088f15eba08a890e745da6096a7a43b5127f78df8ca2b7c0`.
Each policy's 132 training hashes must exactly match the complement of the whole
three-case group in the original 165 labels. The original labels and policies
are reused without generation, fitting or reserved-case execution.

Scope: 198 policy/parent pairs, three counterbalanced repetitions, 594 comparisons
and 2,376 planned single-target paths (reference, secant, proposal and fresh
reference). Each four-arm comparison starts at the same original native parent.
No preload is repeated. Proposal-only material capture remains charged; original
comparison and solver tolerances are retained. The existing bounded policy cache
starts empty once per process and reuses payloads across calls; each arm does not
start cold. The audit replays the exact policy order and eviction counts.

Preparation validates all 198 pairs with zero solver calls, new fits or reserved
evaluations. Thirteen focused diagnostic tests pass, including whole-group
exclusion and cache-accounting regressions; Ruff passes. Numerical execution
must wait until the running 512-layer solve finishes to avoid overlapping timing
measurements. Freeze the complete source and driver before launch and preserve
any failure; do not silently rerun completed comparisons.

These are synthetic, already inspected training families. Results can describe
local seed effects and identify whether there is enough variation to investigate
a switching policy. They cannot establish independent generalization, train a
validated selector by themselves, be summed into an oracle full-history speedup,
or replace full-path cost selection. Historical label/fit costs stay separate.
