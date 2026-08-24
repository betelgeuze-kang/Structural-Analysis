# Structural Native Workspace

This workspace is the staged Rust/C++ product boundary. Slice A implements the CPU-only
build graph and C ABI v1 foundation. Slice B adds strict Rust `ModelIR` v2 wire decoding,
Draft 2020-12 schema validation, Python-compatible canonical bytes and three SHA-256
identities. Slice C adds the ABI v1.1 typed descriptor, immutable C++ semantic owner,
deterministic validation report and caller-owned canonical snapshot. The safe Rust round-trip,
ABI v1.1 RAII owner and `structural-cli model validate` then complete Slice D and promote the
bounded ModelIR domain to C3. Frame Alpha appends ABI v1.2 with a bounded CPU-only linear
Timoshenko Frame3D compile/solve path; ABI v1.3 adds a load-case operation for uniform
initial-member-local QX/QY/QZ force loads, and ABI v1.4 activates bounded RX/RY/RZ member-end
release masks. ABI v1.5 appends sparse finite global node-to-member-end rigid-offset rows without
changing the legacy input prefix. Raw and safe Rust bindings plus independent Python six-mode,
rotated multi-member, rigid-offset-transform, closed-form QX/QY/QZ uniform-load cantilever, and released-member static-condensation parity remain C1 evidence. A strict `structural-runtime` adapter now
accepts the exact linear Timoshenko subset of `engine_v2_phase0_linear_3d` ModelIR, converts
canonical SI input to the native kN kernel, derives ModelIR self weight from finite material
density, section area and the fixed standard gravity `9.80665 m/s^2`, and returns a hash-bound
authority-limited SI result. The same adapter deterministically flattens bounded nested linear load
combinations into pattern factors and sends one combined native load case without duplicating the
stiffness solve.
An additional three-case differential pack drives that complete ModelIR/Rust/C++/ResultIR path
against the tracked Python Frame3D reference for rotated rigid offsets with mixed loads, condensed
rotational releases, and nested combinations containing nodal, uniform and self-weight terms. It
binds the exact native binary and Python sources and remains bounded implementation verification,
not external validation, CPU/HIP parity or release evidence.
The bounded CLI now promotes that exact profile to a strict, canonical, hash-bound `ResultIR`,
projects a source-bound deterministic `ReportIR`, emits standalone HTML, and strictly replays a
persisted ResultIR to ReportIR/HTML. A source-tree ReportLab tool can project that verified replay
and an optional CLI-replayed ComparisonIR to a deterministic PDF plus canonical receipt. HIP parity,
restart, native-binary/packaged PDF and durable or browser-executed packaged Workbench E2E remain
unimplemented.
Before ResultIR promotion, Rust now
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
DOFs, local-axis roll, linear elastic Timoshenko stiffness, RX/RY/RZ end releases, finite global rigid end offsets, nodal loads and uniform
initial-member-local QX/QY/QZ force loads; and returns global displacement, global reaction and
member-local end-force vectors including fixed-end effects. It rejects duplicate/parallel members,
disconnected graphs, prescribed nonzero supports, translational releases, zero-effective-length offsets, nonuniform or
member-point loads, nonlinear behavior and oversized models. The load-case API is reached through
`Api::load_frame3d_offsets()` and a
unique Rust RAII model owner. These C0/C1 checks do not establish HIP parity, broad engineering
validation, public Workbench execution or release approval.

`Runtime::analyze_linear_frame3d` composes the native ModelIR validator with that surface. It
requires the canonical SI/global-axis/six-DOF profile and exact
`linear_timoshenko_frame3d` formulation; Euler-Bernoulli is not silently substituted. Nonzero
prescribed values, translational releases, zero-effective-length offsets, physics extensions and unsupported feature
families fail closed. A ModelIR self-weight vector is interpreted as dimensionless global-axis
multipliers of standard gravity; each member's `density_kg_m3 * area_m2` mass per length is projected
to its offset-aware initial local basis and combined with explicit uniform loads before the native
solve. A caller must select exactly one pattern or combination; combinations are limited to 256
definitions and 4096 recursively expanded terms, require the ModelIR-validated acyclic linear graph,
and fail closed on factor or load accumulation overflow. ResultIR and ReportIR carry mutually
exclusive nullable `load_pattern_id` and `load_combination_id` bindings. The returned vectors are converted back to N/Nm and bound to all three
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
  --load-combination ULS1 --result-id frame-alpha.ULS1 --output result-ir

cargo run --manifest-path native/Cargo.toml -p structural-cli -- \
  model analyze-frame3d frame-alpha.model-ir.v2.json \
  --load-pattern LC1 --result-id frame-alpha.LC1 \
  --report-id frame-alpha.LC1.report --output report-ir

cargo run --manifest-path native/Cargo.toml -p structural-cli -- \
  model analyze-frame3d frame-alpha.model-ir.v2.json \
  --load-pattern LC1 --result-id frame-alpha.LC1 \
  --report-id frame-alpha.LC1.report --output html > frame-alpha.html

