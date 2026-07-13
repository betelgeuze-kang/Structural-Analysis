# Engine v2 HIP Native Probe 및 DeviceExecutionContext v1

- 문서 버전: 0.1.0
- 기준일: 2026-07-10
- 구현 상태: Phase 0 네이티브 탐지 및 모델 버퍼 상주 기반 완료
- capability profile: `phase0_hip_model_buffer_context_foundation`

## 1. 결론과 증명 범위

현재 구현은 `libamdhip64`를 직접 탐지하고, 선택한 HIP 장치에
`SolverModelBuffers v1`의 16개 정규 버퍼를 각각 한 번 할당·전송한 뒤 컨텍스트가
닫힐 때 해제하는 기반이다. 실제 ROCm/HIP 장치에서 모델 입력 버퍼가 상주한다는
사실과 그 과정의 전송·할당·동기화 양을 영수증으로 검증한다.

이 단계는 HIP 구조해석 솔버가 아니다. 강성행렬·CSR 연산자는 아직 바인딩되지
않고, `StateIR`도 장치에 올라가지 않으며, residual/JVP 커널·Krylov 솔버·결과
복구를 실행하지 않는다. 따라서 현재 영수증이 증명하는 최대 범위는
"검증된 SolverModelBuffers가 선택한 HIP 장치에 읽기 전용으로 상주한다"까지다.

| claim | `context_ready` | 의미 |
| --- | ---: | --- |
| `model_buffers_device_resident` | `true` | 16개 모델 버퍼의 초기 H2D와 명시적 동기화 완료 |
| `operator_bound` | `false` | CSR/강성 연산자가 컨텍스트에 결박되지 않음 |
| `state_bound` | `false` | StateIR displacement/state epoch가 결박되지 않음 |
| `residual_jvp_ready` | `false` | residual 및 JVP 장치 연산 미구현 |
| `solver_ready` | `false` | 선형·비선형 해석 솔버 미구현 |
| `device_resident_newton_krylov` | `false` | Newton/Krylov 장치 상주 루프 미구현 |
| `cpu_hip_parity_proven` | `false` | CPU/HIP 수치 동등성 미검증 |
| `commercial_readiness` | `false` | 상용 해석 기능·검증·성능을 의미하지 않음 |

위의 일곱 `false` 값은
[`hip_context_receipt_v1.schema.json`](../src/structural_analysis/schemas/hip_context_receipt_v1.schema.json)에서
상수로 고정되어 있다. 현재 v1 영수증을 재해석하거나 필드만 바꾸어 HIP 솔버
증거로 승격할 수 없다.

## 2. 구현 구성

### 2.1 Native capability probe

[`native.py`](../src/structural_analysis/engine_v2/backends/hip/native.py)는 다음 순서로
HIP runtime을 찾는다.

1. 호출자가 명시한 library 경로 또는 loader 이름
2. `/opt/rocm/lib` 및 `/opt/rocm/lib64`의 `libamdhip64.so*`
3. 시스템 동적 loader가 찾는 `amdhip64`

해결 가능한 실제 library 파일은 내용을 SHA-256으로 해시한다. 그 다음 `ctypes`로
다음 비할당 탐지 API만 호출한다.

- `hipInit`
- `hipGetDeviceCount`
- `hipDeviceGetName`
- `hipRuntimeGetVersion`
- `hipDriverGetVersion`

`HipCapabilityReceipt`는 runtime library의 탐지 경로·실제 경로·SHA-256,
선택 ordinal, 장치 수와 이름, raw runtime/driver version을 canonical JSON
SHA-256으로 결박한다. `fallback_policy="forbidden"`, `fallback_used=false`이며
context·모델 상주·operator·solver 실행을 모두 미증명으로 기록한다.

여기서 `context_created=false`는 probe가 Engine v2 stream, device allocation,
모델 컨텍스트를 만들지 않았다는 뜻이다. `hipInit` 내부의 driver/runtime 초기화
구현 세부까지 부정하는 표현은 아니다.

### 2.2 DeviceExecutionContext

[`context.py`](../src/structural_analysis/engine_v2/backends/hip/context.py)는 probe가
`ready`일 때만 다음 생명주기를 수행한다.

1. `SolverModelBuffers`의 schema, descriptor, numeric/entity/artifact hash를 먼저
   검증한다.
