# Hosted terminal outcome for 20a940b07 and local regression correction

Published source `20a940b072860aad80e07a578e88a0c4d331d1ca`:

- Frontend Web run 35470895335 passed, including 735 Workbench tests in 10.7 min.
  The previous ResultIR/ReportIR readiness timeout did not recur in this run.
- Workflow Contract and P0 Canonical runs passed.
- Repository Python run 35470914975 failed. Collection passed. Development job
  105971600317 ended with **81 failures, 1,424 passes and 82 setup errors** in
  993.80 s. All 163 failure/error summary entries have the same cause:
  `ValueError: verified layout row requires every original artifact`.
- All four full shards failed before actual repository-suite execution. Inspected
  shard 0 retains external-code-to-code product replay and technical receipt
  readiness blockers. Aggregate CI is failed.

The development regression came from adding optional `cost_skip` to `_ROLES` in
`rc_search_http.py`. Layout and staged-layout readers import that set as the exact
required complete-analysis artifact set. Consequently legitimate verified layout
rows were rejected because they correctly lacked a cost-exclusion receipt.

The fix preserves the original shared complete-analysis role set and permits
`cost_skip` only in the explicitly adaptive design comparison mount. No verified
layout artifact requirement is removed; no skipped design is promoted to verified.
The affected original, standalone and staged HTTP paths are rerun together with
the adaptive-design HTTP tests. Fresh hosted verification is still required for
the repaired source and later local changes.

The combined adaptive-design, layout-search and staged-layout HTTP regression
selection passed **213 tests in 139.73 s** after the correction. This exercises
original graph delivery and rehashed tampering cases through the affected readers;
it does not replace the full development or full repository suite.
