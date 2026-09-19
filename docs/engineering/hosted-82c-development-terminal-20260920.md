# Hosted outcome for 82c8a0d47

Exact source: `82c8a0d472036bc06d9b778c3299859a0b156fd9`.

[Repository Python Tests run 35469793244](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/35469793244)
completed with failure. Development job 105968544919 passed **1,574 tests in
977.98 s**; collection passed. Four full shards failed in evidence preparation,
not in repository test execution. Inspected shard 0 job 105968545028 retains
`external_code_to_code_product_replay_not_passed` and
`external_code_to_code_technical_receipt_not_ready`. Full-suite closure is absent.
Workflow Contract and P0 Canonical lanes passed; aggregate CI failed.

[Frontend run 35469772548](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/35469772548)
completed with 727 passes and one failure in its 728-test Workbench suite.
The failing same-origin ResultIR/ReportIR test exhausted the default 5 s wait for
`data-native-frame-artifacts=ready`. The uploaded failure snapshot already shows
`pair_verified` and the corresponding original artifact identities. This supports
an asynchronous readiness timing diagnosis, rather than missing validation data;
it does not establish a universal absence of timing defects.

The same test passed three consecutive local runs against the live Vite server.
Its initial integrity assertion now has a bounded 15 s readiness allowance; all
integrity/authority assertions remain unchanged. A subsequent hosted run is needed
to confirm the fix under CI load. The initial local invocation mistakenly targeted
an unused default port and failed before loading the app; those connection errors
are excluded from the reproduction conclusion.