cargo run --manifest-path native/Cargo.toml -p structural-cli -- \
  model analyze-frame3d frame-alpha.model-ir.v2.json \
  --load-pattern LC1 --result-id frame-alpha.LC1 \
  --report-id frame-alpha.LC1.report --output workbench-bundle \
  --output-dir published/frame-alpha.LC1

cargo run --manifest-path native/Cargo.toml -p structural-cli -- \
  result report-frame3d published/frame-alpha.LC1/result-ir.json \
  --report-id frame-alpha.LC1.replayed-report --output report-ir

python3 scripts/render_native_frame3d_pdf.py \
  --structural-cli native/target/release/structural-cli \
  --result-ir published/frame-alpha.LC1/result-ir.json \
  --report-id frame-alpha.LC1.pdf-report \
  --out output/pdf/frame-alpha-LC1.pdf
~~~

`ResultIR` and `ReportIR` reject duplicate JSON keys, stale hashes and authority-profile drift.
The persisted replay command applies those same Rust checks without rerunning ModelIR analysis. The
PDF command accepts no numerical authority of its own: it requires successful CLI replay and writes
no-overwrite PDF/receipt outputs whose hashes and bounded authority are explicit. It is source-tree
tooling, not part of the portable CLI distribution or a Workbench action. The workstation delivery
builder packages this exact pair only after parsing the PDF and replaying the receipt's strict
schema, hash, byte-length, page-count and authority binding; it never substitutes a placeholder PDF.
The bundle command performs one analysis and creates a new directory without overwrite. It writes
canonical `model-ir.json`, `result-ir.json`, `report-ir.json` and deterministic `report.html`, then publishes
`manifest.json` last with exact byte lengths, SHA-256 identities and ResultIR/ReportIR bindings.
An existing directory or any incomplete write fails closed; the completion manifest is artifact
handoff, not a durable job or Workbench execution claim.

The bounded native runtime also exposes an explicitly single-host, one-attempt filesystem job
profile. Submission stores canonical ModelIR, an immutable self-hashed request, revision-zero event
and queued view without overwrite. `run` appends started and terminal hash-chain events, publishes
the same Workbench bundle, and atomically replaces only the materialized view. `inspect` verifies the
request, complete event chain, view bindings and terminal manifest reference:

~~~bash
cargo run --manifest-path native/Cargo.toml -p structural-cli -- \
  job submit-frame3d frame-alpha.model-ir.v2.json \
  --store jobs --job-id job_0123456789abcdef0123456789abcdef \
  --load-pattern LC1 --result-id frame-alpha.LC1 \
  --report-id frame-alpha.LC1.report

cargo run --manifest-path native/Cargo.toml -p structural-cli -- \
  job run job_0123456789abcdef0123456789abcdef --store jobs

cargo run --manifest-path native/Cargo.toml -p structural-cli -- \
  job inspect job_0123456789abcdef0123456789abcdef --store jobs
~~~

New direct CLI submissions use `filesystem_append_only_single_host.v2`, not the Python nonlinear
Frame2D service contract. Legacy v1 jobs remain available for exact strict replay but cannot be
mutated or cancelled. The store can append a distinct `Cancelled` event/view for a queued or
running v2 job, but it does not own or prove process termination. By itself it has no process
isolation, durable or cooperative cancellation, resume, stale-lock/crash recovery, multi-host
scheduling, design authority or release authority. An execution failure becomes a terminal failed
event/view without bundle authority. A process or storage failure during a transition can leave a
fail-closed running or partial directory that requires manual diagnosis; neither version claims
automatic recovery.

For source-tree Workbench integration, the CLI can serve a built `dist/` directory and the same
bounded job store on one loopback origin:

~~~bash
VITE_NATIVE_FRAME_SUBMISSION_URL=/api/v1/frame3d/jobs npm run build
cargo run --manifest-path native/Cargo.toml -p structural-cli -- \
  workstation serve --store jobs --workbench dist --listen 127.0.0.1:8787 \
  --worker-timeout-seconds 300
~~~

The browser preserves exact ModelIR text in the versioned submission envelope, submits and runs one
job through a synchronous request backed by a bounded child `structural-cli` process, polls the
strict materialized view over a concurrent same-origin request while that run is in flight, then
passes only the terminal view URL to the existing strict bundle consumer. The host admits at most 16
concurrent requests, rejects a duplicate active worker for the same job and joins accepted request
threads during normal bounded shutdown. An explicit same-origin cancel request can terminate only
the registered active loopback child: the host checks that it is still running, kills and reaps it,
then appends terminal `Cancelled` evidence without bundle authority. A queued v2 job can also be
cancelled before a worker starts. This is not a background queue or a durable/cooperative
cancellation contract.
Non-loopback bind, cross-origin mutation, unknown routes/artifacts, path traversal, duplicate HTTP
headers, transfer encoding and oversized bodies fail closed. The worker boundary contains a solver
process exit and enforces a bounded timeout. If the isolated worker had reached the strictly replayed
revision-1 Running state, a timeout/process/status failure appends a revision-2 Failed event/view
without bundle authority. Queued, terminal, corrupt and partial states are not rewritten. This is
failure finalization, not retry/resume, stale-lock cleanup or durable crash recovery; `run.lock`
remains. It is not a privilege sandbox, CPU/memory resource limiter, browser-executed packaged
Workbench receipt, external validation or release authority. See
`docs/native/frame-alpha-workstation-host.md`.

