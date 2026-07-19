# Engine v2 PR-A 후속 계약 및 PR-C CPU FGMRES 스택

> 2026-07-19 상태 메모: 이 스택은 PR #104로 `main`에 squash merge됐다.
> 후속 Result authority 계약은
> `docs/engine-v2-result-diagnostic-authority.md`에 분리되어 있다.

## 상태 경계

이 문서는 PR #104 exact head 위의 **별도 후속 스택**을 설명한다. PR #104의
원격 Draft 상태, 리뷰 승인, CI receipt 또는 merge 상태를 변경하지 않는다.
PR #104는 F=0 정책과 exact-head CI가 준비됐지만 인간 contract review가 없으므로
Draft 해제·merge·readiness 승격 대상이 아니다.

후속 구현의 PASS는 로컬 계약·수치 테스트 통과만 뜻한다. ResultIR 권한,
engineering-result recovery, reaction authority, CPU/HIP parity, Windows 실실행
receipt, hardware 성능 또는 제품 readiness를 뜻하지 않는다.

## PR-A 후속 계약

### ModelIR v2

- `time_function`과 `construction_stage`가 round-trip 참조 집합에 포함된다.
- round-trip ID가 존재하더라도 `entity_kind`가 다르면
  `roundtrip_entity_kind_mismatch`로 차단한다.
- self-weight만 있는 load pattern은 빈 `nodal_loads`를 허용한다.
- `roundtrip_map.mapping_status=unsupported` 행에서 안정적인 blocker ID를
  자동 유도한다. 명시 blocker와 자동 blocker를 함께 analysis-ready gate에 넣는다.
- 전체 artifact identity인 `content_hash`와 별도로 물리 모델의
  `semantic_hash`, source/document identity의 `provenance_hash`를 제공한다.
- load-combination cycle 검사는 재귀 대신 명시적 stack을 사용해 1,100단계
  acyclic chain도 Python recursion limit와 무관하게 검증한다.

semantic/provenance 분리는 동일한 물리 모델의 source 이동과 물리 변경을 서로
다른 축으로 관찰하기 위한 것이다. 기존 `content_hash`를 대체하지 않으며,
소비자가 어떤 identity를 요구하는지 명시해야 한다.

### StateIR v1

manifest-only 검증도 다음 lifecycle 의미를 재검사한다.

- six-DOF 배수와 vector 길이
- epoch 0의 committed/unparented/zero 상태
- 이후 epoch의 parent 필수 및 self-parent 금지
- canonical little-endian fp64, vector byte hash, constitutive hash

대형 vector용 `StateIR binary manifest v1`은 displacement, velocity,
acceleration, constitutive vector를 JSON에 넣지 않는다. manifest는 dtype,
shape, byte length, data/content hash와 canonical filename URI만 가진다. 실제
artifact는 overwrite 금지 little-endian fp64 파일이며, 부분 쓰기 실패 때 이번
호출이 만든 파일만 제거한다.

### Global CSR → reduced CSR identity

`ExecutionPlanReducedCSR v1`은 다음 배열을 전역 CSR과 free partition에서 한 번만
유도한다.

- `free_csr_row_ptr` (`<i8`)
- `free_csr_column_indices` (`<i4`)
- `free_csr_global_value_indices` (`<i8`)

identity는 bound ExecutionPlan hash, global pattern hash, `global_to_free`와
`free_dofs` content hash, operator numeric-values hash를 함께 고정한다. CPU와
HIP가 reduced matrix를 독립 생성하는 대신 동일한 global-value position을
소비해야 한다.

F=0은 `[0]` row pointer와 빈 column/value-position 배열을 갖는
`no_solve_reaction_only` identity다. EquationScaling과 FGMRES recurrence에는
진입하지 않는다. Stateful nonlinear prescribed-displacement 경로도 같은
terminal disposition을 사용한다. 이 경로는 구성상태와 반력을 직접 평가해
commit할 수 있지만 Newton iteration·linear solve·line search는 모두 0이고,
residual/increment norm은 적용 불가이며 `convergence_claim=false`다. 즉 state
transition 성공을 Newton 수렴으로 승격하지 않는다.

