# Verified cost exclusions through search and Workbench

The explicit `--prune-cost-dominated` option now reaches both candidate-search
CLIs, online design comparisons, the read-only authenticated artifact mount and
Workbench. The frozen plan binds `design_execution_policy`; paired cost accounting
rejects differing execution policies. Defaults remain exhaustive within each
shortlist. The optional exhaustive oracle always evaluates every pool model,
including models excluded online.

`request_count` preserves the declared shortlist plus baseline denominator.
`actual_model_execution_count`, `cost_excluded_candidate_ids` and invocation/work
counts distinguish execution from requests. Skipped candidates consume their
original shortlist slot; this change does not refill the budget or adapt ranking.
The scoped minimum proof applies to the declared design comparison, not unseen
candidates or the entire design space.

Workbench verifies each earlier incumbent's original result, fresh verification,
screens, quantities and price basis before accepting a strict-cost skip receipt.
It checks the receipt's exact incumbent/model/result/verification identities,
unknown feasibility and zero solver invocations. Excluded rows cannot be selected,
have no result download and show unavailable physical metrics. Original skip
receipts are downloadable. Hash-consistent tampering with incumbent, price basis,
feasibility or invocation count is rejected. The HTTP mount enforces original
byte/reference and execution-count bindings; it does not independently rerun physics.

## Actual fixture and checks

`python3 scripts/build_reinforcement_search_workbench_fixture.py --cost-pruned`
ran real training, paired search, exhaustive oracle and standalone learned search.
The saved fixture contains 79 original artifacts (396,172 gzip bytes). Numerical
source declaration is `22815ebe3ce0aa89d0a9d83fa262c7075fc01e60` plus this uncommitted
delivery integration at generation time; this is an internal fixture, not an
exact-commit qualification receipt.

In both arms, baseline and `cheaper` were analyzed and freshly verified; `middle`
was cost-excluded. Declared request count is three, executed models two and API
invocations four. Both selected `cheaper` at synthetic scoped estimate 185.04.
The separate oracle verifies all four pool models. This demonstrates invocation
reduction, not repeated elapsed-time savings or AI benefit.

- Initial focused Python regression: 97 passed in 15.55 s.
- HTTP regression after adding four adaptive mount cases: 50 passed in 1.75 s
  (overlaps the initial selection; do not add these counts).
- Search contracts and desktop/mobile browser review: 64 passed in 18.1 s.
- Actual 390 px and 1440 px reviews check disabled selection, unavailable metrics,
  absent result download and byte-exact skip-receipt downloads.
- TypeScript, Ruff and diff checks passed.

The next numerical measurement remains repeated full-versus-pruned execution,
with balanced order, failures retained and process/storage costs included.
Learned benefit remains unproved; the earlier four-case learned/price experiment
remains negative and unchanged.
