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
- v1.2는 0x00010002이며 bounded CPU linear Frame3D compile/solve table slots를 추가한다.
- v1.3은 0x00010003이며 uniform initial-member-local force load-case solve slot을 추가한다.
- v1.4는 0x00010004이며 기존 32-byte member row의 두 reserved slot을 협상된
  RX/RY/RZ end-release mask로 활성화한다.
- v1.5는 0x00010005이며 기존 80-byte model-input prefix 뒤에 sparse
  `sa_linear_frame3d_member_offset_v1` pointer/count tail을 추가한다.
- minor 증가는 descriptor tail, 새 optional function pointer 또는 명시적 reserved slot의
  version-gated 활성화만 허용한다.
- 기존 non-reserved field offset/width/meaning, enum numeric value와 ownership 변경은 major 증가다.
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

### 5.5 Frame3D v1.2/v1.3/v1.4/v1.5 table extension

ABI v1.2는 128-byte table의 v1.0/v1.1 prefix를 유지하면서 마지막 일곱 reserved slot 중
네 개를 typed Frame3D operation으로 소비한다. v1.0과 v1.1 요청에는 이 네 slot과 capability를
null/false로 반환하며, v1.2 요청에만 다음을 제공한다.

- `linear_frame3d_model_compile` / `linear_frame3d_model_destroy`
- `linear_frame3d_model_sizes` / `linear_frame3d_solve`
- `SA_CAPABILITY_LINEAR_FRAME3D_CPU`

ABI v1.3은 다음 다섯 번째 slot과 capability를 추가한다. v1.2 요청에는 이 tail을 null/false로
반환하므로 기존 caller의 104-byte prefix 의미를 바꾸지 않는다.

- `linear_frame3d_solve_load_case`
- `SA_CAPABILITY_LINEAR_FRAME3D_UNIFORM_MEMBER_LOAD`

load-case descriptor는 기존 full-length nodal vector와 최대 128개의 uniform member-load row를
함께 받는다. 각 row는 member index와 initial-member-local QX/QY/QZ kN/m force 성분을 가지며,
C++는 consistent fixed-end load를 조립하고 member force를 `K_local u_local - f_fixed`로 복구한다.
zero/non-finite row, 잘못된 member index, partial descriptor는 fail closed한다.

ABI v1.4는 새 function slot 없이 capability bit와 model-input minor로 협상한다.

- `SA_CAPABILITY_LINEAR_FRAME3D_ROTATIONAL_END_RELEASE`
- member i/j의 `SA_FRAME3D_MEMBER_RELEASED_DOF_MASK_I/J(...)`: RX/RY/RZ bit만 허용

v1.2/v1.3 model input에서는 두 slot이 계속 0이어야 한다. v1.4 C++ core는 원본
local stiffness의 released partition을 static condensation하고, uniform member load의 consistent
fixed-end vector에도 동일 operator를 적용한다. released local end-force component는 0으로
복구되며 Rust replay는 독립 Gauss-Jordan condensation으로 이를 재검산한다. 병진 release,
singular/ill-conditioned release partition과 globally unstable model은 fail closed한다.

ABI v1.5도 새 function slot 없이 capability bit와 append-only model-input tail로 협상한다.

- `SA_CAPABILITY_LINEAR_FRAME3D_RIGID_END_OFFSET`
- member index와 node-to-deformable-member-end global i/j vector를 갖는 64-byte offset row

v1.2-v1.4 caller의 80-byte input prefix는 그대로 허용하며 offset tail을 읽지 않는다.
v1.5 input은 full 96-byte descriptor와 sorted unique sparse offset rows를 요구한다. C++ core는
offset endpoint에서 길이와 local basis를 계산하고 `T_local_from_global B_rigid`를 stiffness,
consistent member load와 member-force recovery에 동일하게 적용한다. zero-effective-length,
non-finite, duplicate/out-of-range/zero-only row는 fail closed한다.

compile은 caller-owned node/section/member/restraint descriptor를 호출 안에서 검증하고 native
model로 deep-copy한다. Public boundary registry는 stale/double destroy를
`SA_ERR_INVALID_ARGUMENT`, in-flight query와 destroy 충돌을 `SA_ERR_STATE_CONFLICT`로 거부한다.
solve output은 global UX/UY/UZ/RX/RY/RZ displacement와 reaction, member-local
N/Vy/Vz/T/My/Mz end force 순서다. 현재 범위는 2-16 node, 1-32 member, 최대 60 free equation의
CPU dense reference alpha이며 HIP, prescribed displacement, translational release, self weight, load combination,
nonuniform/member-point load와 nonlinear state를 포함하지 않는다. 이 raw ABI operation은 ModelIR을 직접 받지 않으며 아래
`structural-runtime` adapter가 별도 fail-closed composition을 소유한다. ResultIR authority는 없다.

