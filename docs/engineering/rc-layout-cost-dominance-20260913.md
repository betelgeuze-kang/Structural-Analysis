# Verified-incumbent cost bound — 2026-09-13

`layout_cost_dominance(plan, rows)` identifies unevaluated layout candidates whose
declared material cost is strictly greater than an already verified incumbent.
It retains cheaper and equal-cost candidates. An expensive candidate is not
labelled physically infeasible: its feasibility remains unknown.

The function validates the frozen plan hash, pool uniqueness, model/quantity
bindings and one common currency, scope and price table. An incumbent must have
full-reference verification, every requested limit passing, selection eligibility,
and both original analysis/verification invocation records with known positive
step work. Missing or mismatched bindings are rejected. Predictions and incomplete
rows cannot establish an incumbent. The returned bound includes hashes of the
plan and evaluated rows; callers still must verify the underlying original
reference artifacts. It is not an artifact authenticator or solver acceptance gate.

At this observation's source, this is a cost-only scheduling primitive. It does not yet skip execution in the
layout runner, alter its frozen shortlists, or change HTTP/Workbench schemas.
Those integrations require explicit actual-execution records and retention of
the unevaluated candidates. The existing exhaustive cost-optimality audit remains
unchanged and continues to require its full comparison. This primitive alone
does not close the roadmap's multi-fidelity exploration requirement.

Subsequent [actual standalone execution](rc-layout-cost-pruned-execution-20260913.md)
now records performed skips and matched process costs under separate schemas.
The historical simulation below remains a post-hoc observation.

## Verification and retained-record observation

The final source passed Ruff, focused mypy, and **59 tests** across the new bound,
existing cost-optimality audit and Python workflow contract. Tests cover real
reference fixture rows, cheaper/tied candidates, no incumbent, failed limits,
incomplete/unknown/zero work, invalid prices, mixed price identities, duplicate
rows and mismatched/missing model bindings. The development-contract CI selection
now includes the new test module (37 selected modules); this is configuration,
not a claim that the new head's hosted run has passed.

A read-only scheduling simulation used two preserved budget-5 price-order
executions from the standalone layout experiment. Original plan/comparison bytes
were checked against the previously sealed HTTP packet inventory. Both simulations
retained baseline, small and middle, identified large and outside as cost-dominated,
and kept the original selected candidate `middle`. Each original execution had
five rows; the retained three rows account for six API invocations / 36 steps,
and the two dominated rows account for four invocations / 24 steps including
verification. These are historical work counts, not actually skipped work or a
measured speedup. The observer performed no new fits or Newton solves; fixture
tests generated their own separate numerical evidence.

The final helper reproduced every earlier observation bound exactly. The initial
observation remains retained as preliminary. The final packet is read-only at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-layout-cost-bound-final-m9pxh20i`:
3 files, 25,178 bytes, inventory SHA-256
`d55aa474578e62c5c9ef25718488e0a4264eeb148c024f752e6b47e6ed84d4c8`.
It retains the helper source, recheck driver and complete decision traces.
See the [machine-readable observation](rc-layout-cost-dominance-20260913.summary.json).

This supports fewer unnecessary reference evaluations without substituting a
surrogate for acceptance. It does not prove functional equivalence, independent
generalization, global optimality, actual runtime savings, or commercial cost
savings. [The completed envelope experiment](rc-envelope-results-20260913.md)
continues to provide negative evidence for the learned warm-start's net benefit.
