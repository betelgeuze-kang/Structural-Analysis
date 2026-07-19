# Engine v2 선형 정적 엔지니어링 결과 회복 계약

## 목적

`NumericalResultIR`의 변위 권위와 반력·부재력 권위를 분리한 상태에서, 동일한
수치 상태와 동일한 선형 연산자를 재생했을 때만 후자의 권위를 부여한다.

- `LinearStaticRecoveryOperator`: 결과 권위가 없는 불변 회복 입력 계약
- `EngineeringResultIR`: 독립 평형 재생을 통과한 반력·국부 부재단력 결과

두 타입 모두 Engine v2 core에 있으며 legacy assembly, solver, Viewer 또는 특정
CPU/HIP backend를 import하지 않는다.

## 회복 연산자 결합

회복 연산자는 다음 바이트와 식별자를 하나의 canonical hash로 묶는다.

1. equation scaling이 결합된 정확한 `ExecutionPlan`
2. 같은 plan에서 파생된 `ExecutionPlanReducedCSR`
3. reduced solve의 `operator_numeric_values_hash`와 같은 전역 CSR 숫자값
4. `EquationScaling` source와 같은 기준 외력 벡터
5. 요소 순서별 kinematic matrix `Q`
6. 요소 순서별 대칭 local stiffness matrix `K_local`
7. frame 12성분 또는 axial `FX_I`/`FX_J` 결과 프로필
8. 상위 assembler가 검증해야 하는 recovery-law receipt hash

계약 생성 시 `transpose(Q) * K_local * Q`를 요소 순서대로 전역 CSR pattern에
조립하여 원래 CSR 숫자값과 행별 scaled `Linf <= 1e-12`로 비교한다. axial
프로필은 `FX_I`, `FX_J` 외 local stiffness 행과 열이 정확히 0이어야 한다.
따라서 solve에 쓰지 않은 임의의 강성값이나 다른 외력으로 결과를 회복할 수 없다.

회복 연산자 manifest에는 대형 수치 배열을 넣지 않고 dtype, shape, byte length,
data/content hash만 넣는다. 이 타입 자체의 `result_authority`는 항상 false다.

## EngineeringResultIR 승격 게이트

`create_engineering_result_ir`는 authoritative `NumericalResultIR`와 정확히 결합된
회복 연산자를 받아 다음을 독립 재계산한다.

1. `F_internal = K_global * u`
2. `R = F_internal - load_factor * F_reference`
3. free equation scaled `Linf <= 1e-10`
4. `f_local = K_local * Q * u_element`
5. 요소력의 전역 재조립과 `F_internal` 차이 scaled `Linf <= 1e-10`
6. constrained displacement가 모두 정확히 0인지 확인

모든 게이트가 통과하면 constrained residual을 반력으로, 요소 순서의 local end
force를 부재력으로 보존한다. free residual은 반력과 섞지 않고 별도 artifact로
유지한다. 잔차 부호는 `internal_minus_external`로 고정된다.

## 산출물

manifest는 descriptor만 보존하고 다음 little-endian FP64 파일은 별도로 쓴다.

- `reaction_global.f64le`: constrained 위치의 반력, free 위치는 0
- `equilibrium_residual_global.f64le`: free 위치의 잔차, constrained 위치는 0
- `member_local_end_force.f64le`: 요소 순서 × 12 local end-force 성분

write helper는 `xb` 배타 생성으로 기존 파일을 덮어쓰지 않는다. 일부 파일을 쓴
뒤 실패하면 이번 호출이 만든 파일만 제거한다. readback은 descriptor의 byte length,
data hash와 content hash를 모두 다시 확인한다.

## 권위와 한계

`EngineeringResultIR`의 reaction/member-force 축은 bound replay 범위에서
`authoritative`다. numerical state, convergence, displacement 권위는 source
`NumericalResultIR`에서 상속한다.

다음은 계속 비권위 또는 미지원이다.

- recovery-law receipt의 서명자·외부 진위 인증
- CPU/HIP 회복 parity
- prescribed displacement가 0이 아닌 모델
- F=0 `no_solve_reaction_only`
- material/geometric nonlinear recovery
- engineering design 및 code compliance
- legacy output adapter와 Viewer projection
- release readiness와 commercial use

즉 임의 hash를 넣어 만든 객체는 제품 증거가 아니다. 상위 assembler/adapter는
recovery-law receipt와 원래 solver receipt를 먼저 인증해야 한다.

## 검증

```bash
PYTHONPATH=src python3 -m pytest -q \
  tests/test_engine_v2_engineering_result_v1.py \
  tests/test_engine_v2_result_ir_v1.py \
  tests/test_engine_v2_core_dependency_boundary.py

python3 -m ruff check \
  src/structural_analysis/engine_v2 \
  tests/test_engine_v2*.py
```

이 검증은 backend-neutral CPU reference replay와 계약 경계만 증명한다. 실제
legacy/Workbench/Viewer 연결과 CPU/HIP parity는 별도 후속 작업이다.
