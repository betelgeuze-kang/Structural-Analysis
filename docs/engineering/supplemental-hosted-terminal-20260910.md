# Supplemental current-main CI terminal observation

Read-only GitHub inspection confirms that the two previously running workflows
for draft [PR #440](https://github.com/betelgeuze-kang/Structural-Analysis/pull/440)
have finished successfully at head
`f788a3c55964ef963f8145835e188d4a3f3792da`:

- [CI run 34363325328](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34363325328): its `verify` job succeeds with no skipped workflow steps.
- [Repository Python Tests run 34363325247](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34363325247): collection, four shards and the completion job succeed with no skipped workflow steps.

The original job logs identify checkout
`e76bb929f3a0d2987f2d8e7e3479995ebd97a50a`, the GitHub PR merge commit. Fresh
Git commit API reads confirm that its tree and the source head tree both equal
`d322d18227fbdd2b62d1ea46efccba75531572ec`. This is evidence for that R2 candidate,
not the later AI exploration branch. The PR remains open and draft; no merge,
rerun or branch mutation was performed.

## Executed tests and exclusions

| Python shard | Passed | Skipped | Deselected | Passed subtests |
| --- | ---: | ---: | ---: | ---: |
| 0 | 2045 | 21 | 0 | 0 |
| 1 | 1593 | 16 | 0 | 82 |
| 2 | 1536 | 3 | 1 | 0 |
| 3 | 1827 | 12 | 1 | 55 |
| Total | 7001 | 52 | 2 | 137 |

Collection reports 7,055 tests, matching passed + skipped + deselected counts.
Subtests and per-shard smoke tests are not added as extra distinct collected
cases. The CI job separately reports selections of 1,128 passed / 7 skipped,
93 passed / 1 skipped, 76 passed / 2 deselected, and a browser selection of
3 passed / 2 skipped. Overlap between selections is not counted as additional
independent coverage. Individual test skips have not been promoted to passes.

The commit check-runs API returns **45 terminal checks: 44 success and one
skipped**. The skipped check is `live-exact-main`; the source-bound workflow
explicitly excludes pull-request events and requires `refs/heads/main`.
Accordingly, this PR does not supply the live current-main issue-state receipt.
The 45-check listing is a terminal status snapshot; only the seven CI/Python job
logs and the previously recorded identity/workflow-contract evidence were
inspected in detail. It is not an audit of every other check's internal claims.

## Preserved scope

This resolves the previous pending status of these two CI runs. It does not prove
actual signed Product State execution, main deployment, owner/administrator
acceptance, independent physical validation, or release eligibility. Existing
historical records and protected receipts remain unchanged. The R1/R2 integration
requirements beyond the demonstrated candidate checks remain open.

The [machine summary](supplemental-hosted-terminal-20260910.summary.json) binds
the official run/job/commit responses, seven original logs, checks snapshot and
workflow source at
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-r2-ci-terminal-0zq5qlra`.
All **18 files / 2,217,163 bytes** were inventoried and reread exactly; inventory
SHA-256 is `e83f608650f5b2450dd2f55fc715dd3f197e1543155ffa46cdbef18cd44dd990`.
The installed CLI rejected `gh pr checks --json`; collection used the read-only
REST API instead. The locally missing merge object was verified through the
official Git commit API without changing the checkout.
