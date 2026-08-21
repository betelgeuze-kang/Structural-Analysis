# Python to Native Parity Ledger

Status: migration control document

Baseline commit: 14c25f4ddb72eb64cab689e6d0183b056025dca3

Baseline inventory: Python 2,002 files, Rust 2 files, C++/HIP 13 files

이 원장은 기존 Python path를 native replacement보다 먼저 제거하거나, probe 수준
native 코드를 product authority로 승격하지 못하게 하는 cutover 기준이다. 파일 수는
진척률이 아니며 baseline 변화 시 다시 측정한다.

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
  three-hash parity; snapshot bytes are re-parsed and identity-checked in Rust. The validation-only
  command is not C5 by itself; the exact Frame Alpha subset now has a separate bounded public
  CLI input-to-ResultIR/ReportIR C5 path. Python remains the aggregate authoritative oracle and
  rollback owner; broad D1 C5 and C6 remain open.

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
- Stable errors to preserve
  - unsupported formulation/material, invalid geometry/property, trial-state conflict
  - constitutive nonconvergence와 rollback failure
- Required gates: C0 through C6, including CPU/HIP residual/tangent/recovery parity.
- State: the narrow `linear_frame3d_cpu_alpha` prismatic Timoshenko element is C1 on CPU with
  six-mode Python stiffness/force parity. The aggregate element/material domain is not C1:
  nonlinear material, release/offset and HIP residual/tangent/recovery gates remain open.

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
- Stable errors to preserve
  - DOF/reference/layout mismatch, CSR invalid, state epoch mismatch
  - fallback forbidden, backend unavailable와 device mismatch
- Required gates: C0 through C6.
- State: the narrow Frame Alpha dense CPU assembly has C1 displacement/reaction/local-force
  parity for a rotated mixed-roll two-member spatial chain. General sparse operator graphs,
  HIP parity and product authority remain open.

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
- State: ABI v1.5 and safe Rust expose the bounded CPU linear Frame3D compile/load-case solve path
  for nodal and uniform initial-member-local force loads, RX/RY/RZ member-end releases and finite
  global rigid end offsets at C1.
  Independent Python evidence now includes closed-form QX/QY/QZ uniform-load cantilevers and
  released-member static condensation and rigid-offset transforms in addition to six-mode and rotated assembly parity.
  `structural-runtime` composes native ModelIR validation, the exact linear Timoshenko subset,
  explicit SI/kN conversion and a three-hash-bound ResultIR candidate after residual and global
  resultant gates, including condensed fixed-end loads in independent Rust recovery replay. Nonuniform and
  member-point loads, self weight, translational release, checkpoint, Workbench execution and CPU/HIP C2
  evidence remain open; the unified solver domain therefore remains open.

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
- State: Python SQLite single-host authority; Rust migration not started.

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
- State: the exact CPU linear Timoshenko Frame Alpha subset now has strict native ResultIR v1.
  Construction requires native residual, free-DOF residual, global force/moment resultant,
  zero-prescribed-displacement, zero fallback/regularization and independent Rust member-force
  recovery replay gates. Rust reconstructs each 12-DOF local force vector from ModelIR-derived
  geometry/section/local-axis data and solved displacement, then rejects drift beyond scaled L∞
  `1e-9`; a rotated/rolled solve and intentional native-force mutation are tested. Canonical hash,
  duplicate and stale-input negatives also pass. Displacement, reaction and member-force axes are
  `bounded_candidate`; design/code/release/commercial axes remain `not_authoritative`. This is a
  scoped C5 CLI flow, not aggregate D6 cutover: CPU/HIP C2, checkpoint binding, external code-to-code
  comparison and broad experimental validation remain open.

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
- State: strict Python import contracts exist; native product connection not started.

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
- State: the bounded Frame Alpha ResultIR now projects to a strict source-bound native ReportIR v1
  and byte-deterministic standalone HTML. It preserves gate metrics, fixed limitations and
  deterministic displacement/reaction/member-end-force extrema; source transplantation and stale
  hashes fail closed. Comparison is explicitly `not_evaluated`, and design/release are
  `not_authoritative`. External mapping/comparison, PDF rendering and aggregate D8 cutover remain
  open.

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
- State: `structural-cli model analyze-frame3d` now provides a bounded C5 composition for the
  exact CPU linear Timoshenko subset and emits one selected canonical ResultIR, canonical ReportIR
  or standalone HTML artifact to stdout. It has deterministic replay and fail-closed unsupported
  or unknown-load behavior. Workbench v2 now has a separate C0 same-origin, read-only typed
  ResultIR/ReportIR consumer. It fails closed on duplicate keys, schema/profile drift, stale or
  transplanted hashes, detached gates/extrema and authority promotion, and displays the bounded
  result rows without inferring comparison, design or release authority. A configured-pair browser
  test covers the built UI path, while provider contract tests cover canonical replay and negative
  cases. Analysis submission, durable submit/poll/cancel/resume, backend receipts, public API,
  external comparison and full Workbench execution E2E remain open, so aggregate D9 is not cut over.

### D10. ROCm/HIP backend and hardware receipts

- Current partial source
  - implementation/phase1/hip_kernels/*.hip.cpp
  - implementation/phase1/hip_full_residual_ffi.cpp
  - implementation/phase1/mgt_hip_full_residual_ffi/
- Target owner
  - CMake structural_solver_hip and Rust safe execution selection
- Oracle fixtures/tests
  - engine_v2 primitive/current-tangent/FGMRES/sparse parity suites
  - exact configured dedicated hardware lane
- Stable requirements
  - FP64 deterministic mode, fallback 0, resident model/state/operator/Krylov buffers
  - H2D/D2H bytes, sync count, precision, device/architecture와 exact source hash
- Required gates: C0 through C6 plus independently trusted receipt where promotion requires.
- State: partial probe/receipt only; g1_closure remains false.

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
