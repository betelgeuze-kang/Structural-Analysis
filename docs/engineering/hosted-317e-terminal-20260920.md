# Hosted checks for 317e3197f

Exact source: `317e3197f21177fbdcbfc7700cb50c88ffb534b6`.
All runs are terminal. Nested seed preparation and pre-capture guard changes
come later and require their own exact-head checks.

- Python run 35490893903: development job 106025509054 passes **1,754 tests
  in 1211.57 s**; collection job 106025508938 passes.
- Full shards 106025508999, 106025509032, 106025509046 and 106025509052
  fail during evidence preparation and skip actual tests. Aggregate 106026494850
  fails. Shard-0 retains `external_code_to_code_product_replay_not_passed` and
  `external_code_to_code_technical_receipt_not_ready`.
- Frontend run 35490882508, job 106025476865: **814 passed (16.9 m)**;
  aggregate 106027525587 passes. Separate setup: seven tests pass.
- Workflow Contract run 35490882522 and P0 Contract run 35490882499 pass.
- Ordinary CI run 35490882501 fails.

Logs: `/tmp/structural-317e-development.log`,
`/tmp/structural-317e-frontend.log`, `/tmp/structural-317e-shard0.log`.
These receipts prove scoped software tests, not full-suite completion,
independent physics, commercial suitability or release approval. No gate or
numerical tolerance is waived.
