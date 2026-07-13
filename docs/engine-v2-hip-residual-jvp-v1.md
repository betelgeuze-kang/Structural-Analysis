# Engine v2 HIP AOT Canonical-CSR Residual/JVP Replay v1

- 문서 버전: 0.1.0
- 기준일: 2026-07-10
- 구현 상태: AOT 커널·operator/state context·검증 영수증 구현, native 실행은 현재 환경에서 unavailable
- capability profiles: `phase0_hip_csr_residual_jvp_operator_context`, `phase0_hip_canonical_csr_residual_jvp`

## 1. 결론과 claim boundary

이 슬라이스는 `ExecutionPlan v1`의 정규 full-DOF CSR 강성행렬, 전역 하중과
하나의 committed `StateIR`를 HIP 장치에 고정한 뒤, caller-owned stream에서
하나의 fused kernel로 다음을 재생하는 검증 경로다.

- residual: `R(u) = K u - F`
- linear JVP: `Jv = K v`

구현은 다음 세 층을 분리한다.

1. AOT source와 C ABI, toolchain·artifact hash receipt
2. 기존 buffer-only `DeviceExecutionContext v1` 위의 plan/state 상주 context
3. 명시적 결과 다운로드와 별도 CPU CSR oracle parity receipt

현재 증명 범위는 사전 조립된 선형 CSR의 단일 residual/JVP 재생 계약이다.
HIP element/material 조립, constitutive update, 선형해법, Newton/Krylov,
reaction/recovery/energy, end-to-end `O(N)`, CPU 대비 speedup 또는 상용 준비를
증명하지 않는다. 기존 `DeviceExecutionContext v1`의 operator/state/solver claim도
변경하거나 재해석하지 않는다.

## 2. AOT kernel artifact 계약

권위 있는 source는 다음 하나다.

```text
src/structural_analysis/engine_v2/backends/hip/kernels/
  engine_v2_csr_residual_jvp.hip.cpp
```

공개 C entrypoint는 `engine_v2_hip_csr_launch`이며 descriptor ABI version은 `1`,
block size는 `256`이다. 커널은 row당 thread 하나를 사용하고 CSR column 저장
순서대로 두 FP64 accumulator를 갱신한다. atomic, kernel-side allocation,
H2D/D2H, stream sync, device 선택과 CPU 계산은 포함하지 않는다.

빌드는 target을 `gfx*` 문자열로 명시해야 하고 다음 핵심 flag를 고정한다.

```text
-O3 -std=c++17 -fPIC -shared -fno-fast-math -ffp-contract=off
```

`hipcc`와 `ocml.bc`/`ockl.bc`를 포함한 device-library directory는 같은 ROCm
설치 root에 있어야 한다. 다른 버전의 bitcode를 찾아 자동 혼합하지 않는다.
`HIP_CLANG_PATH`, `ROCM_PATH`, `HIPCC_*_FLAGS_APPEND`, `HCC_AMDGPU_TARGET` 등
compiler·path·flag·target을 바꿀 수 있는 26개 ambient override 중 하나라도
설정되어 있으면 값은 읽거나 출력하지 않고 빌드 전에 fail-closed한다. 거부 정책과
전체 변수 이름 목록, override 부재 여부는 compiler identity receipt에 결박한다.
artifact receipt는 source/library SHA-256, compiler identity, device-library content
hash, targets, flags, descriptor layout과 ABI/build-target hash를 결박한다.

receipt의 `operator_execution_proven`, `numerical_parity_proven`,
`speedup_proven`은 모두 `false`다. 빌드와 library load 성공은 GPU kernel 완료나
수치 정확도 증거가 아니기 때문이다. runtime loader는 명시적 content hash,
receipt, native ABI/layout/targets를 다시 확인하고 `RTLD_LOCAL`로만 결합한다.
v1 receipt는 빌드 당시의 절대 library path도 해시에 포함하므로 같은 경로의
prebuilt artifact를 재검증하는 개발 계약이다. 이동 가능한 상용 bundle은
content-addressed 상대 ID 또는 설치 시 재증명 정책을 별도 버전으로 정의해야 한다.

## 3. Plan/state 상주 context

