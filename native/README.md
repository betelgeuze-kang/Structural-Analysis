# Structural Native Workspace

This workspace is the staged Rust/C++ product boundary. Slice A implements the CPU-only
build graph and C ABI v1 foundation. Slice B adds strict Rust `ModelIR` v2 wire decoding,
Draft 2020-12 schema validation, Python-compatible canonical bytes and three SHA-256
identities. Slice C adds the ABI v1.1 typed descriptor, immutable C++ semantic owner,
deterministic validation report and caller-owned canonical snapshot. The safe Rust round-trip,
ABI v1.1 RAII owner and `structural-cli model validate` then complete Slice D and promote the
bounded ModelIR domain to C3. Later bounded slices add CPU ResultIR/ReportIR product composition,
restart, durable jobs and external comparison plus opt-in source-bound HIP C2 candidates;
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
sequential runtime cutover remain open. ABI v1.11 separately adds complete real-iteration
caller-owned Newton begin/advance state. The pointer-free `SASTAC01` checkpoint and public
`static-run`/`static-resume` ResultIR/ReportIR flow provide bounded CPU C4/C5 implementation
evidence without promoting the numerical family past C1; protected HIP C2, arbitrary ModelIR
assembly, durable-job integration and C6 remain open. The third R3 slice moves nonlinear NDTHA to a serial FP64 C++
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
continuation and deterministic export. A separate C5 loopback service slice exposes that exact
store through strict HTTP/1.1 with distinct static client/worker credentials and process-restart
evidence. Another bounded C5 slice strictly ingests hash-bound external result/source artifacts
and compares three global NDTHA quantities; its tracked source is a language-neutral Python C1
golden, not live solver evidence. Broader solver coverage, TLS/non-loopback and multi-tenant or
distributed API authority, live same-mesh external validation, HIP C2, broader Workbench, PDF/A/
accessibility/report output and C6 remain open. The legacy five-symbol ABI is unchanged.
`inplace_scale_f32` is frozen only as an alias/checksum compatibility probe used by the old
Python producer hook. It is not a structural product capability, receives no C0-C6 promotion and
will be removed with that hook after rollback coverage; backend receipts replace its telemetry.

ABI v1.6 adds one bounded ModelIR-to-NDTHA adapter at C3. It accepts exactly one vertical
fixed-guided Euler-Bernoulli frame3d element in global X, derives `12*E*Iy/L^3` stiffness,
`rho*A*L/2` mass and one selected floor FX load, and keeps damping ratio, elastic guard, solver
controls and acceleration explicit. C++ contract tests, an independent Python closed-form oracle
and the safe Rust wrapper bind the result to the existing zero-fallback CPU solver. This is not an
arbitrary topology reducer. A separate exact-profile C5 slice adds public ModelIR run/resume and an
outer C4 checkpoint binding the model's content/semantic/provenance identities, explicit adapter
request, generated native request and inner native state. The exact selectors, formulas,
ownership rules and authority boundaries are documented in
`docs/native/modelir-ndtha-adapter-v1.md` and
`docs/native/modelir-ndtha-product-e2e-v1.md`.

A separate bounded MGT C5 slice makes Rust the owner of original bytes, strict encoding
disposition, source hash, section/row inventory and loss diagnostics. Only the exact numeric
frame/truss subset is normalized to ModelIR and validated/snapshotted by the existing C++ owner;
the four tracked incomplete foundation fixtures remain blocked without invented properties. A
second exact fixture now reaches the Rust-native Workbench, preserving original MGT bytes, import
health and the C++ snapshot through real checkpoint/resume, comparison and native PDF generation.
This does not claim general MGT grammar, shell/load-combination/writeback or broader solver
authority. See
`docs/native/mgt-import-health-v1.md`.

ABI v1.7 adds a bounded CPU reference slice for explicit elastic/bilinear material state,
linear truss3d, Euler-Bernoulli frame3d and a three-node plane-stress membrane. The stateless
element operation publishes complete tangent, consistent mass, residual, JVP and recovery
buffers through one safe Rust wrapper; deterministic dense assembly remains a separate C++
reference target. An independent NumPy oracle compares every output value. Because HIP C2 is
still open, these capabilities remain at C1. See
`docs/native/reference-elements-assembly-v1.md`.

With `STRUCTURAL_ENABLE_HIP=ON`, `structural_elements_hip` evaluates the same five-profile FP64
reference batch and performs stable-order non-atomic dense assembly without an intermediate host
copy. Its live test records device/ROCm/compiler/source/device-library identity, transfer/sync/VRAM
metrics, deterministic repetition and fallback zero. Local hardware execution is a C2 candidate;
the manifest remains at C1 until the protected `native-hip-approved` dedicated workflow emits an
authoritative receipt. See `docs/native/reference-elements-hip-c2.md`.

