# Engine v2 Phase 0 실행·상태·결과 계약 v1

- 상태: Phase 0 CPU 참조 선형정적 계약 및 영수증 체인 구현 완료
- capability profile: `phase0_cpu_reference_linear_static`
- 실행 영수증 경계: `phase0_cpu_reference_linear_static_not_hip_parity`
- 기준일: 2026-07-10

이 문서는 `SolverModelBuffers` 이후의 `ExecutionPlan v1 → StateIR v1 → ResultIR v1` 계약과 이를 연결하는 실행기를 설명하는 구현 기준 문서다. 의미 모델의 책임 분리는 [ADR-002](adr/002-modelir-stateir-resultir-schema.md), 연산자·상태 epoch 규칙은 [ADR-003](adr/003-operator-abi-and-constitutive-source-policy.md), 백엔드·정밀도·fallback 정책은 [ADR-004](adr/004-backend-fallback-precision-and-residency.md)를 따른다.

구현과 스키마가 최종 권위다.

- ExecutionPlan: [구현](../src/structural_analysis/engine_v2/contracts/execution_plan.py), [JSON Schema](../src/structural_analysis/schemas/execution_plan_v1.schema.json)
- StateIR: [구현](../src/structural_analysis/engine_v2/contracts/state_ir.py), [JSON Schema](../src/structural_analysis/schemas/state_ir_v1.schema.json)
- ResultIR: [구현](../src/structural_analysis/engine_v2/contracts/result_ir.py), [JSON Schema](../src/structural_analysis/schemas/result_ir_v1.schema.json)
- 실행·영수증 체인: [runner.py](../src/structural_analysis/engine_v2/runner.py)
- 공통 정규화: [_canonical.py](../src/structural_analysis/engine_v2/contracts/_canonical.py)

## 1. 계약 체인

```text
ModelIR v2
  └─ SolverModelBuffers
       └─ ExecutionPlan v1
            ├─ initial StateIR: committed, epoch 0
            ├─ CPU reference solve of the compiled operator
            ├─ evaluated StateIR: trial, epoch 1
            ├─ committed StateIR: committed, epoch 1
            └─ ResultIR v1
                 └─ LinearStaticRun receipt_chain_hash
```

각 하위 산출물은 상위 산출물의 실제 해시를 저장한다. 검증기는 해시 문자열만 신뢰하지 않고 스키마, 배열 바이트, 순서, 수치 불변식과 부모 상태를 다시 계산한다. 오류는 계약별 안정적인 오류 코드와 경로를 포함하고 fail-closed로 종료한다.

공통 JSON 해시는 다음 규칙을 사용한다.

- UTF-8, 키 정렬, 공백 없는 JSON, `allow_nan=False`
- `sha256:<64 lowercase hex>` 형식
- NaN과 무한대 거부, `-0.0`을 `0.0`으로 정규화
- 배열은 C-order, little-endian `<f8` 또는 `<i4`, immutable `bytes` backing
- 자기 자신의 aggregate hash 필드는 해시 입력에서 제외

## 2. ExecutionPlan v1

스키마 버전은 `structural-analysis-execution-plan.v1`이다. `compile_execution_plan()`은 검증된 `SolverModelBuffers`를 한 번 조립하여 결정적인 실행 계획을 만들고 즉시 `validate_execution_plan()`으로 검증한다. 지원 solver policy는 `dense_direct`와 `scipy_sparse_direct`, FP64, deterministic, fallback 금지다.

### 2.1 소유하는 정보

- ModelIR content hash와 solver buffer의 schema, load pattern, numeric/entity/artifact hash
- node/element 고정 순서와 `ordering_hash`
- node-major 6-DOF 순서 `UX, UY, UZ, RX, RY, RZ`
- `<i4` 전역 DOF, element DOF, constrained/free partition, `global_to_free`
- full symmetric CSR의 sorted columns, diagonal 위치, element scatter 위치
- reduced CSR과 full CSR value 위치의 역매핑
- 조립된 전역 `K`, `F`와 recovery transform/local stiffness
- backend, solver tolerance, state contract와 정확한 operator graph