2. 선택 장치와 non-blocking stream을 준비한다.
3. 정규 순서의 16개 descriptor마다 `hipMalloc`을 한 번 수행한다.
4. 해당 bytes를 `hipMemcpyAsync(..., H2D)`로 한 번 전송한다.
5. 모든 초기 전송 뒤 stream을 한 번 명시적으로 동기화한다.
6. 컨텍스트 사용 중 각 allocation을 읽기 전용 `HipBufferView`로 노출한다.
7. `close()`에서 allocation을 역순으로 해제하고 stream을 파기한다.

`HipBufferView`에는 `name`, `dtype`, `shape`, C layout, byte length,
`data_hash`, `content_hash`, device ordinal, access 및 초기 전송 방식만 들어간다.
device pointer, 주소, stream 또는 native handle은 Python `repr`이나 JSON
영수증에 직렬화되지 않는다. validator는 해당 이름을 가진 runtime key도
거부한다.

## 3. Python API

Capability만 확인할 때는 다음 API를 사용한다.

```python
from structural_analysis.engine_v2.backends.hip.native import (
    probe_hip_capability,
)

capability = probe_hip_capability(device_ordinal=0)
if capability.status != "ready":
    print(capability.status_code, capability.message)
```

모델 버퍼 상주 컨텍스트는 다음과 같이 연다.

```python
from structural_analysis.engine_v2.backends.hip.context import (
    open_device_execution_context,
)

opened = open_device_execution_context(
    solver_model_buffers,
    device_ordinal=0,
    memory_budget_bytes=None,
)

if not opened.ready:
    # 드문 failed-open cleanup 오류에서는 non-ready cleanup-only owner가
    # 반환될 수 있다. 이 객체는 buffer 접근 없이 close() 재시도만 허용한다.
    if opened.context is not None:
        opened.context.close()
    print(opened.receipt.reason)
else:
    assert opened.context is not None
    with opened.context as context:
        coordinates = context.buffer("node_coordinates_m")
        ready_receipt = context.receipt()
```

`runtime_library`로 특정 `libamdhip64`를 명시할 수 있다. `runtime` 인자는
hardware-independent failure/telemetry 테스트를 위한 dependency-injection seam이며,
제품 실행 경로에서는 native runtime을 사용한다.

`export_for_verification(name)`은 명시적으로 선택한 버퍼 하나를 D2H로 내려받아
원래 descriptor의 `data_hash`와 일치하는지 확인한다. 이 API는 검증 경계이며
상시 해석 루프용 데이터 접근 방법이 아니다.

## 4. 정확한 telemetry 계약

영수증은 추정 비율 대신 실제 API 경계에서 누적한 정수 counter를 기록한다.

| 필드 | 계측 의미 |
| --- | --- |
| `h2d_bytes` | 성공한 초기 H2D 대상 descriptor byte length의 합 |
| `d2h_bytes` | 명시적 verification export로 내려받은 byte length의 합 |
| `h2d_operation_count` | 성공한 초기 H2D 호출 수 |
| `d2h_operation_count` | 성공하고 hash 검증된 verification export 수 |
| `blocking_copy_count` | 이 구현이 요청한 blocking copy 수. 현재 항상 `0` |
| `explicit_sync_count` | 초기 upload 완료 및 verification export를 위해 요청한 stream sync 수 |
| `allocation_count` | 성공한 모델 payload allocation 수 |
| `deallocation_count` | 성공한 해제 수 |
| `current_device_payload_bytes` | 아직 컨텍스트가 소유한 descriptor payload bytes |
| `peak_device_payload_bytes` | 컨텍스트가 동시에 소유한 descriptor payload bytes의 최대값 |
| `kernel_launch_count` | 현재 v1에서는 상수 `0` |
| `fallback_count` | 현재 v1에서는 상수 `0` |

`current_device_payload_bytes`와 `peak_device_payload_bytes`는 모델 descriptor의
payload만 계측한다. HIP runtime, stream, allocator metadata, page granularity 또는
다른 프로세스가 차지한 VRAM을 포함하지 않는다. 따라서
`free_memory_bytes_before_upload - free_memory_bytes_after_upload`와 같아야 하는
값이 아니다.

초기 `context_ready` 영수증에서는 다음 불변식을 검증한다.

- `h2d_bytes == sum(BufferView.byte_length)`
- `h2d_operation_count == allocation_count == 16`
- `peak_device_payload_bytes == sum(BufferView.byte_length)`
- `current_device_payload_bytes == sum(BufferView.byte_length)`
- 명시적 verification 전 `d2h_bytes == d2h_operation_count == 0`
- `kernel_launch_count == fallback_count == 0`

