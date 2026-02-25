# Phase1 기준 고정밀 구조해석 + 좌굴 대응 보강 갭 분석

> 목표: 기존 상용 건축구조해석 수준의 정밀도를 확보하면서, 기존 워크플로우에서 놓치기 쉬운 좌굴/불안정/경로의존 문제를 LF→GNN 하이브리드 아키텍처로 확장 가능하도록 보강 포인트를 식별.

## 1) 현재 구현 수준에서 가능한 것과 한계

### 현재 강점 (이미 확보)
- LF→GNN 계약/검증 파이프라인, CI gate, 정적 아티팩트 검증 체계가 존재.
- zero-copy/SoA/서브그래프/Krylov/projection 등 확장용 인터페이스가 이미 스캐폴드로 정리됨.
- 물리 정합성(`physics_residual_contract_report.json`)과 메타학습 task pack(`meta_learning_task_report.json`)을 정적 환경에서도 계약 검증 가능.

### 핵심 한계 (정밀해석 관점)
- 비선형 평형 해석(대변형/재료비선형/접촉)의 실제 반복 알고리즘(Newton-Raphson + tangent update) 미구현.
- 좌굴(선형 고유치/비선형 경로추적/imperfection sensitivity) 전용 해석 루틴 부재.
- 시간/하중 증분 경로에서 수렴성/안정성 판단 지표(arc-length, snap-through 감지)가 없음.
- 검증 데이터셋이 스캐폴드 중심이라, 코드 기준 정확도(예: drift, mode shape MAC, critical load factor 오차) 관리 체계가 약함.

---

## 2) 반드시 보강해야 할 핵심 8개 영역

## A. 해석기(Physics Core) 정밀도 보강

1) **기하/재료 비선형 해석 루프 실장**
- 필요성: 상용 수준 정밀도는 2차효과(P-Delta/P-delta), 소성, 강성저하를 반영해야 함.
- 보강 항목:
  - tangent stiffness 업데이트 인터페이스
  - Newton-Raphson 반복 + line-search
  - 수렴 잔차(힘/변위/에너지) 다중 기준
- 수용기준(예시):
  - 동일 기준모델 대비 층간변위/내력 오차 <= 3~5%

2) **시간/증분 적분 안정화**
- 필요성: 동적·비선형 해석에서 적분기/감쇠모델 품질이 결과를 좌우.
- 보강 항목:
  - Newmark/HHT 선택 가능 인터페이스
  - Rayleigh/모달 감쇠 보정 규칙
  - adaptive time-step + 발산 감지
- 수용기준:
  - 기준 응답 스펙트럼 케이스에서 peak response 오차 관리

## B. 좌굴/불안정 전용 모듈 (현재 가장 큰 갭)

3) **선형 고유치 좌굴 해석**
- 필요성: 임계하중계수(critical load factor) 선별은 최소 baseline.
- 보강 항목:
  - generalized eigenvalue 문제(K + λKg) 인터페이스
  - 모드별 좌굴형상 출력 계약
- 수용기준:
  - 대표 벤치마크(기둥/프레임)에서 λcr 오차 <= 5%

4) **비선형 좌굴 + 경로추적(arc-length)**
- 필요성: snap-through/snap-back은 기존 선형 워크플로우가 놓치기 쉬움.
- 보강 항목:
  - arc-length 제어기
  - branch switching 힌트
  - imperfection seed 시나리오
- 수용기준:
  - 경로추적 실패율, 한계점 포착률을 CI 지표로 관리

5) **초기결함/시공오차 민감도 분석**
- 필요성: 좌굴은 imperfection 민감도가 매우 큼.
- 보강 항목:
  - 초기변형 모드 주입 계약
  - 파라미터 sweep(진폭/위상/위치)
- 수용기준:
  - 민감도 envelope 자동 리포트화

## C. AI 잔차학습/메타학습 신뢰성 보강

6) **물리 제약형 loss + 안정성 제약**
- 필요성: 단순 MSE 잔차학습은 해석 안정성을 해칠 수 있음.
- 보강 항목:
  - equilibrium residual penalty
  - energy monotonicity penalty
  - 경계조건 위반 penalty
