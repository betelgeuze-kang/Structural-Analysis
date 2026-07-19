# G1 실제 MGT 하중결합 아크길이 어댑터

이 증거는 analytic sparse-chain에서 검증한 `R(u, λ)`, `J_u v`,
`-∂R/∂λ` 계약을 실제 MIDAS MGT frame/shell/spring 조립과 작성된 `LIVE`
정적하중에 연결한다. 전체 아크길이 연속해석, material-state Newton,
Engine v2 production Krylov, ROCm/HIP 또는 G1 폐쇄를 실행하거나 주장하지 않는다.

## 요소 연결정보 교정

기존 frame 선택기는 요소 행과 `edge_index` 열이 같은 순서라고 가정했다.
그러나 `edge_index`는 중복 제거된 topology edge 배열이고 요소별 연결정보가
아니다. 확인한 optimized roundtrip에서는 line 요소 `5,576/5,576`개가 자신의
CSR 연결행과 다른 edge 열에 묶였다. 예를 들어 요소 `1224`의 권위 연결은 node
index `2273/2274`인데 기존 선택기는 `90/15`를 사용했다.

현재 계약은 다음처럼 fail closed다.

- frame 요소 결속의 유일한 출처는 `elem_conn_ptr/elem_conn_idx`다.
- `edge_index`는 frame 요소 결속 API에서 제거했다.
- CSR pointer의 길이, 단조성, 전체 span과 요소별 두 node 연결을 검사한다.
- malformed line 연결은 요소 ID와 개수를 기록하고 제외한다.
- 실제 재생 결과는 raw line `5,576`, solved frame `5,572`, short/degenerate
  제외 `4`, malformed 연결 `0`, row accounting exact `true`다.

이 교정은 frame 요소를 소비하는 coupled equilibrium, direct residual,
line-search, ILU/GMRES, ROCm diagnostic 호출 경로에도 함께 적용된다.

## 실제 모델 및 LIVE 하중 결속

- 입력은 `midas_generator_33.optimized.mgt`이며, rigid-link 해소와
  unreferenced-node 제거를 끈 권위 파서 프로파일로 매번 roundtrip을 만든다.
- 유지 모델은 node `13,047`, element `12,728`, frame `5,572`, shell `7,152`,
  global DOF `78,282`, active DOF `78,252`, free equation `70,560`이다.
- authored restraint DOF `7,707`과 finite spring component `10,152`를 같은
  조립에 넣는다.
- source section/material/plate-thickness table `183/6/25`를 소비한다. 다만
  `apply_shell_material_tangent=false`이며 material-state commit/rollback은
  연결되지 않았다.
- retained checkpoint load factor는 `0.656`이다.

파서는 원문의 `*UNIT`과 `*PRESSURE` 의미 필드를 보존한다. 어댑터는 단위가
`KN/M`임을 확인한 뒤 `LIVE` 정적하중만 선택하고 다음 행을 SI 자유도 벡터로
완전 조립한다.

- nodal load: `6/6`행, target node `6`개
- uniform unprojected `PRES/PLATE/FACE/GZ`: `3,644/3,644`행
- selected selfweight: `0`행
- unbound nodal/selfweight/pressure: 모두 `0`행
- pressure-loaded area: `7,802.903986433339 m²`
- nodal 수직 합력: `-22,964 N`
- pressure 수직 합력: `-50,605,366.359766565 N`
- 전체 수직 합력: `-50,628,330.359766744 N`
- 작성 nodal moment 합: `[1,810, 2,960, 0] N·m`
- resultant force 오차: `1.7881393432617188e-07 N`
- reference-load infinity norm: `179,458.19249999968 N`

선택한 `LIVE`에는 자중이 없으므로 밀도 proxy가 필요 없다. 알 수 없는 단위,
selfweight가 포함된 선택 대상, projected/nonuniform pressure, envelope 선택,
누락 node/element 또는 잘못된 surface topology는 근사하지 않고 차단한다.
따라서 `benchmark_bridge_proxy=false`,
`actual_mgt_semantic_load_case_consumed=true`다. 다만 load combination과 `DEAD`
selfweight를 소비한 것은 아니며 `production_load_case_claim=false`를 유지한다.

잔차는 free DOF에서 다음처럼 정의한다.

`R(u, λ) = F_int(u) - λ F_LIVE`

기존 `0.01` gravity 및 unit-normal-pressure benchmark vector는 모두 비활성화했다.
현재 LIVE slice에는 frame initial-stress proxy를 섞지 않으므로
`-∂R/∂λ = F_LIVE`다. 프로토콜 경계에서는 힘을 `N`에서 `kN`으로 정확히
`1000`으로 나눈다.

