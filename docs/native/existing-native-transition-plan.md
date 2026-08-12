# Existing Native Probe to Product Library Transition Plan

Status: migration plan

Baseline: exact main 14c25f4ddb72eb64cab689e6d0183b056025dca3

## 1. Current boundary

현재 native source는 유용한 수치/장치 실험을 포함하지만 하나의 versioned product
library를 구성하지 않는다.

- implementation/phase1/structural_runtime_ffi/src/lib.rs
  - 약 1,288 lines의 단일 Rust file
  - track, nonlinear frame, NDTHA와 utility ABI가 같은 crate에 결합
  - raw repr(C) 구조와 exported symbol이 product runtime/package graph 밖에 존재
- implementation/phase1/mgt_hip_full_residual_ffi/src/lib.rs
  - 약 230 lines의 manual dlopen/dlsym wrapper
  - symbol별 function pointer와 global OnceLock API
  - C++ library lifecycle/error contract를 그대로 Rust에 투영
- implementation/phase1/hip_full_residual_ffi.cpp
  - long positional array ABI와 probe-specific status
- implementation/phase1/hip_*_replay.cpp, hipsparse/rocalution solve source
  - standalone executable/probe가 build와 runtime owner 역할을 겸함
- implementation/phase1/hip_kernels/*.hip.cpp
  - useful operator kernels가 있으나 공통 CMake target, installed header와 product
    execution context가 없음

이 source의 존재는 production residency, full-load nonlinear closure나 durable product
execution을 의미하지 않는다.

## 2. Transition principles

1. move보다 link-first
   - 새 library가 기존 source를 복사하지 않고 가능한 unit을 target source로 compile한다.
2. compatibility before removal
   - 기존 probe가 새 sa_get_api_v1 consumer가 된 뒤 old direct ABI를 제거한다.
3. one owner per concern
   - contracts/serialization은 Rust, numerical truth는 C++, accelerator는 HIP다.
4. no hidden fallback
   - probe behavior에 있던 implicit fallback을 product adapter가 계승하지 않는다.
5. receipt non-promotion
   - 새 packaging/build PASS로 old hardware receipt freshness를 갱신하지 않는다.

## 3. structural_runtime_ffi decomposition

### Step R0: freeze oracle

- existing Cargo.lock, exported symbol, struct layout와 numerical fixtures를 inventory한다.
- current Python and Rust results를 versioned golden vector로 기록한다.
- no symbol removal.

### Step R1: workspace compatibility member

- crate를 native Cargo workspace의 temporary compatibility member로 포함한다.
- package name과 existing cdylib output을 유지한다.
- workspace lint/test는 적용하지만 public ABI 의미는 바꾸지 않는다.

Implementation status: complete on the Slice D successor branch.

- `native/Cargo.toml`의 temporary member이며 native root lock과 Rust 1.77 gate를 사용한다.
- package/cdylib 이름과 기존 Python bridge의 local output 위치를 유지한다.
- ABI v3의 7개 repr(C) layout, 5개 export, error code와 track/scale/static/NDTHA
  golden vector를 `native/compatibility/structural_runtime_ffi_v3.json` 및 Rust contract
  test로 고정한다.
- release cdylib export set을 `nm` 기반 checker로 검사한다.
- numerical authority, public `sa_get_api_v1`, checkpoint 또는 product E2E 승격은 없다.

### Step R2: extract contracts

- TrackSolveConfig/Result와 nonlinear result wire type을 structural-contracts로 옮길
  수 있는 language-neutral schema로 정의한다.
- raw repr(C) mirror는 structural-ffi-sys가 소유한다.
- original crate는 adapter로 새 type을 변환한다.

Implementation status: complete on the R2 successor branch.

- `structural-ffi-sys::legacy_runtime_v3`가 7개 raw `repr(C)` type, ABI version과 고정
  status constant를 소유하고 legacy crate는 같은 public type 이름을 re-export한다.
- `structural-contracts::legacy_runtime`가 4개 operation의 strict typed wire contract를
  소유한다. Draft 2020-12 schema는 unknown field/status를 거부하고 strict decoder는
  duplicate key와 non-finite JSON token을 거부한다.
- SI unit이 field name에 명시되고 story/node/step vector 길이는 typed post-schema
  validation에서 exact-match한다.
- in-place buffer의 process pointer는 wire에서 제외하며 `shared_storage` 의미만 보존한다.
- 네 language-neutral golden fixture의 exact bytes는 SHA-256 inventory로 고정하고 raw-to-wire
  adapter test가 R1 numerical 결과와 일치시킨다.
- R1 ABI layout, status, numerical golden 및 release cdylib 5-symbol exact set은 하위 gate로
  계속 실행한다.

Current next gate: R3. 각 numerical family를 C++ CPU product target으로 옮기고 Python C1
oracle parity를 독립적으로 닫는다. legacy Rust implementation은 ABI rollback과 R4 cutover
gate가 닫힐 때까지 유지한다.

### Step R3: move numerical kernels

- numerical operation을 C++ structural_elements/materials/solver_cpu target으로 한
  family씩 옮긴다.
- Rust implementation은 oracle parity 기간에만 유지한다.
- each family는 native unit, CPU parity와 FFI integration을 독립 통과한다.

Implementation status: first bounded family complete; R3 remains open for the other families.

- `track_point_load`의 serial FP64 kernel은 `structural_solver_cpu`가 소유한다.
- `sa_get_api_v1` ABI v1.2 optional slot과 `structural-ffi` safe wrapper가 caller-owned
  displacement/rotation output을 연결한다.
- C++ unit, C ABI invalid/undersized/overlap/nonconvergence atomicity, Rust layout 및 concurrent
  integration test가 별도 Python C1 product golden과 `1e-15` 절대 오차 내에서 일치한다.
- legacy `structural_runtime_ffi`의 5개 export와 numerical implementation은 그대로 유지한다.
- 제품 Euler endpoint는 Python `np.gradient`의 one-sided slope를 따른다. legacy Rust golden의
  adjacent-interior endpoint는 바꾸지 않고 `3.436580346133486e-5 rad`의 의도적 endpoint-only
  compatibility divergence로 고정한다. displacement/residual/interior rotation은 계속 같다.
- 9-node midpoint-load의 pinned/fixed × Euler/reduced-Timoshenko 4-case matrix만 C1이다.
  broader node/load-position input-space parity와 HIP C2는 open이다.

Current next gate: 승인된 전용 ROCm runner에서 track HIP C2를 구현하거나, 같은 fail-closed
방식으로 다음 R3 CPU numerical family를 이전한다. R4 cutover는 아직 시작하지 않는다.

### Step R4: runtime cutover

- structural-runtime이 job/checkpoint/cancel owner가 된다.
- old exported solve symbol은 compatibility feature에서만 유지한다.
- C4/C5 후 deprecation을 시작한다.

### Step R5: removal

- all consumers, symbols, docs와 package scripts를 search한다.
- C6 proof와 rollback release 뒤 standalone crate를 제거한다.

## 4. mgt_hip_full_residual_ffi decomposition

### Step H0: exact ABI inventory

- C++ create/eval/destroy/device-name/error symbols와 every positional array의 units,
  length, ownership, memory space를 기록한다.
- current receipts are historical oracle only.

### Step H1: table adapter

- C++ side에 sa_get_api_v1 compatibility table을 추가한다.
- existing create/eval operation을 table function으로 adapter한다.
- legacy symbols remain unchanged.

### Step H2: safe Rust wrapper

- manual symbol-by-symbol dlsym과 global last_error를 structural-ffi safe handle로
  교체한다.
- dynamic package loading이 필요한 경우 libloading은 sa_get_api_v1 하나만 resolve한다.
- linked production build가 default이고 dynamic loading은 explicit packaging mode다.

### Step H3: descriptor conversion

- long positional argument를 versioned ModelIR/operator/buffer descriptors로 바꾼다.
- host/device memory space, stride, device와 state epoch를 명시한다.
- C++ core deep copy 또는 execution-context ownership을 test한다.

### Step H4: resident execution

- model/operator/state/Krylov buffer를 typed HIP execution handle이 소유한다.
- eval은 caller state bytes를 매 iteration host에서 다시 전달하지 않는다.
- transfer/sync/fallback instrumentation을 required receipt로 만든다.

### Step H5: legacy removal

- CPU/HIP parity, full lifecycle, failure injection, restart와 bounded product E2E 후
  legacy Rust/C++ ABI를 제거한다.

## 5. C++/HIP source target mapping

| Existing source | First product target | Initial action |
| --- | --- | --- |
| hip_kernels/axpy_kernel.hip.cpp | structural_solver_hip/reductions | deterministic primitive test |
| hip_kernels/beam_element_kernel.hip.cpp | structural_elements + HIP operator | CPU/HIP element parity |
| hip_kernels/engine_v2_primitive_parity.hip.cpp | native test support | keep as parity harness |
| hip_kernels/engine_v2_current_tangent_operator.hip.cpp | structural_solver_hip/operators | descriptor/state epoch adapter |
| hip_kernels/engine_v2_fgmres_recurrence.hip.cpp | structural_solver_hip/krylov | resident context and restart |
| hip_kernels/engine_v2_sparse_lu_apply.hip.cpp | structural_solver_hip/sparse | explicit preconditioner capability |
| hip_full_residual_ffi.cpp | structural_c_abi_v1 compatibility | table wrapper, no new positional args |
| hip_full_residual_resident_worker.cpp | structural-runtime integration test | process lifecycle consumer |
| hip_*_batch_replay.cpp | native integration/benchmark | link product library, stop owning kernels |
| hipsparse_ilu_bicgstab_solve.cpp | structural_solver_hip/sparse | capability-gated backend |
| rocalution_sparse_solve.cpp | optional explicit backend | no automatic fallback |

## 6. Removal blockers

다음 중 하나라도 남으면 legacy source를 제거하지 않는다.

- unknown consumer or unversioned artifact
- golden fixture or error taxonomy mismatch
- Rust safe wrapper가 raw pointer/lifetime를 완전히 감싸지 못함
- checkpoint가 model/state/execution context hash를 검증하지 않음
- HIP path가 iteration state/residual host copy 또는 CPU fallback을 포함
- product E2E가 legacy Python/Rust symbol을 호출
- rollback package/deprecation window 없음
- protected receipt가 old path를 immutable source로 참조하지만 preservation 계획 없음

## 7. PR sequence

1. native workspace/C ABI base
2. ModelIR Rust contract
3. ModelIR C++ core and round-trip
4. structural_runtime_ffi compatibility member
5. mgt HIP table compatibility adapter
6. first element/material/assembly parity slice
7. CPU solver and restart slice
8. dedicated HIP resident slice
9. durable Rust runtime and product E2E
10. legacy deprecation/removal PRs per domain

각 PR은 이전 PR의 latest main을 normal merge하고 별도 gate와 bounded claim을 유지한다.
