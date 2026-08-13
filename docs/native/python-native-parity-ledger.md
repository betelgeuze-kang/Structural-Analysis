# Python to Native Parity Ledger

Status: migration control document

Baseline commit: 14c25f4ddb72eb64cab689e6d0183b056025dca3

Baseline inventory: Python 2,002 files, Rust 2 files, C++/HIP 13 files

이 원장은 기존 Python path를 native replacement보다 먼저 제거하거나, probe 수준
native 코드를 product authority로 승격하지 못하게 하는 cutover 기준이다. 파일 수는
진척률이 아니며 baseline 변화 시 다시 측정한다.

Until a domain closes C6, Python remains authoritative oracle and rollback evidence for every
family not explicitly cut over by a narrower row below.

## 1. Cutover gate

각 domain은 적용 가능한 gate를 왼쪽부터 순서대로 통과한다.

| Gate | 필수 증거 |
| --- | --- |
| C0 native unit | Rust/C++ unit, invalid input, boundary와 failure atomicity |
| C1 CPU oracle parity | 동일 versioned fixture에서 Python oracle와 값, status, error code, canonical bytes/hash 비교 |
| C2 CPU/HIP parity | 수치 domain은 deterministic FP64 CPU/HIP parity, fallback 0, transfer/residency receipt |
| C3 Rust FFI integration | safe wrapper, ownership/lifetime, layout, panic/exception와 concurrency test |
| C4 checkpoint/restart | model/state/execution hash binding, exact restart, cancel/crash recovery |
| C5 bounded product E2E | public CLI/API 또는 Workbench 경로에서 input부터 ResultIR/ReportIR까지 |
| C6 decommission | no native-to-Python product dependency, rollback package, deprecation release와 removal audit |

C2가 물리적으로 적용되지 않는 parser/report domain은 N/A로 조용히 건너뛰지 않는다.
해당 domain row에 이유와 대체 cross-language deterministic gate를 기록해야 한다.
solver, assembly, element/material와 result recovery에는 C2가 항상 필수다.

## 2. Domain ledger

### D1. ModelIR, units and strict validation

- Current Python authority
  - src/structural_analysis/model_ir/types.py
  - src/structural_analysis/model_ir/loader.py
  - src/structural_analysis/model_ir/validation.py
  - src/structural_analysis/schemas/model_ir_v2.schema.json
- Target owner
  - Rust structural-contracts: strict JSON, canonical bytes와 hashes
  - C++ structural_model_ir: typed model, units와 semantic validation
