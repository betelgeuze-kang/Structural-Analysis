# GitHub progress checked on 2026-09-20

PR 439 remains open, Draft and unmerged. Its observed published source is
`9453bc210325305569442cbf7ac2fc075f8d1be0`; its base remains
`4de4e3f55aae1d267cf704cec7d7533f3a627498`. The clean local branch initially
contained seven later commits through `e47e1e0ecfacbf37a5fbef951a764da2e72e65c2`.
The later work includes the demonstrated straight-member subdivision leakage
repair, failed binary64 yielded-prefix evidence, successful retained-arithmetic
reuse measurements, numerical audits and their evidence index. It is development
work, not main integration or production acceptance.

All 26 workflow records returned for the published source are terminal:
21 success, four failure and one skipped. Original logs confirm:

- Development contracts: 1,261 passes in 1,194.34 seconds, job 103802688352.
- Topology: 413 focused passes in 735.40 seconds; 984 regression passes in
  652.30 seconds, plus branch selections, job 103802687566.
- Browser: 706 guarded passes and 36 actual HTTP passes, previously retained
  in `hosted-945-browser-pass-20260914.md`.
- Workflow contracts: 166 passes, also retained in that source-specific receipt.

Selections overlap; their counts cannot be summed as independent validations.
Later local changes require new-source hosted checks after publication.

The CI and Legacy Evidence CI failures are still preparation failures.
Original logs from jobs 103802687966 and 103803171465 explicitly state
`external_code_to_code_product_replay_not_passed` and
`external_code_to_code_technical_receipt_not_ready`. The full repository
shards also failed materialization. No full-suite success, external-engine
agreement, legal approval or signed owner acceptance follows from the passing
development/browser checks. Existing gates are preserved.

The retained-arithmetic two-repeat reuse observation is roughly 20% faster on
one authored path with identical original step bytes. It is deterministic
assembly reuse, not a learned gain. The separate binary64 history mismatch
remains failed. Public metadata is not an admitted independent training corpus.
Unseen-case learned benefit, broader independently verified capability,
full-suite/external receipts, main integration and owner acceptance remain open.

Terminal listing and original logs are read-only at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-945-terminal-20260920-t0zo5nu3`.
External inventory SHA-256:
`28b5ee32ffe69b6b6f3b92aefc1698061653a0e781d0778b0113f5873a7c969b`.

## Follow-up: terminal checks at f0769225e

All four returned workflow records for
`f0769225e2b9cfeac6a892837fbee3415f7302f6` are now terminal: Workflow Contract CI
35464560843, P0 Canonical Verification Contract 35464561013 and Frontend Web CI
35464560877 succeeded. CI 35464560920 failed `Materialize exact current-source
test evidence`, before the full repository tests, with the same two external
replay/technical-receipt blockers above. These statuses do not cover later commits.

Failure artifact 10590174928 is explicitly diagnostic-only, with
`receipt_generation_attested=false` and a warning that receipts may be tracked
or partially rewritten. Its external code-to-code receipt reports a current
product replay against reused external execution values dated 2026-07-30,
`external_runtime_executed_in_this_generation=false`, and
`current_product_replay_pass=false`. It is not a fresh external execution.
Two failed support_N1_UX_N metrics remain: bounded member-feature path absolute
difference 4.96424095305589e-7 N and prescribed-settlement path difference
3.631256504377234e-7 N. Existing absolute/relative tolerances remain unchanged.
The downloaded diagnostic ZIP SHA-256 is
`3f526fe38ca48f69fdaeebbd83e0c463a84c6af7b0651fb7db487ea15f769b05`.

Commit 3720639f6 adds a separate failure receipt to the reuse experiment:
a rejected returned full-path comparison retains elapsed costs and the original
comparison file hash/length, leaves speed ratio null, and still raises the
original failure. It does not repair or relabel the numerical mismatch.
Validation: 31 tests passed before the report-binding addition; three focused
failure tests passed after that addition. See
`rc-reuse-failure-receipt-20260920.md` for scope. The change and this follow-up
require hosted checks on their own published source.
