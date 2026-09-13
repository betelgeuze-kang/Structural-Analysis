# Published 98e diagnostic execution

The [original-log receipt](hosted-98e-completed-ci-20260914.json) binds selected
terminal jobs to `98e3bc2c3eb0c96ec4dfa5c8544c829c6005d0f7`.

| Lane | Original observed result |
| --- | --- |
| Development Python / 103759452847 | 1,176 passed in 840.12 s |
| Runtime frontend / 103759452739 | 706 passed in 10.8 min; separate HTTP suite 26 passed in 2.0 min |
| Runtime Python / 103759452884 | 96 passed in 12.74 s |

The frontend count includes the two new strict-string decoding contract tests.
This is hosted coverage of the published optimization, not a repeated hosted
performance measurement. Later assembly-phase summaries and the registration
of the quadratic/phase test files are not in this head. The 1,176-test development
result must not be used to claim that those newly registered tests executed.

All four repository shards fail the evidence-materialization step and skip the
actual repository suite. Shards 0/1/2 original logs identify
`external_code_to_code_product_replay_not_passed` and
`external_code_to_code_technical_receipt_not_ready`, agreeing with previously
captured shard 3. The earlier shard-3 packet was reread and referenced instead
of redownloaded. Each passing one-test preparation command remains distinct
from the skipped full shard.

The six newly captured jobs, two run metadata records, original logs, script
and summary form a sealed 16-file / 615,748-byte packet. Full source hashes,
job IDs and byte inventories are retained. Topology run 34770631650 was still
running at the latest observation and is not counted as passed here. No full
repository qualification, independent physics, learned gain or release follows.

Separately, the later local failed-assembly test now asserts the new summary's
incomplete path status, two observed dispatches and one raised dispatch, with
physical validation false. The focused actual-exception check passes in 1.89 s;
it extends the prior 39-test summary verification without changing the solver.
