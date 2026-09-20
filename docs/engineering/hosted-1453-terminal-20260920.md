# Hosted receipt for 1453ae48f and subsequent CI coverage

Exact tested revision: `1453ae48fd895164e67b609a995a5647f22422bc`.

- [Repository Python](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/35480207507): **1,674 development tests passed in 1,490.65 seconds**, job `105996541189`; collection passed. All four full shards failed in evidence preparation before repository tests, and the aggregate failed.
- Shard 0 (`105996541231`) retains `external_code_to_code_product_replay_not_passed` and `external_code_to_code_technical_receipt_not_ready`. No acceptance rule is waived.
- [Frontend](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/35480204704): **755 passed in 17.7 minutes**, job `105996531443`; required aggregate `105998838641` passed. Separate seven-test setup also passed.
- Workflow Contract `35480204734` and P0 Canonical Verification Contract `35480204716` passed; ordinary CI `35480204742` failed. Every run was terminal before the subsequent batch was published.

## Subsequent coverage correction

Review of the explicit development job found that the new cost-attribution and immutable same-parent receipt tests were not selected. They were collected for the full suite, whose execution remained blocked, and had only local focused execution evidence. Commit `5d5e9ca58` adds both files, increasing the explicitly selected files from 61 to 63 without changing the full-suite preparation gate or its failure behavior.

Workflow and new-regression checks: **21 passed in 2.07 seconds**. Offline inventory rebuild against the committed source required no changes to the canonical JSON; inventory regressions: **9 passed in 20.57 seconds**. This is local validation of the coverage correction, not a hosted receipt for later commits or qualification of all tests, independent physics, signatures, hardware, merging or release.