## Zero-load 시작점과 sparse predictor

`λ=0, u=0`은 residual `0 N`과 exact load direction을 만족한다. Zero-load와
unit-load tangent의 active/free 지도는 `78,252/70,560`으로 정확히 같고,
zero row, zero diagonal, structural-rank deficiency가 모두 `0`이다.

Free graph는 `2,171`개 component이며 `2,167`개가 authored restrained DOF와
직접 결합하지 않는다. 그러나 LIVE 하중을 받는 component는 `1`개이고 구속
경로에 결합한다. 하중이 없는 `2,170`개 component에는 exact zero solution을
두고, 하중을 받는 `1`개 component만 SciPy sparse direct solver로 풀었다.
Regularization과 fallback은 모두 `0`이다.

- full-unit predictor linear residual: `2.474674503583074e-04 N`
- relative linear residual: `1.378969925590373e-09`
- full-unit maximum translation/rotation:
  `0.003460998957181514 m` / `0.0016765239266973192 rad`
- diagnostic load factors: `0.25/0.5/1.0`
- full-load residual after subtracting the scaled sparse-solve floor:
  `1.4972174540162086e-06 N`
- full-load numerical-noise allowance: `3.5891638499999935e-06 N`
- remainder classification: `linear_within_numerical_floor`

선형 solve residual 자체는 `λ`에 비례하므로 이를 비선형 remainder로 오인하지
않는다. 각 진단점에서 scaled solve floor를 벡터로 뺀 뒤 남은 값이 reference
load의 `2e-11` 이내인지 확인한다. 측정 가능한 quadratic remainder는 없으며
`minimum_observed_remainder_order=null`이다. 이 근거로
`zero_state_sparse_direct_predictor_contract=true`다. 이는 zero-state CPU
predictor 진단일 뿐 arc-length corrector나 continuation path가 아니다.

Full-unit 자유도 예측자 하나는 little-endian binary64 파일로 고정했다. 자유도
순서는 adapter의 free-global-DOF 순서이고, `70,560`개 값과 `564,480`바이트를
갖는다. 데이터 SHA-256은
`5974fb0760380dc4c212d54ec379dd7d60246737c4af23500a2400632e1562bb`이며
영수증의 predictor-direction hash와 같다. 이 파일에서 재평가한 raw LIVE
잔차는 `2.4772050528554246e-04 N`으로 `5e-4 N` 게이트를 통과한다.
`full_unit_semantic_live_predictor_binary_artifact=true`는 이 단일 선형 예측자
벡터만 뜻한다. 시간/반복 이력을 가진 large-vector trace, material/geometric
nonlinear accepted checkpoint, load-`1.0` G1 checkpoint, ROCm/HIP 결과 또는 G1
폐쇄를 뜻하지 않으며 해당 claim은 모두 `false`다.

현재 잔차 모델은 참조 형상의 선형 frame/shell/spring 연산자이므로 그 범위에서
동일한 `70,560 × 70,560` CSR Jacobian(`1,264,133` nonzeros)을 문제 객체에
직접 결속한다. 계약 이름은
`linear_reference_geometry_residual_exact_csr.v1`이며, 행 포인터·열 인덱스·
수치값 해시를 각각 기록한다. `zero_state_problem()`은 과거 `0.656`
체크포인트를 초기 상태로 쓰지 않고 `u=0, λ=0`을 명시적으로 선택한다.

이 CSR은 현재 선형 잔차에는 정확하지만 corotational geometry, state-updated
material tangent 또는 이차수렴을 증명하지 않는다. 따라서
`state_invariant_linear_reference_tangent_bound=true`와 동시에
`nonlinear_current_tangent_claim=false`, `quadratic_convergence_claim=false`,
`material_state_commit_rollback_claim=false`를 유지한다.

## 선택적 상태 갱신 접선 계약

같은 어댑터를 `apply_state_updated_frame_axial_geometry=true`로 구성하면 현재
상태 접선 action은 더 이상 Python closure의 암묵적 수치만 갖지 않는다. 기준
CSR, free/global DOF 순서, prescribed background, 5,572개 frame stiffness delta,
5,572개 finite-chord axial 부모를 12개 canonical little-endian 배열로 결속한다.
실제 70,560식 계약은 총 `31,271,000`바이트이고 계약 해시는
`sha256:56fdb87292249c79557198159590710394f0b0482acf5552d55d7888cd730177`다.