## Descriptor-only vector artifact profile

기존 PR-B v1 inline manifest는 호환성을 위해 그대로 남는다. PR-C 런타임과 대형
모델 export는 `EngineV2VectorArtifactBundle v1`을 사용한다.

- EquationScaling: `scale_divisors_si.f64le`
- ScaledResidualTrace: `raw_residual_si.f64le`, `scaled_residual.f64le`
- manifest: dtype, shape, layout, byte order, byte length, data hash,
  content hash, source-contract binding, artifact URI
- artifact: canonical little-endian fp64 bytes

이 프로필은 source contract의 권한을 바꾸지 않는다. 특히 residual trace는 계속
non-authoritative diagnostic이며, PR-C iteration receipt에는 vector를 inline하지
않는다.

## PR-C deterministic CPU FGMRES

### 필수 입력과 binding

`run_cpu_fgmres`는 다음을 모두 요구한다.

- equation scaling이 bound된 ExecutionPlan
- bind 시 사용한 SI coordinates와 reference load의 full replay
- exact reduced-CSR identity
- global CSR pattern order의 canonical operator numeric values
- global equation order의 right-hand side
- exact free-equation scale vector
- identity 또는 고정 positive inverse-diagonal right preconditioner

operator bytes의 SHA-256이 reduced-CSR identity의
`operator_numeric_values_hash`와 다르면 recurrence 전에 차단한다.

### recurrence와 결정론

- left equation scaling: `D_free^-1 A x = D_free^-1 b`
- flexible right-preconditioned basis (`V`, `Z`를 분리)
- two-pass modified Gram-Schmidt
- ascending-index Python `math.fsum` dot/matvec accumulation
- restart length와 max iteration을 명시적 hashed parameter로 기록
- 각 candidate에서 exact residual `A x - b`를 다시 계산
- convergence: `scaled_l2 <= max(atol, rtol * initial_scaled_l2)`

NumPy/SciPy dense 또는 sparse solve, BLAS dot, backend fallback을 recurrence에
사용하지 않는다. 고정 preconditioner는 v1 범위를 좁히기 위한 것으로 ILU,
multigrid, GPU preconditioner 또는 nonlinear tangent solve를 주장하지 않는다.

### compact checkpoint와 terminal

각 iteration receipt는 vector 본문 없이 다음만 기록한다.

- raw/scaled residual data hash와 solution-free data hash
- translation raw L2/Linf `[N]`
- rotation raw L2/Linf `[N·m]`
- dimensionless scaled L2/Linf
- governing equation, node ID, DOF
- restart index/inner iteration과 observation hash

restart record는 시작/끝 observation hash와 disposition을 연결한다. terminal
reason은 다음 네 값만 허용한다.

- `initial_residual_satisfied`
- `converged_scaled_residual`
- `max_iterations`
- `arnoldi_breakdown`

최종 free solution은 descriptor-only `solution_free.f64le` artifact다. run receipt는
`non_authoritative_solver_recurrence`이며 ResultIR, member force, reaction 또는
engineering result를 만들지 않는다. `replay_cpu_fgmres_run`은 source scaling을
다시 replay하고 모든 compact checkpoint 및 solution bytes를 재계산한다.

## Cross-platform deterministic gate

`Engine v2 Cross-platform Determinism CI`는 다음 4개 조합에서 동일한 고정
golden을 재생한다.

- Ubuntu / Python 3.10
- Ubuntu / Python 3.12
- Windows / Python 3.10
- Windows / Python 3.12

golden 대상은 ModelIR content/semantic/provenance hash, base/bound ExecutionPlan,
EquationScaling, scale-vector bytes/content, reduced CSR, StateIR와 binary manifest,
ScaledResidualTrace와 vector bundles, CPU FGMRES run 및 solution bytes다.

