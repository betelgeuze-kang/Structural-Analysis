# Hosted terminal receipt at 3eb50016d

Exact source: `3eb50016d8abe7672bfc246b334bccd37cb930e5`.

- Python run `35501533911`: collection job `106054041681` succeeds;
  development job `106054041788` passes **1,850 tests in 1,366.63 s**.
- Full shard jobs `106054041737`, `106054041747`, `106054041782` and
  `106054041867` fail at `Materialize exact current-source test evidence`.
  All four actual repository test steps are skipped. Aggregate job
  `106055083009` fails. Shard 0's raw log explicitly retains
  `external_code_to_code_product_replay_not_passed` and
  `external_code_to_code_technical_receipt_not_ready`.
- Frontend run `35501512006`, job `106053982301`: **814 tests pass in 18.8 min**;
  aggregate `106056484743` succeeds.
- Workflow contract `35501511975` and P0 contract `35501511972` succeed.
  Ordinary CI `35501512003` fails.

All these runs are terminal before the next development push. Local retained
logs are `/tmp/structural-3eb-development.log`,
`/tmp/structural-3eb-frontend.log`, and `/tmp/structural-3eb-shard0.log`.
The later accepted-material summary and material-cost gate code is not covered
by this receipt. Its 91 local focused tests remain separate evidence until
new-source hosted checks execute. No full-suite completion, physical validation,
merge, release or independent acceptance is claimed.
