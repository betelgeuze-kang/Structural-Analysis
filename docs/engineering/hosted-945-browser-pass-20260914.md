# Published 945 browser and workflow receipts

Source `9453bc210325305569442cbf7ac2fc075f8d1be0` completes runtime frontend
job `103802688241` successfully. Its original log records all 706 guarded
browser tests passing in 15.4 minutes and all 36 actual HTTP tests passing
in 3.2 minutes. The formerly failing priced design-comparison case is included
in this complete guarded selection. The failure-only diagnostic upload is
skipped because the guarded step succeeds.

This is a new-source successful run, not a reproduction proving the cause
of the earlier c1 timeout. No browser timeout was extended to obtain this
result. The trace-preservation change improves future diagnosis but cannot
be credited as a demonstrated fix for that earlier rendering timeout.

Workflow-contract job `103802687720` at this same source passes 166 tests in
17.76 seconds. These receipts cover the published timing/CLI and diagnostic
preservation changes. Later local remeshed-geometry split work and numerical
audits are outside this source and need their own hosted verification.

Development-contract job `103802688352` and topology regression job
`103802687566` remain live when this receipt is recorded. Full repository
shards previously failed evidence materialization; browser success does not
close full-suite, independent physical, learned-benefit or release gates.

Original logs are retained read-only at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-945-browser-pass-4mbtkyu9`.
External inventory SHA-256:
`4a9a67aedc07783def3d70e6c1be382213f6fcc6903109e16536900b27f10259`.
