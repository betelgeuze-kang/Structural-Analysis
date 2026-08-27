# ADR-009: Native Workspace and C ABI v1

- Status: accepted
- Date: 2026-08-12
- Deciders: native-first product direction

## Context

제품 코드의 수치·실행 권한 대부분은 Python에 있고, 현재 native 코드는 서로
독립된 Rust cdylib 두 개와 probe/replay 중심 C++/HIP source로 흩어져 있다. 통합
Cargo workspace, CMake target graph, 공통 public header와 ABI 호환성 정책이 없다.
기존 긴 위치 인자 FFI와 symbol-by-symbol dynamic loading을 그대로 확장하면
ModelIR, element, material, state, checkpoint와 ResultIR의 lifetime 및 오류 의미가
언어마다 달라질 수 있다.

ADR-002의 language-neutral IR, ADR-003의 descriptor/table ABI, ADR-004의 명시적
backend 및 residency 경계를 유지하면서 물리적 구현 언어와 package layout을
native-first로 고정할 결정이 필요하다.

## Decision

### 책임 경계

- Rust는 CLI/API composition, strict serialization, job runtime, artifact storage,
  checkpoint/resume, ResultIR/ReportIR와 process lifecycle을 소유한다.
- modern C++는 ModelIR의 in-memory domain model, units/semantic validation,
  elements, materials, assembly, CPU reference/optimized solver와 result recovery를
  소유한다.
- ROCm/HIP는 accelerator operator, resident buffer, deterministic reduction,
  sparse/Krylov/Newton execution을 소유한다.
- Python은 migration oracle, compatibility adapter와 fixture generator로만 유지한다.
  새 production authority를 추가하지 않는다.

### Workspace와 build

- 새 코드는 최상위 native Cargo workspace와 CMake project에서 관리한다.
- Cargo가 Rust package graph와 product entrypoint를 소유하고, CMake가 C++ library,
  C ABI shared/static library와 optional HIP targets를 소유한다.
- hosted CPU build는 ROCm 설치 없이 구성 가능해야 한다. HIP는 명시적
  STRUCTURAL_ENABLE_HIP 옵션에서만 활성화한다.
- production Rust는 하나의 versioned C ABI table을 통해 C++/HIP에 접근한다.
  기존 crate와 probe는 compatibility consumer로 옮긴 뒤 제거 gate를 통과할 때까지
  유지한다.

### C ABI v1

- public ABI는 C11-compatible header와 extern "C" symbol 하나
  sa_get_api_v1로 노출한다.
- 모든 public descriptor는 abi_version과 struct_size를 첫 필드로 갖는다.
- ABI를 통과하는 enum은 고정 폭 정수이며 bool, size_t, C++ STL, Rust layout,
  exception 또는 panic을 노출하지 않는다.
- 함수는 stable status code를 반환하고 상세 오류는 호출자가 제공한 error buffer에
  기록한다. global last-error state는 금지한다.
- 입력 slice는 호출 동안만 borrow된다. core가 보존할 값은 호출이 끝나기 전에 deep
  copy한다.
- 출력 byte/array는 caller-owned buffer와 required-size two-call protocol을 사용한다.
  opaque handle만 생성한 library가 destroy하며 allocator를 언어 경계에서 섞지 않는다.
- array length와 stride는 uint64, index는 zero-based uint64, scalar baseline은 IEEE
  754 binary64다. ModelIR canonical units는 m, N, kg, s, rad이고 DOF 순서는
  UX, UY, UZ, RX, RY, RZ다.
- immutable ModelIR handle은 동시 read-only 호출이 가능하다. mutable state/execution
  handle은 한 시점에 하나의 호출만 허용한다. 독립 handle은 병렬 실행할 수 있다.
  destroy는 in-flight call이 없을 때만 허용한다.

### 호환성과 cutover

- v1 descriptor는 tail-only field addition만 허용한다. struct_size로 오래된 caller를
  구분하며 기존 field의 offset, width와 의미를 바꾸지 않는다.
- breaking change는 새 symbol/table major version을 요구한다.
- 기존 Python 또는 probe path는 native unit, CPU oracle parity, 해당되는 CPU/HIP
  parity, safe Rust FFI, checkpoint/restart와 bounded product E2E가 모두 통과하기
  전에는 제거하지 않는다.
- ABI 또는 parity PASS는 commercial, G1 hardware freshness, independent V&V 또는
  public promotion을 의미하지 않는다.

## Normative invariants

- C++ exception과 Rust panic은 ABI를 넘어갈 수 없다.
- length가 0이 아니면 data pointer는 null일 수 없고, byte length의 곱셈 overflow를
  검사한다.
- serialized IR에는 pointer, device address, HIP stream, temporary path와 process ID를
  넣지 않는다.
- residual, tangent, JVP와 result recovery는 같은 constitutive source와 state epoch를
  사용한다.
- HIP 성공은 silent CPU fallback 없이 별도 hardware gate가 증명해야 한다.
- Python oracle과 native 결과가 다르면 native를 승격하지 않으며 oracle 차이를
  조용히 재정의하지 않는다.

## Alternatives considered

- 두 기존 cdylib를 계속 독립 확장: ABI와 lifecycle drift를 막을 공통 owner가 없어
  기각한다.
- Rust C++ 또는 HIP ABI를 직접 노출: compiler/toolchain 안정성이 없어 기각한다.
- JSON string만 모든 operator call에 전달: domain validation과 hot-path buffer
  residency를 분리할 수 없어 기각한다.
- Python을 product orchestrator로 영구 유지: native-first 방향과 crash/process
  lifecycle 소유권에 맞지 않아 기각한다.

## Verification

- C와 C++ translation unit에서 public header compile
- Rust raw bindings layout/constant assertion
- old struct_size compatibility와 ABI major mismatch rejection
- invalid pointer/length/stride/overflow/error-buffer tests
- concurrent immutable reads, mutable-handle exclusion과 destroy-race tests
- ModelIR canonical bytes/hash 및 semantic report의 Python/Rust/C++ parity
- CPU reference, HIP parity/residency, checkpoint/restart와 bounded product E2E의 분리 gate

## Relationship to existing ADRs

이 ADR은 ADR-008의 물리적 Python package 목표 layout을 native workspace로
supersede한다. ADR-008의 dependency 방향, solver truth, adapter와 Workbench authority
규칙은 그대로 유지한다. ADR-002, ADR-003과 ADR-004의 IR, operator source,
fallback/precision/residency 결정도 변경하지 않는다.

## Rollback / supersession

새 workspace를 제거해도 기존 Python path는 parity cutover 전까지 동작해야 한다.
ABI v1을 변경하려면 새 ADR과 새 major table이 필요하며, 기존 v1 consumer의 rollback
기간과 compatibility adapter를 명시해야 한다.