`structural_solver_cpu` also owns a bounded canonical-CSR FP64 PCG reference path. It validates
strict row/column structure and symmetry, uses a Jacobi preconditioner, reports fixed numerical
status values, performs a true-residual convergence postcheck and never falls back. Four profiles
match an independent NumPy direct-solve oracle through C1. A product-owned fixed-tree FP64 HIP C2
candidate keeps the complete PCG state resident and has bitwise local live parity with fallback
zero. ABI v1.8 and a safe Rust wrapper implement the one-shot C3 boundary; ABI v1.10 adds complete
caller-owned PCG begin/advance state. A pointer-free `SAPCGC01` checkpoint and public
`linear-run`/`linear-resume` ResultIR/ReportIR flow provide bounded CPU C4/C5 implementation
evidence. Promotion remains C1 until the protected HIP receipt closes C2, and ModelIR sparse
assembly, durable jobs, PDF and C6 remain open. See `docs/native/sparse-linear-cpu-v1.md`,
`docs/native/sparse-linear-product-e2e-v1.md` and `docs/native/sparse-linear-hip-c2.md`.

The same CPU library now also owns a bounded dense symmetric generalized-eigen reference path.
It covers modal and linear-buckling systems through C1 with deterministic cyclic-Jacobi
decomposition, rigid/infinite-mode filtering, coordinate-axis canonical bases and independent
SciPy parity. ABI v1.9 consumes the two former table-reserved slots for failure-atomic modal and
buckling calls, with a checked safe reentrant Rust wrapper and installed-package coverage. This is
a C3 implementation candidate. A product-owned bounded HIP implementation now keeps the cyclic
Jacobi eigensolve, cluster canonicalization and result recovery resident, with a source-bound live
local C2 candidate and fallback zero. Sequential promotion remains C1 until the protected
`native-hip-approved` receipt exists; sparse extraction, restart and product E2E authority remain
open. See `docs/native/generalized-eigen-cpu-v1.md` and
`docs/native/generalized-eigen-hip-c2.md`.

The bounded nonlinear-static family also has an opt-in `structural_solver_hip` execution. One
device work item keeps all five model vectors, displacement/Newton state, constitutive assembly,
tridiagonal tangent solve, line search and result recovery resident for the full solve. The local
five-profile `gfx1030` run is bitwise repeatable, has exact CPU/HIP status, iteration,
plastic-story and backtracking parity, reports zero measured result error and fallback zero. It is
still only a C2 candidate until the protected runner verifies the same source SHA; no HIP ABI
selector or ROCm package authority follows from it. See
`docs/native/nonlinear-static-hip-c2.md`.

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

The bounded native MGT import-health command is:

~~~bash
cargo run --manifest-path native/Cargo.toml -p structural-cli -- \
  import mgt source.mgt --model-id imported-model-v1 --output-dir import-health \
  --require-normalized
~~~

Blocked inputs still publish their original bytes and complete loss/disposition report; the
optional policy flag then exits 2. A complete exact-profile input additionally publishes canonical
ModelIR, the C++ validation report and byte-identical C++ snapshot.

The exact normalized MGT profile can enter the native Workbench without a Python/Node bridge:

~~~bash
cargo run --manifest-path native/Cargo.toml -p structural-workbench -- \
  workflow-mgt native/tests/fixtures/mgt_import/workbench_fixed_guided_frame3d_x.mgt \
  native/tests/fixtures/mgt_import/workbench_fixed_guided_ndtha_request.json \
  --model-id workbench-mgt-fixed-guided-v1 \
  --external-result native/tests/fixtures/external_comparison/reference_oracle_ndtha_v1.json \
  --source-artifact native/tests/fixtures/solver_cpu/nonlinear_ndtha_one_story_elastic_python_c1.json \
  --workspace workbench-mgt --step-budget 1
~~~

The durable session revalidates the original MGT import and C++ snapshot on every reopen. This is
the bounded exact profile, not general MGT-to-analysis authority.

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

The bounded dense modal/linear-buckling product commands are:

~~~bash
cargo run --manifest-path native/Cargo.toml -p structural-cli -- \
  analysis eigen-run spectral-request.json --output-dir eigen-run
cargo run --manifest-path native/Cargo.toml -p structural-cli -- \
  analysis eigen-resume spectral-request.json eigen-run/checkpoint.eigcp \
  --output-dir eigen-resumed
~~~

The C4 artifact is an explicit validated-ready phase boundary because the native dense eigensolve
is atomic. Direct and resumed C5 artifacts are byte-identical without Python or Node lookup. The
generalized-eigen product document records the bounded authority and open protected HIP C2 gate.

