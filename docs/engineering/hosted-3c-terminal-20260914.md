# Published 3c759fc43 terminal CI observations

All 27 workflow records returned for source
`3c759fc430f4a90e51bec2bdf42305a0d466032e` were completed before the next push.
The retained original logs confirm:

- Topology job 103793726997: 413 focused tests in 693.98 s, branch stages
  22/86/9/28/16/13/65, and 984 regression tests in 627.84 s. These selections
  overlap and must not be counted as independent physical validations.
- Runtime frontend job 103793727556: 706 guarded browser tests in 11.7 minutes
  and 36 actual HTTP integration tests in 3.7 minutes.
- Development job 103793727124: 1 failed / 1,236 passed; workflow-contract job
  103793727167: 1 failed / 164 passed. Both fail the obsolete 45-file selection
  assertion. Its local repair passed the exact 165-test workflow selection.
- Full repository shards failed preparation before actual repository test
  execution. Completed collection is not a completed full suite.

Later local material-active experiments, numerical diagnoses, paired-cost reasons,
selection-count repair and late material-summary invalidation are not covered by
these older passing hosted tests. No running job was cancelled or restarted.
Independent physical acceptance, learned advantage, main integration and signed
owner acceptance remain open.

Packet: `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-3c-terminal-3q2b4cjs`.
Inventory SHA-256: `5021b790a943b86a73d4018f414c7d94e9780362a607edd9d37025dac5ad66de`.
