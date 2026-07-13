# Structural Solver Engine v2 통합 아키텍처 및 마스터 로드맵

- Status: proposed implementation source of truth
- Version: 0.2.25
- 기준일: 2026-07-14
- 감사 기준: `origin/main` commit `602dc8c`
- 범위: 독립 구조해석 솔버, ROCm/HIP 가속, 물리제약 AI 보조솔버, 도면 최적화 폐루프
- Claim boundary: 이 문서는 목표 아키텍처와 구현 순서를 정의한다. 현재 제품 준비도나 G1-G10/AI-G1-AI-G10 폐쇄를 선언하지 않는다.

## 1. 문서 권한

현재 상태와 미래 목표를 혼동하지 않도록 문서 권한을 분리한다.

| 문서 | 권한 |
| --- | --- |
| 본 문서 | Engine v2 목표 구조, 의존성 규칙, 구현 순서, 단계별 종료 기준 |
| [GitHub documentation status](github-documentation-status.md) | 현재 공개 가능한 claim과 GitHub 문서 상태 |
| [Commercialization current state](commercialization-gap-current-state.md) | 현재 상용화 상태 요약 |
| [Commercial solver gap ledger](commercial-structural-solver-product-gap-ledger.md) | G1-G10 현재 상태와 미폐쇄 증거 |
| [Structural AI engine gap ledger](structural-analysis-ai-engine-gap-ledger.md) | AI-G1-AI-G10 현재 상태와 미폐쇄 증거 |
| [Solver-consistent Newton/Krylov plan](solver-consistent-newton-krylov-improvement-plan.md) | 현재 수치해석 폐쇄 전술과 counter-evidence |
| [Independent productization plan](independent-commercial-productization-plan.md) | 릴리스 및 독립제품 승격 기준 |
| [Architecture definition document](architecture-definition-document.md) | 기존 Hybrid Physics-AI 연구 방향과 역사적 맥락 |

충돌 시 현재 상태와 허용 claim은 gap ledger와 readiness 문서가 우선한다. 미래 Engine v2 구조와 구현 순서는 본 문서가 우선한다. 어느 로드맵 항목도 authoritative receipt와 집중 검증 없이 완료로 승격하지 않는다.

## 2. 제품 결정

Engine v2를 다음과 같이 정의한다.

> 독자적인 유한요소 residual/tangent 엔진이 해석의 유일한 수치적 진실이며, AI는 초기값, 고정 rank 보정공간, 전처리기, coarse basis, 설계후보를 제안한다. 모든 AI 제안은 CPU/HIP 물리솔버의 전체 residual, 에너지, 경계조건, 구성방정식 및 설계코드 검증을 통과해야 한다.

핵심 결정:

1. AI를 꺼도 모든 지원 해석과 설계 검증이 완전하게 동작해야 한다.
2. CPU FP64 reference와 HIP production backend는 동일한 element/material 의미론과 operator 계약을 사용한다.
3. AI는 solver state를 직접 확정하지 않고 `AICorrectionProposal`만 반환한다.
4. 제품 실행 중 학습은 역전파 없이 고정 feature와 local RLS/QR/Kalman 계열 업데이트로 제한한다.
5. O(N)은 무조건적 전체 해석 주장이 아니라 제한된 차수와 고정 rank에서의 연산 및 실측 near-linear solve 목표다.
6. 기존 구현은 한 번에 삭제하지 않고 새 core가 parity를 통과할 때마다 검증 harness로 내려보내는 strangler refactor를 사용한다.

## 3. 목표와 비목표

### 3.1 목표

- 3D frame, shell, solid, link, spring, MPC, diaphragm, release, offset을 표현하는 typed structural IR
- 선형정적, P-Delta, modal, buckling, response spectrum, 비선형정적, 시간이력, 시공단계로 확장 가능한 독립 FE operator
- AMD 소비자 및 워크스테이션 GPU에서 실행되는 ROCm/HIP device-resident 솔버
- attention/Transformer 없이 고정 깊이 E(3)-equivariant 공간 특성과 causal temporal state를 결합한 AI 보조솔버
- 역전파 없는 local physical learning과 직교 coarse-space 보정
- AI 후보 생성, HIP batch 재해석, KDS/시공성 검증, Pareto 선택, 도면 diff를 연결한 최적화 폐루프
- MIDAS, IFC, OpenSees, 허용된 ETABS 교환 형식 및 DXF adapter
- 지원 범위를 명시하고 unsupported 입력을 silent-ignore 하지 않는 fail-closed 제품
- CPU/HIP parity, 교차솔버 비교, 독립 V&V, 실제 프로젝트 shadow validation을 포함하는 상용 검증 체계

### 3.2 비목표

- AI가 평형해 또는 안전 판정을 독자적으로 확정하는 구조
- 모든 MIDAS/ETABS/OpenSees 기능을 1년 내 완전 복제하는 것
- 모든 비선형·접촉·고유치·최적화 문제에 대한 무조건적 O(N) 주장
- dense projector, global all-pairs attention, 모델 크기에 따라 증가하는 무제한 coarse rank
- CPU fallback이나 proxy 결과를 숨긴 GPU/AI 성공 claim
- 구조기술사 검토, 법적 책임 또는 인허가 승인을 자동 대체하는 것

## 4. 현재 기준선

현재 저장소에는 재사용 가치가 높은 기술 자산이 있지만 통합 Engine v2는 아직 없다.

| 영역 | 현재 자산 | Engine v2 판정 |
| --- | --- | --- |
| CPU solver | 6DOF frame/truss, dense/sparse solve, residual·reaction·member-force 검사 | reference backend 출발점으로 재사용 |
| Model import | 고급 MGT parser, 제한된 제품 adapter, IFC entity scan | typed ModelIR adapter로 재구성 |
| Physical operator | frame/shell/spring residual, matrix-free JVP, 직접 residual replay | authoritative operator 계약으로 추출 |
| HIP | resident operator buffer, batch residual/JVP, Rust/HIP FFI, sparse bridge | 완전 device-resident Newton/Krylov로 재구성 |
| T-GNN | neighbor aggregation + GRU 학습 prototype | 연구 baseline으로 유지, 제품 runtime 재구현 |
| Simplicial GNN | edge/face aggregation prototype | E(3) equivariance 증거 없음 |
| PINN | 평균화된 저차 physics loss 기반 GRU prototype | 실제 FE residual 기반 discrete physics layer로 교체 |
| E(3)-GNN | 문서 요구사항 | 실제 구현 없음 |
| Projection | 작은 dense/QR/Krylov scaffold와 일부 coarse-basis 경로 | 고정 rank matrix-free projection만 승격 |
| Optimization | 후보 생성, 축약 solver 검증, 비용/DCR proxy, 비교 UI | full-FE solver-verified 폐루프로 교체 |

목표 제품 대비 공학적 추정치는 다음과 같다. 이 수치는 릴리스 점수나 증거 폐쇄율이 아니다.

- 재사용 가능한 기술 기반: 약 50-60%
- 독립 구조해석 제품 전체: 약 20-30%
- 완전 device-resident HIP solver: 약 15-25%
- 통합 E(3)/temporal/no-backprop AI machine: 약 5-20%
- 독립 상용 V&V: 약 5-10%

기존 T-GNN/PINN/PGOB 또는 projection report의 `contract_pass`는 이 문서의 신규 gate를 통과하기 전까지 Engine v2 완료 증거로 인정하지 않는다.

## 5. 목표 아키텍처

```text
MGT / IFC / OpenSees / ETABS / DXF
                  |
                  v
          Typed ModelIR v2
                  |
                  v
    ExecutionPlan + StateSnapshot
                  |
                  v
 Element / Material Operator Contract
 R(u), Kt(u), J(u)v, M, C, energy
           |                    |
           v                    v
 CPU FP64 Reference    HIP DeviceExecutionContext
                                |
                                v
                 JFNK/FGMRES + AMG/DD
                                |
              +-----------------+-----------------+
              |                                   |
              v                                   v
 E(3)/Temporal AI Proposal             Authoritative continuation
 Q, warm start, UQ, hotspot             Newton/Krylov/dynamics
              |
              v
 Constraint projection + small projected solve
              |
              v
 Full residual/energy/BC/material/code replay
              |
       +------+------+
       |             |
       v             v
    accept         discard -> physics fallback
       |
       v
 DesignDelta verification -> Pareto -> drawing regeneration/diff
```

### 5.1 목표 저장소 경계

```text
schema/sair/                   # versioned ModelIR/StateIR/ResultIR

engine/
  core/                        # units, IDs, frames, SoA, DOF map
  elements/                    # frame, shell, solid, link, contact
  materials/                   # elastic, plasticity, RC fiber, damage
  operators/                   # R, Kt, Jv, M, C, energy
  solvers/                     # linear, nonlinear, eigen, dynamic
  preconditioners/             # block, auxiliary-space, AMG, DD, Schur
  backends/{cpu_reference,cpu_optimized,hip}/

runtime/{rust_host,api}/
interop/{midas,ifc,opensees,etabs,dxf}/
ai/{feature_runtime,temporal_runtime,local_learning,projection,uncertainty}/
optimization/{actions,candidate_generation,solver_verification,pareto,drawing_regeneration}/
codes/{kds,rulepacks}/
python/{training,experiments}/
apps/{workbench,viewer}/
validation/{elements,operators,benchmarks,cross_solver,hardware}/
```

### 5.2 의존성 규칙

- importer는 `ModelIR`까지만 생성하며 solver를 직접 호출하지 않는다.
- element/material 의미론은 backend와 분리하고 CPU/HIP에서 동일 fixture를 소비한다.
- Python은 training, conversion, orchestration, validation에 사용하되 production numerical truth가 되지 않는다.
- Rust host는 lifetime, session, checkpoint, job isolation을 관리하되 constitutive truth를 별도로 복제하지 않는다.
- AI는 immutable `StateView`를 읽고 proposal만 반환한다.
- optimization은 `SolverSession.verify(DesignDelta)`를 통과한 변경만 채택한다.
- backend는 fallback, host transfer, precision, hardware를 receipt에 기록한다.
- unsupported entity나 변환 손실은 fail-closed 또는 명시적 partial-import로 종료한다.

## 6. 핵심 데이터 계약

스키마는 versioned binary representation과 사람이 읽는 JSON mirror를 제공한다. 구체적인 binary 기술은 ADR에서 결정하되 ABI와 schema versioning을 먼저 고정한다.

### 6.1 `ModelIR`

- canonical SI unit와 원본 unit/provenance
- node와 typed element/material/section/thickness/reinforcement
- local frame, offset, eccentricity, release
- support, spring, MPC, diaphragm, contact
- load pattern, combination DAG, time function, mass source, damping, construction stage
- 원본 entity ID와 round-trip mapping
- unsupported/approximated/ignored 항목의 명시적 상태

### 6.2 `ExecutionPlan`

- DOF와 constraint/null-space map
- CSR/BSR pattern, ordering, coloring
- partition, halo, coarse hierarchy
- device layout와 kernel specialization
- geometry, topology, property hash와 symbolic 재사용 범위

### 6.3 `StateSnapshot`

- `u`, `v`, `a`, load factor, time, stage
- integration-point/material/contact/hinge/damage/creep history
- accepted/rejected trial 구분
- checkpoint checksum과 provenance

### 6.4 `OperatorContract`

- `R(u, state) = F_int - F_ext`
- consistent tangent `K_t(u, state)`와 matrix-free `J(u, state)v`
- mass, damping, geometric stiffness
- strain/kinetic energy와 dissipation
- component/element force breakdown
- residual/JVP parity와 finite-difference audit hook

### 6.5 `ResultIR`

- displacement, velocity, acceleration, reaction
- member force, stress, strain, integration-point history
- modal, buckling, response spectrum, dynamic envelope
- convergence history와 failure reason
- backend, hardware, precision, version, checksum
- code-check와 optimization provenance

### 6.6 `AICorrectionProposal`

- warm start 또는 bounded local correction basis
- coarse/preconditioner suggestion와 affected support
- uncertainty, OOD, covariance/calibration
- source model/checkpoint/training receipt
- 예상 residual 감소와 연산비용
- final result를 확정하는 권한은 없음

### 6.7 `DesignDelta`와 `VerificationReceipt`

- 단면, 재료, 철근, 벽체, 가새, 접합, 배치 변경
- topology-preserving/topology-changing 구분
- full residual, increment, BC, energy, constitutive gate
- KDS/DCR, drift, 강건성, 비용, 탄소, 시공성
- accepted/rejected와 정확한 원인
- before/after drawing mapping과 diff provenance

## 7. 수치해석 엔진

### 7.1 수치적 진실

authoritative path는 element/material law에서 계산되는 실제 residual과 tangent다. AI residual 감소량, proxy DCR, 축약모델 또는 post-polishing 값은 최종 평형 증거가 아니다.

CPU reference backend 역할:

- FP64, 단순하고 독립적인 구현
- element patch, rigid-body, energy, reaction 검증 기준
- HIP 결과와 독립적으로 생성되는 golden result
- 성능보다 가독성, 재현성, 오류 격리 우선

### 7.2 HIP `DeviceExecutionContext`

- model topology, SoA element data, CSR/BSR, state, load를 최초 1회 적재
- Newton, Krylov, line search, time integration 중 host 왕복 제거
- 동일 constitutive source에서 fused residual과 analytic/생성된 JVP 계산
- 동일 topology 최적화 후보를 multi-state/multi-RHS batch 처리
- property 변경은 symbolic plan 재사용, topology 변경 때만 hierarchy 재구성
- iteration scalar와 최종 선택 결과만 host 전달
- `gfx1030` 단일 하드코딩 대신 fat binary와 runtime capability dispatch

지원 모드:

- verification: deterministic coloring/segmented reduction, FP64 중심
- performance: fused/atomic kernel과 mixed precision 허용
- mixed: FP32 smoother/AI/preconditioner + FP64 residual/energy + iterative refinement

### 7.3 솔버와 전처리기

- 선형: CG, MINRES, GMRES/FGMRES, multi-RHS
- 비선형: Newton, modified Newton, JFNK, trust region, line search, arc-length
- 동해석: Newmark 계열부터 generalized-alpha 등으로 확장
- 고유치: modal/buckling에 필요한 제한 모드 eigensolver
- 전처리: 6x6 block, frame/shell Schur, shell auxiliary-space, RAS, AMG, GENEO
- checkpoint/restart: accepted state와 constitutive history를 원자적으로 보존

AI/Krylov/accepted-history basis는 coarse-space 후보로만 사용한다. AMG/DD를 사용했다는 사실만으로 near-O(N)을 주장하지 않고 mesh 증가에 따른 iteration과 operator complexity를 측정한다.

## 8. AI 보조솔버

T-GNN, E(3)-GNN, physics-informed layer를 하나의 거대 end-to-end 모델로 묶지 않고 역할별로 분리한다.

### 8.1 E(3)-equivariant 공간 runtime

- 거리, 내적, 상대좌표, local frame에 기반한 고정 깊이 local message passing
- scalar, polar vector, axial vector, 필요 시 rank-2 tensor 채널 분리
- 변위와 힘은 polar vector, 회전과 모멘트는 axial vector로 취급
- bounded neighborhood, 고정 channel width, 고정 layer count
- hotspot, coarse basis, preconditioner coefficient, uncertainty 출력

