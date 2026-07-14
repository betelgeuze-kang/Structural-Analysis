# Engine v2 HIP FGMRES model-case parity v1

## 목적

이 계약은 하나의 완료된 native HIP FGMRES 해석을 독립 CPU FGMRES
reference와 비교한다. 비교 대상은 terminal 상태와 반복 횟수뿐 아니라 다음
세 벡터다.

- reduced solution `x`
- exporter가 읽은 true residual
- 보존된 `ExecutionPlanV2`에서 다시 계산한 `b - Ax`

상대 허용오차는 `1e-8`, 절대 허용오차는 `1e-12`로 고정되어 있으며 호출자가
완화할 수 없다. component-wise gate와 L2/L-infinity gate를 함께 적용한다.

## authoritative 입력

`attest_hip_fgmres_model_case_parity_v1`은 직렬화 영수증이 아니라 다음 exact
process-local 결과 객체를 요구한다.

1. 전체 recurrence를 결정론적으로 재실행할 수 있는 CPU reference result
2. completion export와 still-live context에 결합된 terminal observation result
3. loader-issued `LoadedHipRuntime`에 결합된 HIP device identity result

FGMRES plan은 canonical compiler replay로 다시 만들고 recurrence plan은 그
FGMRES witness에서 fresh compile한다. 원본 recurrence manifest와 완전히 같아야
하며, 영수증의 plan ID/hash와 차원은 이 detached witness에서만 생성한다.

## device identity

HIP runtime ABI R0000 layout을 고정한 fresh function binding으로 다음을 읽고
교차검증한다.

- selected device ordinal
- normalized GCN architecture base
- exact 16-byte UUID
- canonical PCI BDF와 numeric domain/bus/device/function
- runtime, driver 및 device-property runtime version
- 선택된 HIP runtime shared library identity/hash

8개 identity symbol은 public `ctypes` cache를 사용하지 않고 private handle의
`dlsym` 주소에서 고정 prototype `CFUNCTYPE` callable을 각각 새로 만든다. Native
loader registry는 loader 시점 library identity 5개 필드와 cached probe callable의
`argtypes`/`restype`/`errcheck`를 detached value snapshot으로 봉인한다. Library는
하나의 열린 FD를 해시하고 그 `/proc/self/fd` snapshot을 `dlopen`한 뒤 동일 FD를
재검증하며, 원래 resolved path도 다시 열어 inode metadata와 SHA-256가 같은지
확인한다. Published result는 private weak publication registry의 exact 객체와
library/query/publication value snapshot에 다시 결속된다.

Device identity receipt는 strict Draft 2020-12 schema를 통과한다. 현재 identity는
해석 완료 후 같은 loader-issued runtime과 ordinal에서 관찰된다. UUID/PCI를 첫
kernel launch 전에 봉인한 execution-epoch 증거는 아니므로, 이 계약을 특정
UUID/PCI 장치에서의 실행을 암호학적으로 증명한 것으로 확대 해석하면 안 된다.
또한 explicit shared-library path는 호출자가 선택한 trust boundary다. SHA-256는
로드 시점의 exact open-file snapshot과 경로 재확인을 결속하지만 AMD vendor
signature나 선택한 DSO 자체의 진위를 증명하지 않는다. 이 증거는 로드 시점의
주 shared object에 한정되며 이후 pathname 영구 불변, 전이 의존성 또는 전체
mapped-state 인증도 아니다.

## claim boundary

단일-case result가 검증되면 다음만 true다.

- exact retained execution-plan snapshot binding
- deterministic CPU reference replay
- terminal outcome/discrete-count parity
- solution, exported residual 및 independent residual replay parity
- current runtime/device identity observation

다음은 항상 false다.

- full model-family parity
- multi-architecture parity
- signed evidence 또는 promotion eligibility
- iteration host-copy zero
- ResultIR integration
- performance/speedup 또는 `O(N)` 증거
- commercial readiness

직렬화 receipt는 process-local identity를 보존하지 않으므로 구조·hash 검증만
가능하다. authoritative 재검증에는 exact result 객체가 필요하다.

## 검증 기준

2026-07-14 기준 다음을 확인했다.

- parity 단위·적대적 회귀: `21 passed`
- device identity 단위·native gate: `55 passed`
- FGMRES RTC 인접 회귀: `112 passed`
- actual RX 6900 XT `gfx1030` later-column convergence 전체 체인과 family
  process-local replay: `1 passed in 141.24s`
- 독립 diff 감사: 잔여 BLOCKER/HIGH/MEDIUM 없음

actual hardware gate는 canonical predecessor, sealed checkpoint, global recurrence,
completion export, terminal observation, CPU replay, device identity 및 parity result
재검증을 한 process에서 수행한 뒤 family aggregate에서 다시 replay한다. 이
한 케이스는 미등록 observation일 뿐 model-family 또는 두 ISA
coverage를 의미하지 않는다.
