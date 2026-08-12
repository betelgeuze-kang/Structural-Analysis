# Native Workspace and C ABI v1 Contract

Status: normative design baseline

Baseline commit: 14c25f4ddb72eb64cab689e6d0183b056025dca3

Related decisions: ADR-002, ADR-003, ADR-004, ADR-008, ADR-009

이 문서는 첫 native implementation PR이 따라야 하는 package, build target와 binary
interface를 고정한다. 문서 자체는 구현 완료나 hardware/readiness 증거가 아니다.

## 1. Target repository layout

~~~text
native/
  Cargo.toml
  crates/
    structural-contracts/
    structural-ffi-sys/
    structural-ffi/
    structural-runtime/
    structural-report/
    structural-cli/
  cpp/
    CMakeLists.txt
    include/structural/
      abi_v1.h
      model_ir_v1.h
    src/
      model_ir/
      units/
      validation/
      elements/
      materials/
      assembly/
      solvers/
      result_recovery/
      abi/
    hip/
      operators/
      reductions/
      sparse/
      nonlinear/
  cmake/
    StructuralOptions.cmake
    StructuralWarnings.cmake
    StructuralHip.cmake
  tests/
    abi/
    fixtures/
    integration/
~~~

기존 implementation/phase1 native source는 처음부터 이동하지 않는다. 새 target에
link 가능한 unit부터 하나씩 가져오고, 기존 probe path가 새 library를 consumer로
사용하도록 바꾼 뒤 parity gate를 통과한 source만 제거한다.

## 2. Rust crate graph

| Crate | 책임 | 허용 dependency | 금지 |
| --- | --- | --- | --- |
| structural-contracts | strict JSON decode, canonical serialization, ModelIR/ResultIR/ReportIR wire types, hash | serde 계열과 pure Rust utility | solver, filesystem runtime, FFI 호출 |
| structural-ffi-sys | abi_v1.h의 raw bindgen 또는 checked handwritten mirror | build metadata | safe policy, allocation owner 변경 |
| structural-ffi | opaque handle RAII, slice validation, error mapping, safe C++ core client | contracts, ffi-sys | product CLI, database, global mutable last-error |
| structural-runtime | durable jobs, artifacts, checkpoint/resume, cancellation, worker lifecycle | contracts, ffi | solver truth 재정의 |
| structural-report | ResultIR/ReportIR projection과 deterministic document source | contracts | solver convergence 추론 |
| structural-cli | CLI/API composition과 process exit contract | contracts, runtime, report | element/material implementation |

structural-contracts와 structural-ffi-sys는 서로 의존하지 않는다. structural-ffi가
두 crate를 조합한다. runtime과 report는 병렬 consumer이며 CLI가 최상위 composition
owner다.

## 3. C++ and HIP target graph

| CMake target | 종류 | 책임 | HIP 필요 |
| --- | --- | --- | --- |
| structural_model_ir | static | ModelIR domain types, units, semantic validation | 아니오 |
| structural_elements | static | element kinematics와 recovery source | 아니오 |
| structural_materials | static | accepted/trial/commit/rollback constitutive source | 아니오 |
| structural_assembly | static | DOF graph, residual/tangent/JVP assembly | 아니오 |
| structural_solver_cpu | static | reference/optimized CPU solver | 아니오 |
| structural_solver_hip | static | resident HIP operators와 solver | 예 |
| structural_c_abi_v1 | shared/static | sa_get_api_v1 table과 exception boundary | 선택 |
| structural_native_tests | executable set | C++ unit, C ABI와 parity test | 기본 아니오 |

dependency 방향은 model_ir <- elements/materials <- assembly <- solver다.
structural_c_abi_v1은 필요한 lower target을 composition하지만 lower target은 ABI나
Rust를 알지 못한다. structural_solver_hip는 CPU target에 fallback하지 않고 동일
operator contract만 공유한다.

## 4. Build ownership

- root native/Cargo.toml은 resolver 2 workspace와 단일 lockfile을 소유한다.
- native/cpp/CMakeLists.txt는 C++20을 baseline으로 사용한다.
- hosted default는 STRUCTURAL_ENABLE_HIP=OFF, STRUCTURAL_BUILD_TESTS=ON이다.
- HIP enable은 발견된 ROCm compiler와 required capability를 configure 단계에서
  검증한다. architecture를 source에 하드코딩하지 않는다.