### 8.2 Temporal graph state

- global attention 대신 node/element별 causal recurrent 또는 graph state-space update
- 소성, 손상, 크리프, 시공단계, 하중이력과 hidden state 대응
- teacher-forced, free rollout, long-horizon rollout 분리 검증
- edge index와 topology tensor 사전 캐시

### 8.3 Physics-informed discrete operator

- 학습 및 acceptance residual은 실제 `OperatorContract.R` 사용
- BC, MPC, release, constitutive, energy 위반을 별도 보고
- 평균 1-DOF 또는 lumped `m/c/k` proxy는 제품 검증에 사용하지 않음
- full FE residual replay 전 모델 출력 승격 금지

### 8.4 비역전파 정의

Engine v2에서 비역전파는 inference-only를 뜻하지 않는다. 제품 runtime parameter update 중 다음을 사용하지 않는다는 뜻이다.

- reverse-mode autograd
- `loss.backward()` 또는 동등한 global backward graph
- saved activation을 통한 전체 그래프 gradient 저장

제품 runtime은 다음으로 제한한다.

- 고정 equivariant feature bank 또는 orthogonal graph reservoir
- local linear/bilinear readout
- square-root RLS, block QR, Kalman 또는 constrained least squares
- 고정 rank local adapter와 bounded gate
- solver가 승인한 state만 teacher signal로 사용

역전파 모델은 정확도 상한과 ablation을 확인하는 연구 baseline으로 유지할 수 있으나 shipped numerical truth나 runtime 적응 경로가 될 수 없다.

### 8.5 Projected Residual Local Learning

AI는 최종 변위를 직접 생성하지 않고 correction subspace를 제안한다.

```text
Q = orthonormalize([physics coarse modes, Krylov modes, AI local modes])
delta_u = Z Q y

y* = argmin_y ||W^(1/2) (R(u) + J(u) Z Q y)||^2 + lambda ||y||^2
u_trial = u + delta_u
```

- `Z`: support/MPC null-space operator
- `Q`: 고정 rank block-local basis
- `W`: residual 또는 energy scaling
- `lambda`: trust/regularization parameter

`Q Q^T` dense projector를 만들지 않고 `Q(Q^T r)` 순서로 적용한다. `u_trial`은 full residual, relative increment, BC/MPC/release, energy, constitutive admissibility, globalization, OOD/UQ 및 해당 설계코드 gate를 모두 통과해야 한다.

하나라도 실패하면 proposal을 폐기하고 원본 accepted state로 byte-reproducible rollback한 뒤 physics solver를 계속한다.

## 9. O(N) 및 성능 계약

`N`은 free DOF, `E`는 mesh/graph incidence, `T`는 time step, `B`는 후보 수, `k`는 correction/coarse rank다.

| 작업 | 목표 복잡도 | 성립 조건 |
| --- | ---: | --- |
| element residual/assembly | `O(N+E)` | element order와 mesh degree 제한 |
| matrix-free `Jv` | `O(N+E)` | bounded local operator |
| 고정 깊이 E(3)/temporal pass | `O(N+E)` | depth, width, neighbor 수 고정 |
| local RLS/QR update | `O(Nc^2)` | local feature rank `c` 고정 |
| projection `Q(Q^T r)` | `O(Nk)` | `k` 고정 |
| basis QR | `O(Nk^2)` | `k` 고정 |
| restarted Krylov | `O(mE + m^2N)` | restart `m` 고정 |
| 전체 Newton-Krylov | 조건부 near-`O(N)` | Newton/Krylov iteration이 mesh-independent |
| T-step 동해석 | `O(T(N+E))` | T를 별도 보고 |
| B개 후보 평가 | `O(B(N+E))` | topology와 symbolic plan 재사용 |

O(N) claim 제외 영역:

- 일반 sparse direct factorization과 fill-in
- 전체 eigen spectrum
- 접촉 탐색의 일반/최악 복잡도
- near-singular, 좌굴점, 고대비 재료에서 증가하는 반복 수
- 전역 topology 최적화의 조합 탐색
- 무제한 rank projection 또는 전역 attention

제품 문구는 다음으로 고정한다.

> 고정 차수 건축 mesh에서 residual, matrix-free iteration, AI inference는 O(N+E)를 목표로 한다. 지정 benchmark family에서 multilevel-preconditioned solve의 실측 time/memory complexity slope 0.85-1.15를 요구한다.

### 9.1 금지 구현 패턴

- 명시적 `P = Q Q^T`
- `toarray()` 등 full sparse-to-dense 변환
- unbounded global sort/all-pairs attention
- 모델 크기와 함께 자동 증가하는 rank, depth, width
- iteration마다 graph topology 또는 edge tensor 재생성
- iteration마다 state H2D/residual D2H
- synthetic loop만 측정한 O(N) receipt
- CPU fallback을 포함한 결과의 HIP PASS 처리

### 9.2 성능 측정 규칙

- 최소 5개 크기군에서 log-log slope 측정
- DOF, element, nnz, Newton/Krylov iteration, AMG operator complexity 동시 기록
- preprocessing, solve, AI inference, residual replay, serialization 분리 계측
- cold/warm run 분리
- peak RAM/VRAM, host transfer bytes, kernel count 기록
- 16GB VRAM 목표 모델에서 OOM 및 숨은 fallback 0건

## 10. AI 도면 최적화 폐루프

```text
ModelIR / drawing
  -> atomic DesignDelta 생성
  -> AI local ranking and hotspot prediction
  -> constructability and code prefilter
  -> shared-topology HIP batch solve
  -> exact residual + KDS + robustness gate
  -> Pareto(cost, carbon, safety, constructability)
  -> selected candidate full authoritative reanalysis
  -> drawing regeneration and before/after diff
  -> engineer approval
```

속도 우위는 해석 생략이 아니라 graph/CSR/ordering/hierarchy 재사용, topology-preserving 후보 batch, AI warm start, 변경 element만 재조립하는 데서 얻는다.

모든 후보는 원본 drawing/member ID, 변경 이유, 비용/탄소 provenance, DCR/drift/residual/robustness 전후값, rejected reason, 최종 full-solve receipt와 생성 도면 checksum을 보존한다.

## 11. Legacy-to-v2 migration

| 현재 자산 | v2 목적지 | 처리 원칙 |
| --- | --- | --- |
| `src/structural_analysis/` linear path | `engine/backends/cpu_reference` | golden fixture를 보존하며 typed operator로 추출 |
| 고급 MGT parser | `interop/midas` | raw token을 typed ModelIR로 승격, 손실 fail-closed |
| equilibrium/residual/JVP runner | `engine/operators`, `validation/operators` | product operator와 audit harness 분리 |
| HIP full residual FFI | `engine/backends/hip` | resident context와 device solver로 승격 |
| Python sparse/Newton probes | `validation/legacy` | 새 core parity 후 production path에서 제거 |
| T-GNN/PINN/simplicial scripts | `python/experiments` | baseline/ablation, product claim 금지 |
| projection scaffold | `ai/projection` test seed | dense projector 제거 후 재작성 |
| design optimization runner | `optimization/candidate_generation` | proxy ranker로 제한, full verification 연결 |
| viewer/delivery comparison | `apps/workbench` | ResultIR/VerificationReceipt 공식 소비 |

기존 파일 이동·삭제 전 입력 fixture와 checksum, 새/기존 parity, rollback 가능한 commit, claim 변화 없음, production dependency 제거 테스트를 확보한다.

## 12. 단계별 로드맵

### Phase 0: 0-90일, 통합 기반

목표는 동일 MGT 모델이 새 IR을 통해 CPU/HIP에서 같은 residual, reaction, member force를 내는 walking skeleton이다.

산출물:

- ADR-001 Numerical truth and claim boundary
- ADR-002 ModelIR/StateIR/ResultIR schema
- ADR-003 Operator ABI and constitutive source policy
- ADR-004 Backend, fallback, precision, residency contract
- ADR-005 AI proposal and rollback contract
- ADR-006 Complexity and benchmark contract
- ADR-007 V&V and promotion policy
- 새 module skeleton과 dependency lint
- frame/shell CPU reference operator
- MGT -> ModelIR v2 adapter와 round-trip audit
- HIP `DeviceExecutionContext` 첫 버전
- CPU/HIP residual/JVP parity suite
- 고정 E(3) feature + local RLS/QR spike
- graph -> AI -> HIP residual replay complexity harness

종료 기준:

- CPU/HIP DOF ordering과 residual 의미론 일치
- 숨은 fallback 없이 HIP kernel invocation 증명
- AI proposal 실패 시 원본 state rollback
- unsupported MGT 항목 silent loss 0건
- 기존 proxy PASS를 Engine v2 완료로 오인하지 않음

권장 인원: 10-12명.

#### Phase 0 현재 진행상태 (2026-07-14)

완료된 기반:

