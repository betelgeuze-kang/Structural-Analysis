# Engine v2 Phase 0 고정 랭크 직교사영 v1

- 문서 상태: Phase 0 구현 계약
- 대상 구현: `src/structural_analysis/engine_v2/ai/projection.py`
- 계약 버전: `structural-analysis-fixed-rank-projection.v1`
- 알고리즘 버전: `two_pass_mgs_jacobi_scaled.v1`

## 1. 목적과 주장 경계

이 프리미티브는 `ExecutionPlan`에 결박된 소수의 물리·Krylov·AI 후보 벡터를
고정 랭크 직교기저로 만들고, 스케일 좌표 벡터에 다음 사영을 적용한다.

\[
\Pi_Q(v) = Q(Q^T v)
\]

명시적 밀집 사영행렬 \(P=QQ^T\)는 생성하지 않는다. 이 구현의 역할은
향후 AI 보조솔버가 사용할 작은 correction/coarse space를 제공하는 것뿐이다.

현재 구현이 증명하지 않는 항목은 다음과 같다.

- `AICorrectionProposal` 생성 또는 후보의 물리적 유효성
- full residual/JVP, 에너지, BC/MPC/release, OOD 및 설계기준 acceptance gate
- `StateIR` 변경, commit 또는 byte-reproducible rollback
- 비선형·동적·HIP 솔버와의 결합
- 전체 구조해석의 `O(N)` 복잡도 또는 CPU/GPU 해석 가속
- T-GNN, E(3)-GNN, PINN의 정확도나 상용 AI 보정 성능

따라서 이 아티팩트의 claim boundary는
`phase0_fixed_rank_projection_primitive_only`이다. 테스트 통과나 복잡도 영수증을
솔버 속도, 수렴성 또는 상용 준비도 증거로 승격해서는 안 된다.

## 2. 좌표와 강성 스케일 계약

`N`을 `ExecutionPlan`의 자유도 수라고 하고, `K_ff`를 동일한 자유도 순서의
축약 강성행렬이라고 한다. 대각 Jacobi 에너지 스케일은 다음과 같다.

\[
D = \operatorname{diag}(K_{ff})^{-1/2}
\]

물리 변위 자유도 벡터를 \(u\), Jacobi 에너지 스케일 좌표를 \(x\)라 하면
좌표 방향은 반드시 다음과 같이 해석한다. \(D=K_{ff,ii}^{-1/2}\)이므로
\(x\)의 단위는 무차원이 아니라 `sqrt_joule_energy_coordinate`다.

\[
u = D x, \qquad x = D^{-1}u
\]

즉 `scaling_diagonal`에는 \(D\)가 저장되지만, 물리 후보를 기저화하기 전에는
`candidate / scaling_diagonal`, 곧 \(D^{-1}u\)로 변환한다.
`scale_free_vector(u)`도 \(x=D^{-1}u\)를 반환하며,
`unscale_free_vector(x)`는 \(u=Dx\)를 반환한다.

`basis_q`와 `apply()`의 입력·출력은 스케일 좌표 공간에 있다. 물리 변위에
사영을 적용하려면 다음 순서를 사용해야 한다.

```text
x          = D^-1 u
x_project  = Q(Q^T x)
u_project  = D x_project
```

`Q(Q^T u)`처럼 물리 변위를 직접 `apply()`에 전달하면 좌표 계약을 위반한다.

스케일은 임의 전처리 파라미터가 아니다. 아티팩트는 `plan_hash`,
`operator_hash`, `pattern_hash`에 결박되고, 검증 시 현재 계획의
`1/sqrt(diag(K_ff))`와 byte-exact하게 대조된다. `diag(K_ff)`의 항목이
0 이하이거나 비유한 값이면 기저 생성을 중단한다. 양의 대각은 이
프리미티브의 필요조건일 뿐 `K_ff` 전체의 양정치성 증명은 아니다.

## 3. 입력과 불변 아티팩트

