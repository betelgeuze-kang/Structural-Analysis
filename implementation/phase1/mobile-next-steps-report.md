# Phase1 다음 진행 항목 보고서 (모바일 개발환경 전용)

> 범위: 모바일/저사양 환경에서 **실행 테스트 없이** 진행 가능한 구현 작업만 정리.

## 1) 지금 바로 진행할 작업 (문서/계약/정적검증)

### N1. CI Gate 실패 코드 표준 사전 고정
- 목적: 런타임 없이도 실패 원인을 바로 분류.
- 작업:
  - `phase1_ci_gate.py`의 `reason_code`를 코드북으로 문서화.
  - `ci_gate_report.json` 예시를 PASS/FAIL 각각 1개씩 추가.
- 완료 기준:
  - 신규 기여자가 리포트만 보고 실패 원인을 역추적 가능.

### N2. LF→GNN 인터페이스 버전 정책 추가
- 목적: 모듈 교체 시 인터페이스 파손 방지.
- 작업:
  - `lf_to_gnn_e2e_smoke_report.json`에 `interface_version` 필드 규약 문서화.
  - `gnn_residual_model.py` 시그니처 변경 정책(major/minor) 명시.
- 완료 기준:
  - 보고서/코드/문서가 동일 버전 규약을 참조.

### N3. Material Rule 변경 이력 템플릿 도입
- 목적: 규정 변경 시 검토 가능성 확보.
- 작업:
  - `material_rule_table.json` 변경 시 사용하는 `CHANGELOG` 템플릿 추가.
  - 필수 메타(`rule_id`, `source`, `effective_date`, `change_reason`) 체크리스트 작성.
- 완료 기준:
  - 룰 추가 PR마다 동일 템플릿 사용 가능.

## 2) 다음 순서 작업 (코드 작성 중심, 실행 불필요)

### N4. Fallback 정책/게이트 매핑표
- `fallback-policy-spec.md`에 정책 키가 `step6_gate_report.json` 어떤 필드에 반영되는지 표로 추가.

### N5. Priority 리포트 통합 명세
- `priority3_summary.json`, `ci_gate_report.json`, `static_artifact_validation_report.json` 간 공통 필드(`run_id`, `schema_version`, `generated_at`) 통일 명세 추가.

### N6. 정적 리뷰 체크리스트 문서
- PR 리뷰어가 모바일 환경에서 볼 항목만 모은 체크리스트(`docs/review-checklist-mobile.md`) 추가.

## 3) 현재 리스크와 회피 전략

- 리스크: 실 Rust/HIP producer 미연결로 strict 결과의 실환경 대표성이 낮음.
- 회피: 문서/계약 레벨에서는 `producer_kind`와 `strict_rust_hip_pass` 검증 규칙을 우선 고정하고, 실연동은 데스크톱 환경에서 즉시 치환 가능한 형태를 유지.

## 4) 완료 보고 포맷 (고정)

매 작업 완료 시 아래 5개 섹션을 유지:
1. Done
2. Next-3
3. Later-3
4. Risks
5. Gate target



## 5) 진행 업데이트 (이번 완료분)

- 완료: `N1`, `N2`, `N3`
  - CI reason codebook + PASS/FAIL 샘플 추가
  - LF→GNN 인터페이스 버전 정책 및 보고 필드(`interface_version`) 추가
  - Material rule changelog 템플릿/기본 changelog 추가
- 다음 Next 항목: `N4`, `N5`, `N6`


## 6) 진행 업데이트 (실무권장순서 1~5 반영)

- 완료: `N4`, `N5`, `N6`
  - fallback 정책/게이트 매핑표 반영
  - Priority 리포트 공통 필드 통합 방향 반영
  - 모바일 정적 리뷰 체크리스트 초안 반영
- 신규 Next 항목:
  1) 동역학/경계조건 계약을 LF exporter 필드와 직접 매핑
  2) PG-GAT 계약을 `run_priority3_modules.py` 통합 리포트에 병합
  3) 서브그래프 사영 스텁을 Krylov 훅 경로와 연결