- 수용기준:
  - physics residual pass율 + long-rollout 안정성 지표

7) **메타학습 task 체계 고도화 (OOD 포함)**
- 필요성: 토폴로지/하중 조합 변화에 대한 일반화가 핵심.
- 보강 항목:
  - train/val/test split + OOD 태그
  - 구조형식(rahmen/truss/dual system)별 task family
  - hazard intensity level 스케일링
- 수용기준:
  - OOD 케이스 성능 하한선(예: critical response 오차)

## D. 검증/품질보증 체계 보강

8) **상용해석기 대비 정량 V&V 체계**
- 필요성: “정밀함”은 수치 KPI 없이는 입증 불가.
- 보강 항목:
  - 벤치마크 세트(정적/동적/좌굴) 고정
  - 지표: drift, base shear, mode shape MAC, λcr, 잔차수렴 이력
  - PASS/FAIL 경계값을 CI gate reason code로 연동
- 수용기준:
  - 릴리즈 후보에서 필수 벤치마크 PASS율 100%

---

## 3) 우선순위 제안 (지금 바로 착수 순서)

### Priority-1 (즉시)
1. 선형 고유치 좌굴 계약/스텁 추가 (`buckling_eigen_contract_stub.py`)
2. validate/gate에 좌굴 리포트 필수 항목으로 병합
3. physics residual에 energy monotonicity 체크 추가

### Priority-2 (단기)
1. 비선형 해석 루프 인터페이스(Newton/line-search) 스캐폴드 추가
2. meta-learning task를 OOD split 포함 구조로 확장
3. 벤치마크 KPI 스키마(`hf_benchmark_schema.json`) 도입

### Priority-3 (중기)
1. arc-length 경로추적 스텁 + failure reason code 체계
2. imperfection sensitivity 자동 리포트
3. 상용해석기 대비 비교 리포트 자동 생성기

---

## 4) 게이트 기준 업데이트 제안

- 신규 Gate-A: `buckling_contract_pass`
- 신규 Gate-B: `physics_energy_monotonic_pass`
- 신규 Gate-C: `meta_ood_generalization_pass`
- 각 게이트는 `phase1_ci_gate.py`에서 reason_code로 분기:
  - `ERR_BUCKLING_EIGEN_INVALID`
  - `ERR_ENERGY_MONOTONICITY`
  - `ERR_META_OOD_FAIL`

이 3개 게이트를 통과하지 못하면, 기존 PASS라도 릴리즈 후보에서 제외.

---

## 5) 결론 (요청사항 대응)

요구한 수준(기존 프로그램 정밀도 + 기존이 놓친 좌굴 문제 해결)을 만족하려면,
단순 스캐폴드 확장보다 **좌굴 전용 해석 모듈 + 비선형 경로추적 + 물리제약형 AI 학습 + 상용대비 V&V 게이트**를
동시에 묶어야 한다.

현재 코드베이스에서 가장 빠르게 효과를 내는 시작점은:
1) 좌굴 계약/지표를 CI에 넣고,
2) physics residual에 에너지 제약을 추가하며,
3) meta-learning을 OOD 기준으로 재구성하는 3축 병행이다.


## 6) Priority-1 구현 매핑표 (파일 기준)

| Priority-1 항목 | 구현 파일 | 산출 리포트 |
| --- | --- | --- |
| 에너지 단조성 계약 추가 | `physics_residual_contract_stub.py`, `validate_phase1_artifacts.py` | `physics_residual_contract_report.json` |
| 좌굴 고유치 계약 추가 | `buckling_eigen_contract_stub.py`, `buckling_contract_schema.json` | `buckling_contract_report.json` |
| 메타학습 OOD 계약 추가 | `meta_learning_task_schema.json`, `meta_learning_task_stub.py`, `validate_phase1_artifacts.py` | `meta_learning_task_report.json` |
| benchmark KPI 계약 추가 | `hf_benchmark_schema.json`, `benchmark_kpi_contract_stub.py` | `hf_benchmark_report.json` |
| CI/validator 최종 병합 | `phase1_ci_gate.py`, `validate_phase1_artifacts.py`, `ci-gate-reason-codebook.md` | `ci_gate_report.json`, `static_artifact_validation_report.json` |
