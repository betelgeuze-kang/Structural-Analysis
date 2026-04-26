# 건축구조동역학 + 철도(궤도/터널) 구조동역학 아키텍처 보강 계획서

- 문서 버전: `v1.0`
- 작성일(UTC): `2026-02-26`
- 적용 범위: `implementation/phase1`
- 운영 원칙: `인터페이스 먼저 고정` -> `LF 물리커널` -> `잔차학습` -> `복합 연성` -> `CI/검증`

## 1) 현재 시스템 분석 요약

기존 ADD/Phase1은 건축물 구조해석 중심으로 구성되어 있으며, 동역학 기반 파이프라인은 이미 일부 구현됨.

### 1.1 이미 구현된 동역학 영역

| 영역 | 파일 | 상태 |
|---|---|---|
| 동역학/경계조건 계약(건축) | `dynamics-boundary-contract.md`, `generate_dynamics_boundary_contract.py` | DONE |
| 동역학/경계조건 계약(track/tunnel 확장) | `dynamics-boundary-contract.md`, `dynamics_boundary_report.track.json`, `dynamics_boundary_report.tunnel.json` | DONE |
| Newmark-β 시간이력(SDOF) | `dynamic_time_history_contract_stub.py` | DONE |
| 감쇠 모델(Rayleigh/Modal/도메인확장) | `generate_dynamics_boundary_contract.py` | DONE |
| 외력 프로파일(`seismic`, `train_passage` 등) | `generate_dynamics_boundary_contract.py` | DONE |
| 시공간 학습 베이스라인(T-GNN) | `train_tgnn_baseline.py` | DONE |
| 고차/연산자 트랙(실험) | `train_simplicial_tgnn.py`, `train_neural_operator_surrogate.py` | DONE(실험) |

### 1.2 철도/터널 도메인 미구현 핵심

| 영역 | 필요 산출물 | 상태 |
|---|---|---|
| 궤도 LF 동역학 커널 | `track_lf_solver.py` / `track_lf_kernel.rs` | DONE (Python prototype) |
| 이동하중/이동질량 적분기 | `moving_load_integrator.py` | DONE (Python prototype) |
| 차량-궤도 연성 해석기 | `vti_coupled_solver.py` | DONE (Python prototype) |
| 궤도 불규칙도 입력기 | `track_irregularity_generator.py` | DONE (Python prototype) |
| 터널 링/세그먼트 그래프 변환 | `tunnel_graph_converter.py` | TODO |
| 터널 SSI 해석 | `soil_tunnel_ssi.py` | TODO |
| 터널 열차통과 하중 | `train_passage_load_generator.py` | TODO |
| 터널 종방향 지진 | `tunnel_seismic_longitudinal.py` | TODO |
| 복합 연성(건축-궤도-터널) | `substructuring_interface.py` 등 | TODO |
| 환경진동 규정평가 | `vibration_compliance_checker.py` | TODO |

## 2) 보강 대상 3대 도메인

## 도메인 A: 철도 궤도 구조동역학 (Track Dynamics)

- 목표:
  - Vehicle-Track Interaction(VTI) 해석
  - 이동하중/이동질량 효과
  - 레일-침목-도상-노반 다층 동역학 반영

- 구현 요구:
  - 10-DOF 이상 차량 모델
  - Hertzian wheel-rail 접촉
  - Timoshenko/Euler-Bernoulli + Winkler/Pasternak 기반 궤도 커널
  - 고주파(500~2000 Hz) 대응

## 도메인 B: 터널 구조동역학 (Tunnel Dynamics)

- 목표:
  - Soil-Tunnel Interaction(SSI)
  - 열차 통과 동하중/미기압파 근사
  - 라이닝 세그먼트/링 조인트 비선형 응답

- 구현 요구:
  - 터널 단면/링/세그먼트 그래프화
  - 지반 임피던스 주파수 의존 파라미터화
  - 종방향 지진 변형 모델

## 도메인 C: 궤도-터널-건축물 복합 동역학

- 목표:
  - 차량 -> 궤도 -> 터널 -> 지반 -> 건축물 전달 경로 연성
  - 부분구조법 기반 서브시스템 결합
  - 환경진동 기준 자동 판정(규정 기반)

## 3) 구현 작업 목록 (우선순위)

## Phase A: 기반 계약 확장 (1~2주)