- Cargo build script는 CMake를 여러 crate에서 중복 실행하지 않는다. 한 integration
  crate 또는 top-level build driver만 native library location을 결정한다.
- production package는 exact ABI version, compiler/runtime identity와 enabled backend
  metadata를 포함한다.

## 5. Public C ABI

### 5.1 Entry table

public shared library가 반드시 노출하는 symbol은 다음 하나다.

~~~c
sa_status_code_v1 sa_get_api_v1(
    const sa_api_request_v1* request,
    sa_api_v1* out_api,
    sa_error_buffer_v1* error);
~~~

sa_api_request_v1과 sa_api_v1의 첫 필드는 abi_version과 struct_size다. function
table의 모든 예약 필드는 null이어야 하며, caller가 모르는 tail은 struct_size로
무시한다. symbol-by-symbol dlsym은 compatibility adapter 밖에서 금지한다.

### 5.2 Version encoding

- uint32 abi_version의 상위 16 bit는 major, 하위 16 bit는 minor다.
- v1.0은 0x00010000이다.
- v1.1은 0x00010001이며 typed ModelIR descriptor/report/snapshot table slots를 추가한다.
- minor 증가는 descriptor tail 또는 새 optional function pointer만 추가한다.
- field offset/width/meaning, enum numeric value와 ownership 변경은 major 증가다.
- library는 지원하지 않는 major를 SA_ERR_ABI_VERSION_MISMATCH로 fail closed한다.

### 5.3 Required base descriptors

~~~c
typedef struct {
    uint32_t abi_version;
    uint32_t struct_size;
} sa_header_v1;

typedef struct {
    uint32_t abi_version;
    uint32_t struct_size;
    const void* data;
    uint64_t length;
    uint64_t stride_bytes;
    uint32_t element_type;
    uint32_t memory_space;
    int32_t device_id;
    uint32_t flags;
} sa_buffer_view_v1;

typedef struct {
    uint32_t abi_version;
    uint32_t struct_size;
    char* data;
    uint64_t capacity;
    uint64_t required;
} sa_error_buffer_v1;
~~~

ModelIR first slice는 별도 typed descriptors와 opaque sa_model_ir_handle_v1을 사용한다.
serialized JSON bytes를 hot operator ABI로 재사용하지 않는다.

### 5.4 ModelIR v1.1 table extension

v1.0의 128-byte table 크기와 첫 24-byte prefix는 그대로 유지한다. v1.0 요청에는 새
slot을 모두 null로 반환하고, v1.1 요청에는 다음 operation과 capability bit를 제공한다.

- `model_ir_create` / `model_ir_destroy`
- `model_ir_validation_report_size` / `model_ir_validation_report_write`
- `model_ir_snapshot_size` / `model_ir_snapshot_write`
- `SA_CAPABILITY_MODEL_IR_V2_TYPED`
- `SA_CAPABILITY_MODEL_IR_V2_SNAPSHOT`

`model_ir_v1.h`의 core family는 generic map이 아니라 versioned typed descriptor다.
Rust-owned pointer는 create가 return할 때까지만 빌리고, C++ handle은 string, nested slice,
extension bytes와 canonical snapshot을 모두 deep-copy한다. C++는 snapshot JSON을 parse하거나
canonicalize하지 않고 typed data만 semantic truth로 사용한다.

create는 descriptor/ABI 구조 실패만 status error로 반환한다. dangling reference, cycle,
unit mismatch와 blocking feature는 handle의 versioned report에 남긴다. 따라서
`semantics_valid`, `contract_valid`와 `analysis_ready`를 서로 독립적으로 판정할 수 있다.

### 5.5 Stable status taxonomy

