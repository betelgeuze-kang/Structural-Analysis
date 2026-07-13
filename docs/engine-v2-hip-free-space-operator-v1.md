# Engine v2 HIP free-space device-direction operator v1

- 상태: 구현된 계약, unsigned·non-promoting
- 범위: zero-prescribed 선형 free-space `K_ff` materialization과 device direction → resident residual/JVP → reduced gather 수직 슬라이스
- 기준 문서: [Structural Solver Engine v2 마스터 로드맵](structural-solver-engine-v2-master-roadmap.md)
- capability profile: `phase0_hip_free_space_device_direction_operator_apply`
- claim 경계: 이 v1은 장치 상주 `K_ff` view와 한 번의 operator apply 체인을 구현한다. CG/FGMRES/PCG, preconditioner, Newton, 반복 해법, iteration host-copy 0, end-to-end `O(N)`, 속도 향상 또는 상용 준비도를 증명하지 않는다.

## 구현 결과

이 단계는 assembly가 소유한 full CSR과 resident context가 소유·차용한 full-space vector를 그대로 사용한다. Host에서 reduced numeric CSR을 만들고 다시 올리는 경로는 없다. Host가 제공하는 것은 자유도 분할을 나타내는 다음 다섯 개의 분리된 immutable `<i4` symbolic array뿐이다.

1. `free_dofs`
2. `global_to_free`
3. `reduced_csr_row_ptr`
4. `reduced_csr_column_indices`
5. `reduced_csr_global_value_indices`

`HipFreeSpaceOperatorPlanV1`은 이 다섯 배열을 source `ExecutionPlanV2`에서 독립적으로 재도출하고, source plan/operator/numeric/symbolic/partition hash에 결박한다. CPU `reduced_stiffness_csr_values`는 descriptor와 hash만 보존하는 검증 oracle이며 plan 안의 역할은 `verification_oracle_only_never_device_input`이다. Evaluation parity의 CPU oracle 역할은 별도로 `verification_only_never_fallback`으로 고정된다. Upload 가능한 payload가 아니고, source plan의 `scipy_sparse_direct` 정책도 덮어쓰지 않는다. Overlay의 `solver_role`은 명시적으로 `none`이다.

Open 시 package-owned materialize kernel은 같은 resident stream에서 다음 device-to-device gather를 수행한다.

```text
full_csr_values[reduced_csr_global_value_indices] -> reduced_csr_values (K_ff)
full_state[free_dofs]                            -> reduced_state (u_f)
full_load[free_dofs]                             -> reduced_load (F_f)
```

따라서 `K_ff`, `u_f`, `F_f`의 초기화에 host numeric/state/load H2D가 사용되지 않는다.

## zero-prescribed 경계조건

현재 reduced 경로는 `K_fc u_c` 항을 별도로 계산하지 않는다. 그러므로 context는 resident lease와 allocation을 얻기 전에 모든 constrained DOF의 committed displacement가 bit-sign까지 포함해 정확한 `+0.0`인지 검사한다.

- 값이 0이 아니면 거부한다.
- 값은 0이지만 `-0.0` sign bit이면 거부한다.
- unsupported 입력을 보정하거나 silent-ignore하지 않는다.

이 preflight가 통과할 때에만 다음 등식이 성립한다.

```text
R_f(u) = (K u - F)_f = K_ff u_f - F_f
r_f    = F_f - K_ff u_f = -R_f(u)
```

Kernel은 constrained full-direction entry를 정확한 `+0.0`으로 쓴다. Verification은 값 비교뿐 아니라 sign bit가 없는지도 검사한다.

## device apply 체인

`HipFreeSpaceExecutionContext.enqueue_operator_apply()`는 하나의 resident stream에서 다음 순서를 enqueue한다.

