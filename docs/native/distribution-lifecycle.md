# Native distribution lifecycle C5 boundary

## Scope

`structural-distribution` owns a bounded Linux product-distribution slice. It is not a release
approval, signing service, remote updater, or C6 decommission receipt. The implemented CPU C5
boundary packages and executes the already-bounded native product profile without Python or Node.

Two CPU profiles are built independently:

- `cpu-only` + `static`: the Rust product binaries own a statically linked C++ core and the bundle
  also installs the CMake-consumable static libraries and public headers.
- `cpu-only` + `shared`: `structural-cli` and `structural-workbench` link the packaged
  `libstructural_c_abi_v1.so.1` with `$ORIGIN/../lib`; that library exports only `sa_get_api_v1`.

The separate `rocm` + `shared` profile is a build candidate until it runs inside the protected
`native-hip-approved` lane. The lane must select HIP through ABI v1.12 from the installed product
library, prove CPU/HIP FP64 parity, resident operator buffers, deterministic repeat and fallback 0,
and bind the installed-backend receipt to the source/device-library-bound full-residual C2 receipt.
The ROCm runtime itself is a declared host prerequisite rather than copied into the bundle. The
product ABI records `$ORIGIN` plus the configured `STRUCTURAL_ROCM_ROOT/lib` directory in its
install RUNPATH, so the three installed Rust binaries remain executable under the lane's empty
environment. Bundle construction fails if that root has no `libamdhip64.so`; the approved E2E also
fails on any unresolved runtime dependency. This runtime binding is build/package evidence only,
not device execution or C2 authority.

## Bundle contract

A bundle is a directory containing `structural-distribution.json` and `payload/`. The manifest is
canonical JSON with an SHA-256 self-identity over all fields except `manifest_hash`. Its sorted
inventory binds each portable relative path, byte length, normalized read/execute mode and SHA-256.
It also binds:

- release ID and package version;
- exact source SHA-256 supplied by the trusted build lane;
- ABI v1.12;
- CPU-only or ROCm backend profile;
- static or shared linkage;
- the installed CMake build identity and backend bit.

The manifest authority is deliberately only `cpu_build_candidate` or `rocm_build_candidate`.
Only the subsequent clean-machine or approved-device receipt can establish the bounded C5 lane.

Creation normalizes in-tree regular-file symlinks such as ELF SONAME links into independent regular
files. Verification rejects symlinks, path traversal, duplicate/non-sorted inventory entries,
special files, extra files, missing files, metadata drift, hash drift and backend/build mismatches.
A release ID is immutable within an install root.

## Durable activation

An install root contains immutable `releases/<release-id>` directories and canonical state under
`state/`. `structural-installer` takes an exclusive OS file lock and publishes a journal before any
activation change. The transaction advances through `prepared`, `materialized` and `activated`.
Every state write uses a same-directory temporary file, file sync, rename and directory sync.

`recover` is roll-forward only: it verifies the staged/materialized bundle and its manifest binding,
finishes activation, then removes the journal. `status` refuses authority while a journal exists.
`rollback` verifies the previous immutable release before atomically swapping current/previous and
increasing the generation. Tests inject process interruption at all three durable boundaries.

## Clean-machine E2E

The hosted distribution gate builds both CPU profiles and then, from their installed paths:

1. verifies the bundle and installs it;
2. executes the three Rust binaries with an empty `PATH`;
3. validates ModelIR and consumes the installed CMake package;
4. selects and executes the installed ABI backend;
5. runs stage-by-stage and one-shot Workbench flows from both strict ModelIR and the bounded MGT
   source, then byte-compares every artifact and preserves MGT import-health evidence;
6. exercises deterministic inspect, immutable explicit `review`, review reopen and handoff export
   from both installed sessions without inferring an engineering approval;
7. installs an immutable update, rolls back and re-verifies activation;
8. emits an append-only v3 hash-bound receipt with ModelIR/MGT result, report, MGT source,
   import-health, review and export identities, Python/Node lookup count 0 and fallback count 0.
   The receipt checker continues to accept frozen v1/v2 receipts without treating them as v3
   operator-surface evidence.

The reference command is:

```text
scripts/build_native_distribution.sh --backend cpu-only --linkage shared \
  --release-id <ID> --source-sha256 sha256:<HEX> --output <BUNDLE>
scripts/run_native_distribution_e2e.sh --bundle <BUNDLE> --release-id <ID> \
  --package-version 0.1.0 --backend cpu-only --linkage shared \
  --source-sha256 sha256:<HEX> --installed-backend-receipt <BACKEND.json> \
  --receipt <E2E.json>
scripts/run_native_rootfs_isolation_e2e.sh --bundle <BUNDLE> \
  --receipt <ROOTFS-E2E.json>
```

On Linux hosts that permit unprivileged namespaces, the rootfs harness executes both Workbench
profiles from the verified CPU bundle as UID/GID 65532 with an empty lookup path, a read-only root
and payload, a writable operator workspace, and only loopback networking. Both profiles also run
inspect, an explicit non-promoting `review`, review reopen, post-review inspect and handoff export.
`structural-installer` verifies each operator artifact's canonical self-hash, session binding,
ResultIR/comparison/PDF binding and fixed `review` decision before it creates and validates the v2
self-hashed receipt. Its authority is deliberately `local_rootfs_diagnostic_c5`; it records that
neither an OCI image nor a customer image receipt or engineering approval was created.
The installer continues to verify frozen v1 rootfs receipts against their original bundle and
claim boundary, while only newly generated v2 receipts carry operator-surface evidence.

The installed flows remain the exact bounded ModelIR/NDTHA and normalized-MGT-to-NDTHA Workbench
profiles. General native UI/MGT coverage, React/TypeScript deletion, live external-solver
execution, signing, cross-platform installers, remote update transport, release retention and
final C6 removal remain open.

The active on-prem image now consumes the CPU static bundle and exposes only the non-root native
Workbench entrypoint. The prior Python image and React Pages workflow are archived outside their
active deployment locations; see `docs/native/deployment-cutover-v1.md`. This is a deployment
authority cutover, not a customer image receipt or global C6 decommission.