| Code | Symbol | 의미 |
| ---: | --- | --- |
| 0 | SA_OK | 성공 |
| 1000 | SA_ERR_INVALID_ARGUMENT | null, length, enum 또는 range 오류 |
| 1001 | SA_ERR_ABI_VERSION_MISMATCH | 지원하지 않는 ABI major/minor |
| 1002 | SA_ERR_STRUCT_SIZE | descriptor가 required prefix보다 작음 |
| 1003 | SA_ERR_BUFFER_TOO_SMALL | required size를 반환했고 출력은 미완료 |
| 1100 | SA_ERR_SCHEMA_INVALID | wire/schema contract 실패 |
| 1101 | SA_ERR_SEMANTIC_INVALID | reference, units, cycle 등 의미 실패 |
| 1102 | SA_ERR_ANALYSIS_NOT_READY | contract-valid지만 blocking unsupported 존재 |
| 1200 | SA_ERR_UNSUPPORTED | 알려졌으나 구현되지 않은 capability |
| 1300 | SA_ERR_STATE_CONFLICT | epoch, trial/commit 또는 concurrent mutation 충돌 |
| 1301 | SA_ERR_CHECKPOINT_MISMATCH | model/state/execution context 불일치 |
| 1400 | SA_ERR_BACKEND_UNAVAILABLE | 요청 backend를 사용할 수 없음 |
| 1401 | SA_ERR_DEVICE_MISMATCH | device/architecture/capability 불일치 |
| 1402 | SA_ERR_FALLBACK_FORBIDDEN | explicit policy가 fallback을 거부 |
| 1500 | SA_ERR_CANCELLED | cooperative cancellation |
| 1900 | SA_ERR_INTERNAL | exception/panic을 log-safe detail로 변환 |

새 오류는 기존 numeric 의미를 재사용하지 않는다. 상세 메시지는 diagnostic이며
program control flow는 code와 typed report만 사용한다.

## 6. Memory and lifetime contract

1. Caller-owned input
   - data는 함수가 return할 때까지만 유효하면 된다.
   - callee가 handle에 보존할 값은 return 전에 deep copy한다.
2. Caller-owned output
   - 일반 descriptor는 capacity 0/data null 호출로 required를 조회할 수 있다.
   - ModelIR report/snapshot은 명시적인 size operation으로 필요한 byte 수를 조회한다.
   - capacity가 부족하면 SA_ERR_BUFFER_TOO_SMALL과 required를 반환한다.
   - 부분 serialization이나 부분 array를 성공으로 반환하지 않는다.
3. Library-owned opaque handle
   - 생성한 table major와 library instance에서만 사용한다.
   - type별 destroy function을 정확히 한 번 호출한다.
   - destroy 후 pointer와 이전 borrowed view는 모두 invalid다.
4. Allocator
   - Rust가 C++ allocation을 free하거나 반대 방향으로 free하지 않는다.
   - ABI v1은 arbitrary allocator callback을 받지 않는다.
5. Failure atomicity
   - create 실패 시 output handle 값은 호출 전과 동일하다.
   - mutation 실패 시 accepted state와 output checksum은 호출 전과 동일해야 한다.

## 7. Array and scalar layout

- 모든 count, length, index와 stride는 uint64_t다.
- length > 0이면 data는 non-null이고 stride_bytes는 element size 이상이다.
- length * stride와 offset 계산은 overflow 검사 후 수행한다.
- scalar baseline은 little-endian host IEEE-754 binary64다. wire serialization은
  UTF-8 JSON이고 process ABI byte order를 artifact format으로 사용하지 않는다.
- dense vector는 packed 1D, dense matrix는 explicit row/column stride descriptor를
  사용한다. 암묵적 column-major default를 두지 않는다.
- CSR은 zero-based row_ptr/col_idx, monotonic row_ptr, row_ptr[0]=0,
  row_ptr[nrow]=nnz, in-range sorted column과 duplicate-free row를 요구한다.
- DOF order는 UX, UY, UZ, RX, RY, RZ다.
- canonical units는 m, N, kg, s, rad다. source unit과 scale은 provenance에 남긴다.
- host와 device pointer는 memory_space로 구분한다. device view에는 device_id와
  owning execution context가 필요하다.

## 8. Thread-safety contract