| ID | 작업 | 산출물 | 현재 |
|---|---|---|---|
| A1 | 궤도/터널 하중 타입 계약 반영 | `dynamics-boundary-contract.md`, `generate_dynamics_boundary_contract.py` | DONE |
| A2 | 차량 모델 입력 스키마 | `vehicle_model_schema.json` | DONE (계약 검증 연결) |
| A3 | 터널 라이닝 입력 스키마 | `tunnel_lining_schema.json` | DONE (계약 검증 연결) |
| A4 | 지반 임피던스 파라미터 테이블 | `soil_impedance_table.json` | DONE (계약 검증 연결) |
| A5 | 레일/라이닝 물성 매핑 확장 | `material_rule_table.json` 확장 | DONE (계약 검증 연결) |

### Phase A 완료 기준

- 계약 스키마 정합성 검증 스크립트 통과
- building/track/tunnel/coupled 도메인 샘플 리포트 생성 성공
- 규정된 reason_code 체계 정의 완료

## Phase B: 궤도 LF Solver 구현 (2~3주)

| ID | 작업 | 산출물 | 현재 |
|---|---|---|---|
| B1 | Timoshenko + Winkler/Pasternak LF 커널 | `track_lf_solver.py`, `track_lf_kernel.rs` | DONE (Python prototype) |
| B2 | 이동하중/이동질량 Newmark 확장 | `moving_load_integrator.py` | DONE (Python prototype) |
| B3 | 차량-궤도 연성 반복수렴 | `vti_coupled_solver.py` | DONE (Python prototype) |
| B4 | PSD 기반 궤도불규칙도 입력기 | `track_irregularity_generator.py` | DONE (Python prototype) |

### Phase B 완료 기준

- 단순보-이동하중 벤치마크에서 참조해 대비 MAPE <= 5%
- 수렴 실패율 < 2%, 최대 반복 제한 동작

## Phase C: 터널 동역학 모듈 구현 (2~3주)

| ID | 작업 | 산출물 | 현재 |
|---|---|---|---|
| C1 | BIM/CAD -> 터널 그래프 변환 | `tunnel_graph_converter.py` | DONE (Python prototype) |
| C2 | 세그먼트 조인트 비선형 | `tunnel_segment_joint_nonlinear.py` (신규) | DONE (Python prototype) |
| C3 | 지반 임피던스 기반 SSI | `soil_tunnel_ssi.py` | DONE (Python prototype) |
| C4 | 열차통과 하중 시계열 생성 | `train_passage_load_generator.py` | DONE (Python prototype) |
| C5 | 종방향 지진 변형 해석 | `tunnel_seismic_longitudinal.py` | DONE (Python prototype) |

### Phase C 완료 기준

- 원형 터널 정/동적 기준 케이스에서 참조해 대비 MAPE <= 5%
- 라이닝 조인트 비선형 구간에서 에너지/잔차 계약 통과

## Phase D: GNN 잔차보정 확장 (2~4주)

| ID | 작업 | 산출물 | 현재 |
|---|---|---|---|
| D1 | 궤도 동역학 잔차 데이터셋 생성 | `generate_track_dynamics_dataset.py` | DONE (Python prototype) |
| D2 | 터널 동역학 잔차 데이터셋 생성 | `generate_tunnel_dynamics_dataset.py` | DONE (Python prototype) |
| D3 | 멀티도메인 T-GNN 확장 | `train_tgnn_baseline.py` 확장 | DONE (Python prototype) |
| D4 | 이동하중 attention | `moving_load_attention.py` | DONE (Python prototype) |

### Phase D 완료 기준

- 궤도/터널 validation MAPE <= 5%
- OOD(track irregularity, asymmetric torsion) 세트에서 안정 수렴

## Phase E: 복합 연성/검증 (2~3주)

| ID | 작업 | 산출물 |
|---|---|---|
| E1 | 부분구조법 인터페이스 | `substructuring_interface.py` |
| E2 | 진동 전달 감쇄 모델 | `vibration_attenuation_model.py` |
| E3 | 환경진동 규정 자동평가 | `vibration_compliance_checker.py` |
| E4 | CI Gate 확장 | `phase1_ci_gate.py` 확장 |
| E5 | White-box 확장 | `whitebox_validation_report.py` 확장 |

