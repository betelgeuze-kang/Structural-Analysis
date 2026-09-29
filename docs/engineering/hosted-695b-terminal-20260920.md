# Hosted receipt for 695b290f3

Exact tested revision: `695b290f35ad6b735a7d49aeaf6f728e4076f398`.

- [Repository Python](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/35483460123): development job `106005335692` passes **1,686 tests in 1,056.85 seconds**. Collection passes. All full shards fail during evidence preparation and their aggregate fails.
- Shard 0 (`106005335685`) records `external_code_to_code_product_replay_not_passed` and `external_code_to_code_technical_receipt_not_ready`. The full repository test body is not executed; development contract success does not waive this gate.
- [Frontend](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/35483426181): job `106005238922` passes **814 tests in 18.8 minutes**, with a separate seven-test setup passing. Required aggregate `106007686360` passes. This covers the scoped L-frame timeout correction and the material-boundary fixture/browser cases at this exact source.
- Workflow Contract `35483426196` and P0 Canonical Verification Contract `35483426180` pass. Ordinary CI `35483426179` fails. All runs are terminal before the next publication.

The prior 90cc two-test screenshot failure remains part of the record; the new
green frontend run covers the correction at 695b. These counts do not cover
the later interior label-generation, pooled runtime driver or audit changes.
Elapsed CI times across commits are not controlled performance comparisons.
Full-suite success, the live pooled runtime result, independent physical checks,
operator/signature/hardware acceptance and release remain unproved.
