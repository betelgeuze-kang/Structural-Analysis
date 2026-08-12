# Structural Native Workspace

This workspace is the staged Rust/C++ product boundary. Slice A implements the CPU-only
build graph and C ABI v1 foundation. Slice B adds strict Rust `ModelIR` v2 wire decoding,
Draft 2020-12 schema validation, Python-compatible canonical bytes and three SHA-256
identities. Slice C adds the ABI v1.1 typed descriptor, immutable C++ semantic owner,
deterministic validation report and caller-owned canonical snapshot. The safe Rust round-trip,
ABI v1.1 RAII owner and `structural-cli model validate` then complete Slice D and promote the
bounded ModelIR domain to C3. Later bounded slices add CPU ResultIR/ReportIR product composition,
restart, durable jobs and external comparison while HIP remains unimplemented;
`capabilities.json` records each separate boundary. The existing `structural_runtime_ffi`
package is a temporary compatibility member. R2 moves its seven raw ABI declarations to
`structural-ffi-sys`, defines strict pointer-free compatibility wire cases in
`structural-contracts`, and keeps the original crate as the numerical oracle plus adapter. Its
ABI v3 layouts, five exports, status codes and bounded numerical vectors remain frozen. R3 first
moves `track_point_load` into `structural_solver_cpu`, exposes it through ABI v1.2 and promotes
only the 9-node midpoint-load support/theory matrix to Python C1. The next slice moves the
nonlinear static story-frame Newton kernel through ABI v1.3 and a safe Rust caller. An independent
NumPy dense-matrix oracle promotes only a five-case 1/3-story topology, elastic/plastic,
mixed-sign load, P-delta and backtracking matrix to C1. Broader input-space parity, HIP C2 and
runtime cutover remain open. The third R3 slice moves nonlinear NDTHA to a serial FP64 C++
Newmark/Newton kernel sharing the static constitutive/assembly source, exposes eleven disjoint
caller-owned response channels through ABI v1.4, and preserves the complete frozen 2-story,
3-step legacy Rust fixture. A separate NumPy dense-matrix oracle and strict product-golden wire
promote a five-case 1/2/3-story Newmark, elastic/plastic, mixed-sign acceleration, P-delta,
damping-cap, adaptive-retry, line-search and collapse matrix to C1. Broader dynamic input-space
parity and HIP C2 remain open. R4 begins with an ABI v1.5 caller-owned inter-step restart state:
the C++ kernel advances a validated private copy, the C boundary publishes only complete success,
and the safe Rust owner proves bitwise one-shot/split identity for completion and collapse. This
state is serialized by `structural-runtime` into a bounded, canonical little-endian artifact with
independent model/state/execution SHA-256 bindings. Same-directory write, file sync, atomic rename
and directory sync provide the bounded Linux CPU durability contract; corruption, truncation,
trailing bytes, binding drift and impossible native state fail closed. Exact save/load/resume is
promoted as the separate CPU checkpoint C4 capability. R5 adds a strict result-free native request,
terminal `bounded_candidate` ResultIR, ReportIR, deterministic Markdown and a self-hashed artifact
receipt. Public CLI run/resume produces bitwise-identical terminal bundles without a Python/Node
runtime lookup, closing only the tracked CPU nonlinear-NDTHA product C5 profile. A separate
single-host C5 durable-job slice owns submit/poll/cancel, expired-lease recovery, checkpoint
continuation and deterministic export. Another bounded C5 slice strictly ingests hash-bound
external result/source artifacts and compares three global NDTHA quantities; its tracked source
is a language-neutral Python C1 golden, not live solver evidence. Broader solver coverage,
distributed API/authorization, live same-mesh external validation, HIP C2, Workbench/PDF and C6
remain open. The legacy five-symbol ABI is unchanged.
`inplace_scale_f32` is frozen only as an alias/checksum compatibility probe used by the old
Python producer hook. It is not a structural product capability, receives no C0-C6 promotion and
will be removed with that hook after rollback coverage; backend receipts replace its telemetry.

## Rust

~~~bash
cargo fmt --manifest-path native/Cargo.toml --all -- --check
cargo clippy --manifest-path native/Cargo.toml --workspace --all-targets --locked -- -D warnings
cargo test --manifest-path native/Cargo.toml --workspace --locked
cargo +1.77.0 check --manifest-path native/Cargo.toml --workspace --all-targets --locked
~~~

`structural-ffi` is the only crate that configures and links the C++ library. The other crates
must not run a second CMake build.