`export_for_verification()` 한 번마다 해당 buffer bytes, D2H operation 1회,
explicit sync 1회가 추가된다. `close()` 후에는
`status="context_closed"`, `model_buffers_device_resident=false`,
`current_device_payload_bytes=0`이 되며, stale `buffer()` 접근은 거부된다.

## 5. 현재 워크스테이션 실측

2026-07-10에 repository의
`frame_cantilever_all_modes.json`/`LC_AXIAL` fixture로 native probe와 실제 context
open/close를 다시 실행했다.

| 항목 | 관측값 |
| --- | --- |
| runtime library | `/opt/rocm-6.0.2/lib/libamdhip64.so.6.0.60002` |
| library SHA-256 | `3210b3126e1bab3fbfe4eaaf5110562026494ab93a973daf03dbc1e603a8fceb` |
| selected device | ordinal `0`, `AMD Radeon RX 6900 XT` |
| enumerated device count | `1` |
| runtime version raw | `60032831` |
| driver version raw | `60032831` |
| reported total memory | `17,163,091,968` bytes |
| architecture | `null` — 현재 probe가 검증하지 않음 |
| canonical BufferView 수 | `16` |
| fixture payload/H2D | `412` bytes / 16 operations |
| initial D2H | `0` bytes / 0 operations |
| allocation/current/peak | `16` / `412` / `412` bytes |
| initial explicit sync | `1` |
| kernel/fallback | `0` / `0` |

이 실측은 해당 시점의 runtime/device 접근과 412-byte fixture의 모델 버퍼 상주를
증명한다. RX 6900 XT의 구조해석 성능, `gfx1030` architecture, 대규모 모델
수용량, residual/JVP 정확도 또는 solver 속도를 증명하지 않는다. raw version
정수도 별도 공식 ABI 해석 없이 사람이 읽는 semantic version으로 변환하지 않는다.

현재 capability/context 집중 테스트는 실제 장치 경로를 포함해 26개가 통과했다.
하드웨어가 없는 호스트에서도 fake runtime으로 동일 계약과 실패 정리를 검증한다.

## 6. unavailable 및 fail-closed 동작

HIP 준비가 되지 않으면 CPU 경로로 전환하지 않는다. 일반 반환값은
`HipContextOpenResult(context=None, receipt.status="unavailable")`이며,
`actual_backend=null`, `fallback_used=false`, `fallback_count=0`, buffer view 0개,
모든 solver claim `false`를 유지한다. 단, failed-open transaction의 `free` 또는
stream destroy 자체가 실패하면 남은 native resource를 잃지 않도록 `context`에
non-ready cleanup-only owner를 process-local로 반환한다. 이 객체는 buffer/export를
거부하고 `close()` 재시도만 허용하며 pointer/stream을 receipt에 직렬화하지 않는다.

Context reason code는 다음으로 제한된다.

- `hip_native_library_missing`
- `hip_native_abi_mismatch`
- `hip_runtime_init_failed`
- `hip_no_device`
- `hip_device_ordinal_invalid`
- `hip_device_access_failed`
- `hip_allocation_failed`
- `hip_copy_failed`
- `hip_memory_budget_exceeded`

명시한 memory budget보다 descriptor payload 합이 크면 allocation 전에
`hip_memory_budget_exceeded`로 종료한다. 중간 allocation/copy가 실패하면 이미
성공한 allocation의 해제를 시도하고 성공한 free만 telemetry와 current bytes에
반영한다. cleanup까지 성공하면 `current_device_payload_bytes=0`인 unavailable
영수증을 반환한다. cleanup 일부가 실패하면 남은 bytes를 그대로 기록하고 위의
cleanup-only owner가 pointer/stream 소유권을 보존한다. 변조된 SolverModelBuffers
hash는 native probe와 allocation보다 먼저 거부한다.

사용자 입력 형식 오류나 위조된 receipt/hash는 runtime unavailable과 구분되는
계약 예외다. receipt는 Draft 2020-12 JSON Schema, canonical receipt hash, 원본
SolverModelBuffers binding, 16개 descriptor metadata 및 claim 불변식을 다시
검증한다.

## 7. 기존 HIP/ROCm 자산의 사용 경계

