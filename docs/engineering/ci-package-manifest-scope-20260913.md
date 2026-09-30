# CI action inventory and package manifest scope — 2026-09-13

Two integration failures were traced to stale assumptions, using hosted logs at
`8daf3e5a908017d4119fe512df48468b33652cd6`. Repairs and local tests started from
`b25bf0899bd1f8af8076924a870c493cd31bd567` with the recorded changes present.

## Workflow action inventory

[Workflow Contract CI run 34722859505](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34722859505)
completed with 160 passes and one failure. The action-pin contract expected one
`actions/upload-artifact` occurrence in Repository Python Tests, although that
workflow now preserves development-contract results as well as failed-materialization
diagnostics. Both uploads use the same reviewed immutable SHA. The contract now
expects two; immutable action checking and the existing named-step/condition/path
checks remain in place. No job gate, upload condition or action revision changed.

Running the exact pytest selection extracted from Workflow Contract CI locally
passed all 161 tests in 10.87 seconds. This is local verification, not a hosted
success receipt.

## Package manifest identity

[Native Frame Alpha Clean Install run 34722859635](https://github.com/betelgeuze-kang/Structural-Analysis/actions/runs/34722859635)
failed on both Linux and Windows while constructing portable transition evidence:
`baseline_manifest_count_invalid`. The production build already included the
original viewer data and its `workbench/src/structure-viewer/drawings/manifest.json`.
The archive readers selected every name ending in `/manifest.json`, confusing that
ordinary viewer asset with the package's `<package-id>/manifest.json`.

Package manifest discovery now requires exactly one slash as well as the manifest
filename. This matches the existing top-level package layout. The correction covers
CLI/workstation archive verification, transition coordinates, portable preflight
and extraction, clean-install replay extraction, and the trusted workflow's inline
archive verifier. Existing duplicate-entry, path, root, inventory and content-hash
checks remain in place. A nested manifest is still a declared, hash-checked asset.

The distribution, portable-install and replay fixtures now contain a nested viewer
manifest. The distribution suite builds the real Rust release CLI, while existing
synthetic static-host and replay/installation doubles retain their original test
scope. Coverage includes update/rollback flows, packaged nested-asset tampering,
and rejection of a second package-root manifest or an unlisted root manifest.
These fixtures do not constitute a real Windows clean-machine installation.

The first run finished with 58 passes and one stale fixture-count assertion (four
static files versus the old expectation of three). That expectation and the total
ZIP entry count were updated. The final selection of distribution, portable-install,
clean-install replay, clean-install workflow and strict YAML tests passed all 75
cases in 44.62 seconds. Ruff and `git diff --check` passed. No structural tolerance,
physical verification criterion, licensing declaration or release authority changed.

## Remaining work

These local repairs remove the observed causes; current-head hosted completion is
still required. The earlier jobs skipped downstream clean-install, cross-platform,
browser and attestation work after their build failures. Their success cannot be
inferred from the local tests. Repository-wide materialization gates, independent
physical validation, learned net benefit and owner/hardware dependencies remain
separate open requirements.

Log hashes and local execution scope are preserved in the accompanying summary.
