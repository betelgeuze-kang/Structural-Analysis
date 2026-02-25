# 차세대 하이브리드 건축구조 분석 AI 아키텍처 명세서 (ADD)

- 버전: 1.0
- 목표: FEM 연산 병목을 줄이고, GNN + 잔차 보정 학습 + 물리 제약 기반 검증을 통해 상용 구조해석 툴 수준 이상의 속도/정확도/확장성 확보

## 1) 시스템 개요

본 아키텍처는 BIM/CAD 구조 모델을 그래프 기반 표현으로 변환하고,
물리 솔버의 저해상도 해석 결과를 GNN이 비선형 잔차로 보정하는
**Hybrid Physics-AI Solver**를 핵심으로 한다.

핵심 아이디어:

1. 물리 기반 저비용 근사해(`U_LF`)를 먼저 계산
2. GNN이 오차(`ΔU`)만 학습
3. `U_final = U_LF + ΔU`로 고정밀 해 구성
4. 물리 평형 위반 시 국부 FEM 재해석으로 신뢰성 강제

---

## 2) 3단계 코어 파이프라인

### Phase 1. 위상수학적 그래프 추상화 + 파라미터 인코딩

건축 구조를 그래프 `G = (V, E)`로 매핑한다.

- **노드(`V`)**: 조인트, 지점, 하중 작용점
  - 예: 지반 침강량, 외력(X/Y/Z), 경계조건, 질량
- **엣지(`E`)**: 기둥/보/가새/벽체의 연결 부재
  - 예: `f'_c`, 철근 강도, 보강비, 단면2차모멘트 `I`, 길이 `L`, 초기 장력

모든 파라미터는 무차원화/정규화 후 텐서로 인코딩한다.

예시 무차원화:

- `\tilde{E} = E / E_ref`
- `\tilde{σ} = σ / f'_c`
- `\tilde{δ} = δ / L_ref`
- `\tilde{F} = F / (E_ref A_ref)`

### Phase 2. 잔차 보정 학습 엔진 (Residual Correction Learning)

#### 2-1) Low-Fidelity Solver

- 선형 탄성 가정 + 희소행렬 풀이
- 출력: `U_LF` (기초 변위/응력장)

#### 2-2) GNN Non-linear Residual Predictor

입력:

- 그래프 텐서 `X(G)`
- 기초 해석 결과 `U_LF`

출력:

- 비선형 오차 `ΔU`

Graph Attention 기반 예시:

`h_i^{(l+1)} = \sigma\left(\sum_{j \in N(i)} \alpha_{ij}^{(l)} W^{(l)} h_j^{(l)}\right)`

`\alpha_{ij}`는 하중 유형/경계조건/부재 특성에 따라 동적으로 산정한다.

#### 2-3) High-Fidelity Output Synthesis

최종 예측:

`U_final = U_LF + ΔU`

손실함수(예시):

`L = λ_1 ||U_final - U_HF||_2^2 + λ_2 ||R_eq(U_final)||_2^2 + λ_3 L_{reg}`

- `U_HF`: 고정밀 FEM/실험 정답
- `R_eq`: 힘/모멘트 평형 잔차

### Phase 3. 물리 무결성 검증 + 다중 파라미터 최적화

#### 3-1) Hard-Constraint Fallback

`||R_eq(U_final)|| > ε`인 서브그래프만 선별해 국부 고정밀 FEM 재해석.

효과:

- 전체 계산량은 줄이면서,
- 신뢰성은 상용 툴 수준으로 유지

#### 3-2) Multi-parameter Optimization

목표함수(예시):

- 중량 최소화
- 비용 최소화
- 최대 변위/응력 제약 만족

`min_x C(x)` s.t. `g_k(U_final(x)) <= 0`

추천 출력:

- 보강재 추가 위치
- 재료 물성 조정 범위
- 취약 부재 우선순위

---

