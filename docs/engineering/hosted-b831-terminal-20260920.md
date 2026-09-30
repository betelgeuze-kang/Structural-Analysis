# Hosted receipt for b8316c6c7

Exact tested revision: `b8316c6c778293ab4cf012d27c0e497e2c1bd096`.

- [Repository Python](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/35486561772): development job `106013921710` passes **1,712 tests in 1,224.68 seconds**. Collection succeeds. All four full shards fail during `Materialize exact current-source test evidence`; actual repository tests are skipped and the full aggregate fails. These step states are confirmed in the jobs API.
- [Frontend](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/35486547470): job `106013877986` passes **814 tests in 18.4 minutes**, with seven separate setup tests passing. Required aggregate succeeds.
- Workflow Contract `35486547490` and P0 Canonical Verification Contract `35486547473` succeed. Ordinary CI `35486547475` fails. All runs are terminal before subsequent publication.

These checks cover native scalar serialization and numerical-equivalence test
registration, not the later policy parse reuse implementation. The 85af596ed
numerical study has separately completed both audits and retained secant. The
new 7a41a1566 policy-reuse full-path study is still running. New-head hosted
checks, independent physics and full-suite qualification remain outstanding.
