# Actual layout cost pruning — 2026-09-13

The standalone `run_control_layout_cost_pruned_strategy()` now uses a verified
incumbent to omit strictly more expensive candidates from actual reference
execution. Each decision is written before the relevant solver call, and binds
the frozen plan and previously evaluated rows. Cheaper and equal-cost candidates
remain eligible for execution. Skipped candidates retain their original model,
quantities, price estimate and decision record; physical feasibility stays unknown.

This extends the [earlier cost-bound primitive](rc-layout-cost-dominance-20260913.md).
The old comparison and standalone entry points preserve their existing contracts.
The new result, plan and comparison use separate cost-pruned schemas. The runner
does not expand the frozen shortlist when it saves an evaluation. Its budget is
the consideration horizon including the baseline; unused analysis capacity is
not reallocated. Full coverage and exhaustive cost-optimality audits remain null.
This is a cost scheduling rule, not a learned model or full multi-fidelity closure.

## Matched actual executions

All four child processes used frozen source
`d11248ce06627c8466ae348a88f91a3b167ce05e`. The order was fixed before execution:
full then pruned, followed by pruned then full. Each used the same five-model
pool, six-target reversing history, limits and synthetic declared price table
from the sealed [standalone HTTP packet](rc-layout-standalone-http-20260913.md).
Each child started from fresh state, with BLAS/OMP/MKL threads set to one and
OpenBLAS core type Haswell. The host was not isolated. These are repeated orders
of one previously known authored geometry/history family, not independent cases.

| Order | Full process | Pruned process | Pruned / full |
| --- | ---: | ---: | ---: |
| Full → pruned | 18.469023880 s | 12.049219819 s | 0.652402 |
| Pruned → full | 18.810235327 s | 11.752732547 s | 0.624805 |
| Sum of matched child intervals | 37.279259207 s | 23.801952366 s | 0.638477 |

Every execution selected `middle`, declared material estimate 246.34836 in the
synthetic KRW price table (original JSON retains 246.34835999999999). Baseline and
small fail the requested strain limit. After middle passes actual analysis and
fresh complete-path verification, large and outside are skipped as more expensive.
This does not label them physically infeasible. Both full executions also calculate
them. The common candidates' complete response histories, requests, terminal
responses and checkpoint hashes match exactly across repeated executions.

| Per execution | Full | Pruned |
| --- | ---: | ---: |
| Actual reference model rows | 5 | 3 |
| Analysis + fresh verification API invocations | 10 | 6 |
| Target steps including verification | 60 | 36 |
| Newton iterations / linear solves | 120 / 120 | 72 / 72 |

The four executions total 16 rows, 32 invocations, 192 target steps and 384 Newton
iterations/linear solves. Every calculated row passed its fresh reference
verification; selection additionally requires the requested limits. No policy,
fit, training labels or separate oracle was used. The measured 36.15% reduction
in summed child process time is a local deterministic scheduling observation.
It is not evidence of learned benefit, independent generalization, commercial
savings, functional equivalence or global optimality outside this candidate pool.

## Verification, accounting and retained evidence

The implementation passed Ruff and focused mypy. The regression run passed 124
tests across layout execution, cost dominance, cost optimality, HTTP and workflow
contracts. A subsequent focused run passed three strengthened/new conditions:
forged eligibility cannot override failed limits or failed verification, and
learned ordering continues to a cheaper candidate after skipping an expensive one.
Those tests overlap the earlier scope and are not an additional disjoint suite.
Real-reference tests also check original decision publication before calls,
preservation of skipped pool models, unknown-work termination, fixed horizons
and rejection of entry-point overrides. Learned-order scheduling doubles do not
constitute evidence of a trained model's benefit.

The observation audit checked 639 frozen source files against Git, seven original
input bindings, all plan/report hashes, 128 row artifact hashes/lengths, quantities
recomputed from models and estimates recomputed under the common prices. It
recomputed every one of the ten pruning decisions from preceding original rows,
verified fresh-verification result/work bindings, recomputed performance and
limit outcomes, and checked 11 repeated physical response records exactly. It
performed no extra solver calls or Newton iterations. This is original-record
verification, not another independent physical validation or numerical replay.

Child times include startup through exit, including preparation, decisions,
analysis, fresh verification and result writes. The complete numerical driver
interval is 61.081729207 s; it contains the four child intervals, so these times
must not be added together. The successful audit interval is 2.338104552 s and
sealing took 0.240571339 s, separately. A first audit stopped on an exact comparison
to a rounded decimal cost. Its source and failure record are retained; the audit
was corrected to compare original exact estimates, without numerical re-execution.
The first audit's elapsed time is unknown. Initial source/input preparation,
historical research, test costs, HTTP/UI, publication and other orchestration
costs are outside the child intervals. No complete research-lifetime cost is claimed.

Read-only packet:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-layout-cost-pruned-pntrrwsy`.
It contains 874 files / 130,645,732 bytes, inventory SHA-256
`2d3ae9245605e9df04c8c4b79a603ace82b8344a0c18abbf4d2c346c66e9970b`.
The launcher, frozen source, protocol, original inputs, execution records,
decision traces, audit and failed audit attempt are preserved there.
See the [machine-readable summary](rc-layout-cost-pruned-execution-20260913.summary.json).

At the numerical observation's source, HTTP artifact admission and Workbench
support remained open. Subsequent [HTTP admission and actual delivery](rc-layout-cost-pruned-http-20260913.md)
now preserve and check the new original graphs; Workbench support remains open.
The [envelope experiment](rc-envelope-results-20260913.md) still provides negative
learned warm-start evidence. This change does not resolve current-head full-suite
materialization, independent external validation, broader physical models or
roadmap closure. No merge, release or deployment is represented by these results.
