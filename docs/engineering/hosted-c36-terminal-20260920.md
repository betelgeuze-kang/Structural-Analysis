# Hosted receipt for c36cf1da6

Exact tested revision: `c36cf1da6c89306d7beecaab3586d07830a77819`.

- [Repository Python](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/35485591203): development job `106011244261` passes **1,691 tests in 1,193.23 seconds**. Collection passes. All four full shards fail during `Materialize exact current-source test evidence`, with actual repository test execution skipped. The full aggregate fails.
- Shard 0 (`106011244259`) records `external_code_to_code_product_replay_not_passed` and `external_code_to_code_technical_receipt_not_ready`. These remain external-evidence blockers; development success does not waive them.
- [Frontend](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/35485579894): job `106011213608` passes **814 tests in 18.5 minutes**, with seven separate setup tests passing. The workflow succeeds.
- Workflow Contract `35485579950` and P0 Canonical Verification Contract `35485579895` succeed. All listed runs are terminal before the next publication.

This source predates the scalar serialization optimization, numerical-equivalence
auditor and its development-test registration. Those changes need new hosted
checks. The running 85af596ed numerical campaign is separate from this CI receipt
and has no final selection result yet. No full-suite, physical-validation or
release qualification follows from these results.
