# Terminal 17010d495 development and full-shard results — 2026-09-14

Head `17010d495d651d3d53407db4dfc7b9dcee0867ad` completed
[Repository Python Tests run 34774223487](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34774223487).
Original metadata/logs show:

- Development job `103769241858`: **1217 passed in 839.62 s**, with no failed or
  skipped steps. This includes the published supplied-parent cost observer tests.
- Full shards 0–3: all fail `Materialize exact current-source test evidence` and
  skip `Run materialized repository test suite shard`. The original blockers are
  `external_code_to_code_product_replay_not_passed` and
  `external_code_to_code_technical_receipt_not_ready` in all four logs.
- The aggregate full-suite job fails. No complete-repository pass is inferred from
  the independent development selection.

The [runtime/browser lanes](hosted-170-runtime-20260914.md) are separately
successful. Topology job `103769241422` in run `34774223461` remained active at
capture. These results apply to 17010d495, before the later local successful-retry
and checkpoint-history changes; those additions still require hosted execution.

The [development receipt](hosted-170-development-20260914.json) binds the capture
script, original run/job metadata, log and summary. Read-only packet:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-170-development-c48volsp`,
5 files / 115702 bytes; adjacent `.inventory.json` SHA-256:
`5a3c680d20056d4899ee70a9a68c73636add6ef106dca29030661dba82f77073`.

The [four-shard receipt](hosted-170-shards-20260914.json) binds the original run
metadata and all four job metadata/log pairs. Read-only packet:
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-170-shards-8bs7srub`,
9 files / 419246 bytes; adjacent `-inventory.json` SHA-256:
`751658bbcb35f07bc3a151b05bb3c106fdc2e7a3acd4f40f6a1a010ea3970dd5`.
Each file was reread against its length/hash before sealing.

A contemporaneous read-only GitHub check confirms main remains
`4de4e3f55aae1d267cf704cec7d7533f3a627498`. PR #440 remains Draft, open and unmerged,
head `f788a3c55964ef963f8145835e188d4a3f3792da`, based on that main. No main
integration or R2 closure is inferred from the present AI branch's selected CI.
This status check is not a new signed owner/production acceptance receipt.
