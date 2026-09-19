# Actual strict-cost exclusions in direct-control design comparison

`compare_rc_control_designs(..., prune_cost_dominated=True)` and the design CLI
flag `--prune-cost-dominated` now provide an explicit adaptive execution mode.
Default behavior still analyzes every requested alternative. The mode requires
one common declared price table and binds its execution policy in the original
request before any numerical work.

In authored order, every model undergoes geometry validation, quantity/estimate
calculation and original-model persistence. A candidate is excluded from numerical
execution only when its estimate is **strictly greater** than a preceding
incumbent's estimate. An incumbent must have completed original analysis and fresh
full-reference verification, passed every requested screen and recorded completed,
known-work invocations. Predictions cannot supply this authority. Equal-price
candidates are still solved so the existing candidate-ID tie rule is unchanged.
A later cheaper feasible result replaces the incumbent. Invalid geometry remains
an invalid row, not a cost exclusion.

The separate `experimental-rc-control-cost-pruned-design.v1` report preserves all
rows and the full denominator. Excluded rows have no result/checkpoint, no API
invocations, no performance/screens and false verification/selection flags.
Their model and `cost-skip.json` retain price basis, estimate and incumbent
model/result/verification hashes. Feasibility is explicitly not evaluated.
The scoped minimum is asserted only if a selected verified feasible result exists
and every other row is verified or cost-excluded; any unresolved invalid/failing
row prevents that assertion. It is a minimum of declared scoped estimates, not
construction-cost savings or engineering approval.

The completed adaptive CLI exits successfully with `complete_with_cost_exclusions`
when exclusions occurred, without equating all rows to physical verification.
No wall-time saving is asserted by this report.

## Verification and integration boundary

Initial design/search regression selection: 83 passed in 43.24 s. Final focused
adaptive/CLI/workflow checks: 25 passed in 7.58 s (overlapping selections; do not
sum as independent tests). Ruff and diff checks passed.

A real public cantilever comparison uses baseline, cheaper and costlier models.
The full and adaptive modes select the same cheaper model; baseline and selected
result hashes agree exactly. API calls fall from six to four (analysis plus fresh
verification for each evaluated model), while the declared denominator remains
three and the verified count is two. No skipped result file exists. Further
checks cover failed screens, equal prices, invalid geometry, missing prices,
unknown work and actual CLI argument/file parsing. These are internal software
and numerical contracts, not independent physical validation.

The independent development CI lane includes the new test file (60 files total).
The new schema is deliberately separate: candidate-ranking orchestration,
HTTP/Workbench adaptive-report validation and review, plus repeated elapsed-cost
comparison against exhaustive execution, still require explicit integration.
Existing viewers must not silently treat excluded models as analyzed. This is
the first actual execution-skip path, not a closure claim for the full roadmap.
