# Structural Native Workspace

This workspace is the staged Rust/C++ product boundary. Slice A implements the CPU-only
build graph and C ABI v1 foundation. Slice B adds strict Rust `ModelIR` v2 wire decoding,
Draft 2020-12 schema validation, Python-compatible canonical bytes and three SHA-256
identities. Slice C adds the ABI v1.1 typed descriptor, immutable C++ semantic owner,
deterministic validation report and caller-owned canonical snapshot. The safe Rust round-trip,
ABI v1.1 RAII owner and `structural-cli model validate` then complete Slice D and promote the
bounded ModelIR domain to C3. Frame Alpha appends ABI v1.2 with a bounded CPU-only linear
Timoshenko Frame3D compile/solve path; ABI v1.3 adds a load-case operation for uniform
initial-member-local QX/QY/QZ force loads. Raw and safe Rust bindings plus independent Python
six-mode, rotated multi-member and closed-form QX/QY/QZ uniform-load cantilever parity remain C1 evidence. A strict `structural-runtime` adapter now
accepts the exact linear Timoshenko subset of `engine_v2_phase0_linear_3d` ModelIR, converts
canonical SI input to the native kN kernel and returns a hash-bound authority-limited SI result.
The bounded CLI now promotes that exact profile to a strict, canonical, hash-bound `ResultIR`,
projects a source-bound deterministic `ReportIR`, and emits standalone HTML. HIP parity, restart,
PDF, comparison and Workbench execution remain unimplemented. Before ResultIR promotion, Rust now
independently reconstructs every member-local end-force vector from the adapted geometry, section,
local axis and solved displacement and fails closed on drift from the C++ recovery. A C0
Workbench v2 surface can consume the bounded artifacts read-only without promoting their authority;
`capabilities.json` records those boundaries.

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

The Frame Alpha surface is intentionally narrower than a product analysis workflow. It accepts
2-16 nodes, 1-32 prismatic members and no more than 60 free equations; supports fixed restrained
DOFs, local-axis roll, linear elastic Timoshenko stiffness, nodal loads and uniform
initial-member-local QX/QY/QZ force loads; and returns global displacement, global reaction and
member-local end-force vectors including fixed-end effects. It rejects duplicate/parallel members,
disconnected graphs, prescribed nonzero supports, releases, offsets, self weight, nonuniform or
member-point loads, nonlinear behavior and oversized models. The load-case API is reached through
`Api::load_frame3d_member_loads()` and a
unique Rust RAII model owner. These C0/C1 checks do not establish HIP parity, broad engineering
validation, public Workbench execution or release approval.

`Runtime::analyze_linear_frame3d` composes the native ModelIR validator with that surface. It
requires the canonical SI/global-axis/six-DOF profile and exact
`linear_timoshenko_frame3d` formulation; Euler-Bernoulli is not silently substituted. Nonzero
prescribed values, self weight, releases, offsets, physics extensions and unsupported feature
families fail closed. The returned vectors are converted back to N/Nm and bound to all three
ModelIR hashes. `Runtime::analyze_linear_frame3d_result_ir` additionally requires the free-residual
and global force/moment equilibrium gates, a bounded independent Rust member-force recovery replay,
zero fallback/regularization, and promotes only the fixed `bounded_candidate` authority profile.
The replay is a separate cross-language implementation gate, not external code-to-code or
experimental validation. It grants no design, code, commercial or release authority.

The bounded analysis command writes exactly one selected artifact to stdout and never chooses an
implicit report path:

~~~bash
cargo run --manifest-path native/Cargo.toml -p structural-cli -- \
  model analyze-frame3d frame-alpha.model-ir.v2.json \
  --load-pattern LC1 --result-id frame-alpha.LC1 --output result-ir

cargo run --manifest-path native/Cargo.toml -p structural-cli -- \
  model analyze-frame3d frame-alpha.model-ir.v2.json \
  --load-pattern LC1 --result-id frame-alpha.LC1 \
  --report-id frame-alpha.LC1.report --output report-ir

cargo run --manifest-path native/Cargo.toml -p structural-cli -- \
  model analyze-frame3d frame-alpha.model-ir.v2.json \
  --load-pattern LC1 --result-id frame-alpha.LC1 \
  --report-id frame-alpha.LC1.report --output html > frame-alpha.html
~~~

`ResultIR` and `ReportIR` reject duplicate JSON keys, stale hashes and authority-profile drift.
The HTML uses fixed numeric rendering and keeps all limitations visible. Report comparison remains
`not_evaluated`; HTML is deterministic presentation, not PDF or engineering validation evidence.

Workbench v2 accepts an optional same-origin ResultIR URL and an optional source-bound ReportIR URL:

~~~text
VITE_NATIVE_FRAME_RESULT_URL=/evidence/native-frame-result.json
VITE_NATIVE_FRAME_REPORT_URL=/evidence/native-frame-report.json
~~~

Deployments may provide the equivalent `window.__STRUCTURAL_WORKBENCH_CONFIG__` fields
`nativeFrameResultUrl` and `nativeFrameReportUrl` before the application starts. Cross-origin URLs
are rejected. If both URLs are configured, the pair is atomic: missing, malformed, stale,
transplanted or authority-promoted input makes the whole pair unavailable. The browser repeats the
strict duplicate-key, exact-schema/profile, canonical-hash, source/gate and deterministic-extrema
checks before displaying displacement, reaction and member-local end-force rows. This C0 typed
consumer neither submits nor reruns analysis; it establishes no durable job, comparison, PDF,
browser-side recovery reconstruction, design, commercial, release or aggregate Workbench E2E
authority. It requires and displays the source ResultIR's independent Rust recovery gate.

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
library symbol remains `sa_get_api_v1`; ABI v1.1 ModelIR, ABI v1.2 Frame3D and ABI v1.3 uniform
member-load operations are negotiated through its append-only 128-byte table.

The old probe crates remain outside this workspace. Their preservation and next migration
owner are recorded in `compatibility-owners.json`; no legacy symbol is removed by Slice A.
