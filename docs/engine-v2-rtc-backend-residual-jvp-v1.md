# Engine v2 격리 HIPRTC CSR Residual/JVP Replay v1

## 1. 범위와 수치적 의미

`structural_analysis.engine_v2.rtc_backend`는 `ExecutionPlan v1`에 이미
컴파일된 canonical full CSR 강성행렬을 ROCm/HIP 장치에 상주시킨 뒤, 하나의
fused kernel에서 다음 두 연산을 같은 CSR 순회로 재생하는 격리된 검증
backend다.

- full residual: `R(u) = K u - F`
- linear JVP: `Jv = K v`

이 구현은 **CPU reference assembler가 만든 CSR의 HIP replay**다. HIP에서
element/material 구성법칙을 실행하여 `K`를 조립하지 않고, 선형계의 해를
구하지 않으며, Newton/Krylov solver도 아니다. 따라서 이 근거만으로 HIP
구조해석 solver, device constitutive assembly, 상용 준비 또는 전체 Phase 0
종료를 선언하지 않는다.

residual 부호는 `internal_minus_external`이다. 출력은 제약 DOF를 포함하는
node-major 6DOF full-global vector이며, free/constrained 결과는 동일한 full
output을 `ExecutionPlan` partition으로 나눈 검증 view다. Phase 0 replay는
`StateIR.load_factor`를 다시 적용하지 않고 plan에 결박된 전체 `F`를 그대로
사용한다.

## 2. 격리 package와 계약 체인

선택된 HIPRTC 경로는 기존 generic AOT HIP package와 파일 수명 및 namespace를
공유하지 않는다.

- package: `structural_analysis.engine_v2.rtc_backend`
- context API: `open_hip_rtc_csr_execution_context`
- module owner: `HipRtcCsrKernel`
- kernel source:
  `src/structural_analysis/engine_v2/rtc_backend/kernels/engine_v2_csr_residual_jvp_v1.hip.cpp`
- context schema: `structural-analysis-rtc-csr-context-receipt.v1`
- evaluation schema: `structural-analysis-rtc-residual-jvp-receipt.v1`

context를 열기 전에 다음을 fail-closed로 검증한다.

1. `SolverModelBuffers v1` descriptor와 numerical/entity/artifact hash
2. `ExecutionPlan v1`의 exact buffer binding, plan/operator/pattern/partition
   hash, `<i4` CSR index 및 `<f8` value/load descriptor
3. committed `StateIR v1`의 plan/operator binding, epoch, immutable
   displacement hash

runtime/module/function/stream/device pointer는 process-local owner 안에만 있고
receipt에 직렬화하지 않는다. 자동 CPU fallback은 없다. CPU CSR 계산은 실제
HIP output을 명시적으로 다운로드한 뒤 수행하는 verification oracle일 뿐이며,
HIP 실행 실패를 대체하는 backend가 아니다.

context/result receipt의 canonical hash는 payload 무결성을 재검사하지만 서명이
아니다. unsigned v1 JSON을 가진 공격자는 내용을 바꾸고 canonical hash를 다시
계산할 수 있으므로 `promotion_eligible`은 native parity가 관찰되어도 항상
`false`다. v1은 live `expected_context`와 다시 대조하는 backend parity 관찰
근거이며, 배포·gap closure 승격에는 신뢰 anchor와 signature/key provenance를
갖춘 signed evidence v2가 필요하다.

## 3. HIPRTC development lane

현재 native 경로는 package가 소유한 고정 source만 HIPRTC로 컴파일한다. core는
GPU architecture를 추측하지 않는다. hardware test와 probe script가 core
밖에서 `rocm_agent_enumerator`가 반환한 실제 `gfx*` agent를 고르고, 검증한
target을 명시적으로 전달한다.

kernel identity는 다음을 결박한다.

- kernel ABI/name과 source SHA-256
- 순서가 고정된 compile options
- target `gfx*` architecture
- `libhiprtc` 및 `libamdhip64` identity
- code-object SHA-256과 byte length

HIPRTC는 현재 **development/verification lane**이다. 상용 배포에는 승인된 GPU
architecture matrix, 재현 가능한 toolchain/container, signed source/code-object
manifest, SBOM 및 release provenance가 있는 hermetic AOT/fat-binary lane이
별도로 필요하다. generic AOT 연구 자산의 성공 영수증을 이 HIPRTC receipt로
간주하지 않는다.

## 4. Fused kernel과 structural work receipt

하나의 thread가 하나의 sorted CSR row를 담당한다. row를 한 번 순회하며 두
FP64 accumulator에 `K*u`와 `K*v`를 동시에 누적하고, 각각 `K*u-F`와 `K*v`를
기록한다. atomic add, host arithmetic, hidden second operator 및 중간 full-vector
download는 없다.

