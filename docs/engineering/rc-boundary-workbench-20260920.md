# Actual false-pass prediction reviewed in Workbench

The w44/10 mm case from the [boundary observation](rc-reinforcement-boundary-20260920.md)
is now a reproducible original-byte Workbench fixture. Its learned `middle`
prediction passes the 0.0007 strain screen, while its full reference value
0.0007000920865862819 fails. The numerical path and fresh verification complete;
that does not make the candidate eligible under the requested limits.

The fixture exporter pins the original packet inventory from the committed
observation summary, verifies every graph file's SHA-256/length, mounts the graph
through the authenticated read-only HTTP handler, and checks returned bytes.
It includes 91 artifacts, 1,087,473 compressed bytes; fixture SHA-256 is
`5494abba37ccdb35b63c92925f8be78bf4379b69301259d49cb87fdc1bd3d9c1`.
Numerical source remains `baaf0c0a6cfacb0b57b985edea27e96e8afad618`.
The exporter performs no solve, fit, source mutation or external deployment.

Workbench's existing verifier accepts this original graph and recomputes one
false-safe prediction, the actual failing screen and zero candidate-pool cost
regret for the selected `cheap`. Browser checks at 1440 and 390 px show predicted
pass beside verified limit failure, disable `Select middle`, allow selection of
`cheap`, and download the rejected middle candidate's original numerical result
byte exactly for inspection. Download availability does not grant selection.

Initial mobile inspection showed that the detailed failing status was off to the
right in the horizontally scrolling metric table. The panel now prints each
exceeded caller limit above the table with the metric, full-precision value and
limit, wrapping within the viewport. The candidate row explicitly distinguishes
`Analysis verified; requested limits failed`. Passing candidates, cost-excluded
unknown candidates and numerical execution failures keep their distinct meanings.
No acceptance threshold or underlying verdict was changed.

Final boundary/reinforcement/cost-exclusion checks: 14 passed in 21.8 s. TypeScript,
Ruff and diff checks passed. Browser routing uses synthetic credentials and exact
original fixture bytes; the HTTP handler check is in process. This validates
consumer behavior and mobile presentation, not network deployment, independent
physical accuracy, code compliance or an AI speedup.

The existing RC design browser suite also passed 13 tests in 50.7 s, covering
selection, original downloads, strict/unpriced cases, corruption, worker retirement,
credential-origin checks and deliberately delayed validation.

## Hosted confirmation at 60df039db

Frontend Web CI run
[35473078294](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/35473078294)
completed successfully for source `60df039db50ce767e778798f8ba0ae0464eb314a`.
The main frontend selection passed **738 tests in 10.9 min**. Job 105977497147's
log explicitly includes the actual boundary prediction check and unselectable
false-pass candidate at both 1440 px and 390 px. This supplies hosted confirmation
of the previously local boundary-fixture integration. It does not rerun the
source numerical campaign or confer physical/design approval.

Workflow Contract and P0 also passed at this source. The full Python shards still
stop at external replay/technical receipt preparation. Python development tests
were still running when this frontend receipt was recorded. Later local concrete
refinement commits are not covered by this hosted source.

The subsequent terminal Python receipt for the same `60df039db` source passed
**1,596 development tests in 1,368.34 s**, job 105977523578 of run 35473086713.
All four full-suite shards failed at evidence materialization, so the aggregate
remains failed. All five workflows at this source were terminal before publishing
the later refinement/probe changes; no active validation was cancelled.
