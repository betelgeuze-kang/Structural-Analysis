# Repeated standalone layout costs — 2026-09-13

The frozen source at `596e058f167e8663f62e3bc3e8c6ab0bff18807a` executed
12 separate Python processes: budgets 2, 3 and 5, with price then learned and
learned then price at each budget. Every budget includes a fresh baseline row.
All processes completed. Forty reference rows, 80 analysis/verification invocations
and 480 attempted control steps were recorded; all 40 rows passed fresh full-path
verification. Passing verification does not imply passing the performance limits.

The existing four-training-layout SVD policy was reused without a new fit. This
is a fixed known geometry/history campaign, chosen after previous pilot outcomes
were available. Orders, budgets, quality rule and cost scope were frozen before
the first process; this is not a blind independent-generalization experiment.
The host was not isolated. BLAS/OMP/MKL thread counts were one and the OpenBLAS
core type was Haswell. Source archive, Python version and inputs are retained.

## Selection and total process costs

| Budget including baseline | Price selection in both orders | Learned selection in both orders | Comparison |
| --- | --- | --- | --- |
| 2 | No eligible selection | `large`, estimate 289.8216 | Unequal outcomes; no speed ratio |
| 3 | `middle`, estimate 246.34836 | `middle`, estimate 246.34836 | Matched eligible selections |
| 5 | `middle`, estimate 246.34836 | `middle`, estimate 246.34836 | Matched eligible selections |

Estimates use the same synthetic declared material prices. They do not establish
equivalent building function, a real quotation or actual monetary savings. The
small-budget result shows a feasibility advantage in this known pool, while it
does not establish minimum cost or generalization. No new separate oracle ran.
Budget 5 itself evaluates every member of the frozen five-model pool in each arm.

| Included budgets | Price process sum | Learned process sum | Historical training once | Training-inclusive learned/price |
| --- | ---: | ---: | ---: | ---: |
| 3 | 22.959843 s | 22.938580 s | 13.289224 s | 1.577877 |
| 5 | 36.222174 s | 36.846237 s | 13.289224 s | 1.384110 |
| 3 and 5 | 59.182017 s | 59.784817 s | 13.289224 s | **1.234734** |

These cohorts overlap and must not be added together. Each row represents its own
deployment accounting scenario, charging the same historical training interval
once. Across all six pairs, including budget 2, the price and learned process sums
are 75.778401 s and 76.136976 s. The overall ratio is null because two pairs have
unequal eligible-selection outcomes; no failed selection is removed silently.

For the four comparable pairs, learned online process cost was about 1.02% higher;
with historical training counted once, it was about **23.47% higher**. At budget 3,
the tiny aggregate online difference (about 0.09%) changed sign across the two
orders and is not treated as acceleration. Budget 5 was slower in both orders.
This campaign does not demonstrate learned net savings.

The parent clock encloses process launch, interpreter/imports, input loading,
preflight, ranking where applicable, reference solves, fresh verification,
artifact writes, stdout and process exit. Nested arm/ranking intervals are not
added again. Source export, preparation, post-run audit, HTTP and Workbench review
are outside this cost scope. The historical training cost is the prior recorded
interval, not a same-session retraining or a prediction of future amortization.

## Audit and retained evidence

The post-run audit checked the frozen source manifest, original policy/training
bytes, common pool/request/limits/prices, self-hashed plans/results/comparisons,
single-arm membership, budget, work availability, original quantities/estimates,
eligible winner and 320 original row artifact hashes/lengths. It verified that
each parent process interval enclosed its recorded online interval. Price-only
executions retained no policy or training artifacts and recorded no ranking work.
The audit did not run another solver or replace independent physical validation.

The packet is at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-layout-standalone-costs-y3fu39g2`:
1,406 files, 123,863,173 bytes; inventory SHA-256
`840fde16b826e61941b24e47fcd522a22b388c9b90c08b74d09540eccb5e0233`.
It retains the protocol, frozen source, original inputs, run/child/audit scripts,
all process outputs and numerical artifacts. Files were made read-only after the
inventory audit; previous packets were unchanged. Full process and comparison
records are in the [machine-readable summary](rc-layout-standalone-costs-20260913.summary.json).

## Remaining work

The evidence supports separate strategy accounting and exposes the current
feasibility/cost tradeoff. It does not close AI net benefit, independent
project/geometry/history transfer, external physical verification, functional
equivalence, standalone-layout HTTP/Workbench admission, hosted full CI, or the
broader material/3D roadmap. The current frozen source's Repository Python Tests
run `34711714292` was still pending when checked, with no completion claim.