- Oracle fixtures/tests
  - tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json
  - examples/*.model-ir.v2.json
  - tests/test_model_ir_v2_contract.py
  - tests/test_native_model_ir_rust_parity.py
  - tests/test_bounded_planar_model_ir_adapter.py
- Stable errors to preserve
  - duplicate JSON key, schema_validation_error, dangling_reference, duplicate_id
  - non-finite number, invalid unit scale, load_combination_cycle
  - analysis-not-ready blocking unsupported feature
- Required gates: C0, C1, C3, C5, C6
- C2 disposition: JSON/semantic validation은 backend-independent이므로 byte/hash와
  Rust/C++ deterministic parity가 대체 gate다. 생성된 model descriptor를 소비하는
  operator부터 C2가 필수다.
- State: D1 is C3. Rust wire/schema/canonical identity and the C++ typed semantic/snapshot core
  are connected through the ABI v1.1 safe RAII wrapper. Eight tracked positive fixtures plus
  semantic/blocker negatives have zero-diff Python/C++ issue code/path, readiness, blocker and
  three-hash parity; snapshot bytes are re-parsed and identity-checked in Rust. ABI v1.6
  additionally connects one exact
  fixed-guided one-story frame3d global-X reduction through C3: C++ owns structural derivation,
  an independent Python closed-form oracle owns C1 parity, and the safe Rust wrapper proves a
  zero-fallback elastic CPU solve. A separate exact-profile product slice reaches C5: strict
  `model-run`/`model-resume` bind all three ModelIR identities, the explicit adapter request, the
  generated request and inner C4 state, then emit nine bitwise-identical terminal artifacts in an
  environment with no Python/Node lookup. Aggregate D1 remains C3 because this is not arbitrary
  ModelIR solver readiness; broader topology, generated-operator HIP C2 and C6 remain open. Python
  remains the broader ModelIR oracle and rollback owner.

### D2. Elements and materials

- Current Python authority
  - src/structural_analysis/elements/
  - src/structural_analysis/materials/
- Target owner
  - C++ structural_elements와 structural_materials
  - HIP element/material kernels는 같은 constitutive source/epoch adapter를 사용
- Oracle fixtures/tests
  - tests/test_corotational_frame3d_global.py
  - tests/test_stateful_corotational_frame3d_materials.py
  - tests/test_stateful_corotational_fiber_frame3d.py
  - tests/test_mgt_frame_material_nonlinear_tangent.py
  - tests/test_mgt_shell_material_nonlinear_tangent.py
  - tests/test_native_reference_elements_python_parity.py
- Stable errors to preserve
  - unsupported formulation/material, invalid geometry/property, trial-state conflict
  - constitutive nonconvergence와 rollback failure
- Required gates: C0 through C6, including CPU/HIP residual/tangent/recovery parity.
- State: aggregate D2 remains partial, with one bounded CPU reference slice at C1. C++20 now owns
  explicit elastic-isotropic validation, one epoch-checked bilinear uniaxial
  trial/commit/rollback point, linear truss3d, Euler-Bernoulli frame3d and a three-node
  plane-stress membrane. The same element response source emits tangent, consistent mass,
  residual, JVP and recovery; an independent NumPy oracle compares every value. ABI v1.7 and a
  safe reentrant Rust wrapper provide failure-atomic caller-owned integration with CPU fallback
  zero. A product-owned FP64 HIP batch now evaluates the complete five-profile CPU matrix and
  reports zero-error local live parity, bitwise deterministic repetition, resident
  element/operator buffers, one final synchronization and fallback zero on `gfx1030`. This is a
  C2 candidate rather than promotion evidence until the protected `native-hip-approved` workflow
  emits its source/device-bound receipt, so the sequential cutover remains C1. General
  corotational/fiber/material families, shell bending/drilling, state checkpoint, product E2E and
  C6 remain open. Existing unrelated partial HIP probes are not product authority.

### D3. Assembly and operator graph

- Current Python authority
  - src/structural_analysis/assembly/
  - src/structural_analysis/engine_v2/assembly_backend/
- Target owner
  - C++ structural_assembly
  - HIP operator/reduction/sparse targets
- Oracle fixtures/tests
  - tests/test_mgt_physical_residual_assembly.py
  - tests/test_mgt_equilibrium_shell_assembly.py
  - tests/test_mgt_residual_jacobian_consistency_probe.py
  - tests/test_engine_v2_hip_current_tangent_operator.py
  - tests/test_native_reference_elements_python_parity.py
  - tests/test_native_model_ir_assembly_python_parity.py
- Stable errors to preserve
  - DOF/reference/layout mismatch, CSR invalid, state epoch mismatch
  - fallback forbidden, backend unavailable와 device mismatch
- Required gates: C0 through C6.
- State: aggregate D3 remains C0, with one bounded dense and constraint-reduced canonical-CSR
  reference assembly slice at C1. C++20 validates unique stable element indices, local
  matrix/vector shape, finite values, global DOF references and unique bounded homogeneous
  constraints, then scatters tangent, consistent mass, residual and JVP in stable-index order.
  It also emits sorted active-DOF mapping and canonical CSR structure independent of contribution
  and constraint input order. The complete dense three-DOF/two-contribution output and an irregular
  constrained three-element CSR graph match an independent NumPy oracle. A separate C++
  composition target now resolves every element in a bounded typed ModelIR linear
  frame3d/truss3d graph, maps six canonical DOFs per node, selects one direct nodal-load pattern,
  and emits reduced tangent, mass, internal/external/equilibrium residual, JVP and per-element
  recovery. Its three-node mixed graph independently matches NumPy for all 43 structural entries.
  This is not general ModelIR assembly: nonzero constraints, offsets/releases, self-weight,
  combinations/stages, shell/nonlinear formulations, reordering, stateful epoch propagation, Rust
  FFI and product integration remain open. The same product-owned HIP candidate assembles a 38-DOF
  overlapping five-element graph without atomics in stable order and matches CPU with zero error
  while retaining element outputs on device; protected-runner C2 promotion remains open.
  Probe/replay and Python-managed HIPRTC paths are not product authority.

### D4. Linear, nonlinear, eigen and dynamic solvers

- Current Python authority
  - src/structural_analysis/solvers/
  - src/structural_analysis/analyses/
  - src/structural_analysis/dynamics/
  - src/structural_analysis/api/frame3d_direct_control.py
- Target owner
  - C++ structural_solver_cpu and structural result recovery
  - HIP resident sparse/Krylov/Newton execution
  - Rust structural-runtime owns execution lifecycle only
- Oracle fixtures/tests
  - tests/test_bounded_frame3d_direct_control_api.py
  - tests/test_mgt_full_frame_6dof_sparse_equilibrium.py
  - tests/test_engine_v2_cpu_fgmres_checkpoint_v1.py
  - tests/test_transient_checkpoint_authority.py
- Stable errors to preserve
  - convergence/status taxonomy, residual/increment gate, singularity
  - unsupported scope, cancellation, checkpoint mismatch와 forbidden fallback
- Required gates: C0 through C6.
- State: D4 remains C0 overall. The bounded 9-node midpoint-load `track_point_load` support/theory
  matrix is C1 with a deterministic
  `structural_solver_cpu` reference kernel, ABI v1.2 caller-owned operation and safe Rust wrapper;
  the legacy five-symbol Rust cdylib is unchanged. C++ matches the separate language-neutral
  Python product golden within `1e-15`, with CPU backend and fallback count 0. The frozen legacy
  fixture still matches iteration, residual, displacement and interior rotation; its endpoint
  convention differs by `3.436580346133486e-5 rad` and is recorded as an intentional endpoint-only
  compatibility divergence. HIP C2, the remaining solver families, checkpoint/restart and product
  E2E and broader node/load-position parity remain open.
- The bounded `nonlinear_static` story-frame slice is C1. Its serial FP64 C++ Newton kernel,
  ABI v1.3 caller-owned five-input/one-output contract and safe Rust wrapper match an independent
  NumPy dense-matrix oracle over five cases: 1/3-story topology, elastic/plastic response,
  mixed-sign loads, P-delta and line-search backtracking. Displacement uses `1e-12 m`, residual
  `1e-7 N` and base shear `1e-10 kN` absolute tolerances; iteration/plastic/backtrack fields and
  nonconvergence taxonomy also match. The frozen legacy 3-story fixture remains byte-identical to
  one product golden. ABI v1.11 adds complete caller-owned real-iteration Newton begin/advance
  state through a safe Rust wrapper. Separate bounded CPU implementation slices now cover C4 and
  C5: `SASTAC01` binds exact request/model/Newton-state/execution identities, and public
  static-run/static-resume publish typed active/failure receipts or self-hashed
  ResultIR/ReportIR/Markdown artifacts with direct/resumed byte identity and Python/Node lookup
  removed. A product-owned bounded single-thread HIP candidate now keeps model/Newton/tangent/
  recovery buffers resident and covers the same five profiles plus numerical exhaustion. Local
  `gfx1030` execution has bitwise repeats, exact status/iteration/plastic/backtrack parity, zero
  measured displacement/residual/recovery error, zero intermediate/control transfers and fallback
  zero. This does not bypass the open protected `native-hip-approved` C2 gate or promote the
  numerical family beyond C1. Broader nonlinear input-space, parallel/general ModelIR assembly,
  transient HIP, durable jobs and C6 remain open, and the legacy Rust export is unchanged.
- The bounded `nonlinear_ndtha` story-frame slice is C1. Its serial FP64 C++ Newmark/Newton kernel
  shares constitutive assembly and recovery with nonlinear static, uses ABI v1.4 nested
  caller-owned descriptors and a safe Rust wrapper, and matches all 11 response channels plus the
  summary of the frozen 2-story, 3-step legacy Rust fixture within `1e-15`. Invalid and numerical
  nonconvergence calls are failure-atomic; physical collapse is a complete terminal result. An
  independent NumPy dense-matrix oracle and strict neutral golden wire cover five 1/2/3-story
  cases across Newmark parameters, elastic/plastic response, mixed-sign acceleration, P-delta,
  damping cap, adaptive retry, line search and collapse. C++/Rust matches displacement `1e-12 m`,
  drift `1e-10 %`, force `1e-8 kN` and residual `1e-6 N` tolerances with exact integer/boolean
  taxonomy. Broader record/material coverage and HIP C2 remain open. A separate bounded CPU
  checkpoint capability is C4 and one tracked request-to-ResultIR/ReportIR CLI profile is C5;
  neither promotion expands this solver family's C1 numerical authority.
- A bounded canonical-CSR sparse linear reference family is C1. C++20 owns strict CSR and symmetry
  validation, deterministic Jacobi-PCG, a true-residual postcheck, fallback zero and fixed
  singularity/indefinite/nonconvergence/increment/residual taxonomy. Four SPD profiles—including
  irregular topology and a `4e12` diagonal condition ratio—match an independent NumPy direct
  solve, with malformed/asymmetric/failure paths covered at C0. General sparse/direct/indefinite
  solvers and C6 remain open. A product-owned fixed-tree FP64 HIP C2
  candidate keeps every PCG vector and iteration decision resident, has bitwise repeats, exact
  CPU/HIP status and iteration parity, local live maximum solution error `4.4408920985006262e-16`
  and fallback zero. ABI v1.8 and a safe reentrant Rust wrapper implement the one-shot C3 boundary
  with fixed numerical errors and failure-atomic output. ABI v1.10 additionally exposes complete
  caller-owned PCG begin/advance state. The capability remains sequentially at C1 until the
  `native-hip-approved` protected-runner C2 receipt exists. Separate bounded CPU implementation
  slices cover C4 and C5 without bypassing that sequence: SAPCGC01 binds exact
  request/model/real-state/execution identities, and public linear-run/linear-resume publish typed
  active/failure receipts or self-hashed ResultIR/ReportIR/Markdown artifacts. Direct and
  real-iteration resumed terminal directories are byte-identical with Python/Node lookup removed.
  Arbitrary ModelIR sparse assembly, durable jobs, PDF projection, protected C2 and C6 remain open.
- A bounded dense symmetric generalized-eigen reference family is C1. C++20 owns modal
  `K phi = omega^2 M phi` and linear-buckling `K phi = lambda Kg phi` for at most 128 DOFs,
  including strict definiteness/semidefiniteness, rigid and infinite-mode filtering, stable
  complete-cluster selection, coordinate-axis canonical mode bases, residual/orthogonality
  gates, deterministic repetition and fallback zero. Six modal/buckling profiles—including
  non-identity coordinate recovery, a rigid mode, singular geometric stiffness and a `1e-15`
  finite reciprocal mode—match an independent SciPy generalized-eigen oracle. This is not sparse
  extraction or whole-model solver ownership. ABI v1.9 now exposes distinct failure-atomic modal
  and buckling calls through the last two table slots, and a safe reentrant Rust wrapper validates
  complete result metadata before publishing owned modes; this is C3 implementation evidence, not
  sequential promotion. A product-owned bounded HIP cyclic-Jacobi kernel now provides a live local
  C2 candidate: eight modal/buckling profiles repeat bitwise, numerical and contract failures
  match, eigensolve/canonicalization/result recovery stay resident, maximum relative eigenvalue
  error is `1.3706125276112035e-16`, and fallback remains zero. It is explicitly a single-thread
  dense reference profile, not a sparse performance claim. Protected-runner C2 remains open, so
  the numerical capability remains C1. Separate bounded CPU implementation slices now cover C4
  and C5 without bypassing that sequence: SAEIGC01 binds exact request/model/ready-state/execution
  identities at the honest pre-dispatch phase boundary, and public eigen-run/eigen-resume produce
  self-hashed ResultIR/ReportIR/Markdown/receipt artifacts that are byte-identical in an
  environment with Python/Node lookup removed. Sparse/ModelIR adaptation, spectral durable jobs,
  protected C2 and C6 remain open, and Python remains the broader modal/buckling oracle and
  rollback owner.

### D5. Durable Job API and process lifecycle

- Current Python authority
  - src/structural_analysis/execution/job_service.py
  - src/structural_analysis/execution/job_http_api.py
  - src/structural_analysis/execution/nonlinear_frame_worker.py
- Target owner
  - Rust structural-runtime
- Oracle fixtures/tests
  - tests/test_durable_job_service.py
  - tests/test_batch_job_runner.py
  - tests/test_dynamic_time_history_checkpoint_authority.py
- Stable errors to preserve
  - queued/running/checkpointed/succeeded/failed/cancelled transition
  - content hash, lease, tenant/worker authorization, artifact size/media type
  - resume contract mismatch, cancellation과 crash recovery
- Required gates: C0, C1, C3, C4, C5, C6.
- C2 disposition: orchestration 자체는 backend-independent이지만 같은 job contract가
  CPU와 HIP execution handle을 명시적으로 선택하고 fallback을 기록하는 E2E가 필요하다.
- State: Rust now owns a bounded single-host CPU NDTHA slice through C5: strict idempotent
  submit/poll/cancel, append-only hash-chained events, content-addressed artifacts, OS-lock worker
  leases, expired-lease crash reconciliation, C4 checkpoint resume, deterministic terminal
  re-projection and environment-cleared CLI export. The existing Python SQLite service remains
  authoritative for tenant authorization, HTTP/API compatibility and solver families outside this
  bounded request. HIP C2, distributed claim semantics and final C6 decommission remain open.

### D6. ResultIR and engineering result recovery

- Current Python authority
  - src/structural_analysis/results/
  - src/structural_analysis/engine_v2/contracts/result_ir.py
  - src/structural_analysis/engine_v2/contracts/engineering_result.py
  - src/structural_analysis/schemas/*result*.schema.json
- Target owner
  - C++ structural result recovery computes physical quantities
  - Rust structural-contracts serializes ResultIR
- Oracle fixtures/tests
  - tests/test_engine_v2_result_ir_v1.py
  - bounded Frame3D result contract tests
  - reaction/member-force element parity suites
- Stable errors/authority to preserve
  - not_evaluated, not_authoritative와 bounded_candidate
  - convergence, backend, units/frame, model/state/checkpoint hashes
- Required gates: C0 through C6. CPU/HIP parity includes UX/UY/UZ/RX/RY/RZ,
  reactions and member-local N/Vy/Vz/T/My/Mz when the scope supports them.
- State: Python contracts remain authoritative overall. Rust now emits one canonical self-hashed
  `bounded_candidate` ResultIR from the tracked CPU nonlinear-NDTHA terminal state with exact
  model/state/execution/checkpoint provenance; broader recovery and HIP parity remain open.

### D7. MGT import health and bounded ModelIR conversion

- Current Python authority
  - src/structural_analysis/io/midas/raw_parser.py
  - src/structural_analysis/io/midas/canonical.py
  - src/structural_analysis/io/midas/loader.py
  - tests/test_midas_mgt_parser.py
- Target owner
  - Rust input/API layer owns bytes, encoding, original hash와 import diagnostics
  - C++ structural_model_ir owns normalized domain validation
- Oracle fixtures/tests
  - tests/fixtures/foundation_realish/*.mgt
  - tests/fixtures/model_ir_v2/
  - existing MGT roundtrip/provenance contract tests
- Stable errors to preserve
  - encoding/hash mismatch, unsupported/dropped/mapped disposition
  - unit/axis/offset/release/load-case diagnostics와 blocker paths
- Required gates: C0, C1, C3, C5, C6.
- C2 disposition: import는 backend-independent이다. 생성된 ModelIR fixture를 CPU와
  HIP operator가 동일하게 소비하는 downstream parity를 별도 요구한다.
- State: a bounded native import-health slice is C5 for one explicit contract. Rust owns the exact
  source bytes, strict UTF-8/BOM versus unsupported-encoding disposition, source SHA-256, section
  and row inventory, and `mapped`/`preserved_only`/`dropped`/`unsupported` diagnostics. The exact
  numeric frame/truss grammar alone emits canonical ModelIR and crosses the existing C++ semantic
  validator/snapshot with three-hash identity. A language-neutral golden and Python raw parser
  freeze six sources: two complete exact profiles and all four existing `foundation_realish` MGT
  fixtures. The latter remain blocked where material/section/support/load data or shell support is
  absent; native code does not invent values. One exact fixed-guided profile now continues through
  the Rust-native Workbench to C++ derivation, real checkpoint/resume, ResultIR/ReportIR,
  comparison and native PDF while retaining original MGT bytes, health, receipt and C++ snapshot;
  direct and restarted clean-environment artifacts are byte-identical. Aggregate D7 is still
  partial: CP949, repeated `USE-STLD`, self-weight/load combinations, shells,
  offsets/links/thickness, general writeback, broader downstream CPU/HIP consumption and C6 remain
  open.

### D8. ReportIR, external comparison and PDF

- Current Python authority
  - src/structural_analysis/reporting/
  - implementation/phase1/convert_midas_gen_table_export_to_result.py
  - implementation/phase1/run_midas_gen_same_mesh_native_comparison.py
  - implementation/phase1/design_optimization/report_builder.py
- Target owner
  - Rust structural-report and structural-contracts
- Oracle fixtures/tests
  - midas-gen-same-mesh-result.v1 fixtures
  - comparison/report snapshot and PDF render checks
- Stable errors/authority to preserve
  - node/member mapping, unit/local-axis mismatch, unsupported quantity
  - source provenance, tolerance, comparison authority와 missing external result
- Required gates: C0, C1, C3, C5, C6.
- C2 disposition: report serialization은 backend-independent이다. ReportIR의 source
  ResultIR에는 CPU/HIP recovery parity와 exact backend provenance가 필요하다.
- State: Python report generators still dominate. Rust now emits one deterministic ReportIR and
  Markdown document source bound to the bounded CPU nonlinear-NDTHA ResultIR. A separate bounded
  C5 Rust comparison contract verifies exact source/executable bytes and three global NDTHA
  quantities against a Python C1 golden without promoting that fixture to live external-solver
  evidence. A separate bounded C5 Rust renderer now byte-verifies the exact ResultIR/ReportIR/
  Markdown projection and emits a deterministic single-page A4 PDF plus self-hashed receipt with
  no product dependency on Python/Node/external renderers. An additive C5 v2 path embeds a renamed
  OFL-1.1 Type0/ToUnicode subset for exact `en-US`/`ko-KR` labels plus printable-ASCII dynamic
  values, with clean-environment CLI and Workbench parity while preserving absent-locale v1 bytes.
  Live MIDAS/OpenSees/CalculiX execution, same-mesh node/member mapping, PDF/A/accessibility/general
  localization/arbitrary-Unicode/multipage output and broader report/comparison profiles remain
  open. The bounded Workbench also re-verifies the exact artifact chain and emits self-hashed
  `en-US`/`ko-KR` UTF-8 linear text, including Unicode human-review text without ANSI/color/layout
  semantics. Neither the terminal alternative nor fixed-label PDF is tagged PDF, WCAG/PDF-UA
  certification, or general localization closure.

### D9. CLI/API and Workbench composition

- Current authority
  - src/structural_analysis/api/
  - frontend Workbench providers/components
  - tests/frontend/workbench-v2-*.spec.ts
- Target owner
  - Rust structural-cli/API/process lifecycle
  - Workbench is a typed ResultIR/ReportIR consumer
- Stable behavior to preserve
  - Import -> Run -> Compare -> Report state
  - submit/poll/cancel/resume, bounded authority and unsupported blocker display
- Required gates: C0, C1, C3, C4, C5, C6.
- C2 disposition: selected backend와 receipt를 UI까지 전달하는 CPU/HIP E2E가 필요하다.
- State: the public Rust CLI now owns a bounded CPU nonlinear-NDTHA run/checkpoint/resume to
  ResultIR/ReportIR flow at C5. The exact fixed-guided frame3d ModelIR profile also reaches that
  flow through public model-run/model-resume with provenance-bound restart and frozen artifacts;
  the matching exact MGT profile reaches the same flow through `import-mgt`/`workflow-mgt` with
  original source and import-health evidence bound into the durable session.
  Rust also owns bounded single-host durable submit/poll/cancel,
  expired-lease recovery, checkpoint continuation and export at C5. A separate loopback,
  single-tenant HTTP slice exposes submit/poll/cancel/work-once and immutable artifact retrieval
  at C5 with distinct static client/worker credentials and clean-process restart evidence. TLS,
  non-loopback deployment, tenant isolation and distributed claims remain open. The Rust-native
  Workbench separately owns a C++-verified deterministic topology view for every current positive
  ModelIR profile and one provenance-bound node-coordinate edit that reparses, C++-revalidates and
  create-new publishes the edited model plus a self-hashed receipt. Visual dragging, broader model
  property/load/constraint/topology editing, result exploration, broader solver API composition and
  the general TypeScript-to-native Workbench replacement remain open.

### D10. ROCm/HIP backend and hardware receipts

- Current partial source
  - implementation/phase1/hip_kernels/*.hip.cpp
  - native/cpp/src/hip/*.hip.cpp
  - implementation/phase1/mgt_hip_full_residual_ffi/
  - implementation/phase1/hip_*_replay.cpp (product ABI consumers only)
- Target owner
  - CMake structural_solver_hip and Rust safe execution selection
- Oracle fixtures/tests
  - engine_v2 primitive/current-tangent/FGMRES/sparse parity suites
  - exact configured dedicated hardware lane
- Stable requirements
  - FP64 deterministic mode, fallback 0, resident model/state/operator/Krylov buffers
  - H2D/D2H bytes, sync count, precision, device/architecture와 exact source hash
- Required gates: C0 through C6 plus independently trusted receipt where promotion requires.
- State: the full-residual replay and resident-worker executables no longer own HIP kernels or
  direct runtime allocation/copy calls; all four link the product library through the single
  `sa_get_api_v1` symbol. This closes the source-ownership cleanup only. Approved-runner H4/C2,
  broader Newton/Krylov residency remain open, and g1_closure remains false.

## 3. Removal protocol

Python file 또는 public path를 제거하는 PR은 다음을 모두 포함해야 한다.

1. 이 원장의 domain row와 exact replacement owner
2. versioned fixture 목록과 before/after hashes
3. C0-C5 결과 또는 적용 불가 사유
4. legacy consumer search와 no-native-to-Python dependency proof
5. rollback package/flag와 deprecation window
6. claim/readiness non-promotion assertion

여러 domain을 한 PR에서 동시에 제거하지 않는다. compatibility adapter가 numerical
truth나 result authority를 다시 계산하면 제거 gate를 통과한 것으로 보지 않는다.

## 4. Progress reporting

진척도는 language file count가 아니라 domain별 마지막 통과 gate로 보고한다.
예: D1=C3, D2=C1, D3=C0. partial, proxy, fallback, external-blocked와 hardware
freshness는 별도 필드로 유지한다.

`structural_runtime_ffi` R2 contract extraction은 migration topology, raw/wire ownership과 기존
ABI/golden freeze다. 수치 구현의 C0/C1이나 product C3를 새로 통과한 것으로 세지 않는다.
후속 R3 compatibility decomposition은 같은 authority를 `contracts.rs`, `runtime.rs`, `ffi.rs`,
작은 `lib.rs` façade로 물리 분리했으며 5개 export와 golden bytes를 그대로 유지한다. 이 역시
product gate 승격은 아니다.
네 pointer-free neutral fixture는 향후 C++ parity 입력/결과 계약이지만 현재 numerical truth는
기존 Rust compatibility owner에 있다. `track_point_load`, `nonlinear_static`,
`nonlinear_ndtha`의 한정 product matrix는 각각 별도 Python C1 golden이 수치 truth를 소유한다.
track은 legacy endpoint 차이를 명시적으로 보존하고, nonlinear static은 legacy 3-story case를
byte-identical product golden으로 포함하며, nonlinear NDTHA는 legacy 2-story config/input을 새
strict product wire에서도 보존한다. R4에서 product Cargo graph와 product Rust test의 live legacy
crate 의존은 제거됐다. 기존 Python bridge/hook은 native product package 밖의 deprecated
rollback consumer로 남으며, HIP C2·해당 기능의 bounded replacement·deprecation window·rollback
release와 최종 C6가 닫히기 전에는 삭제하지 않는다.

`inplace_scale_f32`는 이 domain gate 표의 numerical product family가 아니다. 기존 Python
producer hook의 pointer alias/checksum 계측을 보존하는 compatibility-only probe이며 C0-C6로
승격하지 않는다. HIP execution receipt가 transfer/residency/fallback 계측을 직접 소유하고
rollback/deprecation 조건이 확보되면 hook과 export를 함께 제거한다.
