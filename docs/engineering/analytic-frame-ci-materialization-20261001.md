# Analytic frame evidence epochs in CI

The protected analytic receipt is retained verbatim from development base
`354fc6edf35937c2aecf62f70e5283b5194a2af3` (Git blob
`17931829ffce2f8947f462e627d3ac7b2acb22ba`). The refreshed receipt from `b1b139d`
and the historical bytes, hashes and provenance are preserved outside source in
`/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/pr-backlog-20260929/quality-gate-failure-triage-20261001/implementation/protected-epoch-preservation.json`.
The native protected-path classifier remains unchanged. This follows the
[package-preparation CI precedent](package-preparation-ci-boundary-20260913.md).

Each ephemeral CI checkout runs the authoritative analytic producer and its
current-source reproduction check, then rebuilds and checks the hierarchy:

```sh
python scripts/build_analytic_frame_verification_artifact.py
python scripts/build_analytic_frame_verification_artifact.py --check
python scripts/build_verification_hierarchy_status.py
python scripts/build_verification_hierarchy_status.py --check
```

Preparation precedes consumers in all six jobs: `ci.yml/verify`,
`python-test-collection.yml/full_shards`,
`nightly-full-quality.yml/python_full_shards`,
`nightly-full-quality.yml/deterministic_quality`,
`nightly-heavy-solver.yml/heavy-full-quality`, and
`release-publish-current.yml/publish`. Existing pristine snapshot checks precede
materialization. Release preparation follows the existing cryptographic
authority checks and finishes before candidate construction.

The hierarchy must follow analytic generation because it records that receipt's
file hash. Source checksums, numerical tolerances, reruns and invalid-evidence
rejection remain enforced. The original committed record and fresh CI records
are separate evidence epochs; bare full pytest requires this preparation in a
disposable checkout. These three analytic families remain internal Level 1
computational evidence with external, experimental, customer and release claims
false. CI generation does not grant legal or release authority.