## 3) Expert Mode 리스크/대응

### CTO 관점 (시스템/인프라)

- 리스크: 대형 그래프의 GPU OOM
- 대응:
  - Cluster-GCN 기반 서브그래프 미니배치
  - 층/모듈 단위 분할 연산
  - 메모리 풀링 + gradient checkpointing
  - ROCm 환경에서 mixed precision(FP16/BF16) 적용

### 수석 구조 엔지니어 관점 (도메인 정확도)

- 리스크: 크리프/건조수축/피로 같은 시계열 현상 반영 부족
- 대응:
  - T-GCN(Temporal GCN) 결합
  - 시간 스텝별 상태 전이 모델 도입
  - 4D(공간+시간) 해석 모드 제공

### AI/수학 연구원 관점 (데이터 무결성)

- 리스크: 입력 스케일 불균형으로 학습 불안정
- 대응:
  - 변수별 표준화 + 무차원화
  - 손실 가중치 자동 조정(uncertainty weighting)
  - SHAP 기반 XAI로 변수 영향도 시각화

---

## 4) 구현 우선순위 제안 (실행 로드맵)

### Step A (2~3주): 데이터/물리 인터페이스 고정

- BIM/CAD → 그래프 변환 규격 확정
- Low-fidelity solver 입출력 스키마 확정
- 기준 단위/무차원화 테이블 설계

### Step B (3~5주): Residual GNN 베이스라인

- `U_final = U_LF + ΔU` 학습 루프 구현
- 정적 하중 케이스 우선 학습
- 평형 제약 포함한 loss 구성

### Step C (2~4주): 신뢰성 강화

- Hard-constraint fallback 구현
- 지역 재해석 파이프라인 연결

### Step D (지속): 확장

- T-GCN 시계열 모듈
- 다중 목적 최적화(NSGA-II/Bayesian optimization)
- XAI 리포트 자동 생성

---

## 5) 다음 단계 권장 (우선 착수 항목)

현재 단계에서는 **AI 로직 프로토타이핑(Residual GNN 스켈레톤)**을 최우선으로 권장한다.

이유:

1. 가장 빠르게 성능 병목 지점을 확인 가능
2. 데이터/물리 엔진 인터페이스를 조기 고정 가능
3. 이후 무차원화/메모리 최적화 이슈를 실측 지표로 튜닝 가능

동시에 병행할 최소 항목:

- 입력 정규화/무차원화 사양서
- 서브그래프 분할 규칙(층/코어/아웃리거 단위)


---

## 6) SOTA를 넘어서는 한 차원 앞의 개선안 (Next-Frontier Upgrades)

아래 항목은 기존 상용 해석기/일반 GNN 하이브리드 대비 **성능 상한을 한 단계 더 끌어올리기 위한 핵심 업그레이드**이다.

### 6-1) Operator Learning 결합 (Graph Neural Operator + Residual)

기존 잔차 GNN 위에 **Neural Operator(FNO/GNO 계열)**를 결합해,
격자/메시 해상도가 바뀌어도 일관된 연산자를 학습한다.

- 기대효과:
  - 모델이 구조 스케일/분할 방식 변화에 덜 민감
  - 신규 프로젝트(다른 층수/경간)로 제로샷 전이 성능 향상

### 6-2) 불확실성 정량화(UQ) + 위험기반 의사결정

출력값을 단일 점추정이 아니라 **분포(평균/분산/신뢰구간)**로 제공한다.

- 방법:
  - Deep Ensemble 또는 Evidential Regression
  - 하중/재료/지반 불확실성을 샘플링하여 확률론적 안전율 계산
- 기대효과:
  - 설계자가 "보수율"을 정량적으로 선택 가능
  - 과소설계/과잉설계 동시 억제

### 6-3) Active Learning 기반 HF 데이터 획득 최적화

고정밀 FEM 라벨은 고비용이므로, **오차가 큰 샘플만 선택적으로 추가 해석**한다.

