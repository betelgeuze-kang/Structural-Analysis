# Hosted checks for 11d9a8ee3

Exact source: `11d9a8ee3f2b2afcc254aeaf6e65c8ecf444cc02`.
All runs below are terminal. These receipts do not qualify later local source.

- Python run 35488722406: development job 106019745094 passes **1,719 tests
  in 1300.47 s**; collection job 106019745212 passes.
- Full shards 106019745196, 106019745217, 106019745297 and 106019745321
  fail during evidence preparation and skip actual full tests. Aggregate
  106020548250 fails. Shard-0 logs explicitly retain
  `external_code_to_code_product_replay_not_passed` and
  `external_code_to_code_technical_receipt_not_ready`.
- Frontend run 35488709288, job 106019706442: **814 passed (18.3 m)**.
- Workflow Contract run 35488709277 and P0 Contract run 35488709279 pass.
- Ordinary CI run 35488709278 fails.

Observed logs: `/tmp/structural-11d9-development.log`,
`/tmp/structural-11d9-frontend.log`, `/tmp/structural-11d9-shard0.log`.

Development/frontend success is not full-suite completion, independent physical
validation or release acceptance. No numerical tolerance or external gate was
weakened. The new concrete decomposition and 512-layer comparison changes need
their own exact-head checks after publication.