```text
reduced K_ff, u_f, F_f
  -> r_f = F_f - K_ff u_f
  -> reduced_direction = reduced_residual = r_f
  -> scatter: full_direction[free] = r_f,
              full_direction[constrained] = exact +0.0
  -> opaque device-direction generation 발급
  -> resident가 generation을 한 번만 소비
  -> full R = K u - F, full Jv = K full_direction
  -> gather: reduced_jvp = full_jvp[free_dofs]
```

Generation은 resident child lease에 묶인 monotonic opaque 값이다. 정확히 일치하는 generation만 소비할 수 있고, 성공한 resident enqueue 뒤에는 재사용할 수 없다. Producer launch가 실패하면 generation을 발급하지 않으며, stale token·중복 소비·다른 child의 token은 fail-closed한다.

Apply receipt는 각 stage의 attempt/success와 nested resident enqueue receipt를 결박한다. Producer, resident, gather가 모두 성공해야 `status=enqueued`다. 다만 이 receipt는 완료 fence가 아니라 queue 제출을 뜻하며 `completion_fence_observed=false`, `solver_iteration=false`다. Device error flag의 apply 결과도 verification fence 전에는 완료된 것으로 주장하지 않는다.

## 장치 버퍼와 소유권

Free-space context는 12개 장치 버퍼를 소유하고, resident/assembly chain의 6개 버퍼를 빌린다.

| 구분 | 버퍼 | 용도 |
|---|---|---|
| owned symbolic 5 | `free_dofs`, `global_to_free`, `reduced_csr_row_ptr`, `reduced_csr_column_indices`, `reduced_csr_global_value_indices` | immutable reduced topology와 full→reduced mapping |
| owned work 7 | `reduced_csr_values`, `reduced_state`, `reduced_load`, `reduced_direction`, `reduced_residual`, `reduced_jvp`, `error_flag` | device-only materialization, direction/JVP workspace, 오류 전달 |
| borrowed 6 | `full_csr_values`, `full_state`, `full_load`, `full_direction`, `full_residual`, `full_jvp` | assembly/resident full-space operator와 vector |

Free-space close는 borrowed buffer를 해제하지 않는다. 이 context가 해제하는 것은 owned 12개뿐이다.

## transfer와 fence 경계

### Open

성공한 open의 경계는 다음과 같다.

1. exact `+0.0` prescribed-state preflight
2. caller-supplied test kernel이 있으면 lease 획득 전 호출 가능성·closed 상태 preflight
3. exclusive resident downstream lease 획득
4. caller kernel이 없으면 package-owned fixed HIPRTC module compile/load
5. owned 12개 allocation
6. symbolic 5개와 zeroed `error_flag`만 H2D, 총 6 operation
7. 같은 stream에서 `K_ff`, `u_f`, `F_f` materialize kernel enqueue
8. `error_flag` 4 byte D2H
9. 같은 stream fence 1회 뒤에만 `context_ready`

Open telemetry는 다음 값을 항상 0으로 고정한다.

- `reduced_numeric_h2d_bytes`
- `state_h2d_bytes`
- `load_h2d_bytes`
- `direction_h2d_bytes`
- `new_stream_create_count`
- `fallback_count`

### Raw apply

한 번의 성공한 `enqueue_operator_apply()`는 free-space producer 1회, resident fused residual/JVP 1회, reduced gather 1회를 enqueue한다. 이 호출 자체의 경계는 다음과 같다.

- H2D: 0
- D2H: 0
- device allocation: 0
- sync/fence: 0
- fallback: 0
- 완료 증명: 없음

따라서 raw apply만으로 iteration host-copy 0이나 완전 device-resident Krylov iteration을 주장할 수 없다. 아직 iteration 자체가 구현되지 않았기 때문이다.

### Verification

`evaluate_for_verification()`은 검증 전용 wrapper다. 호출할 때마다 먼저 새 apply 체인을 enqueue한 뒤 아래 7개 FP64 배열과 `error_flag`를 D2H한다.

- `reduced_values`
- `reduced_state`
- `reduced_load`
- `residual_direction`
- `reduced_jvp`
- `full_residual`
- `full_direction`
- 별도 `error_flag` 1개