### Phase E 완료 기준

- 복합계 전달경로 시뮬레이션 계약 PASS
- 규정 비교 레포트 자동 생성
- CI 게이트에서 복합계 아티팩트 필수화

## 4) ADD 보강 대상 섹션

| ADD 섹션 | 보강 내용 |
|---|---|
| §1 시스템 개요 | 대상 범위: 건축물 + 철도 인프라(궤도/터널) |
| §2 Phase 1 그래프 추상화 | 궤도/터널 그래프 매핑 규칙 |
| §2 Phase 2 잔차학습 | 이동하중/연성 비선형 잔차학습 |
| §2 Phase 3 물리검증 | 궤도 평형잔차/터널 안전율 기준 |
| §6 멀티스케일 계층 | L0(윤축접촉) ~ L3(건축물) |
| §11 2-Bead MD 엔진 | 레일/도상/세그먼트 Bead 매핑 |
| §12 O(N) 철학 | 이동하중 영향범위 기반 windowed graph |

## 5) 기존 코드 재사용 전략

| 기존 자산 | 재사용 방식 |
|---|---|
| FIRE/CG 평형 루프 | 궤도/터널 LF 수렴 엔진 재사용 |
| Newmark-β 적분기 | MDOF 차량+궤도/터널 확장 |
| 비선형 LJ 힌지 | 세그먼트 조인트/체결장치 비선형 물성 전환 |
| T-GNN 시계열 | 궤도/터널 잔차학습으로 확장 |
| O(N) 가드레일 | 멀티도메인 복잡도 추적 동일 적용 |
| Zero-copy 브리지 | Rust/HIP <-> Python 인터페이스 공용 |
| CI Gate 프레임 | 신규 아티팩트 검증 축 추가 |

## 6) 리스크 및 대응

| 리스크 | 영향도 | 대응 |
|---|---|---|
| 이동하중 고주파로 dt 폭주 | 높음 | adaptive dt + 관심대역 제한 |
| VTI 반복수렴 실패 | 높음 | relaxation factor + max_iter + fallback |
| SSI 파라미터 불확실성 | 중간 | UQ 샘플링(Bayesian) |
| 멀티도메인 그래프 메모리 증가 | 높음 | windowed 활성노드 + 서브그래프 |
| 규정 적용범위 확장 부담 | 중간 | rule table 버전관리 |

## 7) 착수 순서 (고정)

1. Phase A (계약/스키마 고정)
2. Phase B (궤도 LF)
3. Phase C (터널 동역학)
4. Phase D (멀티도메인 GNN)
5. Phase E (복합 연성/검증)

중요:
- Phase A를 최우선으로 수행한다.
- 인터페이스가 고정되기 전 B/C 구현을 시작하지 않는다.

## 8) 검증 계획

## 자동 검증

- `validate_phase1_artifacts.py`에 track/tunnel/coupled 계약 추가
- `phase1_ci_gate.py`에 track/tunnel 신규 reason_code 및 필수 아티팩트 추가
- LF 솔버 검증:
  - 단순보-이동하중
  - 원형터널-정적
  - 연성 자유진동
  - 목표: MAPE <= 5%
- GNN 확장 검증:
  - 궤도/터널 validation MAPE <= 5%

## 수동 검증

- ADD 개정본 리뷰
- 물리 타당성 점검:
  - 변위 규모
  - 고유진동수 범위
  - 접촉력/라이닝 안전율

## 9) 운영 규칙 (향후 구현시 준수)

- 모든 신규 모듈은 다음을 반드시 포함:
  - `schema_version`, `run_id`, `generated_at`
  - `contract_pass`, `reason_code`, `reason`
- 각 Phase 완료 시:
  - 산출물 경로 업데이트
  - CI 게이트 연동
  - 정적 검증기 연동
- 구현 이슈 발생 시:
  - 인터페이스 우선 수정 여부를 먼저 판단
  - 임시 우회 코드 대신 계약 업데이트를 선행

## 10) 즉시 Next-3 (실행 큐)

1. A5: `material_rule_table.json`에 레일/도상/세그먼트 물성 규칙 추가
2. B1: `track_lf_solver.py` 초기 버전 + 단순 이동하중 벤치 구현
3. E4 준비: `phase1_ci_gate.py` track/tunnel 필드 예약(reason code/required artifacts)