The exact-profile ModelIR analysis commands are:

~~~bash
cargo run --manifest-path native/Cargo.toml -p structural-cli -- \
  analysis model-run model.json model-request.json --output-dir model-run
cargo run --manifest-path native/Cargo.toml -p structural-cli -- \
  analysis model-run model.json model-request.json --output-dir model-partial --step-budget 2
cargo run --manifest-path native/Cargo.toml -p structural-cli -- \
  analysis model-resume model.json model-request.json model-partial/checkpoint.ndcp \
  --output-dir model-resumed
~~~

The outer checkpoint prevents structurally or provenance-distinct models from sharing state even
when they derive equal scalar properties. Direct and resumed terminal directories contain the
same nine frozen artifacts; see `docs/native/modelir-ndtha-product-e2e-v1.md`.

The bounded external-comparison command is:

~~~bash
cargo run --manifest-path native/Cargo.toml -p structural-cli -- \
  comparison run result-ir.json external-result.json raw-solver-output \
  --output-dir comparison --require-pass
~~~

Live external evidence additionally requires `--executable-artifact`. Exact source and executable
bytes are verified before comparison; see `docs/native/external-comparison-v1.md` for the
non-promoting authority boundary.

The bounded native PDF command is:

~~~bash
cargo run --manifest-path native/Cargo.toml -p structural-cli -- \
  report render-pdf result-ir.json report-ir.json report.md \
  --output-dir pdf-report
~~~

The renderer re-projects and verifies all three inputs before emitting a deterministic A4 PDF and
self-hashed receipt. It invokes no external renderer; see `docs/native/pdf-report-v1.md` for the
PDF/A, accessibility and broader-report boundary.

The bounded native job service command is:

~~~bash
chmod 600 client.token worker.token
cargo run --manifest-path native/Cargo.toml -p structural-cli -- \
  service serve --listen 127.0.0.1:8080 --store native-jobs \
  --client-token-file client.token --worker-token-file worker.token
~~~

It refuses non-loopback binds and exposes only the bounded durable submit/poll/cancel/work-once
and immutable artifact routes. See `docs/native/job-service-api-v1.md` for exact HTTP, credential,
restart and authority boundaries.

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
v1.4 slot. ABI v1.5 uses offset 96 for bounded caller-owned NDTHA state advancement. ABI v1.6
uses the former reserved slot at offset 104 for the bounded ModelIR-to-NDTHA adapter. ABI v1.7
uses the next append-only slot at offset 112 for bounded CPU reference elements. ABI v1.8 adds
canonical-CSR sparse PCG at offset 120. ABI v1.9 consumes offsets 128 and 136 for bounded modal
and linear-buckling CPU operations. ABI v1.10 appends sparse PCG begin and advance operations at
offsets 144 and 152. ABI v1.11 appends nonlinear-static Newton begin and advance operations at
offsets 160 and 168. ABI v1.12 preserves that 176-byte prefix and appends one backend-selector
slot at offset 176; the current table is 184 bytes. The selected CPU/HIP table owns the bounded
full-residual context, telemetry, and no-fallback device choice. Existing callers may continue to provide
their older struct size, and every request exposes later-minor slots as null.

`structural_runtime_ffi` is the R3 temporary compatibility member while retaining the existing
package name, cdylib name, Python bridge output location and rollback lockfile. Its frozen
inventory is `compatibility/structural_runtime_ffi_v3.json`; workspace tests, neutral fixture
hashes and the release binary-symbol checker fail closed on drift. The language-neutral wire
contract serializes shared-storage identity as a boolean and never serializes process pointer
addresses. Its compatibility implementation is physically split into the neutral `contracts`
adapter, frozen numerical `runtime`, raw-pointer/export `ffi`, and public `lib` façade; ownership
checks reject boundary regression. The C++ shared product library still exports only `sa_get_api_v1`, while all five
legacy Rust symbols remain in the compatibility cdylib. `mgt_hip_full_residual_ffi` is now the
H3 workspace compatibility adapter: it resolves only `sa_get_api_v1`, converts the frozen
positional ABI to v1.12 descriptors, and delegates context ownership to the product library.
The four retained frame/shell/full-residual replay and resident-worker executables are also
host-only compatibility consumers: they link `structural_c_abi_v1`, resolve no symbols manually,
and contain no HIP kernels or runtime allocation/copy calls. Hosted CTest exercises their CPU
self-test while the dedicated lane is configured to exercise the same binaries on HIP.
H4 remains a C2 candidate until an approved-device receipt; no legacy removal is claimed.