- 방법:
  - 불확실성 기반 샘플링 + 다양성 제약(k-center)
  - 비용 대비 성능 향상률이 낮아지면 자동 종료
- 기대효과:
  - 동일 예산 대비 학습 속도/최종 정확도 개선

### 6-4) 멀티-스케일 계층 그래프 (부재-층-전체 구조)

단일 그래프가 아닌 계층 그래프를 구성해,
로컬 좌굴/접합부 거동과 전역 횡변위를 동시에 잡는다.

- Level-1: 접합/부재 상세
- Level-2: 층/코어/아웃리거 모듈
- Level-3: 빌딩 전역 동적 응답

### 6-5) PINN형 제약 강화 (강한 물리 제약 학습)

현재 평형 잔차 손실 외에, 에너지 최소 원리/재료 구성방정식 위반 항을 추가한다.

`L_total = L_data + λ_eq L_eq + λ_energy L_energy + λ_constitutive L_const`

- 기대효과:
  - 학습 데이터 외 영역(out-of-distribution)에서 붕괴 방지
  - 물리 위배 예측을 구조적으로 억제

### 6-6) 실시간 디지털 트윈 동기화 (Online Adaptation)

SHM 센서(가속도, 변형률, 처짐) 스트림을 받아 모델을 온라인 보정한다.

- 방법:
  - 배치 재학습 대신 저랭크 어댑터(LoRA류) 또는 칼만필터 기반 상태 업데이트
- 기대효과:
  - 준공 후 노후화/손상 누적까지 반영한 라이프사이클 해석 가능

### 6-7) 생성형 설계 탐색 (Generative Design Loop)

해석 AI를 "평가자"에서 "설계 제안자"로 확장한다.

- 방법:
  - diffusion/진화전략으로 설계안을 생성
  - 제약조건 위반안은 물리 제약 모듈에서 즉시 필터링
- 기대효과:
  - 동일 성능 대비 재료비 절감형 구조안 자동 발굴

### 6-8) 하드웨어 공설계 (HPC + ROCm + Sparse Kernel)

알고리즘/커널/배치를 함께 최적화하는 시스템 공설계를 적용한다.

- 핵심:
  - block-sparse 커널, 그래프 재정렬(reordering), 비동기 파이프라이닝
  - CPU-FEM fallback과 GPU-GNN 동시 실행
- 기대효과:
  - 엔드투엔드 지연시간 추가 단축(실시간에 근접)

---

## 7) 상용 프로그램 대비 승부 포인트 KPI (권장 목표)

- 정확도: 주요 응답(층간변위, 최대응력) 기준 HF FEM 대비 MAPE ≤ 3~5%
- 신뢰성: 물리 제약 위반 케이스 자동 fallback 후 허용오차 내 99% 이상
- 속도: 동일 시나리오 배치 평가에서 상용 해석 워크플로우 대비 10~50x
- 확장성: 노드/엣지 10^5 규모에서 OOM 없는 추론/학습 파이프라인
- 실무성: 설계 대안 탐색(수백~수천안) 1일 이내 완료

위 KPI를 분기별로 추적하고, 미달 지표에 대해 데이터 수집/모델 구조/커널 최적화 중 어디가 병목인지 원인 분해(RCA)하는 운영 체계를 함께 도입한다.

---

## 8) 초격차 달성을 위한 3대 추가 아키텍처 (Expert Mode 심화)

기존 SOTA 하이브리드 모델의 한계(형상 일반화 부족, 시간 의존 오차 누적, 로컬 자원 병목)를 넘기 위해, 아래 3가지를 **코어 필수요건**으로 추가한다.

### 8-1) 알고리즘 도약: E(n)-Equivariant + Bayesian UQ 결합

#### (A) 3D 회전/병진/반사 대응 E(n)-Equivariant GNN