`structural-contracts` packages its own byte-identical transition copy of the Python-oracle
`ModelIR` v2 schema. A focused test blocks silent drift between the two copies. The C1
capability covers wire/schema/canonical identity only, not C++ semantics or solver readiness.
It also packages the strict nonlinear-NDTHA CPU v1 golden schema; that separate contract records
only the bounded five-case C1 matrix and rejects duplicate/unknown/non-finite fields, length drift
and impossible terminal states.

The `modelir_v2_cpp_core` capability remains narrower than aggregate `modelir_v2`: Slice C
introduced it at C0 and Slice D's Python semantic parity advances it to C1. Slice D's C3 aggregate
adds the exhaustive Rust descriptor arena, safe RAII ownership, concurrent immutable queries,
eight-fixture byte/hash round-trip and the validation CLI. Semantic invalidity is returned in the
versioned report; it is not disguised as an ABI create failure. Explicit blockers fail only when
the CLI's `--require-analysis-ready` policy is selected.

The validation-only product command is:

~~~bash
cargo run --manifest-path native/Cargo.toml -p structural-cli -- \
  model validate tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json \
  --require-analysis-ready
~~~

Without `--require-analysis-ready`, a contract-valid document with explicit blockers exits zero
while preserving `analysis_ready: false` in the report. Semantic or wire invalidity exits 2;
runtime/input transfer failure exits 1.

The bounded analysis product commands are:

~~~bash
cargo run --manifest-path native/Cargo.toml -p structural-cli -- \
  analysis run native/tests/fixtures/product_e2e/nonlinear_ndtha_request.json \
  --output-dir run
cargo run --manifest-path native/Cargo.toml -p structural-cli -- \
  analysis run native/tests/fixtures/product_e2e/nonlinear_ndtha_request.json \
  --output-dir partial --step-budget 2
cargo run --manifest-path native/Cargo.toml -p structural-cli -- \
  analysis resume native/tests/fixtures/product_e2e/nonlinear_ndtha_request.json \
  partial/checkpoint.ndcp --output-dir resumed
~~~

Output-directory publication is create-new and fail-closed; it never overwrites an existing path.
The exact scope and remaining authority boundaries are in
`docs/native/bounded-product-e2e-v1.md`.

The bounded external-comparison command is:

~~~bash
cargo run --manifest-path native/Cargo.toml -p structural-cli -- \
  comparison run result-ir.json external-result.json raw-solver-output \
  --output-dir comparison --require-pass
~~~

Live external evidence additionally requires `--executable-artifact`. Exact source and executable
bytes are verified before comparison; see `docs/native/external-comparison-v1.md` for the
non-promoting authority boundary.

## CPU-only C++

~~~bash
cmake -S native/cpp -B build/native \
  -DSTRUCTURAL_BUILD_TESTS=ON \
  -DSTRUCTURAL_ENABLE_HIP=OFF \
  -DSTRUCTURAL_WARNINGS_AS_ERRORS=ON
cmake --build build/native --parallel
ctest --test-dir build/native --output-on-failure
~~~

`STRUCTURAL_ENABLE_HIP=ON` is opt-in and fails configuration unless a HIP compiler and an
explicit `CMAKE_HIP_ARCHITECTURES` target are available. CPU-only configuration never probes
or links ROCm.

## Installable package

`cmake --install` installs the C11/C++20 header, static or shared `structural_c_abi_v1`
library, CMake package targets and `structural-native-build.json`. The only public shared
library symbol remains `sa_get_api_v1`; ModelIR stays on ABI v1.1, track CPU occupies the ABI v1.2
slot, nonlinear static CPU occupies the ABI v1.3 slot and nonlinear NDTHA CPU occupies the ABI
v1.4 slot. ABI v1.5 uses offset 96 for bounded caller-owned NDTHA state advancement while keeping
the table at 128 bytes. v1.0-v1.4 table prefixes remain byte-compatible.

`structural_runtime_ffi` is the R3 temporary compatibility member while retaining the existing
package name, cdylib name, Python bridge output location and rollback lockfile. Its frozen
inventory is `compatibility/structural_runtime_ffi_v3.json`; workspace tests, neutral fixture
hashes and the release binary-symbol checker fail closed on drift. The language-neutral wire
contract serializes shared-storage identity as a boolean and never serializes process pointer
addresses. The C++ shared product library still exports only `sa_get_api_v1`, while all five
legacy Rust symbols remain in the compatibility cdylib. `mgt_hip_full_residual_ffi` remains
outside the workspace at H0; no compatibility cutover or removal is claimed.