- [ADR-001~007](adr/README.md) accepted baseline
- [Engine v2 capability matrix](engine-v2-capability-matrix.md): implementation/promotion 상태 분리
- [ModelIR v2 Phase 0 contract](modelir-v2-contract.md)
- strict JSON Schema, semantic validator, deterministic fingerprint, golden frame fixture
- deterministic `SolverModelBuffers v1` ABI와 numerical/entity/artifact hash 분리
- [ExecutionPlan·StateIR·ResultIR v1 계약](engine-v2-execution-state-result-contracts-v1.md): node-major 6DOF map, canonical full/reduced CSR, 정확한 7단계 operator graph, K/F 및 recovery hash 결속
- [Sparse-only ExecutionPlan v2·CPU direct CSR](engine-v2-sparse-execution-plan-v2.md): global `(G,G)` 강성행렬 없이 sorted full/reduced CSR과 structural-zero slot을 결정론적으로 직접 조립하고 sparse residual/JVP·SciPy direct solve·reaction/recovery/energy를 제공; support-mask/source bytes 재도출, alias-free tuple snapshot, exact same-runtime solve replay와 adversarial rehash/TOCTOU 방어 검증; retained plan-array byte slope `1.0219`는 peak-memory나 solve O(N) 증거가 아님
- immutable StateIR initial/trial/commit과 rejected trial의 byte-identical rollback
- residual/reaction/member-force/energy를 재계산하는 ResultIR aggregate receipt와 dense/sparse backend 구분
- precompiled `ExecutionPlan`을 재조립 없이 실행하는 CPU reference runner와 ModelIR→buffer→plan→state→result receipt chain
- [HIP DeviceExecutionContext v1](engine-v2-hip-context-v1.md): native `libamdhip64` capability probe, 전체 ModelBuffer 지속 allocation, 실제 H2D/D2H/allocation/sync 계측, explicit unavailable/no-fallback 및 failed-open cleanup-only ownership 경계
- [HIP allocation lineage foundation v1](engine-v2-hip-allocation-lineage-v1.md): arbitrary pointer 등록 없이 실제 malloc 전 orphan cleanup authority를 예약하고 성공한 exact base에만 process-local owner capability를 발급한다. f64/i32/u8 extent·alignment·uintptr overflow, domain/device range overlap와 bounded monotonic generation, multi-owner atomic exclusive borrow, immutable free/orphan target, success/quarantine handshake, pointer·device drift와 terminal marker·caller handoff·publication rollback의 비동기 예외 안전성, per-device fail-closed poison, weak registry/quarantine compaction을 검증했다. 이 foundation 단독 문서는 allocator/fence/solver receipt나 live predecessor를 증명하지 않으며, 실제 FreeSpace/Krylov 연결은 다음 통합 계약에서 별도로 검증한다
- [HIP FreeSpace/Krylov allocation lineage integration v1](engine-v2-hip-free-space-krylov-allocation-lineage-v1.md): FreeSpace 12개와 Krylov 9개 owned 실제 malloc/free를 owner-minted capability와 immutable free/orphan lease에 연결하고, Krylov가 parent 5개 capability를 all-or-none exclusive group borrow로 소비한다. Context v2는 managed byte/count, allocation/deallocation·quarantine·unknown-outcome telemetry와 exact stage/byte conservation을 결박하고, owner/capability/orphan/token 및 HIPRTC module의 중단 안전 handoff와 persistent terminal disposition으로 double-free/double-unload를 차단한다. 이는 process-local unsigned/non-promoting lifetime 증거이며 FGMRES live predecessor, device content/mask, solver parity, host-copy zero, O(N), speedup 또는 상용 준비 증거가 아니다
- [HIP FGMRES live checkpoint resource context v1](engine-v2-hip-fgmres-live-checkpoint-context-v1.md): actual Krylov parent의 `reduced_state`·`reduced_load`·`jacobi_inverse` 3개와 fresh peer owner의 `solution_x`·`true_residual`·`work_w`·`basis_v`·`preconditioned_basis_z`·`packed_dense_state`·`fgmres_control_state_v2`·`solve_record` 8개를 exact11 group lease로 결속한다. Registry-level exact-token control은 canonical owner role/allowlist, 예약 후 successful publication exactly 8, controlled borrow admission을 강제하고 same runtime/device/stream, internal RTC v2 module/checkpoint token, module→group→owned8→owner→semantic-last 역순 cleanup과 failed-open/BaseException 복구를 검증한다. Actual `gfx1030` resource chain은 fallback 없이 관찰했지만 H2D/D2H/kernel/sync 0인 resource-only slice이며 owned content, authoritative predecessor/mask validator, checkpoint transaction, solver/solution, iteration host-copy zero, O(N), speedup과 상용 준비 증거는 아니다
- [HIP FGMRES canonical predecessor v1](engine-v2-hip-fgmres-canonical-predecessor-v1.md): live exact11을 유지한 채 Krylov parent의 reduced CSR3와 reduction ping/pong2를 비직렬 delegated projection으로 결합해 exact16 physical capability를 같은 runtime/device/stream에 결속한다. 추가 allocation 없이 owned8을 sealed `hipMemsetAsync` 8회로 초기화하고 `INIT`→first-column scale prefix→non-advancing `PREDECESSOR_VALIDATE=14`의 exact `27+14S` kernel row를 제출한 뒤 exact-runtime final fence 하나와 pending consume를 완료한다. Control offset 116/120/124의 `empty→armed→consumed`·mask snapshot·reduction-epoch snapshot을 후속 checkpoint seal로 고정했다. Product path는 actual mask/verdict를 D2H하지 않으므로 발행 capability는 device outcome에 조건부이며 authoritative predecessor, checkpoint transaction, invalid-source atomicity, solver/solution, iteration host-copy zero, O(N), speedup과 상용 준비를 승격하지 않는다
- [HIP FGMRES checkpoint invalid-source atomicity v1](engine-v2-hip-fgmres-checkpoint-atomicity-v1.md): `CHECKPOINT_DECIDE`와 pure-copy COMMIT 사이에 destination access가 0인 non-advancing `PREFLIGHT_COMMIT_SOURCE=9`를 삽입하고 state 3을 정상 preflight ticket으로 고정했다. 정상 legacy `0→3→0`, sealed `2→3→0` lifecycle과 same-stream fixed four-row owner를 구현해 late invalid source에서도 `solution_x`/`true_residual` 전체 bytes를 보존한다. Multi-block invalid failure state는 scheduling에 따라 `2|3`이고 mask/reduction snapshot을 보존한다. Terminal `commit_required=continuation_required=0`은 future action gate clear이며 과거 no-commit/rollback 단독 증거가 아니다. 이 true claim은 exact registered nonoverlap allocation, exclusive source ownership과 fixed owner sequence에만 적용하며 arbitrary raw duplicate, external writer/DMA/device fault는 포함하지 않는다. 새 F-sized workspace·product H2D/D2H/intermediate sync/fallback은 없지만 end-to-end O(N)이나 speedup 증거는 아니다
- [HIP FGMRES canonical-capability-consuming sealed checkpoint transaction v1](engine-v2-hip-fgmres-sealed-checkpoint-transaction-v1.md): still-open canonical context의 non-owning child가 conditional predecessor capability를 reserve 후 enqueue에서 single-use consume하고, exact live kernel/checkpoint token/stream/direct11과 physical16 projection에 fixed four-row transaction을 제출해 transaction-owned final fence 1회로 닫는다. Upstream canonical prefix를 포함한 chain은 total fence 2이고 추가 allocation/device bytes/borrow/checkpoint owner/module/H2D/D2H/intermediate sync/fallback은 0이다. Unit/legacy `23/56`, actual `gfx1030` valid/late-invalid scoped cases `2 passed`를 확인했다. Consume-return interruption은 shared consume bit에서 retryable cleanup owner로 reconcile하고 closed receipt는 current binding claim을 해제한다. Standalone receipt는 semantic consistency만 검증하므로 provenance authenticity에는 `expected_context` 또는 서명이 필요하다. Product receipt는 actual mask/verdict/commit/device outcome을 관찰하지 않아 conditional continuation만 발행하며 authoritative predecessor/numerical transaction/solver/solution, later recurrence, host-copy-zero, O(N), speedup, promotion과 상용 준비는 false다
- [HIP FGMRES sealed-continuation global recurrence owner v1](engine-v2-hip-fgmres-global-recurrence-v1.md): `initial + R*M columns + FINAL_GUARD` fixed program을 exact full/sealed-prefix/continuation segment로 분할하고 suffix만 같은 direct11/physical16·kernel/runtime/device/stream/checkpoint authority에 제출한다. v0.2.24 RTC의 flat exact-type identity witness, 네 launch path의 private expected-prior-pending atomic gate와 suffix 전/후 deep binding check 2회는 deterministic `L=1/35`에서 identity serialization 0과 pending count `0..L-1`을 확인해 fixed-row-work host submission의 제한된 `O(L)` 구조 gate를 만든다. RTC `103`, owner `11 passed in 268.76s`, sealed/global lifecycle `6 passed in 123.64s`와 independent lifecycle audit를 통과했다. `F=12,nnz=144,M=2,I=2` later-column required `gfx1030` case는 full/prefix/suffix `84/45/39`에서 `1 passed in 38.29s`로 직전 `165.02s` 대비 test wall-clock이 약 `4.31x` 짧아졌고 terminal `E/Q=79/26`과 verification-only CPU exact parity를 유지했다. 추가 required `F=24,nnz=360,M=2,I=5,R=3` case는 `1 passed, 1 deselected in 59.39s`, full/prefix/suffix `228/45/183`, restart `1->2->3`, CPU max-iteration oracle iteration/restart `5/3`·operator/preconditioner `9/5`, device terminal restart 3 column 0 `E/Q=179/58`과 solution/residual allclose를 확인했다. 두 case의 product path allocation/H2D/D2H/intermediate sync/fallback/live read/branch는 0이고 global fence는 1이다. `FINAL_GUARD E/Q=215/70`은 제출되었지만 terminal 후 inactive이므로 active final-guard fallthrough은 raw-only/unproven이다. `38.29s`는 host-control test wall-clock이지 kernel/solver speedup이나 일반 `N`-DOF O(N) 증거가 아니다. Dead unconsumed stream-idle lease는 lazy reap하지만 consumed/pending cleanup owner 유실은 자동 reap하지 않고 parent close를 fail-closed한다. Product terminal observation, full parity, iteration host-copy-zero, promotion과 상용 준비는 false다
- v0.2.24 linear audit에서 validation 후 live row/pointer 재조회의 transient TOCTOU HIGH를 발견했고, registry-sealed tuple-backed immutable dispatch snapshot과 canonical row-value tuple로 실제 launch argument를 고정했다. 최초 regression은 `1 passed in 26.62s`, 수정 후 F12/F24 required hardware는 `2 passed in 96.11s`를 통과했다. Final independent re-audit은 transient row/pointer/two-thread, bool-int alias, value-equal launches tuple, forged registry dispatch slot을 launch 전 거부 또는 canonical-only 제출로 확인했고, `+0.0/-0.0`을 `float.hex()`로 exact seal해 drift 시 `binding_invalid`/launch 0을 확인했다. Direct deep call은 `L=1/35` 모두 2, aggregate deep-validator count는 enqueue 3/fence 4로 고정이었다. Focused `4 passed in 120.65s`, immutable `1 passed in 26.74s`, Ruff/format/py_compile PASS 후 요청 범위 remaining defect 0으로 종료했다
- v0.2.25 lifecycle checkpoint는 checkpoint lease witness/snapshot에 exact loaded-runtime `hipStreamQuery`를 봉인한다. `0=COMPLETE`, `600=NOT_READY`만 exact bool로 구분하고 기타 status/예외·stale token/device/stream/binding·pending mismatch는 fail-closed다. Sealed parent의 recovery cell은 child/lease를 strong reference로 보유하지 않고 weakref callback에서 abandonment만 기록하며 HIP을 호출하지 않는다. Parent close는 exact query→필요 시 successful sync 1회→query→exact pending pop→terminal release로 소유권을 정리하고 interruption을 monotonic state로 재시도한다. Independent audit `BLOCKER/HIGH/MEDIUM/LOW 0/0/0/0`, focused recovery `33 passed`, RTC full `111 passed in 34.77s`, checkpoint context v2 full `261 passed in 248.58s`를 통과했다. Actual RX 6900 XT `gfx1030` `F=12,M=2,I=2` lifecycle gate는 39-launch suffix child를 소실시킨 뒤 pending `39 -> 0`, query `(False, True)`, sync 1, product malloc/H2D/D2H/runtime sync 0을 확인하며 `1 passed, 2 deselected in 37.42s`를 기록했다. 이는 process-local cleanup 증거일 뿐 completion capability, numerical outcome/parity/result, 일반 O(N), speedup, promotion/commercial claim을 만들지 않는다. C++/HIP/public schema/ABI와 global/combined/source semantic hash는 불변이다
- [HIP 요소·재료 장치 조립 v1](engine-v2-hip-device-assembly-v1.md): host가 reference-axis code와 symbolic reverse map만 만들고 HIPRTC frame/truss 요소 기여도와 결정론적 reverse-segment gather로 CSR 수치값을 장치에서 생성; host CSR numeric H2D 0 계약, exact attempt/success telemetry, failed-open cleanup ownership 및 `gfx1030` 컴파일·두 symbol 확인까지 완료; assembly-only receipt 자체는 fresh native launch·수치 parity·downstream 실행을 증명하지 않으며 소비 계약은 아래 별도 gate가 담당
- [HIP assembly-resident CSR consumer v1](engine-v2-hip-resident-csr-consumer-v1.md): live assembly owner의 CSR row/column/value와 foundation load를 exclusive epoch lease로 빌려 같은 runtime/device/stream의 fused `R=Ku-F`/`Jv=Kv`가 소비; consumer-owned state/direction/residual/JVP 4개, state-only open H2D, zero-transfer/allocation/fence enqueue, test-double full/free/constrained parity, caller-kernel preflight, atomic parent/child lifetime·poison·retry cleanup, concurrent receipt snapshot, operation↔byte·stage-prefix·ownership 상태기계 및 nested receipt-chain 검증; resident 단독 계약은 host verification producer만 공개하며 아래 free-space child가 별도 device producer 계약을 제공한다
- [HIP free-space device-direction operator v1](engine-v2-hip-free-space-operator-v1.md): detached symbolic 5-array overlay만 H2D하고 assembly-owned full CSR와 resident state/load에서 `K_ff`, `u_f`, `F_f`를 같은 stream에서 장치 물질화한 뒤 `F_f-K_ffu_f` 방향을 opaque single-use generation으로 resident full residual/JVP에 전달하고 reduced JVP를 gather한다. Zero-prescribed exact `+0.0` preflight, full residual의 자유 성분과 direction 부호 교차검증, owned 12/borrowed 6 buffer authority, 단계별 partial-failure receipt, shared poison·retry cleanup, HIPRTC 3-symbol compile 및 조건부 native hardware gate를 검증했다. 기본 환경의 hardware gate는 skip될 수 있으며 CG/FGMRES/PCG·preconditioner·solver loop·iteration host-copy 0·O(N)·속도·상용 증거는 아직 없다
- [HIP Krylov vector/reduction·positive Jacobi primitives v1](engine-v2-hip-krylov-primitives-v1.md): exact latest free-space apply 재검사와 exclusive grandchild lease를 parent queue-lock에서 원자화하고, reduced CSR/direction/JVP 5개를 빌리며 9개 workspace를 소유해 positive unshifted Jacobi, fixed affine/Jacobi, numerical `atomicAdd` 없는 deterministic dot tree와 scale-first LASSQ norm diagnostic batch를 same stream에 enqueue한다. Raw batch H2D/D2H/allocation/sync/fallback 0, planned multistage reduction receipt, explicit 7-D2H+1-fence CPU parity, live batch/execution witness, parity-failure shared poison, pending-stream module-unload 차단과 acknowledgement-failure retry owner, HIPRTC 9-symbol compile 및 조건부 native hardware gate를 검증했다. 이는 recurrence나 solver-integrated preconditioner가 아니며 CG/FGMRES/PCG·SPD·iteration host-copy 0·O(N)·속도·상용 증거는 아직 없다
- [CPU fixed-restart FGMRES reference v1](engine-v2-cpu-fgmres-reference-v1.md): actual `r0=b-Ax0`, positive unshifted Jacobi right preconditioning, DGKS conditional second-pass MGS, incremental Givens, scale-relative Arnoldi/triangular breakdown, candidate/restart true-residual replay와 solver-L2+authoritative-scaled-L∞ dual gate를 SciPy iterative/fallback 없이 독립 구현했다. Strict immutable result receipt는 source/policy/array/count/history를 재도출하고 공개 weak mode 없이 전체 recurrence를 결정론적으로 재실행한다. 네 frame load mode direct parity, zero/tiny RHS, arbitrary/direct `x0`, happy/unhappy breakdown, `2+2+1` restart cap, 극단 scale와 fully-rehashed forgery를 검증했지만 HIP 실행·속도·O(N)·ResultIR·상용 증거는 아니다
- [HIP fixed-restart FGMRES allocation/policy plan v1](engine-v2-hip-fgmres-plan-v1.md): exact ExecutionPlan/free-space view, finite-positive Jacobi diagonal/inverse와 CPU policy를 결박하고 7 borrowed/9 owned HIP buffer, `M<=16`, global `I<=4096`, `P=ceil(F/512)`, dense `M²+5M+1`, solve record `192+72R`를 계획한다. Little-endian header/restart field offset, terminal/termination/hint code, flag bit, convergence/breakdown/stagnation/divergence 규칙과 live primitive/apply lineage 요구를 logical memory hash 및 strict schema에 고정했다. 이는 compile-time plan이며 allocation·HIPRTC recurrence·device convergence observation·iteration host-copy 0·native parity는 아직 없다
- [HIPRTC FGMRES 7-symbol recurrence substrate v1](engine-v2-hip-fgmres-rtc-substrate-v1.md): Krylov primitive parent에 exact source apply·pointer/runtime/stream identity를 결박하는 exclusive FGMRES solver-child lease를 추가하고, fixed-source record-init/active-masked reduced CSR SpMV/residual/host-scalar copy-scale/positive Jacobi/external-device-scalar terminal-control/restart-record 7-symbol을 구현했다. Plan과 공유하는 little-endian solve-record field/code/flag hash에 device-error/control-mode/per-symbol launch ABI를 더한 interface hash를 HIP source marker와 compile 전 교차검사하고, header에 `M`을 보관해 append-only/monotonic restart, `step<=M`, `reorth<=step`, dual-gate metric/flag/hint, actual iteration 소진을 device에서 검사한다. Pending-stream unload fence·retry cleanup, 실제 `gfx1030` HIPRTC compile/7-symbol을 검증했다. 후속 live resource context는 별도 구현됐지만 이 v1 substrate 자체에는 L2/L∞ producer·device-scalar recurrence·MGS/DGKS·Givens·backsolve·solution update·live solver receipt·native 수치 parity가 없다
- [HIP FGMRES recurrence allocation/control plan v2](engine-v2-hip-fgmres-initial-recurrence-v2.md): exact v1 plan semantic replay에 `u8[256]` control state를 하나만 추가해 7 borrowed/10 owned extent를 고정했다. Restart-1/column-0 scale-prefix 종료 `E=26+14S,Q=14S`에서 epoch을 증가시키지 않는 predecessor validator schedule `sha256:b083896de86a808b1398d0fde4abe73726cb91f50399651274ef82dc09a5ef58`과, 이어지는 `CHECKPOINT_DECIDE`→non-advancing `PREFLIGHT_COMMIT_SOURCE`→`COMMIT_CHECKPOINT`→`CHECKPOINT_FINALIZE` schedule `sha256:2423da989b6cd419b7c4bef46d6c76f2120825a0c840cb516803bb2643ca11e5`를 canonical payload·strict schema에 결박했다. 전역 `R*M` schedule, terminal padding과 final guard semantic payload `sha256:425ea7f4cd30e67a255b1da7490011bd4ecda8537444011e7b7fa005bb477ad4`를 recurrence interface에 포함한 current combined kernel ABI는 `sha256:4078f8f07b3bf605baae04ded1795f8a49038c636910b1c40916b42d3fe8c017`, fixed HIP source는 `sha256:2ecbbe21f8f95686117e2a12cf8cf0984f7e51b11fa331e7d5c81e15f8ed7967`이다. v0.2.22 combined/source `sha256:bb5b94457fbf3be4c5f2b38dda3f50c8a757094e0b97fb4d7288e7bdbf4db39f`/`sha256:a1d2da3f0d9a6c4a574fb1cb9d5be24c30c1e6e5e1c6de3ff1a4b50eeefad113`와 v0.2.21 source는 historical로 유지한다. Plan/kernel과 conditional suffix owner가 구현됐지만 authoritative terminal outcome·solution claim은 없다
- [HIPRTC FGMRES initial + first-column checkpoint recurrence v2](engine-v2-hip-fgmres-initial-recurrence-v2.md): valid-predecessor raw numerical 경로에서 unit floor 없는 `x_scale_l2=trial_x_l2+committed_x_l2`를 만들고, inclusive dual gate→invariant→strict divergence→stagnation→iteration limit 우선순위로 결정한다. Source-only preflight가 commit source를 먼저 전역 검사하고 COMMIT은 pure copy만 수행하며 finalizer가 record/header/terminal state를 단일 발행한다. Device validator는 actual decision admission·mask domain·reduction epoch을 검사해 snapshot을 `armed`로 발행하고 DECIDE가 `consumed`, 정상 preflight가 `commit-preflighted`로 전환하며 정상 FINALIZE가 snapshot-first/state-last 순서로 지운다. Raw actual `gfx1030` 13-case/race `5/5`와 v0.2.22 sealed valid/late-invalid 2 case에서 scoped contract를 확인했지만 product receipt의 actual mask/verdict/commit host observation이나 authoritative numerical transaction을 만들지는 않는다
- [HIP FGMRES caller-attested checkpoint transaction context v2](engine-v2-hip-fgmres-checkpoint-context-v2.md): exact 11-role f64/u8 extent·alignment·uintptr와 local/process-global shifted range registry, allocation generation rollback/high-water, loader-minted read-only HIP runtime, private dlsym/fresh fixed `CFUNCTYPE`, actual `hipGetDevice`, compiler-issued module/function/callable witness, atomic raw lease, single-use nonconstructible predecessor, same-stream DECIDE→PREFLIGHT→COMMIT→FINALIZE enqueue·partial/ambiguous poison, exact-runtime fence·atomic pending consume와 unload/registry retry cleanup을 구현했다. v0.2.16 historical context `246`, raw RTC `60`, HIP context 결합 `258 passed`는 그대로 보존한다. 후속 resource context에 live Krylov parent·allocator lifetime이 생겼지만 이 caller-attested transaction과 결합되지 않았고 장치 content/mask를 관찰하지 않으므로 authoritative transaction 또는 solver receipt가 아니다
- [HIP FGMRES full recurrence ABI v2 design](engine-v2-hip-fgmres-recurrence-abi-v2.md): 공개 solve record와 분리된 256-byte transient control state, shifted pointer 없는 V/Z/H base+logical-index layout, mode-driven control/vector/indexed-SpMV/deterministic dot·LASSQ·L∞ reduction 4-symbol module과 `R*M` active-masked fixed schedule를 고정했다. Later column/restart kernel rows, terminal padding, final guard, gap-free sealed-prefix/continuation compiler와 conditional suffix owner까지 구현됐고 raw actual `gfx1030`은 3-restart exhaustion·early terminal padding·valid/malformed final guard를 검증했다. Integrated actual owner chain은 active later column과 restart `1->2->3`의 active later restart, fixed guard submission, suffix allocation/copy/intermediate-sync 0과 one-fence completion을 확인했다. 그러나 product receipt는 validator/commit/terminal outcome을 host에 노출하지 않고, integrated active final-guard fallthrough, completion export, model-family full parity와 iteration host-copy-zero는 unavailable이다. Host-control `O(L)` 구조 gate는 kernel/solver `O(N)`이나 speedup 증거가 아니다
- [HIP AOT canonical-CSR residual/JVP replay v1](engine-v2-hip-residual-jvp-v1.md): 단일 AOT source와 versioned descriptor C ABI, 동일 ROCm-root toolchain/hash/target artifact 계약, plan·committed-state 상주 context, fused `Ku-F`/`Kv`, exact attempt/success telemetry, test-double/native 증거 분리와 좁은 CPU CSR oracle
- [격리 HIPRTC canonical-CSR residual/JVP v1](engine-v2-rtc-backend-residual-jvp-v1.md): package-owned fixed source, exact native runtime/kernel gate, plan·committed-state 결박, 8개 child allocation·5개 초기 H2D, 단일 fused `Ku-F`/`Kv`, RX 6900 XT `gfx1030` full/free/constrained FP64 parity·repeat/zero-direction·fallback 0·cleanup 0 관찰; unsigned v1은 항상 non-promoting
- [HIPRTC fixed-degree-3 kernel scaling gate v1](engine-v2-rtc-kernel-scaling-v1.md): RX 6900 XT `gfx1030`에 사전 고정한 off-cache 5개/4x family를 same-stream HIP event로 측정해 OLS slope `1.0089`/R² `0.99999`, Theil-Sen `1.0090`, bootstrap 95% CI `[1.0084, 1.0098]`, full-vector FP64 정합성·timed transfer/allocation·fallback 0을 관찰; 저장 receipt는 unsigned/non-promoting이며 fixed synthetic fused kernel 밖의 솔버·end-to-end O(N)·speedup을 증명하지 않음
- [Fixed-rank projection v1](engine-v2-fixed-rank-projection-v1.md): plan-bound Jacobi square-root-energy scaling, rank `<=16`, deterministic 2-pass MGS, dense projector 없는 `Q(Q^T v)`, 정확한 `O(Nk)`/`O(Nk^2)` 연산 영수증
- [AI proposal·physics gate·QR memory v1](engine-v2-ai-proposal-gate-qr-v1.md): immutable `DQy` initial-guess overlay, full CPU `Ku-F`/`||DR_f||₂`/potential-energy/BC/stateless-linear-constitutive replay, exact rollback, AI-off/observed authoritative receipt-chain bit parity, validated-ready-run-only rank `<=16` FIFO QR memory
- [6DOF CPU reference linear static v1](cpu-reference-linear-static-v1.md): frame four-mode 및 truss analytic, dense-sparse/JVP, buffer 무결성 검증
- [MGT → ModelIR v2 Phase 0 adapter](mgt-modelir-v2-phase0-adapter.md): lossless lexer, MGT 9.3.0 strict linear-frame subset, SI 정규화, source mapping/audit, semantic reverse projection
- MGT → ModelIR → `SolverModelBuffers` → CPU reference axial/bending walking skeleton
- blocking unsupported와 analysis-ready 분리
- v0.2.18 광범위 Phase 0 Engine v2 회귀 `1427 passed`, ModelIR/MIDAS v2 `83 passed`, 레거시 핵심 `29 passed`; 실패·오류·skip·fallback 없음. FreeSpace/Krylov allocation-lineage·context·RTC·lease 집중 회귀 `350 passed`, 독립 적대적 감사 `171 passed`, 실제 RX 6900 XT `gfx1030` FreeSpace/Krylov hardware gate 재실행 `2 passed`, capability matrix `7 passed`, Draft 2020-12 schema `40/40 valid`
- v0.2.19 focused 회귀는 allocation-lineage/control `220 passed`, FGMRES solver-child lease `45 passed`, live checkpoint context `42 passed`, FreeSpace/Krylov/FGMRES RTC ownership `169 passed`, common RTC compile-owner `23 passed`를 통과했다. 독립 재감사는 reserve 경쟁, 모든 mutation/borrow 우회, publication rollback/STORE 중단, semantic-last 동시 split/final/recover를 재현하고 `BLOCKER/HIGH/MEDIUM/LOW = 0/0/0/0`, hang/deadlock 0으로 판정했다. 광범위 Engine v2 `1608 passed`, ModelIR/MIDAS v2 `83 passed`, 기존 core/MGT parser `33 passed`, 실제 RX 6900 XT `gfx1030` FreeSpace/Krylov/live resource chain `3 passed`, capability matrix `7 passed`, Draft 2020-12 schema `41/41 valid`도 실패·오류·skip·fallback 없이 통과했다
- v0.2.20 focused 회귀는 recurrence plan/RTC/raw checkpoint context/live resource/projection/canonical producer `61/99/247/42/14/14 passed`, capability matrix `7 passed`, Draft 2020-12 schema `42/42 valid`를 통과했다. 실제 RX 6900 XT `gfx1030`에서 raw validator→transaction `arm→consume→clear` 5 case와 assembly→resident→FreeSpace→Krylov→live→canonical producer 1 case를 fallback 없이 재검증했다. 첫 broad 실행은 이전 `reserved_zero_fields`를 참조하던 stale native test 1건을 발견했고, 현재 ABI의 `transient_zero_fields`로 수정·단일 native 재검증한 뒤 전체 Engine v2 `1650 passed in 1420.51s`를 실패·오류·skip 없이 통과했다. Selected source/test/schema aggregate SHA-256은 `110ab18c3d6e5cbd4ec1d21750cd9e9aca064bc1b6ef401ee46856d97d58d534`/`edbd15e1757800fa9173b7380f34b9e8216de6e4c3da11b6d2644f877c66b9d9`/`515ad55eabdbb810dad52e66747c6f5ba31eeaca01ca712bf7543be297020969`이다. `802664`-byte wheel(`sha256:a58afc56f4d5bd37d18758718b85dd67e4859caa36b8c3e0bd01729794e47dd6`)을 격리 target에 설치해 public canonical API, packaged schema와 current ABI marker를 포함한 HIP kernel resource import를 확인했다
- v0.2.21 atomicity focused 회귀는 recurrence plan/schema `63 passed`, RTC owner/source `100 passed`, checkpoint context 신규·인접 `77 passed`, actual RX 6900 XT `gfx1030` recurrence `13 passed`, repeated race stress `5/5`, capability matrix `7 passed`와 Draft 2020-12 schema `42/42 valid`를 통과했다. 별도 full checkpoint context 전수 회귀는 `261 passed in 523.33s (0:08:43)`를 통과했다. Source preflight destination access 0, late invalid source에서 `solution_x`/`true_residual` 전체 raw byte sentinel 불변, valid legacy/sealed `0→3→0`/`2→3→0`, gate-false source/destination no-read를 확인했다. 감사 중 diagnostic overwrite race, state-code ABI binding, same-kind row/pointer TOCTOU와 u8 role alignment를 수정했고 최종 High/Medium 결함은 없었다. Ruff format/check, py_compile, canonical hashes와 actual HIP source hash assertion도 통과했다. 이 수치는 scoped raw fixed-four-row contract evidence이며 canonical sealed-capability 소비, authoritative predecessor/transaction/solver, later recurrence, iteration host-copy-zero, full parity, O(N), speedup 또는 commercial readiness를 승격하지 않는다
- v0.2.22 sealed transaction focused 회귀는 적대적 unit `23 passed`, 인접 live+canonical legacy `56 passed`를 통과했고 Engine v2 + MIDAS v2 + ModelIR v2 광범위 회귀는 `1778 passed in 2682.66s (0:44:42)`를 통과했다. Consume-return interruption reconciliation, closed current-binding claim release, fixed identity semantic replay와 context-bound provenance relabel rejection을 포함한다. Actual RX 6900 XT `gfx1030` valid canonical-to-sealed `1 passed in 41.30s`와 `F=513` late-nonfinite multi-block sealed `1 passed in 432.80s`에서 conditional capability single-use consume, direct11/physical16 continuity, fixed four-row pending consume, transaction fence 1/canonical 포함 total fence 2, 추가 allocation/borrow/module/H2D/D2H/intermediate sync/fallback 0을 확인했다. Invalid case는 predecessor state `{2,3}`, pending status/code 6/47, mask/reduction snapshot provenance, future action gate clear와 두 destination full-byte 불변을 verification-only D2H로 대조했다. `826616`-byte wheel(`sha256:9c0eaaa4e27f2cbb9b2ac827a91b1f3785c8ca01c3e494077d01aae763420ffb`) 격리 설치에서 public API/schema/kernel resource import를 확인했다. Historical v0.2.22 validator/checkpoint/combined/source hash는 `sha256:b083896de86a808b1398d0fde4abe73726cb91f50399651274ef82dc09a5ef58`/`sha256:2423da989b6cd419b7c4bef46d6c76f2120825a0c840cb516803bb2643ca11e5`/`sha256:bb5b94457fbf3be4c5f2b38dda3f50c8a757094e0b97fb4d7288e7bdbf4db39f`/`sha256:a1d2da3f0d9a6c4a574fb1cb9d5be24c30c1e6e5e1c6de3ff1a4b50eeefad113`다. Product receipt는 actual outcome을 관찰하지 않으므로 authoritative numerical transaction과 solver claim은 false다
- v0.2.23 global recurrence는 immutable 전역 plan·segment와 later columns/restarts/final guard kernel을 current global-contract/combined/source `sha256:425ea7f4cd30e67a255b1da7490011bd4ecda8537444011e7b7fa005bb477ad4`/`sha256:4078f8f07b3bf605baae04ded1795f8a49038c636910b1c40916b42d3fe8c017`/`sha256:2ecbbe21f8f95686117e2a12cf8cf0984f7e51b11fa331e7d5c81e15f8ed7967`에 결박했다. Raw actual `gfx1030`은 `F=513,M=2,I=5`의 298-row 3-restart exhaustion과 early-terminal padding, active valid/malformed final guard를 별도 CPU/GPU oracle로 검증했다. Actual integrated live→canonical→sealed→global owner gate는 3-node serial cantilever `F=12,nnz=144,M=2,I=2`, full/prefix/suffix `84/45/39`에서 `1 passed in 167.47s`를 통과했다. Active later column이 terminal `E/Q=79/26`에서 CPU solution/residual과 verification-only exact parity를 만들었고 global product path allocation/H2D/D2H/intermediate sync/fallback/live read/host branch 0, global fence 1과 exact pending consume 39를 관찰했다. Product receipt는 verification 전에 고정되어 outcome/status/parity/solution false를 유지한다. `R=1`이라 active later restart는 실행하지 않았고 terminal 뒤 final guard는 inactive였으므로 active final-guard fallthrough도 integrated 증거가 아니다. Standalone receipt validation은 structural/semantic consistency만 증명하며 provenance에는 `expected_context` 또는 signed chain이 필요하다
- v0.2.24 host-control/lifecycle checkpoint는 flat exact-type RTC witness, 네 launch path의 atomic expected pending count, per-row frozen row/resource/child check와 suffix 전/후 direct deep binding check 2회를 적용했다. Deterministic `L=1/35`에서 direct deep 2, identity `to_dict` 0, pending `0..L-1`을 확인했고 RTC `103 passed`, owner `11 passed in 268.76s`, sealed/global lifecycle `6 passed in 123.64s`와 lifecycle audit additional defect 0을 기록했다. `F=12,nnz=144,M=2,I=2` required `gfx1030` case는 `1 passed in 38.29s`로 직전 `165.02s` 대비 약 `4.31x` 짧은 host-control test wall-clock을 보였고, `F=24,nnz=360,M=2,I=5,R=3` active-restart case는 `1 passed, 1 deselected in 59.39s`로 full/prefix/suffix `228/45/183`, restart `1->2->3`, CPU count `5/3`·`9/5`, terminal `E/Q=179/58`과 solution/residual allclose를 확인했다. 수정 후 combined hardware는 `2 passed in 96.11s`다. `FINAL_GUARD E/Q=215/70`은 terminal 후 inactive이므로 active guard는 raw-only다. Transient TOCTOU HIGH는 registry-sealed immutable dispatch snapshot/canonical row tuple로 수정했고 final re-audit focused `4 passed in 120.65s`, immutable `1 passed in 26.74s`, aggregate deep-validator enqueue/fence `3/4`, Ruff/format/py_compile PASS와 요청 범위 remaining defect 0을 확인했다. Dead unconsumed idle lease만 lazy reap하고 consumed/pending owner 유실은 parent close를 fail-closed한다. C++/HIP/public schema/ABI는 불변이며 current hashes는 v0.2.23과 동일하다. 이 증거는 fixed suffix host-control `O(L)` 구조 gate일 뿐 kernel/solver speedup, 일반 `N`-DOF O(N) 또는 commercial readiness를 승격하지 않는다
- v0.2.25 lifecycle recovery는 exact `hipStreamQuery` lease binding과 parent-owned weak-liveness cleanup authority를 추가해 v0.2.24의 consumed/pending owner-loss limitation을 process-local 범위에서 닫았다. Callback은 HIP을 호출하지 않고, parent close는 COMPLETE 또는 NOT_READY→single-sync→COMPLETE를 exact bool로 확인한 뒤 pending pop과 terminal release를 수행한다. Stale pending, partial close, frozen authority drift와 interruption은 fail-closed/monotonic retry로 고정했고 independent audit `0/0/0/0`을 통과했다. RTC full `111 passed in 34.77s`, checkpoint context v2 full `261 passed in 248.58s`, focused `33 passed`다. Actual `gfx1030` F12/M2/I2 lifecycle run은 pending `39 -> 0`, query `(False, True)`, sync 1, product malloc/H2D/D2H/runtime sync 0, `1 passed, 2 deselected in 37.42s`다. C++/HIP/public schema·semantic hashes는 그대로이며 completion/numerical/product outcome, O(N), speed/commercial claim은 여전히 false다
- v0.2.25 package checkpoint는 wheel `875235` bytes/`sha256:e6522f810af2a4a0f6d62c770f510bcab57278e64cec4e0070b8fbec2eb2b8e2`, sdist `823734` bytes/`sha256:8094a8bcaf30d3aaf954d5c5f0183baaf03881ff96ae62b33b6832276b2b3d3c`를 구성했다. Wheel 격리 설치에서 global public API, schedule/sealed-continuation API, Draft 2020-12 global schema와 fixed HIP source resource import를 확인했으며 이는 package completeness일 뿐 release promotion은 아니다
- v0.2.25 최종 전수 회귀는 global owner `54 passed in 1387.12s`, sealed transaction `30 passed in 507.23s`를 추가로 통과했다. Sealed suite에는 recovery cell 등록 없이 consume하는 direct/private 경로가 HIP/query/sync/pending 변경 없이 fail-closed하고 unused reservation은 재사용 가능한 계약 검증이 포함된다
- TOCTOU 수정 후 두 required `gfx1030` integrated hardware case는 combined `2 passed in 96.11s`로 재통과했다