기존 `implementation/phase1` 자산은 알고리즘·ABI 참고 및 회귀 oracle로는
유용하지만, 이 v1 컨텍스트의 권위 있는 실행 또는 telemetry 증거로 가져오지
않는다.

- [`hip_full_residual_ffi.cpp`](../implementation/phase1/hip_full_residual_ffi.cpp)는
  opaque handle과 HIP kernel 패턴을 제공하지만, eval마다 state 전체 H2D,
  device synchronization, residual 전체 D2H를 수행한다. 현재 목표인 반복 루프
  장치 상주를 증명하지 않는다.
- [`hipsparse_ilu_bicgstab_solve.cpp`](../implementation/phase1/hipsparse_ilu_bicgstab_solve.cpp)는
  hipSPARSE CSR/ILU 호출 예제지만 BiCGStab vector, dot, norm 및 반복 제어가
  host에 있고 SpMV·preconditioner 호출마다 vector를 왕복한다.
- [`rocalution_sparse_solve.cpp`](../implementation/phase1/rocalution_sparse_solve.cpp)는
  `device_residency_ratio=1.0`, `host_copy_bytes=0`을 결과에 고정 기록하므로
  현재의 exact transfer counter를 대신할 수 없다. library 내부 fallback도 이
  상수만으로 판별할 수 없다.
- [`gpu_newton_core.py`](../implementation/phase1/gpu_newton_core.py)는 반복 중
  `.cpu().numpy()` 경계를 포함하므로 device-resident Newton 증거가 아니다.
- [`rust_nonlinear_frame_bridge.py`](../implementation/phase1/rust_nonlinear_frame_bridge.py)는
  CPU fallback 실행 경로와 상수형 residency/copy metadata를 포함한다. Engine v2
  native HIP backend의 fallback 금지 영수증으로 승격할 수 없다.

따라서 기존 성공·부분 성공·실패 benchmark는 설계 입력과 counter-evidence로
보존하되, 새 capability/context receipt와 해시 체인을 통과하지 않은 결과를
Engine v2 HIP 구현 완료나 상용화 증거로 합산하지 않는다.

## 8. 다음 슬라이스: CSR operator 및 residual/JVP

다음 최소 슬라이스는 현재 v1 컨텍스트에 solver 이름을 붙이는 작업이 아니라,
backend-neutral 계약에 결박된 HIP CSR operator와 state를 새 버전으로 추가하는
작업이다.

1. ExecutionPlan의 정규 CSR `row_ptr`, `column_indices`, FP64 values 및 load vector를
   plan/operator hash와 함께 장치에 한 번 적재한다.
2. StateIR의 정확한 plan hash와 state epoch에 결박된 displacement/direction
   vector를 장치 상주 view로 추가한다.
3. `r(u) = K u - F`와 `Jv = K v`를 HIP/rocSPARSE 경로에서 계산한다.
4. kernel launch, H2D/D2H, sync, allocation telemetry를 실제 호출 경계에서
   누적하고 암묵적 full-vector 왕복을 금지한다.
5. CPU reference와 residual/JVP FP64 parity, zero direction, tampered plan/state,
   비유한값, stale epoch 및 unavailable 경로를 집중 검증한다.
6. 새 receipt에서 위 조건이 모두 검증된 경우에만 `operator_bound`,
   `state_bound`, `residual_jvp_ready`를 `true`로 만들 수 있다.

현재 v1 schema는 이 claim들을 `false`로 고정하므로 수정 승격하지 않는다.
CSR/JVP용 새 capability profile과 versioned receipt를 추가해야 한다. 그
슬라이스에서도 `solver_ready`, `device_resident_newton_krylov`,
`cpu_hip_parity_proven`, `commercial_readiness`는 각자 별도의 수치·실행 증거가
생길 때까지 계속 `false`여야 한다.

CSR residual/JVP가 닫힌 다음에만 device-resident Krylov/preconditioner,
reaction/recovery/energy, nonlinear state transition, Newton globalization 및
대규모 성능 검증으로 진행한다.

후속 계약 구현은 [HIP AOT canonical-CSR residual/JVP replay v1](engine-v2-hip-residual-jvp-v1.md)에
기록한다. 해당 후속 층도 현재 워크스테이션에서는 native artifact build/run과
CPU-HIP parity가 unavailable이며, 본 buffer-only v1 receipt의 고정된 `false`
claim을 승격하거나 재해석하지 않는다.