런타임 수치 payload는 메모리 안의 immutable 배열로 유지한다. manifest는 배열 값 또는 descriptor/hash를 계약에 맞게 노출한다. device pointer, stream, allocator handle 같은 프로세스 종속 값은 직렬화하지 않으며 스키마가 추가 속성을 거부한다.

### 2.2 정확한 7단계 operator graph

순서와 dependency는 스키마 상수다. 모든 단계의 `state_epoch_source`는 `state_ir`이며, 순서 변경도 유효한 계획으로 인정하지 않는다.

| 순서 | id / kind | depends_on | 입력 → 출력 | representation |
|---:|---|---|---|---|
| 1 | `assembly` / `assembly` | 없음 | `solver_model_buffers` → `global_dof` | `assembled_csr` |
| 2 | `partition` / `constraint_partition` | `assembly` | `global_dof` → `reduced_dof` | `index_partition` |
| 3 | `solve` / `linear_solve` | `partition` | `reduced_dof` → `global_dof` | `direct_solve` |
| 4 | `residual` / `residual` | `assembly`, `solve` | `global_dof` → `global_dof` | `matrix_vector` |
| 5 | `reaction` / `reaction` | `residual` | `global_dof` → `global_dof` | `index_partition` |
| 6 | `recovery` / `result_recovery` | `solve` | `global_dof` → `element_result` | `element_local` |
| 7 | `energy` / `energy` | `solve`, `recovery` | `element_result` → `scalar_result` | `scalar_reduction` |

이 graph는 연산 의미와 검증 순서를 고정한다. 각 단계의 실측 시간이 존재한다는 의미는 아니다.

### 2.3 해시 경계

- array `data_hash`: 정확한 C-order 바이트
- array `content_hash`: dtype, shape, layout, byte length 등의 canonical metadata와 바이트
- `ordering_hash`: node/element 순서, entity mapping hash, DOF/end 순서
- `partition_hash`: constrained/free/global-to-free descriptor 집합
- `pattern_hash`: full/reduced CSR, diagonal, scatter, full-value mapping descriptor 집합
- `operator_hash`: CPU backend-native `K/F/constraint` 연산자 해시
- `recovery_operator_hash`: element 순서, global DOF, local transform, local stiffness
- `plan_hash`: `plan_hash` 자체를 제외한 전체 manifest

검증기는 partition이 서로 겹치지 않는 완전한 DOF cover인지, CSR을 element connectivity로 다시 만들 수 있는지, `K`가 유한·대칭인지, CSR 값이 dense `K`와 같은지, recovery transform이 직교인지 확인한다. `expected_buffers`를 주면 buffer 자체의 세 해시와 descriptor를 재검증하고 계획의 binding과 load도 대조한다. 검증 과정에서 `K`를 숨겨서 재조립하지 않는다.

## 3. StateIR v1

스키마 버전은 `structural-analysis-state-ir.v1`이다. 한 StateIR은 하나의 immutable `committed` 또는 `trial` snapshot이다. 모든 snapshot은 ModelIR, solver buffer 세 해시, ExecutionPlan, operator, load pattern과 DOF 수에 결합된다.

상태 벡터는 flat node-major `<f8` 배열이다.

- `displacement_si`: `m, m, m, rad, rad, rad`
- `velocity_si`: `m/s, m/s, m/s, rad/s, rad/s, rad/s`
- `acceleration_si`: `m/s2, m/s2, m/s2, rad/s2, rad/s2, rad/s2`
- constitutive state: Phase 0의 `stateless_linear_elastic`, 빈 값 배열

세 운동 벡터와 빈 constitutive vector에는 각각 raw-byte hash가 있다. `state_hash`는 `state_hash` 필드만 제외한 전체 canonical payload를 결합한다. 외부 입력 배열은 복사 후 immutable bytes-backed 배열로 만들며, signed zero는 해시 전에 정규화한다.

