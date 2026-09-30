# Hosted checks for 31cae34ee

Exact source: `31cae34eefa689b7e7ee0e2c0522e539509b1f8a`.
All runs below are terminal. Later matched-parent driver/audit changes require
their own exact-head checks.

- Python run 35489739959: development job 106022514211 passes **1,744 tests
  in 1290.52 s**; collection job 106022514057 passes.
- Full shards 106022514160, 106022514165, 106022514275 and 106022514443
  fail during evidence preparation and skip actual full tests. Aggregate
  106023445228 fails. Shard-0 explicitly reports
  `external_code_to_code_product_replay_not_passed` and
  `external_code_to_code_technical_receipt_not_ready`.
- Frontend run 35489731178, job 106022488653: **814 passed (18.3 m)**;
  required aggregate 106024567943 passes. Separate setup: seven tests pass.
- Workflow Contract run 35489731196 and P0 Contract run 35489731174 pass.
- Ordinary CI run 35489731188 fails.

Observed logs: `/tmp/structural-31ca-development.log`,
`/tmp/structural-31ca-frontend.log`, `/tmp/structural-31ca-shard0.log`.
These are software-contract receipts, not full-suite, independent physics,
commercial or release acceptance. No numerical or external gate was relaxed.