즉 D2H는 최대 8 operation이고, 마지막에 같은 stream fence를 정확히 한 번 수행한다. Evaluation 구간의 H2D, device allocation, fallback은 0이다. CPU oracle은 전체 device chain, 모든 export와 fence가 성공한 다음에만 실행되며 계산 대체 경로로 사용되지 않는다.

### Close

Close 순서는 다음과 같다.

```text
same-stream fence
  -> orphan/owned 12 allocation lineage retirement
  -> allocation owner close
  -> HIPRTC module close with persistent disposition
  -> resident downstream lease release
```

## parity 의미론

Verification oracle은 source `ExecutionPlanV2`의 full/reduced FP64 CSR을 사용하며 절대·상대 tolerance는 각각 `1e-8`이다. 다음 항목을 독립적으로 검사한다.

- device-materialized `K_ff` values
- gathered `u_f`, `F_f`
- `r_f = F_f - K_ff u_f`
- `Jv_f = K_ff r_f`
- full resident residual `R = Ku-F`
- scattered full direction
- `r_f`와 실제 exported `-full_residual[free_dofs]`의 cross parity
- constrained full direction의 exact `+0.0`

마지막 두 항목은 reduced 계산끼리만 비교하는 self-consistency 오류를 피하기 위한 경계다. 특히 direction oracle은 full operator residual에서 독립적으로 유도되므로, 누락된 coupling 항이나 잘못된 free mapping이 reduced oracle 양쪽에서 동시에 숨는 것을 막는다. `parity_failed`는 context와 resident chain을 poison하며 PASS로 승격되지 않는다.

## 수명, poison, cleanup

- Free-space context는 resident의 exclusive downstream child다. Active child가 있으면 resident close가 sync/free 전에 거부되고, resident가 assembly lease를 유지하므로 assembly close도 함께 차단된다.
- Parent resident의 직접 enqueue/host verification과 다른 downstream child acquire는 active free-space lease 동안 허용되지 않는다.
- Runtime, device, stream, resident state, source plan/overlay identity·hash, owned/borrowed pointer 객체와 kernel identity를 snapshot한다. Enqueue 전에 live authority가 바뀌면 fail-closed한다.
- Direction producer, resident apply, gather, verification export/fence, device error 또는 parity 실패는 free-space와 resident를 공유 poison 상태로 전환한다.
- Open 실패 시 fence가 가능하면 할당된 owned buffer를 역순으로 해제하고, module을 닫은 뒤 lease를 반환한다.
- Free/module/lease cleanup이 끝나지 않으면 `cleanup_failed` context가 남은 resource를 계속 소유한다. `close()` 재시도는 이미 회수한 resource를 반복 해제하지 않고 남은 단계부터 진행한다.
- Module unload 실패도 kernel owner를 보존해 retry할 수 있다.
- Receipt에는 pointer, stream, module 또는 function handle을 직렬화하지 않는다.

## native evidence gate

`evidence_scope=native_hiprtc_free_space_composite`는 이름이나 caller claim으로 선택할 수 없다. 다음 조건이 모두 참일 때만 생성된다.

1. Free-space kernel을 context가 package-owned source에서 내부 compile했다.
2. Resident가 이미 `native_hiprtc_composite`다.
3. Loaded runtime과 free-space kernel이 exact native 구현 type이다.
4. Free-space와 parent kernel의 architecture가 같다.
5. Runtime library SHA-256이 parent와 일치한다.
6. Runtime/HIPRTC library discovery source가 `injected`가 아니다.

Caller-supplied kernel은 native identity와 같은 값을 흉내 내더라도 항상 `injected_test_double`이다. Context receipt는 v2이고 plan/apply/evaluation receipt는 v1이며 모두 `promotion_eligible=false`다. Canonical hash는 내부 변조 탐지이지 provenance 서명이나 attestation이 아니다.

