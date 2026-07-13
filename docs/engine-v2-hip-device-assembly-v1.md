# Engine v2 HIP 요소·재료 장치 조립 v1

- Status: implemented contract, unsigned and non-promoting
- Scope: zero-offset, zero-release, zero-prescribed-displacement 3D Euler-Bernoulli frame and linear truss
- Authority: [Structural Solver Engine v2 마스터 로드맵](structural-solver-engine-v2-master-roadmap.md)
- Claim boundary: HIPRTC 컴파일과 결정론적 조립 context를 구현했지만, 현재 샌드박스에서 실장치 module launch·수치 parity는 실행하지 못했다. 솔버·Krylov·속도·end-to-end O(N)·상용 준비도 증거가 아니다.

## 결과

기존 HIP residual/JVP replay는 CPU가 조립한 `csr_values`를 장치로 옮겼다. 이 v1은 그 경로를 제거하고 다음 두 커널로 CSR 수치값을 장치에서 생성한다.

1. 요소당 144개 `TᵀkT` 기여도를 계산한다.
2. CSR slot별 reverse segment를 소스 기여도 순서대로 합산한다.

수치 atomic을 사용하지 않으며, `atomicCAS` 는 첫 오류 코드 기록에만 사용한다. 조립 순서는 `element -> local row -> local column`으로 고정된다.

## 계약

### `HipAssemblyPlanV1`

CPU는 수치 강성을 만들지 않고 다음 심볼릭 입력만 컴파일한다.

- `reference_axis_code: uint8[E]`
- `reverse_segment_offsets: int32[Z+1]`
- `reverse_contribution_indices: int32[144E]`

축 코드는 global Y=`1`, global Z=`2`다. CPU reference 규칙에 따라 기본 Z를 쓰고 `abs(local_x.z) > 0.9`일 때만 Y를 선택한다. GPU는 이 임계값을 다시 계산하지 않고, 해시로 결속된 host 코드를 소비한다.

역방향 map은 `O(C+Z)`, `C=144E`로 컴파일되며 빈 segment와 structural-zero slot을 보존한다. 단, JSON mirror의 `.tolist()` 생성은 `O(C+Z)` Python 객체 메모리 증폭을 수반한다.

### HIPRTC fixed module

고정 소스와 두 심볼을 사용한다.

- `engine_v2_linear_frame_truss_element_contributions_v1`, block 144
- `engine_v2_linear_frame_truss_csr_gather_v1`, block 256

요소 커널은 connectivity, element type/formulation, material law/index/properties, section family/index/properties, roll, 길이, finite value를 fail-closed 재검사한다. 큰 index 곱셈은 64-bit offset으로 수행하고 host ABI는 `144E <= INT32_MAX`을 강제한다.

현재 ROCm 6.0.2 HIPRTC `gfx1030` 컴파일은 성공했다.

- source SHA-256: `72df17cd699997b48cfa4701fb3c1f6baa96499804e5e4b097b33afdbed1ff4c`
- code object: 17,056 bytes
- code-object SHA-256: `9db2c0517dca9ddf94843f4278b4472a06991bb65b61643cccf45159d58c9b2d`
- compiler log: empty
- 두 fixed symbol: `llvm-nm` 확인

이 code-object identity는 내부 컴파일 측정값이며 서명된 독립 증거가 아니다.

### `HipAssemblyExecutionContext`

기존 `DeviceExecutionContext` 스트림과 16개 ModelBuffer 상주 할당을 재사용한다. 자식 할당은 다음 8개다.

- CSR row pointer, column index
- reference-axis code
- reverse offsets, reverse indices
- element contributions
- CSR values
- error flag

H2D는 앞의 심볼릭 5개 배열과 zero error flag만 허용한다. `element_contributions`/`csr_values`는 host backing을 생성하지 않는 device-only 할당이다. 영수증의 `host_csr_values_h2d_bytes`는 항상 0이다.

조립은 context open 중 한 번만 실행한다. 두 launch, error-flag D2H, 선택적 CSR D2H, 한 번의 assembly sync가 동일 stream에 순서대로 들어간다. `verify_cpu_parity=False`면 CSR을 다운로드하지 않고 device operator만 보유하며, parity claim은 false다.

## 오류·소유권 정책

- kernel/copy/sync/error-flag/nonfinite/parity 실패는 context를 poison 처리한다.
- CPU 수치 결과는 성공한 GPU 실행 후 parity oracle로만 사용하며 fallback으로 쓰지 않는다.
- allocation/H2D/D2H/sync/launch/free/module unload/base close의 시도와 성공을 분리 계수한다.
- 중간 실패 후 resource가 남으면 cleanup-only owner를 반환해 `close()`를 재시도할 수 있게 한다.
- kernel만 회수하지 못한 경우에도 owner를 유실하지 않는다.
- 입력 plan/buffer는 open 시점에 다시 detach해 caller mapping 교체 TOCTOU를 차단한다.
- receipt/operator view에 pointer, address, stream, handle, module, function을 직렬화하지 않는다.
- 주입 runtime/kernel은 항상 `injected_test_double`로 표시하고 native evidence로 승격하지 않는다.

## 검증

집중 검증은 다음을 포함한다.

- 심볼릭 plan, 커널, context, hardware gate 결합: `85 passed, 2 skipped`
- reverse map random 400건과 `±0.9`/nextafter 경계
- 외부 mapping 교체, 완전 재해시 receipt 위조, mutable/nested type 공격
- host CSR H2D 함정과 output-only host allocation 함정
- malloc/H2D/D2H/sync/free/unload/base-close/postprocess/host-OOM 실패 회수
- pointer/stream `uintptr` overflow, 악성 예외 `__str__`, runtime-reference redaction
- 성공 evaluation의 전체 telemetry/ID/binding/parity 재도출

현재 샌드박스에서 gfx agent가 노출되지 않아 두 hardware launch test는 skip됐다. 두 경우 모두 CPU fallback을 사용하지 않았다.

## 남은 경계

- 실제 AMD GPU의 frame+truss module launch·global CSR parity receipt
- [상주 CSR residual/JVP consumer lease](engine-v2-hip-resident-csr-consumer-v1.md)의 native hardware parity와 device-direction producer; test-double same-stream 소비 계약은 별도 v1으로 구현됨
- device Krylov/CG/FGMRES와 preconditioner
- release, offset, prescribed displacement, shell/solid/link, nonlinear material
- property-only 재조립과 topology batch
- peak host/device memory 및 실메시 scaling/latency/speedup
- 서명된 다중 ROCm·GPU V&V 증거

따라서 이 v1의 정확한 결론은 **CPU-조립 CSR replay를 제거할 수 있는 장치 조립 계약과 HIPRTC 코드 경로를 구현했다**는 것이다. 별도 resident-consumer v1이 test-double same-stream 소비 계약을 연결했지만, 실장치 combined parity와 device Krylov는 다음 gate다.
