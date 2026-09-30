# A fixed schedule that checks cheaper candidates near the predicted boundary

The opt-in `feasibility_then_cheaper_boundary.v1` strategy improves finite-pool
selection in one prospectively declared, same-family observation. It selects the
verified pool minimum with three model requests, including the baseline. The
existing learned ordering still selects a more expensive candidate with six
requests. The fitted policy and its predictions are identical in both strategies.
This is a scheduling result, not improved prediction accuracy, calibrated
uncertainty, independent generalization or an end-to-end speedup claim.

## Implementation and contract

Implementation source: `387478e923a04f88bd6e0164170099899e078eec`.

`compare_rc_control_candidate_search(..., ranking_strategy=...)` and the search
CLI's `--ranking-strategy` accept the new strategy. The default remains
`feasibility_then_price.v1`, preserving its v2 plan and original ordering.
The new strategy emits a v3 plan with a hashed ranking explanation. Existing
result/cost report versions and reference-solver authority remain unchanged.

Before any online analysis, it fixes the following order:

1. The cheapest candidate predicted to pass all requested limits.
2. Strictly cheaper abstentions, ordered by price and candidate ID.
3. Other strictly cheaper candidates, ordered by maximum relative limit
   exceedance, then price and ID.
4. Remaining candidates in the original prediction-tier/price/ID order.

Without a predicted feasible seed, it keeps the original ordering. Equal-price
alternatives do not count as cheaper challengers. Every alternative remains in
the complete ordering. This is a fixed schedule: an analyzed seed that fails
its actual limits does not cause retrospective reranking or erase that failure.

For each predicted constraint, positive exceedance is `(value - limit) / value`;
a passing constraint contributes zero. The score is the maximum over requested
constraints. All inputs have already passed the original finite, nonnegative
prediction and typed-limit contracts. This arithmetic remains bounded from zero
to one, avoids division by zero, and gives one for a positive value against a
zero limit. Abstentions retain a null score. The score is a heuristic distance,
not a probability, error bar, material safety factor or verified margin.

The HTTP snapshot mount recognizes the explicit v3 plan/strategy binding while
retaining its byte-integrity/access-control role. Workbench independently
reconstructs the schedule and explanation from predictions, constraints and
prices, before accepting the original full-path results. Rehashed changes to the
seed, distance, role, strategy or uncertainty claim reject. The UI displays the
strategy and complete evaluation order. An old v2 plan cannot silently acquire
new ranking metadata. Every selected model still requires full reference
reanalysis and a fresh complete verification execution.

## Prospective same-family experiment

The [preceding observation](rc-candidate-boundary-20260910.md) is development
data used to identify the scheduling problem. The new protocol was written
before predictions or solves for this pool, and before implementing the rule.
It fixes ten alternative widths:
**0.35 / 0.37 / 0.39 / 0.41 / 0.44 / 0.45 / 0.47 / 0.49 / 0.51 / 0.53 m**.

The baseline remains 0.43 m. The fixed synthetic maximum strain limit is
0.0003302745924965656; the 600 kN preload, seven displacement targets, other
limits and synthetic prices remain unchanged. The previously trained centered
policy is reused: **zero new fits**, with its original three-label training
cost retained once. All ten original predictions are recomputed exactly during
the audit, and are identical across all six search executions.

For each budget 2, 3 and 6, the experiment first executes the original strategy
and then the new strategy. Each search contains a price-order arm and a learned
arm. The sole exhaustive oracle executes after **all twelve online arms**.
Every budget includes a separate baseline; every requested model includes a
fresh full-path verification. No candidate, limit, budget or policy is changed
after seeing this pool's predictions or responses. These are still authored
models in one familiar family, not an independent building or campaign split.

| Model budget including baseline | Price order | Existing learned order | Cheaper-boundary order |
| --- | --- | --- | --- |
| 2 | No feasible selection | 0.49 m; gap 3.6 | 0.49 m; gap 3.6 |
| 3 | No feasible selection | 0.49 m; gap 3.6 | **0.47 m; gap 0** |
| 6 | No feasible selection | 0.49 m; gap 3.6 | **0.47 m; gap 0** |