일반 GNN의 좌표계 의존성 문제를 제거하기 위해, 좌표 변환에 대해 동변성을 보장하는 메시지 패싱을 채택한다.

수학적 요구사항(벡터 출력의 동변성):

`f(Rx + t) = R f(x)`

- `R`: 직교변환(회전/반사)
- `t`: 병진

구현 원칙:

- 거리/내적 기반 스칼라 불변량을 기본 피처로 사용
- 방향 벡터는 동변량 채널로 별도 처리
- 구조 응답(힘/변위 벡터)이 좌표계 변화에 일관되게 반응하도록 계층 단에서 제약

#### (B) Bayesian Neural Network 기반 불확실성 정량화(UQ)

점추정 대신 예측 분포를 출력해, "AI가 확신 없는 영역"을 자동 표기한다.

예시 출력:

- 평균: `\mu(\Delta U)`
- 분산: `\sigma^2(\Delta U)`
- 신뢰구간: `CI_{95%}`

의사결정 규칙 예시:

`if σ(ΔU_i) > τ_uq => subgraph_i -> HF FEM fallback`

효과:

- Active Learning 대상 샘플 자동 수집
- 안전율 설계의 정량 근거 확보

### 8-2) 도메인 물리 도약: 4D 시공단계 시계열 잔차 학습

정적 1회 해석 중심에서 벗어나, 시공 단계별 하중 누적/재료 시변 물성을 반영한다.

핵심:

- 시간축 `t`를 포함한 그래프 시퀀스 `G_t`
- 탄성계수 시변 모델 `E(t)` 및 크리프/건조수축 파라미터 결합
- T-GCN 또는 Physics-Informed RNN 기반 상태 전이

상태 업데이트 개념식:

`h_t = Φ(h_{t-1}, G_t, E(t), Load_t)`

`ΔU_t = Ψ(h_t, U_{LF,t})`

`U_{final,t} = U_{LF,t} + ΔU_t`

효과:

- 층별 시공 순서에 따른 응력 재분배 반영
- 장기 거동(크리프/수축/피로) 누적 오차 억제

### 8-3) 시스템 도약: 로컬 워크스테이션 극한 최적화(16GB VRAM 기준)

학계형 클라우드 전제 대신, 실무 로컬 환경에서 OOM 없는 처리를 목표로 한다.

필수 구성:

1. **희소 행렬 네이티브 경로**
   - `K` 행렬/그래프 연산을 sparse 포맷으로 유지
   - ROCm + PyTorch sparse + 커스텀 HIP 커널 최적화
2. **혼합 정밀도 + 체크포인팅**
   - BF16/FP32 혼합
   - gradient checkpointing으로 activation 메모리 절감
3. **계층 풀링 + 슈퍼노드 압축**
   - 코어월/강결합 모듈을 super-node로 축약
   - E(n)-GNN 계산량 증가를 상쇄
4. **비동기 CPU-GPU 파이프라인**
   - CPU: 그래프 샘플링/미니배치 준비
   - GPU: 전/역전파 전담
   - PCIe 병목 최소화를 위한 prefetch + pinned memory

---

## 9) 전문가 리스크 검토 및 실무 대안 (Actionable)

### AI/수학 연구원 관점

- 리스크: E(n)-GNN으로 정확도는 오르나 추론 TPS 저하 가능
- 대안:
  - Hierarchical Graph Pooling + Super-node 압축
  - 중요도 기반 adaptive message passing(핵심 서브그래프만 고해상도)

### 수석 구조 엔지니어 관점

- 리스크: UQ 지표가 인허가 문서/실무 의사결정으로 바로 연결되지 않을 수 있음
- 대안:
  - 3D 모델 UQ Heatmap 자동 시각화
  - 고불확실 구역만 FEM 재검증 스크립트 자동 생성(Python→SAP2000/ANSYS API)

### CTO 관점