- v0.2.21 전체 Engine v2 게시 전 회귀는 동일 소스 스냅샷에서 `1670 passed in 1496.65s (0:24:56)`를 실패 없이 통과했다

아직 미완료:

- v1 `CanonicalModel` -> v2 explicit migration report와 MGT 지원 grammar 확장
- shell CPU reference와 frame offset/release 확장
- 현재 워크스테이션의 matching ROCm device-library 확보와 native AOT artifact build/run
- HIPRTC 단일 `gfx1030` fixture 너머의 model-family·multi-architecture parity와 signed promotion evidence v2
- sparse v2의 StateIR/ResultIR receipt-chain 및 HIP operator ABI 연결, descriptor-only streaming manifest와 실제 peak RSS 측정
- sparse v2가 임시 의존하는 v1 private frame/truss formula를 versioned shared element source로 분리하고 장세장/ill-conditioned 모델 scaling·refinement 강화
- HIP 요소·재료 장치 조립→resident residual/JVP의 fresh native frame/truss launch·수치 parity와 signed/attested evidence
- [FGMRES recurrence ABI v2](engine-v2-hip-fgmres-recurrence-abi-v2.md)의 다음 순서: active final-guard fallthrough integrated native coverage → completion-only export와 명시적 terminal-outcome observation contract → model-family CPU/HIP full parity·iteration host-copy-zero; 이후 certificate-bound SPD-gated PCG 상태기계. Consumed/pending owner-loss recovery는 v0.2.25의 process-local lifecycle 계약으로 닫혔지만 completion 또는 numerical receipt를 승격하지 않는다. Verification-only D2H를 product receipt observation으로 재분류하지 않고 conditional program continuity와 authoritative numerical transaction receipt를 계속 분리한다
- iteration host-copy 0 convergence 정책, reaction/recovery/energy 및 ResultIR 연결
- E(3) feature와 attention-free temporal runtime
- calibrated OOD/UQ와 proposal을 실제 소비하는 iterative solver warm-start
- solver-approved QR memory 위 local RLS/Kalman/readout parameter update
- sparse-only model compilation, device solver 및 실제 FE family를 포함하는 end-to-end complexity harness