`build_fixed_rank_projection(plan, candidate_vectors, ...)`의 후보 행렬은
물리 자유도 좌표의 열벡터 모음이며 shape은 `(N, m)`이다.

- `N`: `ExecutionPlan.free_dofs`의 수
- `m`: 후보 수
- `rank_cap`: `1..16`
- `1 <= m <= rank_cap`
- 기본 종속 벡터 제거 허용오차: `1e-12`

입력 후보 수를 무제한으로 받고 앞부분만 조용히 절단하지 않는다. 후보 수가
상한을 넘으면 fail-closed 처리한다. 이는 고정 랭크 복잡도 계약의 일부다.

생성된 `FixedRankProjection`의 핵심 필드는 다음과 같다.

| 필드 | 의미 |
| --- | --- |
| `plan_hash` | 정확한 `ExecutionPlan` 결박 |
| `operator_hash` | 조립된 선형 연산자 결박 |
| `pattern_hash` | 축약 CSR symbolic pattern 결박 |
| `free_dof_count` | `N` |
| `candidate_count` | 입력 후보 수 `m` |
| `rank_cap` | 요청된 고정 랭크 상한, 최대 16 |
| `retained_rank` | 종속 후보 제거 후 랭크 `k` |
| `scaling_diagonal` | \(D=\operatorname{diag}(K_{ff})^{-1/2}\) |
| `candidate_vectors` | 재검증을 위한 원본 물리 후보 열벡터 |
| `basis_q` | 스케일 좌표의 직교기저, shape `(N, k)` |
| `complexity_receipt` | 기저화와 1회 사영의 정확한 작업량 |
| `projection_hash` | 메타데이터·배열 descriptor·영수증의 집계 해시 |

`scaling_diagonal`, `candidate_vectors`, `basis_q`와 API가 반환하는 벡터는 모두
C-contiguous, little-endian FP64(`<f8`), immutable `bytes` backing을 사용한다.
manifest에는 O(`Nk`) 수치값을 중복 삽입하지 않고 dtype, shape, byte length,
raw data hash와 metadata-bound content hash만 기록한다.

## 4. 기저 생성 알고리즘

각 물리 후보 \(u_j\)에 대해 다음 결정론적 순서를 사용한다.

```text
work = D^-1 u_j
reference_norm = ||work||_2

repeat exactly twice:
    for each previously retained q_i in insertion order:
        alpha = dot(q_i, work)
        work  = work - alpha * q_i

residual_norm = ||work||_2
if residual_norm <= drop_tolerance * reference_norm:
    drop candidate
else:
    retain work / residual_norm
```

이는 두 번의 modified Gram-Schmidt(MGS) 재직교화다. 후보 순서와 유지된 기저
순서를 변경하지 않으며 QR/SVD 라이브러리의 임의 pivoting에 의존하지 않는다.
모든 후보가 영벡터 또는 허용오차 내 선형종속이면 랭크 0 아티팩트를 만들지
않고 실패한다.

생성 후 다음 값을 기록하고 재검증한다.

- Frobenius 오차 \(\lVert Q^TQ-I\rVert_F\)
- Gram 오차의 최대 절댓값
- Phase 0 Frobenius 허용한계 `1e-10`
- 원본 후보와 스케일을 이용한 두 번의 MGS byte-exact replay

따라서 해시만 갱신한 후보·기저 변조도 알고리즘 replay 결과와 다르면
거부된다.

## 5. 암시적 사영

`apply_fixed_rank_projection()`은 스케일 좌표 벡터 `v`에 대해 기저 열을
순회한다.

```text
result = zeros(N)
for q_i in Q:
    coefficient = dot(q_i, v)
    result += coefficient * q_i
```

O(`N^2`) 크기의 `QQ^T`를 만들지 않으며, 결과도 immutable FP64 배열이다.
검증용 소형 테스트 oracle을 제외하고 제품 코드에서 명시적 projector를
만드는 것은 금지한다.

일반 호출 순서는 다음과 같다.