- 리스크: 4D 시계열 + 대형 그래프 동시 처리 시 I/O 병목(PCIe, 로더)
- 대안:
  - 비동기 멀티프로세싱 데이터로더
  - 그래프 위상 연산(CPU)과 텐서 연산(GPU) 파이프라인 분리
  - 배치 구성 시 시간축/공간축 locality-aware 스케줄링

---

## 10) 즉시 실행 가능한 우선 설계 트랙 (3개)

아래 3개 중 하나를 선행하면 초격차 구현의 핵심 리스크를 가장 빨리 검증할 수 있다.

1. **E(n)-GNN 수학/구조 설계 트랙**
   - 목표: 좌표계 불변/동변 보장
   - 산출물: 메시지 패싱 수식, PyTorch 모듈 골격, 동변성 단위테스트

2. **4D 시공단계 T-GCN 트랙**
   - 목표: 시간의존 물성 + 하중누적 반영
   - 산출물: `G_t` 데이터 스키마, `E(t)` 파라미터 테이블, 시계열 loss

3. **VRAM 최적화 인프라 트랙**
   - 목표: 16GB VRAM에서 대형 그래프 OOM 방지
   - 산출물: sparse 연산 경로, super-node 풀링 정책, 체크포인팅/AMP 프로파일

권장 착수 순서:

`(1) VRAM 최적화 인프라` → `(2) E(n)-GNN` → `(3) 4D T-GCN`

이 순서를 따르면 실무 환경에서 "돌아가는 시스템"을 먼저 확보한 뒤, 일반화/정확도를 안정적으로 확장할 수 있다.

---

## 11) Rust/HIP 2-Bead(Cα-SC) MD 엔진 기반 Low-Fidelity 코어 개조안

기존 단백질용 2-Bead MD 엔진(Rust + HIP/ROCm)을 구조해석 Low-Fidelity 코어로 재활용하기 위한 매핑 규칙을 정의한다.

### 11-1) 2-Bead 토폴로지의 구조역학 매핑

- `Cα` 비드 → **메인 조인트 노드(Primary Joint)**
  - 구조 접합부의 병진 자유도(X/Y/Z)와 외력 작용점 표현
- `SC` 비드 → **부재 방향/단면 축(Orientation Node)**
  - 로컬 축 벡터: `v_SC = x_SC - x_Cα`
  - H빔 강축/약축 방향, 비틀림 기준축 추적

핵심 효과:

- 오일러각/쿼터니언 기반 상태를 직접 풀지 않고,
- 3D 좌표 기반 거리/각도 포텐셜만으로 회전 거동을 근사해 6DOF 효과를 저비용으로 반영

### 11-2) 기존 H-bond/원자 상호작용의 구조 비선형으로 재해석

기존 O/N/P/S 상호작용 항을 접합부 비선형 및 지반 접촉 모델에 매핑한다.

1. **반강접합/소성 힌지 모델 (O/N 경로)**
   - 임계 변형률(또는 회전각) 이후 접선강성 저하
   - LJ 계열 포텐셜의 기울기를 항복 이후 점진적으로 0에 수렴시키는 구간함수 적용
2. **SSI/면진 패드 모델 (P/S 경로)**
   - 압축 시 반발력 증가, 인장 시 분리(인력≈0)되는 비선형 접촉 법칙 적용
   - 지반 침하/uplift를 비대칭 접촉 조건으로 표현

### 11-3) 커스텀 포스필드 치환식

단백질 포스필드 상수를 구조 물성 기반 상수로 치환한다.

- 축강성(Bond stretching)
  - `V_bond = 1/2 K_b (r-r_0)^2`
  - `K_b <- (E·A)/L_0`
- 휨강성(Angle bending)
  - `V_angle = 1/2 K_θ (θ-θ_0)^2`
  - `K_θ <- (E·I)/L_0`

권장 구현 포인트:

