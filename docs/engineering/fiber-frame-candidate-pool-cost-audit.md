# Fiber-frame candidate-pool cost audit helper

`audit_fiber_frame_candidate_pool_cost(report)` in
`src/structural_analysis/benchmark/fiber_frame_candidate_cost.py` reads an
already validated fiber-frame candidate comparison report (v2–v5). It returns
a separate audit value without editing the report or running the solver. The
existing comparison, suite, process, fixture, and Workbench schemas are
unchanged; no producer currently exports this value.

The helper verifies the comparison report's canonical `report_hash` before
reading its cost claims. Its output records that hash as `source_report_hash`
so a later consumer can bind the sidecar to the exact source report. This hash
is an integrity check, not a provenance attestation or solver replay.

The audit uses the later full-pool oracle, including the baseline, to find the
lowest feasible scoped material estimate. Feasibility requires successful
reference verification and known pass/fail outcomes for every requested
terminal, committed-history, and material-history screen. Every oracle row
must be resolved before a pool minimum is stated. No oracle or any unknown
row, even one whose preanalysis estimate is high, leaves the minimum, selected
gap, and cheaper-feasible counts `null`. A known failed limit is infeasible,
not an unknown result. A missing or oracle-contradicted online selection also
has no certified gap.

The helper reconstructs the declared price-table hash from its actual price
values and requires one hash, currency, and quantity scope across available
baseline, candidate, and oracle estimates. It rejects conflicting estimates
for the same candidate. A mismatch is invalid input, not an unavailable cost
result. The selected gap is the online selected estimate minus the verified
finite-pool minimum. Cheaper means strictly lower; ties count as matching the
minimum. The baseline participates in the minimum but cannot appear in a
missed-alternative list.

Each arm has two cheaper-feasible lists. `missed_cheaper_feasible_candidate_ids`
covers alternatives outside its frozen planned shortlist.
`unrequested_cheaper_feasible_candidate_ids` covers alternatives outside its
actually attempted prefix, which can differ under `first_verified_feasible`
stopping. Both lists require a confirmed online selection and complete oracle.
This audit is a finite-pool comparison under declared material prices, not a
global design optimum, independent physical validation, construction quote,
or confirmed currency savings.