NumPy 계약 평가기와 독립 analytic callback을 두 실제 방향에서 비교한 상대
무한노름 차이는 `4.480068989692911e-12`와
`1.8032488261425373e-16`이며 `1e-11` 게이트를 통과한다. 서로 다른 유효
누산 순서를 쓰므로 byte exact는 아니다. 이 결과는 CPU 수식/부모배열 동등성
증거일 뿐 HIP 평가기, CPU/HIP 수치 parity, 성능, production nonlinear solver,
G1 폐쇄를 뜻하지 않는다. 상세 계약은
`docs/engine-v2-current-tangent-operator.md`에 기록한다.

## 0.656 체크포인트 감사

좁은 adapter/derivative contract는 통과하지만, 기존 `0.656` 체크포인트는
교정 전 잘못된 frame 연결과 다른 benchmark 하중 계약에서 생성된 상태다.
따라서 교정된 LIVE operator의 평형점으로 승격하지 않는다.

- initial physical residual infinity norm:
  `1,277,024,522.7876618 kN` (`1,277,024,522,787.6619 N`)
- analytic negative-load derivative와 `λ±0.1` centered difference의 최대 오차:
  `1.818401074160647e-08 kN`; absolute tolerance `1e-06 kN`, 상대오차
  `1.0132728123630522e-10`
- `1e-7 m` tangent action과 독립 `2e-7 m` action의 최대 차:
  `7.275957614183426e-05 kN`, 상대오차 `3.3783233839930677e-12`

성분별 free-DOF internal-force infinity norm은 frame
`1.2769597941409329e12 N`, shell membrane `3.417142581974918e10 N`, shell
bending/drilling `3.4783882372304593e5 N`, spring `9.176081954801703e-1 N`이다.
최대 잔차는 node `336`, global DOF `2010` (`Dx`)에 있고 frame이 지배한다.

지배 요소 `16441`은 nodes `336/2294`, 길이 `0.4022747817102226 m`, 단면적
`0.01 m²`, material `5` (`RigidBar`), 탄성계수 `2.8e16 N/m²`다. 기존 checkpoint는
양단에 `0.003891727165247882 m`의 nodal translation jump와
`0.0046208896231890815`의 axial translation strain을 남긴다. 교정된 연결로
재평가한 이 요소의 force infinity norm은 `1.2769395524421929e12 N`이다.

`contract_pass=true`는 유한한 실제 잔차, 권위 연결, 완전한 LIVE 하중 벡터,
load derivative, tangent action 및 zero-state predictor 계약을 뜻한다. 초기
평형 게이트는 `residual_equilibrium_gate_passed=false`다.

## 과거 영수증과의 불일치

동일한 `0.656` checkpoint를 가리키는 저장
`mgt_direct_residual_newton_probe.json`의 base direct residual은
`42,754.66805918372 N`이다. 교정된 현재 조립값은
`1,277,024,522,787.6619 N`으로 약 `29,868,657.17`배다.
`stored_receipt_equivalent_to_current_adapter=false`와
`current_source_diverges_from_stored_direct_residual_receipt`를 유지한다.

저장 영수증의 `generated_at`은 `2026-06-04T07:16:56.554987+00:00`이지만
`source_commit_sha`와 `input_checksums`가 없다. 빌더도 전체 current-source direct
Newton probe를 재실행하지 않는다. 따라서 저장값의 exact replay와 현재 direct
probe 동등성을 주장하지 않는다.

## 산출물과 재현

- `implementation/phase1/release_evidence/productization/g1_mgt_load_coupled_arc_length_adapter_receipt.json`
- `implementation/phase1/release_evidence/productization/g1_mgt_load_coupled_arc_length_adapter_summary.json`
- `implementation/phase1/release_evidence/productization/g1_mgt_live_full_unit_predictor_free_displacement.f64le`
- `src/structural_analysis/schemas/g1_mgt_load_coupled_arc_length_adapter_v1.schema.json`

검사는 실제 파서, semantic-load 조립, frame/shell/spring 조립, component sparse
predictor와 단일상태 감사를 다시 실행한다.
파서 JSON 체크섬은 재생성 시각만 제외한 canonical JSON hash이며
`roundtrip_json_hash_mode=canonical_json_without_generated_at.v1`로 명시한다.

```bash
PYTHONPATH=src:implementation/phase1 /usr/bin/python3 \
  scripts/build_g1_mgt_load_coupled_arc_length_adapter_receipt.py --check
```

남은 폐쇄 단위는 교정된 LIVE operator에서 nonlinear 평형잔차를 만족하는
accepted state, full continuation과 load factor `1.0` accepted checkpoint,
시간/반복 이력을 가진 large-vector binary trace,
production matrix-free Krylov/preconditioner, state-updated material
commit/rollback, production ROCm/HIP 수치계약 및 독립 gfx1100 영수증이다.