새 context는 기존 `DeviceExecutionContext v1`을 소유하되 그 schema나 claim을
수정하지 않는다. 추가로 다음 8개 payload를 context 수명 동안 유지한다.

| 장치 view | dtype | open 시 H2D | 접근 |
| --- | --- | ---: | --- |
| CSR row pointer | `<i4` | 1 | read-only |
| CSR column index | `<i4` | 1 | read-only |
| CSR values | `<f8` | 1 | read-only |
| global load | `<f8` | 1 | read-only |
| committed displacement | `<f8` | 1 | read-only |
| direction workspace | `<f8` | 0 | read/write |
| residual workspace | `<f8` | 0 | write-only |
| JVP workspace | `<f8` | 0 | write-only |

context open 전에 buffer, plan과 committed state의 schema/hash/DOF/operator binding을
검증한다. trial state, cross-plan state, 변조된 artifact receipt와 비유한 vector는
runtime 작업 전에 거부한다. operator/state binding은 context가 닫힐 때까지
고정되며 state를 evaluation마다 다시 올리지 않는다.

검증 evaluation 한 번의 실제 호출 경계는 다음과 같다.

- direction H2D 1회
- fused kernel launch 1회
- residual/JVP D2H 각 1회
- 명시적 stream sync 1회
- fallback 0회

allocation·copy·sync·launch·free에는 attempt/success counter가 각각 존재한다.
evaluation 실패 후 context는 poisoned 상태가 되어 재사용할 수 없고 CPU 결과를
대신 반환하지 않는다. cleanup 일부가 실패하면 아직 해제되지 않은 pointer의
소유권과 current bytes를 process-local context가 보존하며 `close()` 재시도만
허용한다. pointer, stream, handle과 주소는 JSON receipt에 기록하지 않는다.
foundation open transaction 자체의 cleanup이 실패한 경우에는 operator open 결과의
nonserialized `cleanup_owner`가 base resource를 보존하며, `ready=false`와
`actual_backend=null`을 유지한 채 `close()` 재시도만 제공한다.

호출자가 지정한 combined memory budget은 foundation/operator allocation 전에
강제하지만, v1 receipt에는 요청 budget 자체를 기록하지 않는다. 또한 base device
architecture는 nullable이며 artifact target과의 명시적 receipt 교차결박은 아직
없다. 성공한 native launch는 runtime 호환성의 한 사례일 뿐 지원 GPU matrix가 아니다.

## 4. native와 test-double 증거 분리

hardware-independent 테스트는 fake HIP runtime과 fused kernel test double을 쓴다.
이는 상주·수명·전송·hash·수치 의미론을 검증하지만 receipt에는
`execution_evidence_kind="test_double"`로 남고 native HIP 실행을 주장할 수 없다.

`native_hip`은 다음 조건을 모두 만족한 실제 경로에서만 가능하다.

- 검증된 `LoadedHipCsrKernel` 인스턴스와 typed artifact receipt
- injection runtime 없이 native `libamdhip64` context 사용
- kernel enqueue 성공
- 같은 stream의 output D2H와 sync 성공
- finite FP64 residual/JVP 수신

클래스 이름이나 임의 JSON만으로 native 증거를 위조할 수 없다. native 결과도
단일 evaluation 실행만 증명하며 solver나 전역 parity를 증명하지 않는다.

## 5. CPU oracle parity의 정확한 범위

parity verifier는 장치 evaluation과 분리되어 같은 canonical CSR를 CPU에서 직접
재생한다. residual/JVP의 max absolute/relative error와 tolerance, 입력·출력 hash를
한 receipt에 결박한다.

PASS가 증명하는 범위는 `한 모델 × 한 committed state × 한 direction × 한 fused
evaluation`이다. test double PASS는 계약/CPU 수치 재생일 뿐 CPU-HIP parity가
아니다. 실제 `native_hip` 결과의 PASS도 해당 단일 사례의 좁은 parity이며
`cpu_hip_global_parity_proven`, constitutive/solver/Newton/Krylov/commercial claim은
계속 `false`다.

## 6. 복잡도 경계

