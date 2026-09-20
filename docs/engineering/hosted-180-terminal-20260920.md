# Hosted outcomes for 1804038c0

Exact source: `1804038c0614109f1775f8acc715b1e0d3f0e2a9`.
These outcomes cover independent outer centroid geometry and its Workbench
fixture, not subsequent evaluation-deferral or research commits.

- Repository Python run **35476651937**: collection passed; development job
  **105986931095** passed **1,667 tests in 1,450.40 s**.
- Frontend run **35476642369**, frontend job **105986905095**: **755 tests passed
  in 17.7 minutes**; required aggregate job **105989061338** passed.
- Workflow Contract **35476642310** and P0 Canonical **35476642352** passed.
- Ordinary CI **35476642324** failed. All four full Python shards failed during
  `Materialize exact current-source test evidence`, before repository tests ran.
  Inspected shard-0 job **105986931285** retains
  `external_code_to_code_product_replay_not_passed` and
  `external_code_to_code_technical_receipt_not_ready` as explicit blockers.

The logs are retained locally as `/tmp/structural-180-development.log`,
`/tmp/structural-180-frontend.log`, and `/tmp/structural-180-full-shard0.log`.
No acceptance gate was weakened. Development/frontend coverage and external
physical/release qualification remain separate; the full suite is not green.
