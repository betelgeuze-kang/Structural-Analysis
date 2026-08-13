# Native deployment-authority cutover v1

## Closed boundary

The active on-prem product entrypoint is now `deployment/onprem/Containerfile`. Its builder creates
the existing `cpu-only` + `static` distribution, and its final Debian runtime contains only the
installed product payload plus required C/C++ runtime libraries. It executes
`structural-workbench` as UID/GID 65532 with a read-only root and a single operator-mounted
`/workspace`.

The Compose contract adds no port, listener, secret, or network namespace. It drops every Linux
capability, enables `no-new-privileges`, and mounts a no-exec temporary filesystem. The bounded
Import -> Validate -> Run -> Resume -> Compare -> Report flow therefore has no Python, Node,
browser, React, package-manager, or external-renderer runtime lookup.

The same installed payload exposes the C++-verified general ModelIR topology view and the bounded,
provenance-bound `model-edit-node` coordinate command. Distribution E2E v10 proves repeated edited
model/receipt bytes and source nonmutation plus deterministic bounded NDTHA response-history views
for CPU static and shared packages. This does not promote the rootfs diagnostic into general
visual-editing, 3D result exploration, or customer-image evidence.

The prior React Pages workflow moved out of `.github/workflows` to
`deployment/legacy-react-pages`; it can no longer receive Pages write authority or be dispatched.
The prior Python project-ops image moved to `deployment/legacy-python-onprem`. The old packaging
manifest builder intentionally follows that archived path so historical skeleton evidence is not
silently reinterpreted as native evidence.

`scripts/check_native_deployment_cutover.py` fails if Pages deployment authority reappears, either
archived entrypoint is missing, the active image acquires an interpreter or port, Compose loses its
isolation, or the C5 cutover manifest promotes C6/removal prematurely. The check runs in the
`native-pr-fast` dependency-boundary job.

## Evidence and operator verification

The repository-owned checks are:

```text
python3 scripts/check_native_deployment_cutover.py --json --fail-blocked
python3 -m pytest -q tests/test_native_deployment_cutover.py
scripts/build_native_distribution.sh --backend cpu-only --linkage static ...
scripts/run_native_distribution_e2e.sh ...
scripts/run_native_rootfs_isolation_e2e.sh --bundle <BUNDLE> --receipt <RECEIPT.json>
```

The last command is a Docker-independent Linux diagnostic harness. It places the verified bundle
under a read-only bind mount, unshares user/mount/network namespaces, maps the runtime to UID/GID
65532, clears `PATH`, runs the ModelIR and MGT Workbench workflows, and asks the Rust installer to
emit and re-verify a self-hashed `local_rootfs_diagnostic_c5` receipt. The exact receipt requires
`EROFS` from both root and payload write probes, a writable operator workspace, only `lo`, zero
IPv4 routes, reported/completed comparison-passing sessions, and hash-bound ResultIR/report/MGT
artifacts. It also verifies self-hashed benchmark-catalog and copied-evidence views, including the
non-promoting geometry/no-runner and ready/blocked/unavailable boundaries. Its contract fixes
`container_image_built=false` and `customer_image_receipt=false`; browsing does not generate or
approve evidence.

Where Docker is available, build the image with an immutable release ID and source SHA-256, inspect
its configured user/entrypoint/network contract, and execute `--version` without network access.
An image build performed on an arbitrary development host is diagnostic evidence only. A customer
or release-authorized build, vulnerability scan, SBOM attestation, signing, registry/offline
transfer, import, and rollback drill must produce environment-bound receipts.

## Open boundary

This C5 cutover removes active React Pages and Python on-prem runtime deployment authority. The
legacy release publication and branch-writing workflows are archived with their Python mutation
helpers under `deployment/legacy-python-release-publication`; active `contents: write` and branch
push authority are now zero. It does not yet remove Python oracle/technical receipt workflows,
React/TypeScript source, Python compatibility consumers, or rollback packages. It also does not
prove general GUI parity, live external-solver execution, approved-device HIP C2, or final C6.