raw ABI에는 self-weight descriptor가 없다. `structural-runtime`의 ModelIR adapter만
`self_weight`를 global-axis 표준중력 `9.80665 m/s^2`의 무차원 배수로 해석하고,
`density_kg_m3 * area_m2`로 member mass/length를 만든 뒤 offset-aware initial local basis의
uniform QX/QY/QZ로 투영한다. explicit uniform row와 member별로 합산한 뒤 기존 v1.5 load-case,
release condensation, rigid transform, equilibrium 및 independent recovery gate를 그대로 통과시킨다.

load combination도 raw ABI descriptor가 아니라 `structural-runtime` adapter 소유다. selected
linear combination은 C++ ModelIR semantic validator가 확인한 acyclic reference graph를 따라
최대 256 combination / 4096 expanded term 범위에서 pattern factor로 결정론적으로 평탄화한다.
nodal vector와 member별 uniform row를 factor 합산해 단일 v1.5 load case로 solve하며, factor
곱·누적·load vector가 non-finite가 되면 ResultIR 없이 fail closed한다. ResultIR/ReportIR은
`load_pattern_id`와 `load_combination_id` 중 정확히 하나만 non-null로 보존한다.

### 5.6 Stable status taxonomy

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

## 14. Frame Alpha implementation boundary

Frame Alpha는 bounded linear Frame3D domain을 C1까지 연결한다.

- `structural_c_abi_v1`: ABI v1.2 bounded model compile/solve, ABI v1.3 append-only uniform
  initial-member-local load-case slot, ABI v1.4 RX/RY/RZ release condensation, ABI v1.5 finite global
  rigid end-offset transform, Timoshenko assembly, scaled dense solve,
  fixed-end-aware reaction/member-local force recovery와 live-handle registry
- `structural-ffi-sys`: C header와 byte/offset이 고정된 node/section/member/input/result 및
  다섯 function-pointer slot
- `structural-ffi`: v1.2/v1.3/v1.4/v1.5 table 검증, borrowed input-to-deep-copy compile, unique RAII ownership,
  bounded load-case descriptor, shape-checked caller-owned solve result와 stable diagnostic mapping
- `structural-runtime`: native ModelIR contract/readiness 검증 뒤 exact
  `linear_timoshenko_frame3d` subset만 raw Frame3D descriptor로 변환하고, N/Pa↔kN 단위를
  명시적으로 변환하며, 세 ModelIR hash에 결속된 authority-limited SI result를 반환. C++
  recovery와 분리된 Rust offset-geometry/section/local-axis/release/displacement/fixed-end-load 기반 12-DOF
  local-force replay를 수행하고 scaled L∞ `1e-9` 초과 drift를 차단
- `structural-contracts`: residual/free-DOF/global force·moment/independent recovery gate와 zero fallback을 모두
  통과한 결과만 fixed `bounded_candidate` authority의 strict canonical `ResultIR` v1으로
  승격하고, deterministic presentation 전용 `ReportIR` v1 schema/hash를 소유
- `structural-report`: ResultIR source identity, gate, summary와 deterministic first-tie
  displacement/reaction/member-end-force extrema를 결속하고 fixed numeric standalone HTML 투영
- `structural-cli model analyze-frame3d`: 명시한 load/result/report ID로 input→ResultIR,
  input→ReportIR 또는 input→HTML 한 artifact를 stdout에 출력하는 bounded C5 경로
- Workbench v2: same-origin ResultIR와 optional source-bound ReportIR를 strict duplicate/schema/
  profile/canonical-hash/source/gate/extrema/authority 검사 뒤 읽기 전용으로 표시하는 C0 typed
  consumer. 분석 submit/rerun이나 durable native job을 제공하지 않으며 bounded authority를
  승격하지 않음
- C0 evidence: C11/C++20/Rust layout, v1.0/v1.1 null-tail compatibility, v1.2/v1.3/v1.4/v1.5 negotiation,
  stale/double-destroy rejection, singular/invalid/buffer failure와 static/shared C++ tests
- C1 evidence: Python Timoshenko oracle against all six tip load/moment modes, a rotated,
  mixed-roll two-member spatial assembly, closed-form QX/QY/QZ uniform-load cantilevers, and an
  independently condensed released member for displacement, reaction and member-local end force,
  and an independent global rigid-offset transformation oracle

`linear_frame3d_cpu_alpha` solver/recovery domain은 C1이다. Solver domain에 필수인 C2
CPU/HIP parity가 없으므로 C3 cutover라고 주장하지 않는다. 별도의
`linear_frame3d_result_report_alpha`는 이 exact subset의 public CLI input→ResultIR/ReportIR
흐름만 C5로 표시한다. CPU/HIP C2, checkpoint/restart,
PDF·external comparison, Workbench execution E2E, broad engineering validation과 release authority는
열려 있다. 여기서 independent Rust recovery replay는 exact CPU subset에서 닫혔지만 external
code/experiment validation이나 CPU/HIP C2를 대체하지 않는다. 별도
`linear_frame3d_workbench_consumer_alpha`는 artifact consumption만 C0이다.