`tests/test_engine_v2_hip_free_space_hardware_v1.py`는 실제 gfx agent와 native capability가 있을 때 assembly → resident → free-space apply/export/parity와 teardown을 실행하도록 작성돼 있다. 일반 실행에서 gfx agent, HIP capability, native open 또는 parity 조건을 충족하지 못하면 명시적으로 skip하며 CPU fallback은 사용하지 않는다. `ENGINE_V2_REQUIRE_HIP_HARDWARE=1`이면 같은 조건은 skip이 아니라 test failure다. Cleanup 실패는 어떤 모드에서도 skip으로 바뀌지 않는다.

이 문서는 특정 실행에서 native kernel launch가 실제 관찰됐다고 자동 주장하지 않는다. 그 주장은 해당 hardware test가 skip 없이 PASS한 실행 receipt/log와 함께만 할 수 있다. 별도의 HIPRTC compile/symbol test PASS도 code object와 세 fixed symbol의 존재를 입증할 뿐, device launch 관찰을 대신하지 않는다.

## Schema, API, 파일

### Draft 2020-12 schema

- `src/structural_analysis/schemas/hip_free_space_operator_plan_v1.schema.json`
- `src/structural_analysis/schemas/hip_free_space_context_v2.schema.json`
- `src/structural_analysis/schemas/hip_free_space_apply_v1.schema.json`
- `src/structural_analysis/schemas/hip_free_space_evaluation_v1.schema.json`

Plan, context, apply, evaluation payload는 `additionalProperties=false` 경계, exact scalar/container type 검사, canonical receipt hash 재계산과 semantic validator를 함께 사용한다. Context v2 receipt는 source plan/operator/numeric/symbolic/partition/state, resident·assembly parent, lease epoch, kernel/library identity, 12개 owned view와 owner-minted lineage summary, allocation/deallocation·quarantine·unknown-outcome·module lifecycle telemetry를 결박한다. Apply receipt는 nested resident enqueue와 single-use generation을, evaluation receipt는 nested apply, exported array descriptor와 full/reduced parity를 결박한다.

### Public API

- `compile_hip_free_space_operator_plan_v1()`
- `validate_hip_free_space_operator_plan_v1()`
- `compile_hip_rtc_free_space_operator_kernel()`
- `open_hip_free_space_execution_context()`
- `HipFreeSpaceExecutionContext.enqueue_operator_apply()`
- `HipFreeSpaceExecutionContext.evaluate_for_verification()`
- `validate_hip_free_space_context_receipt()`
- `validate_hip_free_space_apply_receipt()`
- `validate_hip_free_space_evaluation_receipt()`
- `validate_hip_free_space_evaluation()`

주요 public value/error type은 `HipFreeSpaceOperatorPlanV1`, `HipRtcFreeSpaceOperatorKernelIdentity`, `HipRtcFreeSpaceOperatorKernel`, `HipFreeSpaceContextOpenResult`, `HipFreeSpaceContextReceipt`, `HipFreeSpaceApplyReceipt`, `HipFreeSpaceEvaluationReceipt`, `HipFreeSpaceEvaluation`, `HipFreeSpaceOperatorPlanV1Error`, `HipRtcFreeSpaceError`, `HipFreeSpaceContextError`다.

### 구현과 검증 파일

- symbolic overlay: `src/structural_analysis/engine_v2/assembly_backend/free_space_plan.py`
- fixed HIPRTC owner/ABI: `src/structural_analysis/engine_v2/assembly_backend/free_space_rtc.py`
- package-owned kernels: `src/structural_analysis/engine_v2/assembly_backend/kernels/engine_v2_free_space_operator_v1.hip.cpp`
- context/apply/verification: `src/structural_analysis/engine_v2/assembly_backend/free_space.py`
- plan 계약 테스트: `tests/test_engine_v2_hip_free_space_plan_v1.py`
- HIPRTC ABI·compile 테스트: `tests/test_engine_v2_hip_free_space_rtc_v1.py`
- context·lifetime·failure 테스트: `tests/test_engine_v2_hip_free_space_context_v1.py`
- allocation-lineage 통합·receipt 보존 테스트: `tests/test_engine_v2_hip_free_space_allocation_lineage_integration_v1.py`
- context authority·receipt·physical cross-invariant adversarial 테스트: `tests/test_engine_v2_hip_free_space_context_adversarial_v1.py`
- 조건부 native hardware 테스트: `tests/test_engine_v2_hip_free_space_hardware_v1.py`

