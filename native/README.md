# Structural Native Workspace

This workspace is the staged Rust/C++ product boundary. Slice A implements the CPU-only
build graph and C ABI v1 foundation. Slice B adds strict Rust `ModelIR` v2 wire decoding,
Draft 2020-12 schema validation, Python-compatible canonical bytes and three SHA-256
identities. Slice C adds the ABI v1.1 typed descriptor, immutable C++ semantic owner,
deterministic validation report and caller-owned canonical snapshot. The safe Rust round-trip,
ABI v1.1 RAII owner and `structural-cli model validate` then complete Slice D and promote the
bounded ModelIR domain to C3. Analysis, restart, ResultIR/ReportIR product E2E and HIP remain
unimplemented; `capabilities.json` records that boundary. R1 additionally includes the existing
`structural_runtime_ffi` package as a temporary compatibility member. Its ABI v3 layouts, five
exports, status codes and bounded numerical vectors are frozen without transferring solver
authority to the product crates.

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
library symbol remains `sa_get_api_v1`; ABI v1.1 operations are negotiated through its table.

`structural_runtime_ffi` is now the R1 temporary workspace member while retaining the existing
package name, cdylib name, Python bridge output location and rollback lockfile. Its frozen
inventory is `compatibility/structural_runtime_ffi_v3.json`; the workspace test and binary-symbol
checker fail closed on drift. `mgt_hip_full_residual_ffi` remains outside the workspace at H0.
No legacy symbol is removed or exposed through `sa_get_api_v1` by R1.
