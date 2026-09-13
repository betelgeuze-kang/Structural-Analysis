# Pinned Workbench cohort E2E — 2026-09-13

Source `200111e4a1c837f03d434686a5ede6cb3cc7dd54` closes the local toolchain-entrypoint limitation recorded in the
previous actual-HTTP cohort observation. It does not qualify the entire repository,
hosted CI, independent physics or learned net savings.

## Toolchain and reproduced failure

The existing system Node was v20.19.0; the repository requires v24.20.0 with an exact
executable hash. An isolated official archive was downloaded from
`https://nodejs.org/dist/v24.20.0/node-v24.20.0-linux-x64.tar.xz` and verified against
the workflow's pinned archive SHA-256
`2f2c0da162318f0de47665410c7c8c2ed3d36c8f3105de4bbc61176c70a7cbf2` before extraction. The executable version and SHA-256
`89af8424dd53e560b1933f87ba650d8bf57c83ca5a04600eefb31f416aabbae7` also matched. No existing runtime or environment was
replaced and no identity, dependency, authorization or physics gate was relaxed.

Using that executable, the formal command was:

```sh
/path/to/verified/node scripts/verify-workbench-v2-e2e.mjs --with-job-api --grep cohort --workers=1
```

The first run passed 15 of 17 tests and failed both cohort viewport tests with
`Unexpected token '<'`. The formal Node E2E static host, separately from the Python
HTTP observer corrected earlier, still returned index HTML for missing JavaScript
files. It now returns plain-text 404 for absent file paths and preserves index
fallback for extensionless application navigation. A new HTTP regression checks
both behaviors. Existing zero-page-error assertions were retained.

## Executed verification

The corrected formal entrypoint completed TypeScript checking, the Vite build,
production viewer-delivery verification and **18 cohort tests** successfully. These
include controlled original-graph validation, desktop/mobile behavior, original
hash pinning, actual WSGI HTTP delivery, credentials and denied operations. This is
a filtered cohort run, not the complete frontend or repository suite.

A separate `PYTHONPATH=src python3 -m pytest -q
 tests/test_frontend_build_reproducibility_contract.py` run passed **9 tests**.
The old v20 default executable remains installed; repeat the formal command with
the verified executable, not an unqualified default `node` invocation.

No new numerical solve or training fit occurred. The tests validate integration and
execution contracts, not new data independence, model accuracy or acceleration.
Earlier observation documents retain their historical failures; this record
supersedes only the local pinned-entrypoint limitation.

## Evidence and next scope

Packet `/mnt/193005ba-8531-4d0b-87c2-43c01ee2ce25/structural-pinned-cohort-e2e-10mizkmi` binds 10 files / 2,475,018 bytes through sibling
inventory SHA-256 `627a8bf3afcd0360af6b000f6b7e3f7a48735d3c1619ec88e9a8aed23ce5f97b`. It contains the failed and corrected
logs, source delta, runtime identity receipt, screenshots and original HTTP test
receipt. The downloaded runtime remains outside the repository at `/tmp/structural-pinned-node-mj7hjybs/bin/node`.

Full hosted CI and independent qualification remain open. The next cost comparison
must replace nested CLI intervals with their enclosing process intervals where
available, count historical training once, and keep separately observed review and
audit costs distinct. Neither this successful E2E run nor unrelated timing intervals
can supply missing complete-campaign measurements. Licensing, owner/administrator
and hardware dependencies remain explicit.