```python
from structural_analysis.engine_v2.ai.projection import (
    build_fixed_rank_projection,
    validate_fixed_rank_projection,
)

projection = build_fixed_rank_projection(
    plan,
    physical_candidate_columns,  # shape: (N, m)
    rank_cap=16,
)
validate_fixed_rank_projection(projection, expected_plan=plan)

x = projection.scale_free_vector(physical_u)
x_projected = projection.apply(x)
physical_u_projected = projection.unscale_free_vector(x_projected)
```

이 예제의 `physical_u_projected` 역시 proposal 후보일 뿐, 승인된 구조응답이
아니다.

## 6. 복잡도 영수증

영수증의 `N`, `k`, `nnz`는 각각 자유도 수, 유지 랭크, 계획의 축약 CSR
symbolic nonzero 수다. `m`은 `candidate_count`이며 `m <= rank_cap <= 16`이다.

| 영수증 필드 | 정확한 값 또는 의미 |
| --- | --- |
| `n`, `k`, `nnz` | 실행계획에 결박된 `N`, 유지 랭크, 축약 CSR nonzero 수 |
| `basis_scaling_multiply_count` | `N*m`; \(D^{-1}\) 좌표 변환의 원소별 scale 연산 수 |
| `orthogonalization_dot_count` | 실제 두 번의 MGS에서 호출한 벡터 dot 수 |
| `orthogonalization_axpy_count` | 실제 두 번의 MGS에서 호출한 AXPY 수 |
| `orthogonalization_multiply_count` | `N*(MGS dot 수 + MGS AXPY 수)` |
| `normalization_divide_count` | `N*k` |
| `multiply_count` | 사영 1회당 `2*N*k` scalar multiply |
| `dot_count` | 사영 1회당 `k` vector dot |
| `axpy_count` | 사영 1회당 `k` vector AXPY |
| `basis_elements` | `N*k` |
| `source_vector_elements` | `N*m` |
| `dense_projector_elements` | 항상 `0` |
| `max_dense_square_dimension` | 직교성 진단 Gram의 `k`, 항상 `<= k` |

영수증의 복잡도 label은 사영 `O(Nk)`, 기저화 `O(Nk^2)`다. 더 정확히는
기저화가 입력 후보 수를 포함해 `O(Nmk)`이지만 `m`과 `k`가 모두 16 이하로
고정되므로 계약 label을 `O(Nk^2)`로 둔다. 이 label은 실행한 kernel 호출과
저장량의 구조적 상한이며 다음을 의미하지 않는다.

- sparse solve 또는 전체 Newton/Krylov 반복이 O(`N`)이라는 증거
- mesh 증가에 따른 실측 시간·메모리 slope
- HIP device residency, kernel fusion 또는 CPU 대비 속도 향상

## 7. Fail-closed 검증

생성과 재검증은 다음 오류를 허용하지 않는다.

- 유효하지 않거나 다른 `ExecutionPlan` 결박
- `K_ff` 대각의 0, 음수 또는 비유한 값
- `rank_cap` 범위 위반, 상한보다 많은 후보, 랭크 0
- 잘못된 shape/dtype/layout 또는 mutable backing
- 후보, 기저, 스케일, 입력·출력의 NaN/Inf
- 현재 계획과 다른 스케일
- 두 번의 MGS replay와 다른 기저
- 직교성 오차 또는 복잡도 counter 변조
- 배열 descriptor나 `projection_hash` 변조

권위 있는 경로에서는 항상
`validate_fixed_rank_projection(projection, expected_plan=plan)`처럼 현재
계획을 전달해야 한다. plan 없이 수행하는 내부 무결성 검증은 계획의 강성
대각이나 `nnz`를 독립적으로 재구성할 수 없다.

## 8. 의존성 및 격리 규칙

이 모듈은 NumPy와 Engine v2의 canonical hash/immutable array,
`ExecutionPlan` 계약만 사용한다.