## 7) 다음 구현점 (이번 요청 반영)

### N7. 리포트 공통 메타 필드 강제
- 대상: `lf_to_gnn_e2e_smoke_report.json`, `ci_gate_report.json`, `static_artifact_validation_report.json`
- 필수: `schema_version`, `run_id`, `generated_at`
- 완료 기준: validator가 메타 필드 누락 시 fail

### N8. PG-GAT/서브그래프/SoA 리포트 메타 정합화
- 생성기 출력에 공통 메타를 동일 규약으로 추가

### N9. 공통 메타 버전 bump 규칙 문서화
- major/minor/patch 변경 기준 문서 추가


## 8) 진행 업데이트 (이번 구현점)

- 완료: `N8`, `N9`
  - PG-GAT/서브그래프/SoA/동역학 리포트 메타 정합화
  - 공통 메타 버전 bump 규칙 문서(`report-metadata-versioning-policy.md`) 추가
- 신규 Next 항목:
  1) `run_priority3_modules.py`에 공통 메타 필드 자동 채움
  2) `priority3_summary.json` 메타/버전 규약 적용
  3) 메타 버전 mismatch 전용 reason_code 추가


## 9) 진행 업데이트 (이번 구현점)

- 완료: Next 항목 1)~3)
  - `run_priority3_modules.py` 공통 메타 자동 채움
  - `priority3_summary.json` 메타/버전 규약 적용
  - 메타 버전 mismatch 전용 reason_code 추가
- 신규 Next 항목:
  1) `phase1_ci_gate.py`에 priority3 입력을 옵션으로 병합
  2) `priority3_summary` PASS/FAIL 샘플 아티팩트 추가
  3) 메타 버전 mismatch 재현용 fixture 추가


## 10) 진행 업데이트 (이번 구현점)

- 완료: 남은 핵심 3가지
  1) `run_phase1_steps.py` Gate2 복잡도 진단 필드 보강
  2) `phase1_ci_gate.py` priority3 입력 옵션 병합
  3) `priority3_summary` PASS/FAIL 샘플 + mismatch fixture 추가
- 신규 Next 항목:
  1) `phase1_ci_gate.py`에서 priority3 strict mode 스위치
  2) gate2 실패시 RCA 힌트 reason_code 세분화
  3) priority3 mismatch fixture 기반 회귀 테스트 자동화


## 11) 진행 업데이트 (물리 정합성 + 잔차/메타학습 계약 강화)

- 완료:
  1) `physics_residual_contract_stub.py` 추가 (평형잔차/경계위반/감쇠 범위 정적 계약 리포트)
  2) `meta_learning_task_schema.json` + `meta_learning_task_stub.py` 추가 (토폴로지/하중 task pack 정적 계약)
  3) `validate_phase1_artifacts.py` 및 `phase1_ci_gate.py`에 신규 계약 아티팩트 검증 연동
- 신규 Next-3:
  1) meta task split(train/val/test) 및 OOD 플래그 확장
  2) physics residual에 에너지 일관성(energy monotonicity) 지표 추가
  3) run_phase1_steps.py에 신규 계약 생성/검증 step 병합


## 12) 정밀해석/좌굴 대응 보강 포인트 (요청 반영)

- 핵심 갭 진단 문서: `implementation/phase1/high-fidelity-gap-analysis.md`
- 즉시 보강 3축:
  1) 좌굴 고유치/경로추적 계약을 CI gate 필수 항목으로 확장
  2) 물리정합성에 energy monotonicity 제약 추가
  3) 메타학습 task를 OOD split 기반으로 재구성
- 목표: 기존 상용 구조해석 정밀도 수준 + 기존 워크플로우가 놓친 좌굴/불안정 구간 대응


## 13) 실테스트 없이 계속 진행할 구현/개선 요소 (요청 반영)