한 evaluation의 source-level structural work는 다음과 같이 기록한다.

- physical HIP kernel launch: 1
- residual/JVP logical evaluation: 각각 1
- CSR pass: 1
- CSR entry visit: `nnz`
- multiplication/accumulation: 각각 `2*nnz`
- load subtraction: `N`
- FP64-equivalent work: `4*nnz + N`

이 값은 source 구조로부터 계산한 logical count다. 실제 DRAM transaction이나
cache hit 수를 측정한 값이 아니므로 `physical_dram_bytes`는
`not_instrumented`다.

## 5. 장치 상주와 정확한 호출 계수

model-buffer foundation 위에 다음 8개 child allocation을 context 수명 동안
유지한다.

1. CSR row pointer
2. CSR column index
3. CSR FP64 value
4. full global load
5. committed displacement
6. direction workspace
7. residual workspace
8. JVP workspace

open 단계에서는 8개 allocation을 모두 만들고 앞의 5개 immutable input만 H2D
한 뒤 한 번 동기화한다. 각 fused evaluation의 정확한 delta는 다음과 같다.

| 항목 | 값 |
| --- | ---: |
| direction H2D | 1 operation, `8*N` bytes |
| fused kernel | 1 attempt, 1 successful launch |
| residual/JVP D2H | 2 operations, `16*N` bytes |
| explicit stream sync | 1 |
| evaluation-time allocation | 0 |
| blocking-copy API | 0 |
| fallback | 0 |

verification replay는 결과 비교를 위해 매 evaluation마다 두 full vector를
명시적으로 다운로드한다. 그러므로 이 단계는 Newton/Krylov iteration당
full-vector host copy 0을 증명하지 않는다.

close는 child 8개, HIPRTC module, model-buffer foundation과 stream을 정리하고
`current_device_payload_bytes=0`을 검증한다. 부분 cleanup 실패는 성공한 closed
receipt로 바꾸지 않고 typed cleanup failure로 남긴다.

## 6. Hardware 검증

hardware test와 probe는
`tests/fixtures/model_ir_v2/frame_cantilever_all_modes.json`의 CPU reference
run에서 생성한 authoritative committed `StateIR`, 고정 deterministic direction,
zero direction을 사용한다.

검증 범위는 다음과 같다.

- native HIPRTC module과 fused kernel 실행 증명
- live context 재검증을 통과한 non-promoting unsigned v1 parity 관찰
- full/free/constrained residual CPU/HIP FP64 parity
- full/free/constrained JVP CPU/HIP FP64 parity
- zero-direction JVP exact zero
- 동일 state/direction 반복 output descriptor/hash 및 receipt hash 일치
- open `8 allocation / 5 initial H2D`
- evaluation `1 H2D / 2 D2H / 1 kernel / 1 sync / fallback 0`
- close child deallocation 8건과 device payload 0

```bash
python3 -m pytest -q tests/test_engine_v2_rtc_residual_jvp_hardware_v1.py
python3 scripts/probe_engine_v2_rtc_residual_jvp.py
```

로컬 ROCm runtime/device, `libhiprtc` 또는 실제 `gfx*` agent가 없으면 hardware
test는 원인을 명시하고 skip한다. probe는 `actual_backend=null`,
`fallback_used=false`인 unavailable report와 exit code `2`를 내며 CPU 결과를
HIP 결과로 대체하지 않는다.

2026-07-10 현재 개발 workstation에서 검증한 조합은 ROCm 6.0.2,
`gfx1030`, Radeon RX 6900 XT다. 이는 다른 AMD GPU와 ROCm 조합의 준비 상태를
증명하지 않는다.

## 7. Timing과 O(N) 주장 제한

현재 검증 환경은 `HIP_LAUNCH_BLOCKING=1`이다. hardware test와 probe는 kernel
시간, speedup 또는 complexity slope를 측정하지 않는다. 동기 launch 환경의
벽시계 수치를 성능 근거로 승격하지 않으며 structural work receipt와 수치
parity만 기록한다.

fused kernel 자체의 source-level 작업량은 `O(N+nnz)`이지만 현재
`ExecutionPlan v1`은 CPU에서 dense global stiffness를 구축·보유하고 dense
reconstruction 검증도 수행한다. 따라서 이 replay로 end-to-end memory/time
`O(N)`, near-linear solve 또는 optimized CPU 대비 속도 우위를 주장할 수 없다.

다음 증거는 여전히 별도로 필요하다.

- HIP element/material assembly와 consistent tangent
- device-resident Krylov/preconditioner/Newton/globalization
- reaction, recovery, energy의 HIP 최종 receipt chain
- iteration당 full-vector host copy 0
- mesh-family complexity slope와 optimized CPU 대비 speedup
- 다중 GPU architecture/ROCm version V&V 및 hermetic release artifact