The subsequent full comparison verifies 0.47, 0.49, 0.51 and 0.53 m as feasible.
The pool minimum is 0.47 m, with a declared estimate of **157.5108**; 0.49 m is
**161.1108**. Gaps above are synthetic common-price units, not observed market
savings. Price-order executions agree across both strategies. Their absent
selection retains a null cost gap, never a zero gap.

The policy still incorrectly predicts 0.47 m to fail. The new schedule evaluates
it anyway, so it becomes the actual selected design. The recorded false-negative
count remains one: evaluating a mistaken prediction does not make that prediction
correct. At budget 3 the two more expensive feasible alternatives are unrequested,
but no cheaper feasible alternative is missed. The original reports without an
oracle retain their null whole-pool fields; a separate post-hoc audit applies the
later common oracle without modifying those original reports.

## Actual work and practical limits

The complete experiment records **55 result rows, 110 full-path invocations,
880 core calls and 2,204 Newton iterations/linear solves**. Online work accounts
for 704 core calls and the oracle for 176. All 55 original fresh full-path
verifications pass and report 440 checked response reassemblies. These counts
include repeated models and are not independent physical cases. All six CLI
processes finish without retry; their parent interval is 60.268051507 s,
excluding source-snapshot preparation.

At budget 3 the new learned arm uses 48 core calls / 122 Newton iterations;
the original learned arm uses 48 / 124. At budget 6 the new arm uses 96 / 248,
versus 96 / 234 for the original. Thus the better selection is not a universal
reduction in Newton work. Both strategies retain the same successful budget-2
seed. The original training cost is 2.761753795 s, including 48 historical label
core calls and a 0.001552685 s fit; it is not charged again as six new trainings.
Search, ranking, transport and review costs remain separate in the summary.
Single fixed-order shared-host timings do not establish net runtime savings.

The experiment observes no steel plastic accumulation or concrete damage. It
does not qualify plastic collapse, shear, bond-slip, broad material behavior or
new load-history/geometry families. A better finite-pool schedule also does not
establish global design optimality or supersede the earlier warm-start study's
selection of secant.

## Original-data and Workbench verification

The audit checks 442 frozen source/resource/dependency files against Git, 440
comparison artifact references against original bytes, logical hashes, complete
work counters, original fresh verification records, all six request/limit/budget
bindings, and the predeclared pool widths. It reconstructs ranking, cost and error
reports. The follow-up check recomputes all ten predictions from the original
model files and frozen policy. These audit steps run no new solver or fit; they
do not claim to repeat the original fresh nonlinear verification themselves.

The actual new budget-6 report is served by the authenticated immutable HTTP
mount to the built Workbench, at **1440 px and 390 px**. Both views show 0.47 m
selected and a zero finite-pool gap. Original model/result/checkpoint/verification
and plan downloads match their bytes. All **412 successful HTTP responses** are
hash/length checked; three additional requests are denied. The complete browser
observation takes 6.988313118 s and runs zero solver calls/fits. Screenshots,
original request receipts and built HTML/JS/CSS assets are retained. This verifies
a local delivery path, not deployment or external operational acceptance.

Focused checks pass: **69 Python search/cost + 34 Python HTTP tests**, **35
frontend contract tests**, and **4 existing-fixture real HTTP browser tests**.
Ruff, scoped mypy, TypeScript/build and the viewer-delivery contract pass. The new
original-data browser observation is additional to those four regression tests.

The preceding commit `16ede1587` has **362 hosted development tests passing in
328.515 s**, verified from the digest-matched JUnit artifact of run 34440016297,
tested merge `fbcc730c99c837e843c5d71bfb343707fd934423`. All four full-suite shards
fail evidence preparation and skip their actual suite execution. This hosted
result predates the new ranking source; it does not verify the new change or
satisfy full-suite/independent-verification closure.

The [machine summary](rc-cheaper-boundary-20260910.summary.json) binds the source
revision, protocol, stage costs, complete schedules, false predictions and cost
gaps. The sealed packet is
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-rc-cheaper-boundary-hnkltr1_`:
1,111 files / 36,217,440 bytes; sibling inventory SHA-256
`7c1093a24ca556df50f0bc2a9623a547ea1b1b5e030c1cf26f5c6944aaebe826`.
All retained files are reread and checked, and original numerical/browser server
processes are absent at seal. Independent physical verification, licensing,
broader splits and full roadmap closure remain open.