### 3.1 수명주기

| 동작 | 결과 역할/epoch | parent | 보존 규칙 |
|---|---|---|---|
| `create_initial_state(plan)` | `committed`, `0` | `null` | step/iteration/load factor/time과 모든 벡터가 0 |
| `open_trial_state(accepted, u, ...)` | `trial`, `accepted.epoch + 1` | `accepted.state_hash` | plan/operator binding 유지; 생략한 velocity/acceleration 상속 |
| `commit_trial_state(accepted, trial)` | `committed`, `trial.epoch` | `trial.state_hash` | trial의 좌표와 모든 벡터/hash 보존 |
| `rollback_trial_state(accepted, trial)` | 기존 `accepted` | 변경 없음 | 새 snapshot을 만들지 않고 정확히 같은 객체 반환 |

trial은 committed state에서만 열 수 있다. trial의 epoch은 정확히 `accepted + 1`이어야 하고 step/time은 accepted보다 과거일 수 없다. commit/rollback 전에 두 상태의 parent와 모든 model/plan/operator binding을 다시 확인한다.

## 4. ResultIR v1

스키마 버전은 `structural-analysis-result-ir.v1`이다. 이 버전은 `status=ready`인 성공한 CPU reference linear-static 결과만 표현한다. 실패 결과를 성공 receipt로 감싸지 않는다.

### 4.1 입력 결합과 결과 배열

`input_bindings`는 다음을 모두 결합한다.

- ModelIR content hash
- solver numeric/entity/artifact hash
- ExecutionPlan hash
- evaluated trial StateIR hash
- committed StateIR hash

결과 배열은 모두 immutable, C-order `<f8`이며 raw `data_hash`와 descriptor `content_hash`를 갖는다.

| 배열 | shape | 의미 |
|---|---|---|
| `displacements_si` | `[node, 6]` | 전역 변위/회전 |
| `residual_si` | `[node, 6]` | `K*u - F` |
| `reactions_si` | `[node, 6]` | restrained DOF residual, free DOF는 0 |
| `element_end_forces_local_si` | `[element, 2, 6]` | i, j 순서의 local end force |
| `element_strain_energy_j` | `[element]` | element strain energy |

`numerical_result_hash`는 다섯 배열의 이름·data/content hash와 total strain energy를 결합한다. `result_ir_hash`는 결과 배열뿐 아니라 모든 input binding, ordering, convergence, recovery 의미, backend/hardware metadata를 포함한 전체 receipt를 결합한다. CPU solver의 `backend_native_result_hash`는 별도 증거이며 `result_ir_hash`와 같은 것으로 취급하지 않는다.

### 4.2 재계산하는 물리 불변식

`validate_result_ir_v1()`은 backend 결과의 라벨이나 native hash만 신뢰하지 않고 다음을 독립적으로 대조한다.

- `residual = K*u - F`
- reaction은 constrained residual과 같고 free DOF에서는 0
- free residual L∞, load scale, scaled residual 및 plan tolerance 충족
- result displacement와 trial/committed displacement의 일치
- committed state가 trial의 직접 자식이고 epoch/step/factor/time/vector hash를 보존
- plan의 global DOF, local transform, local stiffness로 end force 재복원
- element energy `0.5 * u_localᵀ * K_local * u_local`
- total energy가 element 합, `0.5*uᵀKu`, `0.5*uᵀF`, backend total과 일치
- node/element 순서, load pattern, operator/recovery hash와 dense/sparse backend policy 일치

### 4.3 backend receipt와 계측 경계

backend receipt는 실제/요청 backend를 `cpu_reference`, precision을 `fp64`, fallback을 `forbidden/false`로 기록한다. NumPy/SciPy 버전과 platform/machine/processor 문자열도 포함한다. CPU 경로이므로 H2D/D2H bytes, device sync와 peak device bytes는 0이다.

현재 timing과 host peak-memory 계측은 구현되지 않았다.