### A. 물리정합성 계약 강화 (실행 불필요)
1) `physics_residual_contract_stub.py`에 `energy_monotonicity_pass` 필드 추가
2) `reason_code` 확장: `ERR_ENERGY_MONOTONICITY`
3) `validate_phase1_artifacts.py`에서 에너지 단조성 필수 검증

### B. 좌굴 대응 계약 선행 (실행 불필요)
1) `buckling_eigen_contract_stub.py` 신설 (입력: K, Kg 메타 / 출력: `critical_load_factor`)
2) `buckling_contract_report.json` 스키마 확정
3) `phase1_ci_gate.py` required contracts에 좌굴 리포트 병합

### C. 메타학습 일반화 체계 고도화 (실행 불필요)
1) `meta_learning_task_schema.json`에 `split`(train/val/test), `ood_tag` 필드 추가
2) `meta_learning_task_stub.py`에 OOD 샘플 케이스 포함
3) static validator에 `meta_ood_generalization_pass` 판단 룰 추가

### D. 상용수준 정밀도 검증 준비 (실행 불필요)
1) `hf_benchmark_schema.json` 신설 (drift/base shear/MAC/좌굴계수 지표)
2) `benchmark_kpi_contract_stub.py` 추가로 샘플 KPI 리포트 생성
3) CI reason code 연동: `ERR_BENCHMARK_KPI_FAIL`

### E. 문서/게이트 동기화 (실행 불필요)
1) `implementation/phase1/README.md` 실행 순서에 신규 계약 생성 단계 반영
2) `ci-gate-reason-codebook.md`에 신규 reason code 추가
3) `high-fidelity-gap-analysis.md`의 Priority-1 항목과 실제 파일 매핑표 유지

### 권장 실행 순서 (코드 작성 중심)
1. 에너지 단조성 계약 추가
2. 좌굴 고유치 계약 추가
3. 메타학습 OOD 계약 추가
4. benchmark KPI 계약 추가
5. CI/validator 최종 병합


## 14) 진행 업데이트 (권장 실행 순서 1~5 완료)

- 완료:
  1) 에너지 단조성 계약 추가 (`physics_residual_contract_stub.py`, validator 반영)
  2) 좌굴 고유치 계약 추가 (`buckling_eigen_contract_stub.py`, `buckling_contract_schema.json`)
  3) 메타학습 OOD 계약 추가 (`meta_learning_task_schema.json` 확장, `meta_ood_generalization_pass` 반영)
  4) benchmark KPI 계약 추가 (`hf_benchmark_schema.json`, `benchmark_kpi_contract_stub.py`)
  5) CI/validator 최종 병합 (`phase1_ci_gate.py`, `validate_phase1_artifacts.py`, reason codebook 업데이트)
- 결과: 실테스트 없이도 좌굴/에너지/OOD/KPI를 정적 계약으로 CI 판정 가능


## 15) A→B→C 단계 구현 업데이트 (미분없는 경로분기)

- A 완료: `physics_guided_branching.py` 추가
  - 물리적 직교기저 기반 K-branch 후보를 **forward-only**로 평가
  - `uses_backprop=false`를 계약 필드로 강제
- B 완료: `bifurcation_detector_stub.py` 추가
  - 강성 급감 + 잔차 급증 트리거로 분기 이벤트 감지 계약화
- C 완료: `rust_onnx_native_contract_stub.py` 추가
  - Rust/HIP/ONNX native 통합 체크(가중치 동적입력, ROCm EP, 단일 바이너리) 계약화
- 통합 실행기: `run_abc_sequence.py`
- CI/Validator 반영: `phase1_ci_gate.py`, `validate_phase1_artifacts.py`에 A/B/C 계약 병합

- Backprop 확장 완료: `winning_ticket_backprop.py` 추가
  - 정찰(autograd off) -> 승자선택 -> 표적(backprop on, graph_count=1)
  - 물리적으로 가능한 직교사영 분기 경로 중 승자 경로만 역전파