- `θ`는 단순 Cα-Cα-Cα 각보다 `Cα-SC` 기반 로컬축 변화량으로 정의
- 단면 이방성은 축별 `I_y`, `I_z`를 분리해 강축/약축 휨을 구분

### 11-4) Integrator/커널 교체 전략 (정적 평형 지향)

구조해석 Low-Fidelity 경로는 열역학 앙상블보다 **정적 평형 수렴**이 우선이다.

- 기존: Verlet/Leap-frog
- 권장: FIRE(Fast Inertial Relaxation Engine) 또는 Conjugate Gradient 기반 최소화 커널

실행 순서:

1. 외력 벡터(AddForce) 커널 분리 (자중/풍하중/지진 하중)
2. 힘 잔차 `||F_unbalanced||` 기반 수렴 조건 적용
3. 수렴 후 `U_LF`, 부재별 잔류력/에너지 항을 추출

### 11-5) GNN 잔차 보정 파이프라인 연동 규약

Rust/HIP Low-Fidelity 결과를 Phase 2 GNN 입력으로 직접 연결한다.

- 노드 피처: `u_x, u_y, u_z`, `F_unbalanced`, 경계조건 상태
- 엣지 피처: 축력/전단력/모멘트 추정, 국부 강성, 항복지수
- 시계열 확장 시: `t` 스텝별 궤적 텐서 `X_t`

연동 인터페이스 표준 출력(권장):

- `ulf_nodes.parquet` (노드 변위/잔류력)
- `ulf_edges.parquet` (부재력/강성/손상지표)
- `ulf_meta.json` (단위계, 재료맵, 수렴로그)

### 11-6) 리스크 및 대응

- **연산 정확도 리스크**: 과도한 단순화 시 접합부 국부거동 왜곡
  - 대응: 고위험 서브그래프는 기존 HF FEM fallback 강제
- **성능 리스크**: E(n)-GNN + 대형 그래프에서 TPS 저하
  - 대응: super-node 압축 + locality-aware batching
- **실무 리스크**: UQ 결과 해석 난이도
  - 대응: 고불확실 영역 히트맵 + 상용 해석기 재검증 스크립트 자동 생성

### 11-7) 즉시 착수 작업 (Retrofit Backlog)

1. **Integrator 교체**: FIRE 기반 HIP 커널 스켈레톤 작성
2. **포스필드 매퍼**: `E, A, I, L0` → `K_b, K_θ` 변환 모듈 작성
3. **비선형 힌지 함수**: 항복 이후 강성저하 piecewise 포텐셜 구현
4. **LF 출력 스키마**: GNN 입력용 `ulf_nodes/edges/meta` exporter 구현

초기 구현 산출물(저장소 기준): `implementation/phase1/lf_output_schema.json`, `generate_lf_sample.py`, `validate_lf_output.py`

---


## 12) 시스템 철학 명시: O(N) 근사 + 잔차 보정

본 시스템의 핵심 철학은 다음 두 가지를 동시에 만족하는 것이다.

1. **로컬 워크스테이션 환경에서 유지 가능한 계산복잡도**
   - Low-Fidelity 경로의 목표 복잡도는 `O(N)` (노드/엣지 수 `N`에 선형 비례)
   - 이를 위해 sparse 경로 유지, locality-aware batching, super-node 압축을 기본 전략으로 사용
2. **정밀도는 잔차 보정에서 회수**
   - `U_LF`는 빠른 근사해를 우선 계산
   - `ΔU`는 GNN 잔차 보정으로 비선형 오차를 회수
   - 최종적으로 `U_final = U_LF + ΔU`를 사용하고, 물리 위반 시 HF fallback으로 안전성 확보

### 12-1) O(N) 운영 규칙 (Implementation Guardrail)