- `timing.measurement_status = not_instrumented`
- 전체 및 7개 stage 시간은 `null`
- `peak_memory.measurement_status = not_instrumented`
- `peak_host_bytes = null`

따라서 이 receipt는 성능 benchmark, O(N) 복잡도, latency, memory ceiling의 증거가 아니다. `null`을 0초 또는 0 byte 측정으로 해석해서는 안 된다.

## 5. 실행기와 receipt chain

공개 실행 API는 다음과 같다.

```python
from structural_analysis.engine_v2 import (
    pack_solver_model_buffers,
    run_linear_static_v1,
    validate_linear_static_run,
)

buffers = pack_solver_model_buffers(model_ir, load_pattern_id="LC1")
run = run_linear_static_v1(
    buffers,
    matrix_backend="dense",  # 또는 "scipy_sparse"
    residual_tolerance=1.0e-10,
)
validate_linear_static_run(run, expected_buffers=buffers)
manifest = run.to_manifest()
```

`run_linear_static_v1()`은 plan compile부터 실행한다. 이미 컴파일한 plan을 재사용하려면 `execute_linear_static_plan_v1(buffers, plan)`을 사용한다. 이 경로는 `plan.operator`를 실행하여 숨은 재조립을 하지 않는다.

`LinearStaticRun`의 `receipt_chain_hash`는 다음 필드를 포함하는 run manifest에서 자기 자신만 제외하고 계산한다.

- model 및 solver buffer 세 해시
- ExecutionPlan hash
- initial/trial/committed StateIR hash
- backend-native result hash와 ResultIR hash
- status, run schema, claim boundary

`validate_linear_static_run()`은 계획, 세 상태, 상태 lineage, backend displacement, ResultIR의 모든 불변식과 마지막 chain hash를 순서대로 다시 검증한다. 같은 immutable plan과 입력의 재실행은 동일한 receipt chain을 만들며, dense와 sparse는 입력과 symbolic pattern을 공유해도 backend metadata 때문에 서로 다른 plan/result/chain hash를 갖는다.

## 6. 검증 근거

집중 테스트는 다음 경계를 고정한다.

- [ExecutionPlan 테스트](../tests/test_engine_v2_execution_plan_v1.py): schema, 정확한 graph, DOF/CSR/scatter, recovery, determinism, tamper rejection
- [StateIR 테스트](../tests/test_engine_v2_state_ir_v1.py): immutable initial state, trial/commit/rollback, lineage, signed zero, non-finite·forged hash rejection
- [ResultIR 테스트](../tests/test_engine_v2_result_ir_v1.py): upstream binding, dense/sparse 수치 동등성, residual/reaction/recovery/energy 재계산, metadata tamper rejection
- [receipt-chain 테스트](../tests/test_engine_v2_receipt_chain_v1.py): 단일 조립, plan replay, 전체 lineage/hash, buffer binding tamper rejection

## 7. 명시적 제외와 다음 승격 조건

이 계약 완료는 Phase 0 CPU reference 선형정적 실행의 재현성과 무결성 경계를 뜻한다. 다음 항목을 완료했다고 주장하지 않는다.

- ROCm/HIP kernel, device-resident 실행, stream/device memory 수명주기
- CPU↔HIP numerical parity, deterministic parity 및 권위 있는 parity receipt
- 비선형, 동적, 좌굴, 접촉, 재료 이력 등 상용 solver 해석 범위
- 실측 stage timing, peak memory, 전송량 기반 성능 증거
- O(N) 복잡도, 로컬 PC 성능 목표 또는 대규모 모델 scalability
- 설계기준 검증, 독립 benchmark/회귀 corpus, 인증·상용 출시 준비도
- AI 보정·도면최적화·T-GNN/E(3)-GNN/PINN 학습 계약

HIP 승격은 별도 device execution context와 backend receipt를 추가하고, 같은 ModelIR/buffer/plan 의미에 대한 CPU↔HIP 결과·residual·reaction·recovery·energy parity를 권위 있는 테스트와 실측 telemetry로 증명한 뒤 수행한다.