The separate workstation distribution v2 can package a production Workbench static build configured
for `/api/v1/frame3d/jobs` together with the release CLI. Its extracted smoke serves the exact index,
one referenced asset and the v2 capability document from the packaged binary. It does not launch a
browser or establish clean-machine installation, so browser-executed submit/run/result replay remains
an open product E2E boundary.

## Portable CLI distribution candidate

The native PR gate is configured to build source-bound Linux and Windows ZIP candidates containing the release
`structural-cli`, an analysis-ready Frame Alpha ModelIR example, strict manifest/smoke schemas,
bounded workflow instructions and the project license. The archive builder requires an exact clean
Git commit/tree binding, fixes ZIP ordering, timestamps and modes, records every payload byte length
and SHA-256, and refuses overwrite. Its verifier rejects unsafe or duplicate entries and hash drift,
extracts to a new temporary directory, then uses only the extracted binary to validate the example
and publish a complete Workbench bundle.

The same gate also builds a separate workstation distribution v2 after compiling the production
Workbench with the exact same-origin submission URL. That ZIP hash-binds the static build, release
CLI and v2 lifecycle schemas. Its extracted smoke repeats validate/analyze, starts the packaged
loopback host and byte-checks the index, one referenced asset and the v2 capability route.

This is same-runner portable-directory verification, not an installer or clean-machine receipt.
The per-platform artifacts do not establish Linux/Windows result parity, code signing, SBOM,
offline dependency closure, browser execution, crash-free installation or release authority.

## Bounded external comparison

The CLI can compare one canonical bounded ResultIR with one strict external ReferenceIR and emit
either hash-bound ComparisonIR or deterministic standalone HTML:

~~~bash
cargo run --manifest-path native/Cargo.toml -p structural-cli -- \
  result compare-frame3d result-ir.json external-reference.json \
  --comparison-id frame-alpha.LC1.external --output comparison-ir
~~~

The reference must bind the exact model content hash and load identity, cover every native
node/member exactly once, and declare the fixed global-node/member-local axes, sign convention,
units and original export SHA-256. The contract normalizes m/mm and N/kN/N*m/kN*m before fixed
component-level tolerance evaluation. A tolerance failure returns nonzero with an auditable
artifact; malformed, partial or transplanted inputs produce no ComparisonIR. See
`docs/native/frame3d-external-comparison.md`.

The mapping and export hash remain operator declarations. No real SAP2000, MIDAS GEN, OpenSees or
CalculiX receipt is attached, `external_validation` remains `not_established`, and this path does
not grant design, commercial or release authority. ReportIR v1 remains `not_evaluated` for
comparison; Workbench comparison remains a separate gate. The optional source-tree PDF projection
is documented in `docs/native/frame3d-pdf-report.md` and does not change validation authority.

The HTML uses fixed numeric rendering and keeps all limitations visible. Report comparison remains
`not_evaluated`; HTML is deterministic presentation, not engineering validation evidence.

Workbench v2 accepts an optional same-origin ResultIR URL and an optional source-bound ReportIR URL:

~~~text
VITE_NATIVE_FRAME_RESULT_URL=/evidence/native-frame-result.json
VITE_NATIVE_FRAME_REPORT_URL=/evidence/native-frame-report.json
~~~

Alternatively, the two direct URLs can be replaced by one completed bundle manifest URL:

~~~text
VITE_NATIVE_FRAME_BUNDLE_URL=/evidence/frame-alpha.LC1/manifest.json
~~~

Or a deployment can expose the read-only materialized view of one native job:

~~~text
VITE_NATIVE_FRAME_JOB_URL=/evidence/jobs/job_0123456789abcdef0123456789abcdef/view.json
~~~

Job, bundle and direct URLs are mutually exclusive. For a job URL, Workbench treats queued/running
as pending without result authority and failed as terminal without a bundle. Only a strictly valid
succeeded view is followed, and its manifest byte length and SHA-256 must match before bundle
validation begins. Workbench then verifies the fixed artifact paths, media
types, byte lengths, SHA-256 identities, ResultIR/ReportIR hashes and cross-bindings before display;
it also fetches and verifies the HTML artifact even though it does not execute it.

Deployments may provide the equivalent `window.__STRUCTURAL_WORKBENCH_CONFIG__` fields
`nativeFrameResultUrl`, `nativeFrameReportUrl`, `nativeFrameBundleUrl` or the mutually exclusive
`nativeFrameJobUrl`
before the application starts. Cross-origin URLs
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
library symbol remains `sa_get_api_v1`; ABI v1.1 ModelIR, ABI v1.2 Frame3D, ABI v1.3 uniform
member-load operations, ABI v1.4 rotational end-release capability and ABI v1.5 rigid end-offset
capability are negotiated through its
append-only 128-byte table and versioned descriptors.

The old probe crates remain outside this workspace. Their preservation and next migration
owner are recorded in `compatibility-owners.json`; no legacy symbol is removed by Slice A.