- 그래프 전처리/배치/추론의 wall-time을 `N` 대비 추적하여 선형성 지표를 주기적으로 기록
- 선형성 점검 기준(권장):
  - 로그-로그 회귀 기울기 `p`가 `0.85 <= p <= 1.15` 범위 유지
  - 기준 범위를 벗어나면 병목 모듈(배치, 커널, I/O) RCA 수행
- CI/리포트에 `complexity_report.json`을 남겨 회귀를 조기 감지

### 12-2) Phase 1 즉시 실행 항목 추가

- LF exporter 검증과 함께 `O(N)` 선형성 점검 스크립트를 포함해 운영 철학을 코드 수준에서 고정
- 연속 구현 계획 문서(`implementation/phase1/next-implementation-plan.md`)를 기준으로 FIRE/CG → Mapper → 비선형 힌지 → Exporter 순으로 진행
- `implementation/phase1/run_phase1_steps.py`로 1~6 단계 스캐폴드 실행 및 Gate 리포트 자동 생성



---

## 13) 개선해야 될 부분 (지속 개선 Backlog)

아래 항목은 현재 명세(Phase 1~3)와 운영 철학(O(N)+잔차보정)을 유지하면서, 실제 상용 대체 수준으로 끌어올리기 위한 **다음 개선 포인트**다.

### 13-1) 수치 안정성/검증

1. **Projection 수렴성 보증 강화**
   - `projection_quality.threshold_pass`만으로는 충분하지 않으므로, 케이스별 반복 수렴 통계(평균/분산, fail-rate)를 운영 KPI로 추가
2. **Krylov 기저 품질 감시**
   - `orthogonality_error` 상한을 Gate 조건에 포함
   - 임계 초과 시 재직교화(re-orthogonalization) 자동 수행
3. **HF 기준 비교 자동화(White-box Validation)**
   - LF/GNN 결과와 HF FEM 기준값을 자동 비교하는 보고서(변위/응력/반력/에너지 오차)를 표준 산출물로 고정

### 13-2) O(N) 성능 체계

1. **실엔진 프로파일 고정**
   - synthetic 대신 Rust/HIP 실행 결과만 Gate-2 판정에 사용
2. **I/O 병목 분리 계측**
   - compute time, host-copy time, serialization time을 분리 기록
3. **메모리 예산 정책 추가**
   - 구조 규모별 VRAM budget table을 문서화하고, 초과 시 자동 subgraph 분할 전략을 강제

### 13-3) 물성/규정 신뢰성

1. **Material parser 룰셋 버전 관리**
   - KBC/IBC 규정 버전별 룰 ID와 변환식을 별도 테이블로 관리
2. **단위계 회귀 테스트 확대**
   - SI/N-mm/kN-m를 넘는 현장 단위 혼합 입력 케이스를 정기 회귀 테스트에 포함
3. **경고 체계 강화**
   - `parser_warnings`를 등급화(critical/warn/info)하고 Gate 차단 조건과 연결

### 13-4) 연동/운영

1. **Zero-copy 실증 전환**
   - 현재 stub 경로를 실 DLPack producer(Rust HIP)로 교체하고, 포인터 동일성 검증 로그를 아티팩트로 저장
2. **LF→GNN E2E 계약 테스트**
   - `ulf_nodes/edges/meta`를 GNN dataloader에서 실제 한 배치 추론까지 수행하는 smoke test를 CI에 추가
3. **Fallback 정책 운영화**
   - 물리 위반(`||R_eq|| > ε`) 발생 시 어떤 서브그래프를 HF로 보낼지 기준을 정책 파일로 분리

### 13-5) 권장 진행 순서 (다음 4주)

- **Week 1:** White-box validation 자동화 + 단위계 회귀 테스트 확장
- **Week 2:** 실 DLPack zero-copy 검증 + I/O 병목 분리 계측
- **Week 3:** Parser 룰셋 버전관리 + warning 등급 기반 Gate 연동
- **Week 4:** LF→GNN E2E CI smoke + fallback 정책 파일화