Fixed ABI는 block size `256`, FP64 value와 int32 index/error를 사용하며 symbol은 다음 세 개다.

- `engine_v2_free_space_materialize_v1`
- `engine_v2_free_space_residual_direction_v1`
- `engine_v2_free_space_gather_jvp_v1`

## 지원 범위와 명시적 미지원

| 항목 | v1 상태 | 정확한 의미 |
|---|---|---|
| symbolic-only free-space overlay | 지원 | detached immutable 5-array, source hash·partition 재도출 결박 |
| same-stream `K_ff` materialization | 지원 | assembly-owned full CSR에서 D2D gather, host reduced numeric H2D 0 |
| zero-prescribed direction producer | 지원 | `F_f-K_ffu_f`, full constrained exact `+0.0` |
| resident full residual/JVP 연결 | 지원 | opaque generation의 단일 소비와 nested receipt |
| reduced JVP gather | 지원 | `full_jvp[free_dofs]`를 device에서 gather |
| CPU full/reduced parity | 검증 전용 지원 | fence 뒤 oracle replay, fallback 아님 |
| CG | 미지원 | recurrence, reduction, convergence loop 없음 |
| FGMRES | 미지원 | Arnoldi basis, restart, orthogonalization 없음 |
| PCG | 미지원 | SPD gate와 preconditioned recurrence 없음 |
| preconditioner | 미지원 | Jacobi/ILU/AMG/DD hierarchy와 apply 계약 없음 |
| Newton/nonlinear solve | 미지원 | tangent epoch, trial/commit, globalization 없음 |
| iteration host-copy 0 | 미증명 | raw apply는 copy 0이지만 solver iteration 자체가 없고 verification은 D2H 8회 |
| end-to-end `O(N)` | 미증명 | 단일 CSR kernel 구조만으로 전체 solver complexity를 주장하지 않음 |
| speedup | 미증명 | 크기 family, optimized CPU baseline, warm-up/timing 통계 없음 |
| commercial readiness | 미지원·미증명 | signed promotion, 폭넓은 FE/V&V, failure policy, 배포 증거 없음 |

## 다음 gate

후속 [HIP Krylov primitive v1](engine-v2-hip-krylov-primitives-v1.md)이 same-stream affine·positive Jacobi·deterministic dot·LASSQ와 raw-batch zero-transfer 계약을 구현했다. 그러나 이는 아직 diagnostic primitive batch이며 선형 해법기가 아니다. 실제 device-resident 선형 해법기로 확장하려면 최소한 다음이 필요하다.

1. convergence scalar의 host 관찰 빈도와 iteration copy budget 계약
2. recurrence vector/basis 및 restart lifecycle
3. solver-integrated preconditioner apply와 lifecycle/telemetry receipt
4. fixed-restart FGMRES 및 SPD-gated PCG 상태기계
5. breakdown, stagnation, NaN/Inf, max-iteration의 fail-closed 정책
6. 다중 AMD architecture·모델 크기 family의 non-skipped native parity와 timing
7. 이후 Newton trial/commit, tangent epoch, line search/trust-region 연결

따라서 이 v1의 정확한 결론은 **host reduced numeric upload 없이 assembly-owned full CSR에서 `K_ff`를 같은 HIP stream에 materialize하고, `F_f-K_ffu_f` device direction을 단일 사용 generation으로 resident full residual/JVP에 연결한 뒤 free-space JVP를 gather하는 계약이 구현됐다**는 것이다.