따라서 Phase 0 전체 또는 G1/G9/AI gap closure로 승격하지 않는다.

### Phase 1: 90-180일, Developer Preview

- linear frame/shell, spring, MPC, diaphragm, release, offset
- load pattern/combination, P-Delta, modal, buckling, response spectrum 첫 제품 경로
- device-resident Krylov와 첫 AMG/DD hierarchy
- MGT round-trip, 기본 IFC/OpenSees adapter
- E(3)+temporal runtime shadow mode
- 단면/철근 후보 full solver verification

종료 기준은 실제 모델 10개 이상의 CPU/HIP/cross-solver 비교, iteration당 host copy 0, target large-model family의 HIP speedup/parity, AI on/off의 동일 authoritative tolerance, AI failure/OOD의 안전한 fallback이다.

권장 인원: 14-18명.

### Phase 2: 180-365일, 제한형 상용 v1

- corotational frame, fiber/hinge, steel plasticity, 기본 RC 비선형
- shell membrane/bending와 선택 material nonlinearity
- nonlinear static, linear/nonlinear time history
- trust region/arc-length, checkpoint/restart
- KDS rule pack와 서명 가능한 계산서
- solver-gated AI warm start, preconditioner, design optimizer
- Windows/Linux packaging과 workstation hardware tiers

종료 기준은 지원 범위 100개 이상의 versioned V&V, 외부 검토와 실제 고객 shadow project, AI-off 전체 workflow, 최적화 full reanalysis, machine-checkable known limitations다.

권장 인원: 18-24명.

### Phase 3: 365-730일, 범용성 확대

- solid/contact, advanced shell, soil/SSI
- staged construction, creep/shrinkage/prestress
- advanced device, collapse/PBD, moving load
- multilevel DD/AMG와 선택적 multi-GPU
- 300-500개 V&V와 독립기관 검토
- AI topology 탐색과 생산 도면 round-trip
- MIDAS/ETABS/OpenSees 교차검증 corpus 확대

권장 인원: 22-30명. 12명 미만이면 일정을 최소 1.5-2배로 재산정한다.

## 13. 첫 90일 실행 백로그

| 기간 | 작업 | 완료 기준 |
| --- | --- | --- |
| Week 1-2 | ADR 7종, capability matrix, legacy dependency map, golden corpus | 아키텍처/claim/rollback 리뷰 승인 |
| Week 3-4 | ModelIR/StateIR/ResultIR, MGT subset adapter | unit/frame/ID/offset/release round-trip, silent loss 0 |
| Week 5-6 | frame/shell CPU reference operator | patch/rigid-body/energy/tangent/golden parity |
| Week 7-8 | HIP resident context와 runtime dispatch | persistent allocation, residual/JVP, residency telemetry |
| Week 9-10 | device Krylov와 complexity harness | 5-size cold/warm RAM/VRAM/transfer report |
| Week 11-12 | E(3), temporal state, fixed-rank QR/RLS | equivariance, projection, replay, rollback/OOD test |
| Week 13 | 수직 슬라이스 통합 go/no-go | MGT -> IR -> CPU/HIP -> AI proposal -> ResultIR |

통과하지 못한 항목은 gap ledger에 partial 또는 counter-evidence로 유지한다.

## 14. 정량 검증 게이트

아래 값은 초기 목표이며 element family와 해석종류별 tolerance profile로 세분화한다.

| Gate | 초기 통과 기준 |
| --- | --- |
| ModelIR round-trip | 지원 entity 의미 손실 0, unsupported silent-ignore 0 |
| CPU element/operator | patch/rigid-body/energy/reaction golden suite PASS |
| CPU-HIP linear parity | FP64 상대오차 `<= 1e-8` 또는 더 엄격한 family tolerance |
| JVP parity | analytic/finite-difference 상대오차 `<= 1e-6` |
| Nonlinear closure | full load factor `1.0`, scaled residual/increment tolerance 충족 |
| HIP residency | iteration당 state/residual host copy 0, CPU fallback 0 |
| HIP speed | 명시된 large-model family에서 optimized CPU 대비 목표 `>= 5x`; 작은 모델 별도 보고 |
| Complexity | 5개 이상 크기군에서 time/memory slope `0.85-1.15` |
| Multilevel quality | mesh 증가 시 Krylov iteration 증가 `<= 20%` 목표 |
| E(3) equivariance | random rotation/translation/reflection 최대오차 `<= 1e-5` |
| No-backprop | runtime update 중 backward/autograd graph 사용 0 |
| Projection | `||Q^TQ-I||`, rank, condition, 재직교화, BC 오차 기록 |
| AI acceptance | full residual/energy/BC replay 전 promotion 0 |
| Rollback | rejected proposal 후 accepted state byte/checksum 재현 |
| Checkpoint | save -> fresh process load -> 동일 결과 tolerance 통과 |
| Commercial v1 V&V | 지원 범위 100개 이상 versioned case와 외부 검토 |

필수 machine-readable 산출물:

- `model_ir_roundtrip_report.json`
- `cpu_hip_operator_parity_report.json`
- `hip_residency_report.json`
- `equivariance_report.json`
- `real_fe_holdout_report.json`
- `no_backprop_audit.json`
- `projection_quality_report.json`
- `engine_v2_complexity_report.json`
- `hip_residual_replay_report.json`
- `checkpoint_roundtrip_report.json`
- `design_delta_verification_report.json`

## 15. AI 검증 규칙

- E(3)은 random rotation, translation, reflection에서 scalar invariant와 vector equivariant 오차를 각각 검증한다.
- T-GNN은 synthetic simulator 외 authoritative FE holdout을 사용한다.
- teacher-forced, free rollout, long-horizon rollout을 별도 보고한다.
- physics prior weight `0`, 선택값, `1` ablation을 수행한다.
- checkpoint에 normalization, LayerNorm, feature schema, version을 포함하고 fresh-process round-trip을 검증한다.
- AI correction 전후 같은 CSR, DOF ordering, state에서 residual을 replay한다.
- local update 시간과 메모리를 fixed rank별로 기록하고 rank 증가 효과는 sensitivity로 분리한다.
- backprop baseline과 no-backprop lane의 정확도, 시간, 메모리, 안정성을 비교한다.
- residual이 낮아져도 BC, energy, constitutive 또는 increment가 실패하면 폐기한다.
- failure injection으로 fallback이 원본 solve를 정상 종료하는지 검증한다.

## 16. V&V 및 상용화

V&V는 다음 계층으로 관리한다.

1. element: closed-form, patch, rigid-body, energy
2. operator: residual/tangent/JVP consistency
3. algorithm: Newton/Krylov/eigen/dynamics convergence
4. backend: CPU/HIP parity와 deterministic mode
5. cross-solver: MIDAS/ETABS/OpenSees 허용 범위 비교
6. real-project: 지원 범위 실제 모델 shadow run
7. independent review: 외부 구조전문가와 수치해석 검토
8. regression: versioned input/output/checksum과 tolerance profile

상용 승격 순서:

```text
research prototype
  -> non-promoting shadow mode
  -> CPU reference parity
  -> HIP parity and residency
  -> cross-solver V&V
  -> independent review
  -> limited supported-scope commercial release
  -> breadth expansion
```

성능, AI 정확도 또는 UI 완성도만으로 해석 capability를 승격하지 않는다.

## 17. 위험과 대응

| 위험 | 대응 |
| --- | --- |
| big-bang rewrite로 수치 의미론 상실 | strangler migration, golden parity, 단계별 rollback |
| no-backprop 정확도 부족 | backprop 연구 baseline과 비교, AI optional 유지 |
| AMG/DD iteration 증가 | hierarchy/operator complexity gate, family별 coarse-space 설계 |
| 작은 모델에서 GPU 역효과 | size-aware backend selection과 명시적 telemetry |
| 16GB VRAM 한계 | SoA/BSR, mixed precision, bounded batch/rank, memory gate |
| host fallback 은닉 | fallback=0 promotion gate와 transfer instrumentation |
| E(3) 표현 오류 | polar/axial 채널 분리와 equivariance suite |
| AI proposal이 state 오염 | immutable state, trial arena, atomic accept/rollback |
| proprietary interop 위험 | 공개/허용 API와 교환형식, provenance와 license review |
| 기능 폭 과다 | capability matrix와 supported-scope release |
| 외부 V&V 부족 | 초기부터 benchmark/customer/independent-review budget 확보 |

## 18. 팀 가정

12개월 제한형 상용 v1 권장 구성:

- computational mechanics/FE: 6-7명
- GPU/HPC/ROCm: 3-4명
- geometric ML/AI: 3-4명
- interoperability/CAD/BIM: 2-3명
- 구조기술 및 V&V: 4-5명
- UI/product/QA/release: 3-4명

일부 역할은 겸임할 수 있으나 FE, HIP, V&V는 독립 리뷰가 가능해야 한다. 단일 개발자 또는 소수 인력에서는 기능 폭을 줄이고 Phase 0 walking skeleton과 제한형 frame/shell 제품에 집중한다.

## 19. 상용 v1 Definition of Done

- AI-off 상태에서 지원 ModelIR과 해석종류 완전 동작
- CPU FP64 reference와 HIP parity
- full-load nonlinear residual/increment/energy/BC closure
- 지원 element/material/analysis capability matrix 공개
- unsupported 입력 fail-closed
- 지원 범위 100개 이상의 versioned V&V
- 실제 프로젝트, 교차솔버 비교, 독립 검토
- AI proposal/replay/rollback 계약 준수
- no-backprop audit와 E(3) equivariance gate 통과
- 실제 end-to-end complexity/hardware benchmark
- 모든 최적화 결과 full authoritative reanalysis 통과
- 계산서, ResultIR, audit receipt, 도면 diff provenance 연결
- Windows/Linux package, crash recovery, checkpoint/restart, support bundle
- 허용 claim, known limitations, 책임 경계의 문서/UI 일치

## 20. 변경 기록