| 객체 | 동시 read | 동시 mutation | thread 이동 |
| --- | --- | --- | --- |
| API table | 허용 | 해당 없음 | 허용 |
| immutable ModelIR handle | 허용 | 해당 없음 | 허용 |
| material/state handle | read만 허용 | exclusive | 명시적 synchronization 후 허용 |
| execution/solver handle | status read만 허용 | 한 owner thread/lane | 실행 중 금지 |
| HIP context/stream binding | query만 허용 | serialized lane | owning device 안에서만 |

- global mutable last-error, singleton current model과 implicit current device를 금지한다.
- 각 호출은 caller-owned error buffer를 사용한다.
- independent handles는 병렬 실행 가능해야 한다.
- destroy는 in-flight call count가 0일 때만 성공한다. 아니면
  SA_ERR_STATE_CONFLICT를 반환한다.
- cancellation은 atomic token을 관찰하는 cooperative protocol이며 accepted state를
  중간 commit하지 않는다.

## 9. Security and fail-closed rules

- Rust panic과 C++ exception은 catch boundary에서 SA_ERR_INTERNAL로 변환한다.
- error text에 pointer, credential, arbitrary platform message와 source file의 민감한
  path를 포함하지 않는다.
- untrusted count로 allocation하기 전에 configured product limit를 검사한다.
- unknown enum/flag bit, nonzero reserved field와 incompatible struct_size를 거부한다.
- FFI 호출 성공이 engineering/result authority를 자동 부여하지 않는다.

## 10. Definition of done for the foundation implementation

- 하나의 Cargo.lock과 workspace-wide fmt/clippy/test
- CPU-only CMake configure/build/CTest
- C와 C++ header consumer compile
- Rust/C layout assertion과 error taxonomy test
- invalid pointer/length/stride/overflow와 failure atomicity test
- concurrent immutable ModelIR reads와 mutable exclusion test
- 기존 두 Rust crate가 compatibility consumer이거나 명시적 migration owner를 가짐
- HIP disabled build에 ROCm runtime dependency가 없음
- protected evidence와 Python production path는 변경되지 않음

## 11. Slice A implementation boundary

Slice A는 다음 파일에 foundation contract를 구현한다.

- `native/Cargo.toml`과 단일 `native/Cargo.lock`: 여섯 crate의 허용 dependency 방향
- `native/cpp/CMakeLists.txt`: CPU-only 기본값, opt-in HIP/sanitizer/fuzzer 옵션,
  static/shared install/export package
- `native/cpp/include/structural/abi_v1.h`: status taxonomy, base descriptors와
  `sa_get_api_v1` 단일 public symbol
- `native/cpp/src/abi/abi_v1.cpp`: version/struct-size/reserved-field 검사, caller-owned
  error buffer, pointer/length/stride/overflow 검사와 C++ exception containment
- `structural-ffi-sys`와 `structural-ffi`: C layout mirror, immutable function-table safe
  wrapper와 concurrent caller-owned read 검증
- `native/capabilities.json`: ABI base는 C0, Rust ModelIR wire/canonical identity는 C1로
  범위를 제한해 implemented로 표시하고 C++ semantic ModelIR, restart, product E2E와
  HIP는 planned로 fail closed
- installed `structural-native-build.json`: package/ABI/compiler/build-type/backend identity
- `native/compatibility-owners.json`: 기존 `structural_runtime_ffi`와
  `mgt_hip_full_residual_ffi`를 아직 workspace member로 이동하지 않고 각각의 명시적
  migration owner와 legacy-preservation 상태를 고정

이 slice는 ModelIR handle, mutable execution handle, solver, ResultIR, checkpoint 또는 HIP
backend를 구현했다고 주장하지 않는다. ModelIR opaque lifetime·concurrent immutable read와
mutable execution exclusion은 Slice C/D에서 해당 handle이 존재할 때 닫는다. 기존 probe의
compatibility member/table adapter 전환도 transition plan의 R1/H1 순서를 유지한다.

## 12. Slice C implementation boundary

Slice C는 ABI v1.1의 ModelIR core만 C0로 구현한다.

- `model_ir_v1.h`: 모든 ModelIR v2 family, unit, provenance, extension, roundtrip과
  unsupported feature를 운반하는 fixed-width typed descriptor
