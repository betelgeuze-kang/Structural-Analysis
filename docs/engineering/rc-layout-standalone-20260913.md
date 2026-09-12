# Standalone full-layout strategy execution — 2026-09-13

`run_control_layout_strategy(..., strategy="price_order" | "learned_order")`
executes one frozen schedule through the same full-reference row runner used by
the existing two-arm layout comparison. The baseline consumes one budget slot.
The public two-arm comparison remains available with its optional later oracle.

Price-only execution rejects policy and historical-training inputs and never
calls policy prediction or training-cost validation. It still performs the common
model snapshot, fixed-context, geometry descriptor, quantity and price checks.
Learned execution validates and records its frozen policy and historical training
cost outside the online interval; it does not refit. Both strategies publish the
plan before analysis and retain original model, result, checkpoint, verification,
invocation, price and outcome records. Unknown work and interruptions retain the
existing failure receipts rather than producing successful final reports.

Standalone result and plan schemas are explicitly
`experimental-rc-control-layout-strategy.v1` and
`experimental-rc-control-layout-strategy-plan.v1`. An oracle is rejected for a
standalone execution. Without a separate complete-pool reference, optimality stays
unknown; the price strategy has no prediction coverage audit. Its policy/training
hashes and training cost are null, and recorded ranking time is zero.

The outer recorded interval includes preparation, ranking where applicable,
reference analysis, fresh verification and intermediate artifact I/O. It excludes
the final result write, process startup/exit and browser review. Historical
training must be counted once when assembling a matched cohort. Nested arm and
ranking times must not be added again to that outer interval.

Focused tests execute both standalone schedules using actual reference paths,
check a single plan is frozen before the first numerical call, verify original
artifact hashes and selections, and make learned calls fatal in the price test.
Boundary tests reject learned artifacts on the price path, missing learned policy,
unsupported strategy and standalone oracle before creating output. Existing
two-arm and HTTP tests cover compatibility of the original search schema.

The focused run passed 57 tests across layout search, layout HTTP admission and
the repository Python workflow contract. Ruff and the focused mypy check passed.
These local tests are not a completed hosted full-suite run.

This is execution support, not a repeated timing campaign. The standalone layout
schemas are not yet admitted by the HTTP/Workbench readers or existing section
strategy cost-cohort comparator. No speed ratio, learned net benefit, independent
generalization, physical equivalence, external validation or release qualification
is claimed. Matched independent-process measurements and explicit downstream
schema support remain separate work.