| 버전 | 날짜 | 변경 |
| --- | --- | --- |
| 0.2.25 | 2026-07-14 | Checkpoint lease에 exact loaded-runtime `hipStreamQuery`를 immutable witness/snapshot으로 봉인하고 `0=COMPLETE`, `600=NOT_READY`, 그 밖의 status·예외·non-bool 결과를 fail-closed한다. Sealed parent는 child/lease strong reference가 없는 weak-liveness recovery cell로 abandonment만 기록하며 callback은 HIP을 호출하지 않는다. Close는 exact query → 필요할 때 successful sync 1회 → query → pending pop → terminal release를 수행하고 interruption을 monotonic retry하며 stale pending, partial close, exact-bool 위반, frozen authority drift를 fail-closed한다. Independent audit은 `BLOCKER/HIGH/MEDIUM/LOW 0/0/0/0`, focused 검증은 `33 passed`, RTC full은 `111 passed in 34.77s`, checkpoint context v2 full은 `261 passed in 248.58s`다. Actual RX 6900 XT `gfx1030` F12/M2/I2 abandoned suffix는 pending `39 -> 0`, query `(False, True)`, sync 1, product malloc/H2D/D2H/runtime sync 0, `1 passed, 2 deselected in 37.42s`를 확인했다. C++/HIP/public schema/ABI와 semantic hashes는 불변이다. 이 결과는 process-local lifecycle closure일 뿐 completion, numerical parity/result, O(N), speedup 또는 commercial readiness를 승격하지 않는다. |
| 0.2.24 | 2026-07-14 | Global recurrence host-control/lifecycle를 harden했다. Flat exact-type RTC witness, 네 launch path의 atomic expected pending gate, per-row immutable dispatch snapshot/canonical row tuple와 suffix 전/후 direct deep check 2회로 fixed-row-work host submission의 제한된 `O(L)` 구조 gate를 구현했다. `L=1/35`에서 direct deep 2, identity `to_dict` 0, pending `0..L-1`을 확인했고 RTC `103 passed`, owner `11 passed in 268.76s`, lifecycle `6 passed in 123.64s`를 통과했다. `F=12,nnz=144,M=2,I=2`는 `38.29s`(직전 `165.02s`대비 약 `4.31x` 짧은 host-control test wall-clock), `F=24,nnz=360,M=2,I=5,R=3`는 `1 passed, 1 deselected in 59.39s`로 restart `1->2->3`, terminal `E/Q=179/58`과 CPU allclose를 확인했고 수정 후 combined hardware는 `2 passed in 96.11s`다. `FINAL_GUARD E/Q=215/70`은 terminal 후 inactive이므로 active guard는 raw-only/unproven이다. Transient live row/pointer TOCTOU HIGH는 registry-sealed immutable snapshot/tuple로 수정했다. Final independent audit은 row/pointer/two-thread, bool-int alias, value-equal launch tuple, forged registry slot, `float.hex()` signed-zero seal을 검증했고 aggregate deep-validator enqueue/fence `3/4`, focused `4 passed in 120.65s`, immutable `1 passed in 26.74s`, Ruff/format/py_compile PASS 후 요청 범위 remaining defect 0으로 종료했다. Dead unconsumed idle lease만 lazy reap하고 consumed/pending cleanup owner 유실은 parent close를 fail-closed한다. C++/HIP/public schema/ABI는 불변이며 global/combined/source hash는 `sha256:425ea7f4cd30e67a255b1da7490011bd4ecda8537444011e7b7fa005bb477ad4`/`sha256:4078f8f07b3bf605baae04ded1795f8a49038c636910b1c40916b42d3fe8c017`/`sha256:2ecbbe21f8f95686117e2a12cf8cf0984f7e51b11fa331e7d5c81e15f8ed7967`를 유지한다. 이 closure는 요청된 host-control audit에 한정되며 kernel/solver speedup, 일반 `N`-DOF O(N), terminal outcome 관찰 또는 commercial readiness를 승격하지 않는다 |
| 0.2.23 | 2026-07-14 | [HIP FGMRES sealed-continuation global recurrence owner v1](engine-v2-hip-fgmres-global-recurrence-v1.md)을 추가했다. Immutable `initial + R*M columns + FINAL_GUARD` program, exact epoch/counter formulas, row `0..j` 양 pass MGS, terminal byte/epoch-preserving padding과 final guard를 global semantic payload `sha256:425ea7f4cd30e67a255b1da7490011bd4ecda8537444011e7b7fa005bb477ad4`에 고정하고 combined recurrence ABI/source를 `sha256:4078f8f07b3bf605baae04ded1795f8a49038c636910b1c40916b42d3fe8c017`/`sha256:2ecbbe21f8f95686117e2a12cf8cf0984f7e51b11fa331e7d5c81e15f8ed7967`로 갱신했다. Global compiler는 full/sealed-prefix/continuation을 gap·overlap 없이 분할하고 owner는 conditional continuation capability를 single-use consume해 suffix만 exact direct11/physical16·kernel/runtime/device/stream/checkpoint authority에 제출한다. Suffix의 allocation/borrow/module/H2D/D2H/intermediate sync/fallback/live read/host branch는 0이고 global final fence는 1회다. Raw actual `gfx1030`은 `F=513,M=2,I=5` 3-restart exhaustion, early-terminal padding과 valid/malformed final guard를 CPU/GPU oracle과 비교했다. Actual integrated owner gate는 3-node serial cantilever `F=12,nnz=144,M=2,I=2`, full/prefix/suffix `84/45/39`에서 `1 passed in 167.47s`로 active later column, exact pending consume 39, terminal `E/Q=79/26`와 verification-only CPU solution/residual exact parity를 확인했다. Product receipt는 verification 전에 고정돼 terminal observation/parity/solution false를 유지한다. 이 integrated case는 active later restart와 active final-guard fallthrough을 실행하지 않았다. Standalone receipt validation은 structural/semantic consistency만 증명하고 provenance에는 `expected_context` 또는 signed chain이 필요하다. Historical v0.2.22 hashes/evidence는 그대로 보존한다. Full parity, iteration host-copy-zero, O(N), speedup, signed promotion과 commercial readiness는 false다 |
| 0.2.22 | 2026-07-13 | [HIP FGMRES canonical-capability-consuming sealed checkpoint transaction v1](engine-v2-hip-fgmres-sealed-checkpoint-transaction-v1.md)을 추가했다. Still-open canonical context의 single non-owning child가 conditional predecessor capability를 reserve 후 enqueue 시작에서 single-use consume하고, exact live kernel/checkpoint token/stream/direct11과 physical16 projection, fixed four-row `DECIDE→PREFLIGHT→COMMIT→FINALIZE` tuple을 고정한다. Transaction-owned final fence는 1회이며 upstream canonical prefix를 포함한 chain은 total fence 2회다. 추가 allocation/device bytes/borrow/checkpoint owner/module/H2D/D2H/intermediate sync/fallback은 0이다. Open/enqueue race, unused-close/reopen와 consumed-terminal, consume-return interruption reconciliation, pre-row binding/pending-map drift, partial·ambiguous poison, fence/ack before·after-pop retry, callback reentrancy, closed current-binding claim release, fixed identity forgery와 context-bound provenance relabel rejection, nonconstructible capability를 적대적 unit `23 passed`, 인접 live+canonical `56 passed`로 확인했다. Standalone receipt는 semantic consistency만 검증하며 provenance authenticity에는 `expected_context` 또는 서명이 필요하다. Actual RX 6900 XT `gfx1030` valid/late-invalid scoped cases `2 passed`에서 direct11/physical16 continuity, capability consume, four pending consume와 destination full-byte 보존을 verification-only D2H로 대조했다. Invalid preflight는 scheduling에 따라 predecessor state `2|3`을 허용하고 mask/reduction snapshot을 provenance로 보존한다. Pending terminal status/code는 6/47이며 `commit_required=continuation_required=0`은 future action gate clear일 뿐 과거 no-commit/rollback 단독 증거가 아니다. Validator/checkpoint/combined/source는 `sha256:b083896de86a808b1398d0fde4abe73726cb91f50399651274ef82dc09a5ef58`/`sha256:2423da989b6cd419b7c4bef46d6c76f2120825a0c840cb516803bb2643ca11e5`/`sha256:bb5b94457fbf3be4c5f2b38dda3f50c8a757094e0b97fb4d7288e7bdbf4db39f`/`sha256:a1d2da3f0d9a6c4a574fb1cb9d5be24c30c1e6e5e1c6de3ff1a4b50eeefad113`다. Source만 terminal-failure semantics로 바뀌고 combined ABI/checkpoint schedule은 v0.2.21과 동일하며 과거 source hash는 historical로 보존한다. Product receipt는 actual mask/verdict/commit/device outcome을 관찰하지 않아 conditional continuation만 발행하고 authoritative predecessor/numerical transaction/solver/solution, later recurrence, iteration host-copy-zero, O(N), speedup, signed promotion과 commercial readiness는 false다. 다음 순서는 later column/restart global control과 final guard다 |
| 0.2.21 | 2026-07-12 | [HIP FGMRES checkpoint invalid-source atomicity v1](engine-v2-hip-fgmres-checkpoint-atomicity-v1.md)을 추가했다. 기존 multi-block COMMIT의 lane-local finite-check/write 결합을 source-only non-advancing `PREFLIGHT_COMMIT_SOURCE=9`와 pure-copy COMMIT으로 분리하고 state 3을 정상 preflight ticket으로 고정했다. Fixed schedule은 `CHECKPOINT_DECIDE(E0→E0+1)`→`PREFLIGHT(E0+1, non-advancing)`→`COMMIT(E0+1→E0+2)`→`FINALIZE(E0+2→E0+3)`이며 성공 종료 `E/Q=29+14S/14S`는 유지한다. 정상 legacy `0→3→0`, sealed `2→3→0`, snapshot-preserving preflight와 finalizer snapshot-first/state-last clear를 구현했다. Invalid source는 error bit 4/origin 2/code 47/active 0으로 종료하며 scheduling에 따라 state 2 또는 3과 snapshot을 보존한다. COMMIT은 state 3·active 1·error 0·exact snapshot admission 뒤 pure copy만 수행한다. Plan/RTC/context-focused/native `63/100/77/13 passed`, full context `261 passed in 523.33s (0:08:43)`, actual `gfx1030` race stress `5/5`, capability `7 passed`와 schema `42/42 valid`에서 source preflight destination access 0, late invalid lane의 `solution_x`/`true_residual` 전체 bytes 불변, gate-false no-read를 검증했다. 감사 중 diagnostic overwrite race, state-code ABI binding, same-kind row/pointer TOCTOU와 u8 role alignment를 수정했고 최종 High/Medium 결함은 없었다. Ruff format/check, py_compile, canonical hashes와 actual HIP source hash assertion도 통과했다. Historical v0.2.21 validator/schedule/combined/source는 `sha256:b083896de86a808b1398d0fde4abe73726cb91f50399651274ef82dc09a5ef58`/`sha256:2423da989b6cd419b7c4bef46d6c76f2120825a0c840cb516803bb2643ca11e5`/`sha256:bb5b94457fbf3be4c5f2b38dda3f50c8a757094e0b97fb4d7288e7bdbf4db39f`/`sha256:ce4353f61fc3e8cd1311ad52ce50f21a677c7bfa865a2656aa5447b6ec104a83`다. 새 F-sized workspace·product H2D/D2H/intermediate sync/fallback은 없다. True atomicity 범위는 exact registered nonoverlap allocation, same stream, exclusive source ownership과 fixed four-row owner sequence뿐이며 arbitrary raw duplicate/external writer/device fault는 제외한다. v0.2.20 canonical identity와 검증은 historical로 유지하며 canonical conditional capability 소비, authoritative predecessor/transaction/solver, later columns/restarts, full parity, host-copy-zero, O(N), speedup, signed promotion과 commercial readiness는 false다 |
| 0.2.20 | 2026-07-12 | [HIP FGMRES canonical predecessor v1](engine-v2-hip-fgmres-canonical-predecessor-v1.md)을 추가했다. Live exact11과 Krylov-delegated CSR3/reduction2를 추가 allocation 없는 exact16 physical projection으로 결속하고, owned8을 sealed `hipMemsetAsync` 8회로 초기화한 뒤 `INIT`부터 non-advancing `PREDECESSOR_VALIDATE=14`까지 exact `27+14S` kernel row를 같은 stream에 제출해 final fence 1회와 pending consume로 닫았다. Control offset 116/120/124에 validator state/mask/reduction snapshot을 고정하고 `empty→armed→consumed→clear`를 후속 checkpoint seal로 강제했다. Validator/current combined ABI/source hash는 `sha256:b083896de86a808b1398d0fde4abe73726cb91f50399651274ef82dc09a5ef58`/`sha256:d719aebffadafa0c076bb4ff395df35e7b4bd888bdb613b8be9ff7ef0f20335d`/`sha256:cdb8917b8553ceceed047b0c9b3e091afe9d80bccfece8242a778b5d56e00b18`이다. Single-use child, token-specific pending 관찰, first-memset exact rejection, partial/ambiguous accepted interval, projection drift, fence/consume before·after-pop retry, stale capability와 receipt schedule/telemetry 변조를 fail-closed로 검증했다. Focused plan/RTC/raw/live/projection/canonical `61/99/247/42/14/14`, actual `gfx1030` raw/canonical `5+1`, capability `7`, schema `42/42`, 광범위 Engine v2 `1650 passed in 1420.51s`를 실패·오류·skip·fallback 없이 통과했고 Ruff/format/py_compile·문서 링크/whitespace를 통과했다. Selected source/test/schema aggregate는 `sha256:110ab18c3d6e5cbd4ec1d21750cd9e9aca064bc1b6ef401ee46856d97d58d534`/`sha256:edbd15e1757800fa9173b7380f34b9e8216de6e4c3da11b6d2644f877c66b9d9`/`sha256:515ad55eabdbb810dad52e66747c6f5ba31eeaca01ca712bf7543be297020969`, wheel은 `802664` bytes/`sha256:a58afc56f4d5bd37d18758718b85dd67e4859caa36b8c3e0bd01729794e47dd6`이다. Product receipt는 actual mask/verdict를 D2H하지 않으므로 conditional capability만 발행하며 authoritative predecessor/transaction, invalid-source destination atomicity, later recurrence, solver/solution, iteration host-copy-zero, O(N), speedup, signed promotion과 상용 준비는 false다. 다음 순서는 multi-block commit source preflight를 통한 destination all-or-nothing이다 |
| 0.2.19 | 2026-07-12 | [HIP FGMRES live checkpoint resource context v1](engine-v2-hip-fgmres-live-checkpoint-context-v1.md)을 추가해 actual Krylov parent의 `reduced_state`·`reduced_load`·`jacobi_inverse`와 fresh peer owner의 solver-owned8을 exact11 group lease로 결속했다. Owner-control은 exact token, canonical role/ordered allowlist, fresh generation/activity, successful publication exactly 8과 controlled-borrow admission을 registry lock에서 강제하고 publication rollback/return-STORE 중단에도 count와 cleanup authority를 보존한다. Internal FGMRES RTC v2 module/checkpoint token, same runtime/device/stream, module→group→owned8→owner→semantic-last cleanup과 failed-open/BaseException 회수를 구현했다. v0.2.18 이후 더 강한 감사에서 발견한 common RTC cleanup-entry 및 FreeSpace/Krylov/FGMRES same-empty handoff 경쟁은 전용 handoff lock과 `empty -> reserved -> published|spent`, persistent program/module owner, terminal-owner-last 순서로 별도 수정했다. 독립 재감사는 reserve-vs-allocate/close 각 `50/50`, 동시 split/final-recover 각 `20/20`, 모든 mutation/borrow·publication-history 우회를 재현하고 `BLOCKER/HIGH/MEDIUM/LOW = 0/0/0/0`, hang/deadlock 0으로 판정했다. Lineage `220`, solver lease `45`, live context `42`, RTC `169+23`, 광범위 Engine v2 `1608`, ModelIR/MIDAS v2 `83`, 기존 core/MGT parser `33`, 실제 `gfx1030` FreeSpace/Krylov/live hardware `3`, capability `7`, schema `41/41 valid`를 실패·오류·skip·fallback 없이 통과했고 Ruff check/selected-files format check/py_compile도 통과했다. Selected source/test/schema aggregate SHA-256은 `bdcc44df6945b318564a743d8c995a33d3db9c553d43478ccb6679546364ea75`/`31341abdbe1292a051fad5ece61e7b325aa991a3b23369ad4c2ea9b45e0d1e31`/`77da3e976974d5cc77ea2ae54fbe0f45efd88f7d997fb35c8cacb959260052a2`다. 780803-byte wheel(`sha256:93e6235fe1b963a3d476e4861d94231ba33d691340b59d09649e87c53cde3d71`)을 격리 target에 설치해 public live/owner-control API, live schema와 FGMRES v2 HIP kernel resource import를 확인했다. 이 단계는 resource-only/non-promoting이며 owned content, authoritative predecessor/mask validator, checkpoint transaction, solver/solution, iteration host-copy-zero, O(N), speedup, signed promotion과 상용 준비는 false다. 다음 순서는 canonical device producer와 mask-domain validator다 |
| 0.2.18 | 2026-07-12 | [HIP FreeSpace/Krylov allocation-lineage integration v1](engine-v2-hip-free-space-krylov-allocation-lineage-v1.md)을 추가해 FreeSpace 12개와 Krylov 9개 owned 실제 `malloc/free`, parent 5-capability all-or-none exclusive borrow를 owner-minted lineage에 연결했다. Context receipt v2는 managed count/byte, allocation/deallocation·current/peak, H2D/D2H/kernel/sync, owner/module/lease lifecycle, mint/free/orphan/quarantine/unknown byte와 failed-open stage prefix를 결박한다. Exact known-not-freed만 같은 lease로 재시도하고 native·분류 불능 outcome은 quarantine하며, persistent free/module-unload disposition으로 성공 또는 불확실한 native operation을 반복하지 않는다. Owner/capability/orphan/token handoff와 `copy_context().run` 기반 one-shot weak RTC handoff, native load 전 preallocated module cleanup owner, `load_module_into(code_object, box)`와 exact-kernel promotion을 구현해 call/return/`STORE`·load/bind/construct/cleanup 진입 중단에도 double-free/double-unload 없이 소유권을 수렴시킨다. 당시 독립 감사의 최종 판정은 `BLOCKER/HIGH/MEDIUM 0`이었다. 후속 v0.2.19의 더 강한 same-empty/cleanup-entry 동시성 감사에서 추가 RTC handoff 경쟁을 발견해 별도 수정·재검증했으며, 이를 v0.2.18 증거에 소급해 숨기지 않는다. 집중 `350 passed`, 감사 `171 passed`, Engine v2 광범위 `1427 passed`, ModelIR/MIDAS v2 `83 passed`, 레거시 핵심 `29 passed`, 실제 `gfx1030` hardware `2 passed`, capability `7 passed`, schema `40/40 valid`, skip/fallback 0, Ruff/format/py_compile을 통과했다. Source/test/schema `sha256:aaad406e726cac86a456b06ab7fa9bd214dcdb975eb50c2447b3355ddab28c4e`/`sha256:22c1bcf3f9f8893bd6ae92ac83632ccb1ba76b4ad6e620932a66f240e9ff0fd7`/`sha256:f83bd07ebad9bd1f616d36da2cac05629a82ece238bfdaaf2504336286a73179`, 745523-byte wheel(`sha256:1b50a1a2fe80716c7f064edf5348e25bf7b36280b92a6b1d2e2735ac4bc0c484`)과 격리 설치 public API/context-v2 schema/HIP kernel resource import를 확인했다. 이는 unsigned process-local lifetime 통합 증거이며 FGMRES live parent/predecessor, actual device content/mask, invalid-source 원자성, later columns/restarts, full parity, iteration host-copy-zero, PCG/AMG/DD, O(N), speedup, signed promotion과 상용 증거는 미완료다 |
| 0.2.17 | 2026-07-12 | 기존 raw pointer 경계를 대체할 [owner-minted HIP allocation lineage foundation v1](engine-v2-hip-allocation-lineage-v1.md)을 추가했다. Arbitrary pointer 등록/adoption 없이 malloc 전에 orphan cleanup authority를 예약하고, 성공한 exact base에만 nonconstructible process-local capability를 발급한다. f64/i32/u8 extent·alignment·uintptr overflow, domain/device shifted overlap와 quarantine tombstone, bounded domain/device generation, multi-owner atomic exclusive borrow, immutable free/orphan pointer target, success/quarantine terminal handshake를 구현했다. Mutable `ctypes` drift, device drift, concurrent publication rollback, terminal marker 직후 BaseException, owner/capability/borrow/free caller handoff, poison sweep 중단과 per-device poison marker allocation failure를 fail-closed로 수렴시키며 resolved registry는 weak tombstone, range는 병합 compaction한다. 독립 적대적 감사에서 최종 source 기준 남은 BLOCKER/HIGH가 없음을 확인했다. Lineage `160 passed`, 감사 집중 `16 passed`, checkpoint/HIP-context/lineage 인접 `418 passed`, free-space/Krylov 인접 `62 passed`, 전체 FGMRES 수집 `538 passed`, 광범위 `1428 passed`, capability `7 passed`, 기존 core/MGT parser 조합 `33 passed`, skip/fallback 0, Ruff/format/py_compile을 통과했다. Source/test `sha256:2ffe5e27aec23ba5edfd244f89e9a7a63e21030fd0b28b05b1bfbd2c65a6788a`/`sha256:7551d6dc8200cdd2e9c9007f79e7aa9823b8995d054aadbe3f3af1c41fd6cc81`, 715263-byte wheel(`sha256:c53ebca3fb8717fa724e9758310f9c022d6333d44585153f5e80ae4abc459632`)과 격리 설치 public API/kernel resource import를 확인했다. 이 단계는 host registry foundation이며 free-space 12개·Krylov 9개 owned/5개 borrowed 실제 malloc/free, FGMRES live parent/predecessor, authoritative allocator/fence/solver receipt, device content/mask 관찰, invalid-source 원자성, later columns/restarts, full parity, iteration host-copy-zero, PCG/AMG/DD, O(N), speedup, signed promotion과 상용 증거는 미완료다 |
| 0.2.16 | 2026-07-11 | Valid-predecessor column-0 checkpoint에 caller-attested/non-promoting transaction context를 추가했다. 11개 f64/u8 allocation의 exact extent·alignment·uintptr overflow와 모든 local/process-global shifted range overlap, process/device native pointer domain, generation high-water/rollback, immutable launch pointer snapshot을 검증한다. Loader-minted `LoadedHipRuntime`의 read-only identity·weak provenance witness와 private dlsym/fresh fixed `CFUNCTYPE`로 public ctypes `argtypes/restype/errcheck`·cached symbol의 pre/post-bind·concurrent/reentrant 변조가 module load/get-function/device query/launch/sync/unload에 영향을 주지 못하게 했다. Actual `hipGetDevice`, compiler-minted module/function/callable witness, atomic raw lease+binding snapshot, single-use nonconstructible predecessor/transaction capability, DECIDE→COMMIT→FINALIZE one-lock enqueue, rejected/ambiguous accepted interval과 poison, exact-runtime fence·atomic pending consume, acknowledgement/unload/registry cleanup retry를 구현했다. 독립 감사에서 정상 API 기준 신규 BLOCKER/HIGH 없음으로 확인했다. Context `246 passed`, plan `58 passed`, RTC `60 passed`, oracle `95 passed`, HIP context 결합 `258 passed`, 실제 `gfx1030` raw hardware `12 passed`, 전체 FGMRES `538 passed`, 광범위 `1268 passed`, capability `7 passed`, skip/fallback 0, Ruff/JSON/py_compile, source native/context/RTC/checkpoint `sha256:35dad9d9a303d71ffef975e99247dc1ca08f1bfa7a871bf67746a75f3225a59e`/`sha256:de916fe1a41a7aedec49fe1170fe8153fa75babc4d644ac0c27a974dd03f554e`/`sha256:d6e312fba83d60c87dedc10aa5b8c0525cb1715b4beb5980df9b0f9dc40e7f59`/`sha256:52d95b7a57a9c851c52fa8012047e2399e84e8da65cb686346f1ab2694cc2f23`, 699314-byte wheel(`sha256:3a75dd97faac20c1ac0c4ab2cc093689fdc23a9ca8e6c365c551a9df0f867b72`)과 격리 설치 public API/schema/kernel resource import를 확인했다. Predecessor는 actual device content/mask를 관찰하지 않은 caller attestation이므로 authoritative predecessor/transaction, live Krylov parent, allocator provenance, invalid-source multi-block all-or-nothing, later columns/restarts, explicit HIP context/multi-GPU, full parity, iteration host-copy-zero, SPD/PCG, AMG/DD, ResultIR, O(N), speedup, signed promotion과 상용 증거는 미완료다. Runtime file hash→dlopen은 trusted filesystem/selected-DSO 전제이며 sealed binding은 현재 CPython/Linux ROCm 범위다 |
| 0.2.15 | 2026-07-11 | Candidate-scale-metrics 종료 `E=26+14S,Q=14S`에서 `CHECKPOINT_DECIDE`·`COMMIT_CHECKPOINT`·`CHECKPOINT_FINALIZE` 3-launch를 거쳐 `E=29+14S,Q=14S`로 끝나는 first-column checkpoint transaction schedule `sha256:d9b9115287e3b5839096e3f4417c04899ffc7592864483d918be55deaf4b4442`를 추가하고 combined kernel ABI를 `sha256:31fbff2fa25c221a99f28e170818990a8ed71211169d239e05d28628941941c9`로 갱신했다. Valid-predecessor raw numerical slice는 unit floor 없는 `x_scale_l2=trial_x_l2+committed_x_l2`, inclusive dual gate→invariant→strict divergence→stagnation→iteration limit 우선순위, conditional solution/residual commit, finalizer-only record/header/terminal-state 발행을 구현한다. DECIDE/COMMIT은 mask 0/1792/7936과 active를 보존하고 FINALIZE만 clear하며, gate-false는 source no-read를 유지한다. `x_scale` overflow는 status 6/code 47/error 8로 fail-closed하되 solution/residual과 algorithmic metrics/restart row를 보존하고 terminal failure status/code/device-error header만 기록한다. 감사 중 발견한 COMMIT target-scalar 재접근을 제거했고 failure contract를 결과/행 미발행과 terminal header 발행으로 분리했다. Plan `58 passed`, RTC `57 passed`, 독립 oracle `95 passed`, native 포함 통합 집중 `222 passed`, 실제 RX 6900 XT `gfx1030` hardware `12 passed`, 전체 FGMRES `289 passed`, 광범위 `1019 passed`, capability `7 passed`, 실제 HIPRTC compile, Ruff/JSON/schema, source `sha256:34049a08119b19382c26fbe310f957d7af9c41db037dfcbab521828732025e9b`, 680879-byte wheel(`sha256:322c4e8171784322384cabf64cd76eb131278dbd820ac156eb49a23857ea3287`)과 격리 설치 public API/schema/kernel resource import를 확인했다. 이 증거는 `contract_only`인 valid-predecessor raw numerical slice에 한정된다. Typed allocation/extent와 shifted·overlap range 검증, 3-launch atomic enqueue·부분실패 poison, single-use predecessor receipt, exclusive live lease를 갖춘 authoritative RTC transaction owner, invalid-source multi-block all-or-nothing, duplicate-launch policy·later columns/restarts·multi-GPU·iteration host-copy-zero·full parity·SPD/PCG·AMG/DD·ResultIR·O(N)·speedup·상용 증거는 미완료 |
| 0.2.14 | 2026-07-11 | Candidate-residual 종료 `E=26+12S,Q=12S`에서 항상 제출되는 trial `LASSQ_WORK_W`와 committed `LASSQ_SOLUTION_X` 두 tree를 거쳐 `E=26+14S,Q=14S`로 끝나는 first-column candidate-scale-metrics schedule `sha256:1bc8a32247ad2255cc5953f525f67b1991a62ffb9f6ca6bf299a898c11468ba8`를 추가하고 combined kernel ABI를 `sha256:7253d7497275f139e28ea4410da6411416888de754f733af62725b51640e0407`로 갱신했다. Device-only predicate는 active candidate→planned cycle-end→inclusive dual gate→invariant→strict divergence 순으로 평가하며, 계속 경로에서만 mask 1792를 trial bit 12의 5888, committed bit 11의 7936으로 확장한다. Predicate-false active path는 mask 1792, inactive/triangular path는 mask 0을 유지하고 모든 `2S` epoch을 claim하되 `work_w`/`solution_x`/ping-pong/target numeric을 읽거나 쓰지 않는다. Divergence는 `candidate_l2 > divergence_factor*max(initial_l2,0x1p-1022)`이고 overflow된 `+inf` threshold는 divergence나 arithmetic error로 취급하지 않는다. `COMMITTED_X_L2`는 향후 `CHECKPOINT_DECIDE`가 read-only로 보고 finalizer만 clear하는 lifetime을 보존하며, 아직 `x_scale_l2`·checkpoint·commit은 수행하지 않는다. Flag-independent owner와 독립 GPU-tree oracle, 실제 RX 6900 XT `gfx1030` F=513의 5개 scale 분기를 포함한 native `7 passed`를 대조했고 독립 감사에서 차단 결함을 찾지 않았다. Plan+RTC+oracle `171 passed`, native 포함 집중 `178 passed`, 전체 FGMRES `245 passed`, 광범위 `975 passed`, capability `7 passed`, 실제 HIPRTC compile, Ruff/JSON/schema, source `sha256:53a64ff442e8c6759613b56d140d5b8091ac75740dbd2c0e0f3decaf3a477d15`, 663405-byte wheel(`sha256:d5d8cdf5ab16c90785096ae84201d42820969f1e230adbb1f122698c19895831`)과 격리 설치 public API/schema/kernel resource import를 확인했다. `x_scale_l2`·checkpoint decide/finalize/commit·later columns/restarts·range/extent alias·multi-GPU·live lease/fence receipt context·iteration host-copy-zero·full parity·SPD/PCG·AMG/DD·ResultIR·O(N)·speedup·상용 증거는 미완료 |
| 0.2.13 | 2026-07-11 | Candidate-preparation 종료 `e=23+10S,q=10S`에서 candidate SpMV `work_w->V[M]`, gated `OPERATOR_ACCEPT`, in-place `V[M]=b-A*x_trial`, deterministic candidate L2/raw L∞ tree를 거쳐 `e=26+12S,q=12S`로 끝나는 schedule `sha256:c2c74ad20a4b881ad209a632d021cbf368d8ae042bca5f161e82cb0bae9c4ad3`를 추가하고 combined kernel ABI를 `sha256:1b9040d6ac01019da9ab1f9ed04c297ebac8e0a0fb4136f7c134db5861416c41`로 갱신했다. 유효한 candidate는 update/L2/L∞ bit을 합친 mask 1792와 operator count 3을 보존하고, candidate=false·triangular breakdown은 모든 fixed epoch을 claim하면서 mask 0/operator count 2, `V[M]` NaN poison bit, committed `solution_x`/`true_residual`을 그대로 보존한다. Allocation-base logical `M` owner, in-place residual/target/alias 역검증과 독립 GPU-tree residual oracle를 추가하고 실제 RX 6900 XT `gfx1030` F=513의 candidate 5개 경로를 포함한 native `7 passed`를 대조했다. 독립 감사에서 차단 결함을 찾지 않았고, 광범위 `942 passed`, FGMRES `212 passed`, candidate-residual 집중 `145 passed`, 실제 HIPRTC compile, Ruff check, JSON/schema, source `sha256:b742f00b14c16ce65265974ac9c950d203f0b2441ca07d638f2a53c339e1e7fb`, 656314-byte wheel build와 격리 설치 public API/schema/kernel resource import를 확인했다. Represented FP64 candidate L2 overflow는 CPU early-candidate continue edge와 달리 의도적 GPU terminal fail-closed이며 exact parity를 주장하지 않는다. Trial/committed norm·scaled L∞ gate·checkpoint decide/commit·later columns/restarts·range/extent alias·multi-GPU·live lease/fence receipt context·iteration host-copy-zero·full parity·SPD/PCG·AMG/DD·ResultIR·O(N)·속도·상용 증거는 미완료 |
| 0.2.12 | 2026-07-11 | 기존 first-column partial/completion schedule hash를 변경하지 않고 through-Givens 종료 `e=20+9S,q=9S`에서 `BACKSUBSTITUTE`, gated `BUILD_TRIAL_X`, deterministic `UPDATE_L2`, `VECTOR_ACCEPT`를 거쳐 `e=23+10S,q=10S`로 끝나는 candidate-preparation schedule `sha256:8df0561cf0988539ed8718dc7348a1e2a85c86f474056ca156c8b8c6d5bb1aec`를 추가하고 combined kernel ABI를 `sha256:273791455b794afe35e726ef1e102f4953fbc9f60e4bd5fcbc9c8e11ec8c55f6`으로 갱신했다. Fixed HIP kernel은 unit floor 없는 `tau=2^-46` scale-relative upper backsolve, explicit multiply-then-add trial build, scale-first update L2 tree를 수행하고 유효한 candidate에서만 bit 10/mask 1024를 보존한다. Candidate=false와 triangular breakdown은 고정 epoch을 모두 claim하면서 후속 numeric/scratch/target을 공개하지 않고 mask 0으로 끝나며, triangular breakdown은 invariant를 OR-promote한다. Flag-independent Python owner와 독립 GPU-tree candidate oracle를 추가하고, 실제 RX 6900 XT `gfx1030` F=513의 DGKS true/false candidate=false·exact happy breakdown·triangular breakdown 4개 경로를 포함한 native `6 passed`를 대조했다. 독립 감사에서 차단 결함을 찾지 않았고, 광범위 `910 passed`, FGMRES `180 passed`, candidate 집중 `128 passed`, 실제 HIPRTC compile, Ruff check, JSON/schema, 649033-byte wheel build와 격리 설치 public API/schema/kernel resource import를 확인했다. Candidate SpMV/true residual·checkpoint decide/commit·later columns/restarts·poison-sentinel inactive scratch·ISA no-FMA·range/extent alias·multi-GPU·live lease/fence receipt context·iteration host-copy-zero·full parity·SPD/PCG·AMG/DD·ResultIR·O(N)·속도·상용 증거는 미완료 |
| 0.2.11 | 2026-07-11 | recurrence v2의 기존 first-column partial hash를 변경하지 않고, `e=16+7S,q=7S`에서 `e=20+9S,q=9S`까지 conditional second DOT/DOT_ACCEPT/MGS, `H_NEXT`, `V1` normalization, first signed Givens와 candidate state/counter를 별도 completion schedule `sha256:941f1191e4acd806ae6616c36599949506e87219199908e3aa62ee116ac6dbb4`에 고정하고 combined kernel ABI를 `sha256:67dc4157b21b2541001940b2ab71b9df94215ab0dea184b123c2239d214918c8`로 갱신했다. Fixed 4-symbol HIP kernel은 DGKS=false에서도 host 분기 없이 schedule/reduction epoch를 claim하면서 numeric scratch/vector/target은 접근하지 않고, `tau=2^-46` H-next breakdown의 `V1=+0`, normalization 후 Givens, signed c/s/g/H, candidate bit 0/1/2와 accept counter를 장치에서 처리한다. Flag-independent Python completion owner와 독립 GPU-tree through-Givens oracle를 추가하고, 실제 RX 6900 XT `gfx1030` F=513의 DGKS true/false·exact happy-breakdown 3개 first-column 케이스와 initial·duplicate-epoch 포함 native `5 passed`를 대조했다. 독립 감사에서 차단 결함을 찾지 않았고, 광범위 `891 passed`, FGMRES `161 passed`, HIPRTC compile·Ruff·JSON/schema, wheel build와 격리 설치 API/schema/kernel resource import를 확인했다. Candidate true-residual envelope·backsolve·trial/update/commit·later columns/restarts·range/extent alias·live lease/fence receipt context·iteration host-copy-zero·full parity·SPD/PCG·AMG/DD·ResultIR·O(N)·속도·상용 증거는 미완료 |
| 0.2.10 | 2026-07-11 | recurrence v2 plan/schema에 `B=7+4S`의 유일한 RESTART_BEGIN부터 restart-1/column-0 first MGS·device DGKS 판정까지 exact schedule hash, reduction mask, packed `y[0]`/`H[0,0]`/`g[0]`과 accept counter를 추가했다. Fixed 4-symbol HIPRTC에 V0 정규화, positive Jacobi, indexed Arnoldi SpMV, deterministic work LASSQ·signed dot, DOT_ACCEPT/y transient, first MGS와 strict `after_first < 0.717*work_before` 분기를 구현하고 raw owner/kernel의 exact output-active-source/control/record alias를 거부했다. 실제 RX 6900 XT `gfx1030` F=513에서 signed-negative-dot/DGKS=true와 orthogonal-dominant/DGKS=false의 V/Z/work/H/y/state/count를 독립 GPU-tree oracle과 대조했다. Focused `858 passed`, FGMRES subset `141 passed`, HIPRTC compile/source marker·Ruff·JSON/schema와 wheel build·격리 설치 API/schema/kernel resource import를 확인했지만 DGKS second pass/H_NEXT/Givens/backsolve/candidate/commit·live lease/fence receipt context·iteration host-copy-zero·full parity·SPD/PCG·AMG/DD·ResultIR·O(N)·속도·상용 증거는 미완료 |
| 0.2.9 | 2026-07-11 | exact v1 plan에 256-byte control을 하나만 추가한 7-borrowed/10-owned recurrence v2 plan·strict schema와 v2 solve-record producer, hashed initial schedule·NONE/final target·mode 호환성을 구현했다. Fixed 4-symbol HIPRTC의 `x0`/RHS/`A*x0`/`b-Ax0`/L2·L∞/dual-gate·`I=0`, 독립 GPU-tree oracle, single-pending-stream, block-uniform reduction admission을 추가했다. 독립 감사에서 발견한 cross-stream race, barrier divergence, epoch signed-overflow를 수정하고 실제 RX 6900 XT `gfx1030` F=513 initial 수치 parity·fallback 0과 duplicate epoch no-hang fail-closed를 검증했다. Focused `834 passed`, FGMRES subset `117 passed`, wheel build·isolated API/schema/kernel resource import를 확인했지만 full Arnoldi/DGKS/Givens/backsolve/candidate/commit·live lease/fence receipt context·iteration host-copy-zero·full parity·SPD/PCG·AMG/DD·ResultIR·O(N)·속도·상용 증거는 미완료 |
| 0.2.8 | 2026-07-11 | FGMRES child snapshot에 exact free-space plan/view, loaded runtime, architecture를 추가하고 identity/exact-type drift를 shared poison하며 cleanup token은 보존했다. V1 fixed source의 전체 solve-record/status/reason/hint/flag/error/control 정수 상수와 7개 C symbol const/mutable argument signature를 canonical ABI와 compile 전 전수 대조하고, CPU oracle의 restart-boundary `restart_completed`+`converged_restart_true_residual` 의미를 device writer와 일치시켰다. 256-byte transient control, base-index V/Z/H, mode-driven 4-symbol·`R*M` fixed schedule의 [full recurrence ABI v2 design](engine-v2-hip-fgmres-recurrence-abi-v2.md)을 `planned/unavailable`로 고정하고 focused `784 passed`, FGMRES subset `67 passed`를 검증했지만 v2 kernel/context·iteration host-copy-zero·native 수치 parity·SPD/PCG·AMG/DD·ResultIR·O(N)·속도·상용 증거는 미완료 |
| 0.2.7 | 2026-07-11 | exact latest apply·pointer/runtime/stream을 결박하는 exclusive primitive FGMRES solver-child lease와 fixed-source HIPRTC 7-symbol recurrence substrate를 추가했다. Shared solve-record/layout-code-flag ABI와 device-error/control-mode/launch ABI를 source interface marker에 결박하고, `M` 저장·append-only restart·step/reorth/gate/hint·actual max-iteration 소진을 device에서 fail-closed하며 nonfinite/overflow/Jacobi 오류를 분리했다. Pending-stream lifetime, retry cleanup, 실제 `gfx1030` HIPRTC compile/7-symbol과 focused `775 passed`, FGMRES subset `58 passed`를 검증했지만 reduction producer·MGS/DGKS·Givens·backsolve·solution update·live context·solver receipt·native 수치 parity·iteration host-copy-zero·SPD/PCG·AMG/DD·ResultIR·O(N)·속도·상용 증거는 계속 미완료 |
| 0.2.6 | 2026-07-11 | actual `b-Ax0`, fixed-restart right-Jacobi FGMRES, DGKS/Givens, scale-relative breakdown, dual true-residual gate와 mandatory deterministic replay를 갖춘 독립 CPU oracle을 추가하고, exact source/policy/finite Jacobi inverse, 7 borrowed/9 owned extent, little-endian solve-record field/code/flag 및 live-lineage 요구를 결박한 HIP compile-time plan을 추가했다. Focused `757 passed`와 신규 FGMRES subset `41 passed`를 기록했지만 HIPRTC recurrence·allocation·iteration host-copy-zero·native parity·SPD/PCG·AMG/DD·ResultIR·O(N)·속도·상용 증거는 계속 미완료 |
| 0.2.5 | 2026-07-11 | same-stream positive unshifted Jacobi, fixed affine/Jacobi, deterministic dot과 scale-first LASSQ를 제공하는 free-space grandchild primitive context, raw-batch zero-transfer/allocation/sync/fallback receipt, exact latest-apply/lease 원자성, live witness·execution ID·CPU parity, parity-failure shared poison, pending-stream RTC unload/ack-retry 수명주기, strict schema-only nested/status 경계, 다단 reduction stage 계약 및 조건부 native gate를 추가하고 focused `708 passed, 7 skipped`/legacy `33 passed`를 기록; recurrence·CG/FGMRES/PCG·SPD·integrated preconditioner·iteration host-copy-zero·O(N)·속도·상용 증거는 계속 미완료 |
| 0.2.4 | 2026-07-11 | symbolic-only free-space overlay, same-stream `K_ff` 물질화, exact-zero prescribed preflight, device `F_f-K_ffu_f` producer와 single-use resident generation, full residual/JVP→reduced gather, cross-residual parity, authority/partial-stage receipt·retry cleanup 및 조건부 native hardware gate를 추가하고 focused `655 passed, 6 skipped`/legacy `33 passed`를 기록; reduction·preconditioner·Krylov loop·host-copy-zero·O(N)·속도·상용 증거는 계속 미완료 |
| 0.2.3 | 2026-07-11 | resident consumer의 caller-kernel pre-lease 회수 가능성, concurrent receipt snapshot, status별 exact ownership/backend, operation↔byte 및 verification stage-prefix, descriptor·partition·parity aggregate·nested live-context 불변식을 보강하고 focused `596 passed, 5 skipped`/legacy `33 passed`를 기록; native combined hardware·Krylov·속도·상용 증거는 계속 미완료 |
| 0.2.2 | 2026-07-11 | assembly-owned CSR와 foundation load를 재할당·재업로드 없이 같은 runtime/device/stream에서 소비하는 exclusive resident lease, state/direction/residual/JVP 4-vector context, zero-transfer enqueue, verification parity, atomic lifetime·poison·retry cleanup 및 nested receipt를 추가하고 native combined hardware·device direction producer·free-space Krylov·iteration host-copy 0·O(N)·속도·상용 미증명 경계를 분리 |
| 0.2.1 | 2026-07-11 | frame/truss 요소 기여도와 deterministic CSR gather를 수행하는 HIPRTC 장치 조립 계약, symbolic-only H2D, resident CSR operator view, exact telemetry·cleanup·receipt replay 및 `gfx1030` compile/symbol 증거를 추가하고, fresh native launch/parity·resident consumer·Krylov·O(N)·속도·상용 미증명 경계를 분리 |
| 0.2.0 | 2026-07-11 | global dense K 없는 sparse-only ExecutionPlan v2와 deterministic CPU direct-CSR 조립/해법을 추가하고, source partition 재도출·alias/ndarray/descriptor 공격·fully-rehashed result·singular-ready 위조를 차단했으며 retained-array slope와 solve/peak-memory/HIP/상용 미증명 경계를 분리 |
| 0.1.9 | 2026-07-11 | 하네스·스키마·커널·라이브러리 hash에 결박된 RX 6900 XT/gfx1030 off-cache 5-size HIP-event gate에서 fixed degree-3 fused CSR kernel-only near-linear slope를 관찰하고 raw unsigned receipt를 보존했으며, 솔버/end-to-end O(N)·speedup·상용 승격 금지 경계를 고정 |
| 0.1.8 | 2026-07-10 | 격리 HIPRTC fixed-source kernel과 plan/state-bound CSR context를 추가하고, 실제 `gfx1030` fused residual/JVP full/free/constrained parity·exact telemetry·no-fallback·cleanup을 검증했으며 unsigned v1 non-promotion과 solver/O(N)/speedup 미증명 경계를 고정 |
| 0.1.7 | 2026-07-10 | canonical-CSR AOT source/ABI/artifact 계약, plan·committed-state 상주 context, fused `Ku-F`/`Kv`, strict telemetry·cleanup·no-fallback 및 test-double/native 증거 분리를 추가하고 현재 native toolchain/device unavailable 경계를 기록 |
| 0.1.6 | 2026-07-10 | square-root-energy `DQy` proposal, full CPU physics/linear-constitutive replay, OOD fail-closed exact rollback, non-consuming authoritative shadow parity와 solver-approved bounded QR memory 기록 |
| 0.1.5 | 2026-07-10 | native HIP probe와 buffer-only DeviceExecutionContext, exact transfer telemetry, plan-bound fixed-rank implicit projection 및 bounded complexity receipt 기록 |
| 0.1.4 | 2026-07-10 | ExecutionPlan v1 canonical DOF/CSR/7-stage graph, immutable StateIR lifecycle, full-invariant ResultIR, precompiled CPU receipt-chain runner 기록 |
| 0.1.3 | 2026-07-10 | MGT 9.3.0 strict linear-frame subset의 lossless lexer, SI ModelIR adapter, schema-validated audit, semantic reverse projection, buffer/CPU walking skeleton 기록 |
| 0.1.2 | 2026-07-10 | SolverModelBuffers v1 ABI와 narrow 6DOF Euler-Bernoulli CPU reference operator, analytic/dense-sparse/JVP 검증 기록 |
| 0.1.1 | 2026-07-10 | Phase 0 ADR, capability matrix, ModelIR v2 strict contract/validator/golden fixture 진행상태 기록 |
| 0.1.0 | 2026-07-10 | 최초 Engine v2 아키텍처, O(N) 경계, no-backprop AI, HIP 및 90/180/365/730일 로드맵 작성 |
