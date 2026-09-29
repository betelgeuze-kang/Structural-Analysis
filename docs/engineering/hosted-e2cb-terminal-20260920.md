# Hosted receipt for e2cb16ca8

Exact tested revision: `e2cb16ca81973e271f07074ded2517631f6e5c5a`.

- [Repository Python](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/35487600392): development job `106016731634` passes **1,713 tests in 1,300.57 seconds**. Collection succeeds. All four full shards fail during `Materialize exact current-source test evidence`, skip actual repository tests, and leave the full aggregate failed; these steps are verified in the jobs API.
- [Frontend](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/35487581122): job `106016680286` passes **814 tests in 18.5 minutes**, with seven setup tests passing separately. Required aggregate succeeds.
- Workflow Contract `35487581165` and P0 Canonical Verification Contract `35487581120` succeed. Ordinary CI `35487581117` fails. All listed runs are terminal before subsequent publication.

This revision covers the policy parse reuse implementation and its original
regression test, but predates the additional cache-lifecycle auditor tests.
The 7a41a1566 numerical study separately completes all three audits and retains
secant. These hosted passes are not full-suite, independent physical validation
or release qualification. Later commits require their own hosted verification.
