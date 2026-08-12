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
6. installs an immutable update, rolls back and re-verifies activation;
7. emits an append-only v2 hash-bound receipt with ModelIR/MGT result, report, MGT source and
   import-health identities, Python/Node lookup count 0 and fallback count 0. The receipt checker
   continues to accept frozen v1 receipts without treating them as MGT evidence.

The reference command is:

```text
scripts/build_native_distribution.sh --backend cpu-only --linkage shared \
  --release-id <ID> --source-sha256 sha256:<HEX> --output <BUNDLE>
scripts/run_native_distribution_e2e.sh --bundle <BUNDLE> --release-id <ID> \
  --package-version 0.1.0 --backend cpu-only --linkage shared \
  --source-sha256 sha256:<HEX> --installed-backend-receipt <BACKEND.json> \
  --receipt <E2E.json>
```

The installed flows remain the exact bounded ModelIR/NDTHA and normalized-MGT-to-NDTHA Workbench
profiles. General native UI/MGT coverage, React/TypeScript deletion, live external-solver
execution, signing, cross-platform installers, remote update transport, release retention and
final C6 removal remain open.
