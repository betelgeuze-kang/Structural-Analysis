# RC direct-control failure work consumers

[Topology run 34749003181](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34749003181)
at d8b22b206 completed rather than remaining live. Its focused topology stage
passed 413 tests; later focused stages also passed. The regression-neighborhood
stage finished with 980 passes and two failed assertions in the direct-control
API test module. These were stale expectations after the failed-work counter fix.

Both failures reproduce locally on the current code. The zero-iteration-budget
case still evaluates its initial state and dispatches one increment solve before
returning blocked. The test now binds one recorded convergence row, one Newton
count and one linear solve to the API work summary, with zero unknown attempts.
Uncommitted status, exact parent/accepted rollback and physical failure remain
required. A zero iteration budget is not reported as zero performed work.

The forged-receipt test now expects replay to retain the actual one-call work
instead of zero, while rejecting the submitted counters of seventeen. Both
iteration counter fields are forged together, nested receipt hashes are rebuilt,
and the returned replay work must equal the genuine blocked source summary.
Exception paths retain their existing unknown-work semantics.

Local reproduction: 2 failed / 93 deselected. After correcting expectations,
the complete module passes 95 tests in 21.61 seconds. After additionally forging
the newton_iteration_count field, the two changed tests pass again in 2.00 seconds.
Ruff and whitespace checks pass. Original failure log, both correction checks,
final test bytes and source identities are bound in the
[receipt](rc-api-failed-work-consumers-20260913.json).

This change updates tests only. No solver, tolerance, failure status or protected
receipt changes. The previous remote failure remains a failure; a new hosted
pass and full roadmap qualification are not inferred from this local module.