- `structural_model_ir`: descriptor header/pointer/count/UTF-8/overflow 검사, complete
  deep copy, unit·ID·reference·geometry·constraint·load graph·time·roundtrip·bounded profile
  semantic validation
- `structural_c_abi_v1`: v1.0 null-tail compatibility, v1.1 table negotiation, exception
  containment, caller-owned no-partial report/snapshot export
- immutable handle registry: query가 보유한 shared lifetime과 destroy를 조정해 in-flight
  query가 있으면 `SA_ERR_STATE_CONFLICT`로 fail closed
- native CTest: v1.0/v1.1 negotiation, layout, failed-create atomicity, deep-copy proof,
  undersized output, semantic invalid report, cycle/time/blocker와 concurrent immutable query

이 boundary는 C++가 JSON Schema나 canonicalization을 소유한다고 주장하지 않는다. 또한
Rust descriptor builder, Python/C++ zero-diff oracle parity, semantic/provenance snapshot hash
재검증, safe RAII wrapper와 CLI는 Slice D 전까지 aggregate `modelir_v2` capability를
planned 상태로 유지한다.

## 13. Slice D implementation boundary

Slice D는 backend-independent ModelIR validation domain을 D1=C3까지 연결한다.

- `structural-ffi-sys`: ABI v1.1 table과 모든 typed ModelIR descriptor의 handwritten layout
  mirror; v1.0 128-byte table prefix와 null extension slot compatibility 유지
- `structural-ffi`: schema-valid document를 위한 Rust-owned descriptor arena, immutable opaque
  handle RAII, concurrent report/snapshot read, caller-owned output와 exact drop ownership
- Rust parse/arena/report reconstruction은 C 호출 전후의 safe Rust에서만 실행되고 C가 다시
  호출하는 Rust callback/export를 제공하지 않으므로 Rust panic이 ABI frame을 횡단하지 않음
- round-trip verification: C++ canonical snapshot을 Rust strict parser로 재구성하고 original
  canonical bytes, content/semantic/provenance hash와 report identity를 모두 비교
- Python oracle parity: tracked positive fixture와 semantic/blocker negative matrix에서
  issue code/path, readiness, blocker와 세 hash를 비교
- `structural-cli model validate`: versioned report를 출력하고 contract validity와 optional
  `--require-analysis-ready` policy를 분리

이 boundary는 parser/validation domain의 C2 대체 deterministic cross-language gate다. solver,
element/material, assembly와 result recovery의 CPU/HIP C2를 대체하지 않는다. 또한 checkpoint,
ResultIR/ReportIR analysis E2E, Python 제거 또는 legacy probe R1/H1 migration을 주장하지 않는다.

## 14. Legacy structural runtime R1 boundary

ModelIR Slice D 다음 PR은 `implementation/phase1/structural_runtime_ffi`만 temporary native
workspace member로 편입한다.

- package `structural_runtime_ffi`와 `cdylib`/`rlib` output name은 유지한다.
- native root `Cargo.lock`, workspace fmt/clippy/test와 Rust 1.77 compile gate가 적용된다.
- 기존 Python bridge는 explicit local target directory를 사용해 기존 shared-library path를
  유지하지만 dependency resolution은 native workspace lock을 따른다.
- ABI v3의 7개 `repr(C)` layout, 5개 legacy export, error taxonomy와 네 bounded golden case를
  versioned compatibility inventory와 Rust test로 고정한다.
- CI는 source export와 release cdylib dynamic export가 inventory와 exact-match인지 검사한다.
- legacy standalone `Cargo.lock`은 rollback/deprecation 기간을 위해 보존하지만 native build
  graph의 lock authority는 `native/Cargo.lock` 하나다.

R1은 numerical source를 C++로 옮기지 않고 legacy function을 `sa_get_api_v1` table에 추가하지
않는다. 따라서 solver, restart, ResultIR/ReportIR, product E2E 및 어떤 C0-C6 capability도 새로
승격하지 않는다. 다음 gate는 R2 contract extraction이며 H1 HIP table adapter는 CPU product
path가 생길 때까지 H0 상태를 유지한다.