커널의 논리 작업량은 row visit `N`, CSR entry visit `nnz`, multiply `2*nnz`,
load subtraction `N`이므로 `O(N + nnz)`다. 추가 장치 workspace는 full vector
세 개로 `O(N)`이다.

이것은 커널 한 번의 source-level 작업량이다. 현재 `ExecutionPlan v1`은 CPU에서
operator를 컴파일하며 검증 evaluation은 full residual/JVP를 host로 내린다.
따라서 전체 해석 시간·메모리 `O(N)`, iteration당 host copy 0,
device-resident solve 또는 speedup 주장의 근거가 아니다.

## 7. 현재 워크스테이션의 fail-closed 상태

2026-07-10 재검사 결과는 다음과 같다.

| 항목 | 관측 |
| --- | --- |
| compiler | HIP `6.0.32831`, AMD clang `17.0.0`, ROCm `6.0.2` |
| enumerated offload target | `gfx1030` |
| `/dev/kfd`, render node | 현재 sandbox에 없음 |
| native runtime probe | `unavailable`, `hip_init_failed`, fallback `false` |
| AOT toolchain probe, 일반 shell | `hip_csr_toolchain_environment_override` |
| AOT toolchain probe, override 제거 후 | `hip_csr_device_libraries_unavailable` |
| matching ROCm 6.0 device bitcode | compiler root 안에서 찾지 못함 |

현재 일반 shell에는 toolchain 의미를 바꿀 수 있는 ambient override 이름이 있어
강화된 기본 probe는 먼저 `hip_csr_toolchain_environment_override`로 중단한다.
해당 값을 노출하지 않고 clean environment에서 동일 compiler root를 확인해도
matching ROCm 6.0 device bitcode가 없으므로 native artifact를 만들 수 없다.

ROCm 5.7.1 bitcode를 ROCm 6.0.2 compiler에 강제로 연결한 결과는 재현 가능한
동일 toolchain 증거가 아니므로 readiness, native execution 또는 parity 근거로
사용하지 않는다. 현재 환경의 host-only 구문 검사는 C++ source 진단일 뿐 shared
artifact build나 GPU 실행 증거가 아니다.

## 8. 엄격한 빌드·실행 명령

matching toolchain이 준비된 환경에서 artifact와 receipt를 별도 경로에 생성한다.
target, output과 receipt는 모두 명시해야 하며 기존 파일을 덮어쓰지 않는다.

```bash
python3 scripts/build_engine_v2_hip_csr_kernel.py \
  --target gfx1030 \
  --output /absolute/path/libengine_v2_hip_csr.so \
  --receipt-out /absolute/path/libengine_v2_hip_csr.receipt.json
```

prebuilt artifact를 실제 ModelIR v2 fixture에 결합하는 probe는 다음과 같다.
unavailable, artifact/ABI/hash 오류 또는 cleanup 오류는 nonzero로 끝나며 CPU
결과로 대체하지 않는다.

```bash
python3 scripts/probe_engine_v2_hip_csr_replay.py \
  --artifact /absolute/path/libengine_v2_hip_csr.so \
  --artifact-receipt /absolute/path/libengine_v2_hip_csr.receipt.json \
  --model tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json \
  --load-pattern LC_AXIAL \
  --direction ones
```

기존 `scripts/probe_engine_v2_hip.py`는 runtime과 buffer-only v1 availability만
확인하므로 residual/JVP 실행 증거로 사용하지 않는다.

## 9. 다음 승격 gate

1. 동일 version의 hermetic ROCm compiler/device-library 환경에서 AOT artifact 생성
2. artifact/receipt를 별도 clean runtime에서 재검증하고 실제 `gfx*` 장치에 load
3. device architecture/target 교차결박과 requested/required memory-budget receipt
4. 지정 fixture family의 native residual/JVP parity와 반복 deterministic 실행
5. zero direction, 복수 state/direction, 크기 증가 family와 failure injection 확대
6. iteration 중 full-vector host 왕복이 없는 device Krylov/preconditioner 구현
7. reaction/recovery/energy와 최종 `ResultIR` receipt chain 연결
8. 실측 time/memory slope와 optimized CPU 대비 성능 보고

위 gate 전 capability promotion은 `contract_only`/`unavailable` 경계를 유지한다.
