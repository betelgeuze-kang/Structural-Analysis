# Reproducible multi-case reuse campaign

`scripts/run_rc_reuse_campaign.py` runs a declared case list serially through the
existing full-history-gated experiment. It snapshots all inputs before solving,
binds inputs and runner script bytes, retains per-case exception/cost/receipt
identity, persists partial progress after each case, and continues independent
cases after an ordinary failure. Any failed case keeps the CLI exit nonzero.
It never averages only successful speed ratios; aggregate ratio remains null.
Keyboard/process interruptions are not converted into completed cases. A case
return without a success receipt is also rejected.

The example and command are in `examples/research/rc_reuse_campaign/README.md`.
The example deliberately starts with the original large-reversal failure, then
runs the smaller concrete-damaging reversal. It is not an independent dataset.

Validation on 2026-09-20: eight focused tests pass, Ruff passes, and the final
script completes a real two-case campaign with expected exit 1. Case one fails
and records 2.639113096 s; case two completes and records 10.423419490 s. Both
cases are retained; campaign elapsed time is 13.065803339 s through the final
receipt boundary. `campaign_complete=true`, `all_cases_completed=false`, and
`aggregate_speed_ratio=null`. Bound original receipt hashes/lengths and the
saved campaign script hash were independently re-read and checked.

The numerical run used base Git revision
`b44d5ff1e2ea93427f5254fb578293e99d7d4729` plus the then-uncommitted runner bytes,
which are saved and hashed in the packet. The revision alone is not a source
attestation. An earlier pre-final-guard execution is separately retained at
`structural-reuse-campaign-bxd9a645`; the final run is authoritative for this
runner validation. This is orchestration/cost-accounting validation, not new
physical, convergence or learned-benefit evidence.

Final packet:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-reuse-campaign-final-znepwsiu`.
Its external inventory covers 985 files, re-read for hash verification; SHA-256:
`a377e8baae8ce247ae5c857237817883fec14606c84146c9fda9098542619e00`.