각 matrix job은 해시 계산에 그치지 않고 StateIR 4개 vector, scaling vector,
raw/scaled residual vector, FGMRES solution까지 8개 canonical little-endian 파일을
임시 기록하고 다시 읽어 byte length와 SHA-256을 고정 golden과 비교한다.
ModelIR fixture 원문 bytes도 별도 SHA-256 golden으로 고정한다.
`build_engine_v2_cross_platform_determinism_receipt.py run`은 실제 OS/Python,
NumPy 버전, checkout HEAD, tracked-clean 상태, GitHub run identity, contract hash와 binary
readback을 coordinate 영수증으로 기록한다. 네 job은 각 영수증을 별도 workflow
artifact로 올린다.

PR 이벤트는 합성 merge SHA가 아니라 `pull_request.head.sha`를 명시적으로
checkout하고 영수증의 source commit으로 사용한다. Push와 수동 실행은
`github.sha`를 사용한다. 따라서 이 lane의 source identity는 실행 당시 exact
PR head 또는 exact push SHA다.

`matrix-receipt` job은 실패한 matrix까지 `always()`로 관찰하고 네 artifact를
다운로드한다. 집계기는 정확히 다음을 모두 요구한다.

- 네 OS/Python 좌표가 누락·중복 없이 존재
- 실제 OS와 Python major/minor가 요청 좌표와 일치
- 같은 clean checkout commit과 같은 GitHub run ID/attempt/URL
- 같은 frozen golden set과 실제 binary readback
- 원래 matrix job 결과가 `success`

통과한 집계 JSON도 workflow artifact로만 보존한다. 이 JSON의 유효성은 연결된
GitHub Actions run과 coordinate artifact가 유지되는 동안에 한정되며, 저장소에
복사된 JSON 하나만으로 원격 실행을 주장할 수 없다.

로컬 Linux PASS는 workflow 계약과 현재 플랫폼 replay 증거다. 실제 Windows
coordinate 및 통과한 four-way matrix artifact가 실제 원격 run에서 생기기 전에는
Linux/Windows deterministic closure나 Developer Preview Windows gate를 닫지
않는다. Four-way Engine v2 hash replay가 통과하더라도 별도의 전체 제품
Linux/Windows replay gate를 대신하지 않는다.

## 검증 명령

```bash
python3 -m ruff check \
  src/structural_analysis/engine_v2 \
  src/structural_analysis/model_ir \
  tests/test_engine_v2*.py \
  tests/test_model_ir_v2_contract.py

python3 -m pytest -q \
  tests/test_engine_v2*.py \
  tests/test_model_ir_v2_contract.py

python3 -m pytest -q \
  tests/test_engine_v2_cross_platform_goldens.py \
  tests/test_build_engine_v2_cross_platform_determinism_receipt.py
```

수치 검증에는 deterministic diagonal solve, coupled SPD 직접해 비교, 강제
restart/max-iterations, exact-zero initial residual, singular Arnoldi breakdown,
고정 diagonal preconditioner replay, binary tamper/overwrite, coherent manifest
tamper가 포함된다.

## 남은 게이트

- PR #104 인간 contract review, Draft 해제, 승인된 squash merge
- 이 후속 스택의 독립 리뷰와 승인된 integration 경로
- 실제 GitHub Actions run에서 보존된 4-way coordinate 및 matrix receipt artifact
- displacement-only NumericalResultIR/DiagnosticIR 타입은 후속 slice에 구현됨;
  engineering result recovery, reaction 및 member-force 계약은 계속 미구현
- CPU/HIP가 동일 reduced identity와 numeric bytes를 소비한다는 hardware receipt
- benchmark hierarchy, nonlinear consistent residual/Jacobian, full-load continuation
- 제품 shell/Viewer/persistence 상태와 PR #102 정리

따라서 이 문서는 G1–G10, AI-G1–AI-G10, Developer Preview, RC 또는 commercial
readiness closure 증거로 사용할 수 없다.