- PyTorch, JAX, TensorFlow, autograd를 import하지 않는다.
- reverse-mode graph, saved activation, backward 학습루프가 없다.
- `implementation/phase1` 또는 기존 `structural_analysis.ai` 연구 구현을
  import하지 않는다.
- legacy projection, QR, Krylov 구현의 성공 영수증을 재사용하지 않는다.

이 격리는 기존 연구 scaffold의 claim이나 숨은 dense/fallback 경로가 새
Engine v2 계약으로 유입되는 것을 막기 위한 것이다. 향후 AI feature runtime도
이 프리미티브에 후보 벡터만 전달하고 수치 진실 또는 acceptance 권한은
소유하지 않는다.

## 9. 구현된 상위 companion 계약

이 projection을 사용하는 제한된 Phase 0 상위 경로는
[AI proposal·physics gate·QR memory v1](engine-v2-ai-proposal-gate-qr-v1.md)에
구현되어 있다. 아래 항목은 projection 프리미티브 자체의 권한이 아니라
별도 contract/gate의 권한이다.

### 9.1 `AICorrectionProposal` 계약

`AICorrectionProposal v1`은 `ExecutionPlan`, committed `StateIR`, projection,
operator/state epoch, `Qy`, `DQy`, trust, OOD 상태를 해시로 결박한 immutable
initial-guess overlay다. 현재 builder는 calibrated feature provenance/UQ를 생성하지
않으며 `acceptance_eligible=false`다.

### 9.2 물리 acceptance gate와 rollback

CPU reference gate는 full `Ku-F`, `||D R_free||₂`, potential energy, constrained
increment, stateless linear-elastic element-law consistency를 replay하고 항상 exact
rollback한다. OOD/calibration이 없으므로 현재 proposal은 물리 check가 좋아져도
`rejected`다. nonlinear history, MPC/release 확장, 설계기준 gate는 아직 미구현이다.

### 9.3 bounded QR memory

`FixedRankQRMemory v1`은 전체 영수증을 다시 검증한 ready
`LinearStaticRun`의 committed-minus-initial physical mode만 teacher로 받는다.
후보 수와 유지 랭크는 16 이하로 고정하고 다음을 명시적으로 검증한다.

- deterministic insertion/drop 순서와 두 번의 재직교화
- topology, DOF ordering, operator 또는 plan 변경 시 invalidation
- authoritative committed state만 teacher signal로 사용하는 lineage
- rank, condition, 직교성, drop 사유 및 메모리 byte 수 영수증
- proposal/trial/rejected receipt을 teacher로 받지 않는 type 경계

이 메모리는 RLS/Kalman/readout update를 하지 않으므로 no-backprop learning
완성이 아니다. 또한 현재 direct solver가 proposal을 소비하지 않으므로 고정 랭크
사영을 구조해석 수렴 가속기로 표현하지 않는다.

## 10. 검증 범위

집중 테스트는 실제 `ExecutionPlan` fixture를 사용해 다음을 확인한다.

- `D=1/sqrt(diag(K_ff))`와 물리/스케일 round trip
- 결정론적 두 번의 MGS, 종속 후보 제거와 직교성
- 암시적 `Q(Q^T v)`와 소형 oracle의 수치 일치 및 멱등성
- 정확한 작업량·저장량 counter와 dense projector 0
- rank 상한, mechanism의 0 강성 대각, 비유한 값 거부
- 후보·기저·영수증·재해시 스케일 및 다른 plan 결박 변조 거부
- ML framework와 legacy 구현 import 부재

관련 상위 방향은 [Structural Solver Engine v2 마스터 로드맵](structural-solver-engine-v2-master-roadmap.md),
[ModelIR/StateIR/ResultIR 경계 ADR](adr/002-modelir-stateir-resultir-schema.md),
[AI proposal/rollback ADR](adr/005-ai-proposal-and-rollback-contract.md),
[복잡도·benchmark ADR](adr/006-complexity-and-benchmark-contract.md)을 따른다.
