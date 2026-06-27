# Phase1 모바일웹 개발환경 기준: 실행 테스트 제외 개발 백로그

> 목적: 모바일웹/저사양 로컬 환경에서도 **실행 테스트 없이** 바로 진행 가능한 구현 항목만 분리한다.

## 원칙
- 실제 런타임 실행(`python ...`, 엔진 훅 호출, CI run)은 제외한다.
- 코드/문서/스키마/계약/정적검증 중심으로 진행한다.
- 산출물은 PR 단위로 리뷰 가능한 텍스트/코드 변경으로 남긴다.

## Priority-A (즉시 진행 가능)

### A1) LF→GNN 입력/출력 계약 정리 고도화
- 작업
  - `lf_to_gnn_e2e_smoke.py`의 입출력 필드 계약을 문서화(필수/선택/기본값).
  - `gnn_residual_model.py` 시그니처를 실제 프로젝트 모듈 교체 가능하도록 인터페이스 설명 추가.
  - 오류 메시지 표준(필드 누락/타입 불일치/빈 배치) 설계.
- 산출물
  - `implementation/phase1/README.md`에 계약 표 추가.
  - 인터페이스 주석/도큐스트링 보강.

### A2) Strict Rust/HIP Probe 통합 준비 (실 producer 연결 전)
- 작업
  - `zero_copy_real_probe.py`에 "실 producer 커맨드 템플릿"과 환경변수 매핑 규칙 명세.
  - mock/stub/report 차이를 한눈에 보는 판정 매트릭스 문서화.
  - strict 실패 코드별 next_action 사전 정의.
- 산출물
  - README에 producer command 템플릿/체크리스트.
  - `next_action` 코드북(문서).

### A3) Step5 RCA 결과를 CI 판단 입력으로 쓰는 계약 고정
- 작업
  - `step5_rca_summary.json` 필드 스키마(필수키/타입/범위) 명문화.
  - `phase1_ci_gate.py` 입력 유효성 검증 로직(누락 키/음수 값/NaN) 설계 및 구현.
  - 아티팩트 매니페스트 확장 규칙(버전/타임스탬프/run_id) 정의.
- 산출물
  - 스키마 문서/코드 내 검증 분기.
  - CI 아티팩트 규약 문서.

## Priority-B (개발 계속 가능)

### B0) 정적 아티팩트 계약 검사 자동화
- 작업
  - `validate_phase1_artifacts.py`로 smoke/ci/rca 보고서 필드 및 타입을 정적으로 검사.
  - 실패 항목을 카테고리별(`smoke`,`ci`,`rca`)로 집계.
- 산출물
  - `static_artifact_validation_report.json`

### B1) Krylov 적응 재직교화 정책 명세 강화
- 작업
  - `orthogonality_error` 구간별 동적 pass 증가 정책 표 작성.
  - fail 시 진단 메시지 규격(`reason_code`, `suggested_reorth_pass`) 통일.
- 산출물
  - 정책 표 + 코드 주석/리포트 필드 확장.
  - `projection_quality.reason_code`, `suggested_reorth_pass`

### B2) Material Rule Table 운영성 개선
- 작업
  - `material_rule_table.json` 버전별 diff 정책 문서화.
  - 룰 추가 시 필수 메타(`rule_id`, `source`, `effective_date`) 계약 추가.
- 산출물
  - 룰 테이블 관리 가이드.
  - 파서 출력에 규정 메타 필드 확장(실행 없이 코드 반영 가능).

### B3) Fallback Policy Gate 연동 문서/계약 강화
- 작업
  - `fallback_policy.json` 키별 의미/허용범위/기본값 정의.
  - Gate report에 policy fingerprint(해시/버전) 포함 규칙 추가.
- 산출물
  - fallback 정책 스펙 문서.
  - 리포트 필드 설계 반영.

### 진행 반영
- B1 일부 반영: `orthogonal_krylov_projection.py`에 `reason_code` 및 `suggested_reorth_pass` 추가
- B3 일부 반영: `run_phase1_steps.py` Gate 출력에 `fallback_policy_version`/`fallback_policy_fingerprint` 추가, `fallback-policy-spec.md` 문서화
- A1/A2/A3 모바일 정적 pass 반영: `implementation/phase1/mobile-static-contracts.md`에 LF→GNN 계약, strict Rust/HIP producer handoff, Step5 RCA static schema 운용 규칙을 추가
- A3 스키마 앵커 추가: `implementation/phase1/step5_rca_summary.schema.json`는 현재 gate 필수값(`timing_breakdown_seconds.compute|host_copy|serialization`)과 선택 provenance(`schema_version`, `generated_at_utc`, `run_id`, `producer`, `host_copy_share`, `strict_probe_ref`, `artifact_manifest`)를 정의
- A3 helper 추가: `implementation/phase1/step5_rca_contract.py`는 `validate_step5_rca_summary()`와 `missing_fields`/`invalid_fields` detail payload를 제공하며, 이후 `phase1_ci_gate.py::_validate_inputs()`가 import 또는 inline할 수 있는 정적 계약 구현이다
- A1 코드 반영: `lf_to_gnn_e2e_smoke.py`는 `LF_GNN_REQUIRED_INPUT_FIELDS`, `LF_GNN_OUTPUT_FIELDS`, `LF_GNN_STANDARD_REASON_CODES`, `LEGACY_TO_STANDARD_REASON_CODE`, `claim_boundary`를 노출하고 report에 `standard_reason_code`를 추가한다
- A1 모델 반영: `gnn_residual_model.py`는 compatibility entrypoint/docstring, required batch/node/edge field constants, `mobile_static_contract_ref`, `claim_boundary` metric을 노출한다
- A1/A2/A3 README 앵커 보조 문서 추가: `implementation/phase1/README.mobile-static-contracts.md`는 `mobile-static-contracts.md`, `step5_rca_summary.schema.json`, `step5_rca_contract.py`, LF→GNN 파일군, strict Rust/HIP handoff를 한 곳에 연결한다
- 모바일 정적 코드리뷰 병목 수정: `ERR_RESIDUAL_ACCURACY`와 `ERR_COMPLEXITY_GUARDRAIL`를 각각 `ERR_LF_GNN_ACCURACY_BELOW_TARGET`, `ERR_LF_GNN_COMPLEXITY_GUARDRAIL`로 분리해 과도한 unsupported/shape-mismatch 분류를 제거했다
- 모바일 정적 코드리뷰 병목 수정: LF→GNN smoke fallback 경로가 `model_module=gnn_residual_model`로 보일 수 있는 혼동을 줄이기 위해 `fallback_used`, `fallback_reason`, `model_module=python_fallback` 리포트 필드를 표준화했다
- 모바일 정적 코드리뷰 병목 수정: GitHub Markdown 자동 앵커에 맞춰 A1/A2/A3 문서 링크와 코드 내 `mobile_static_contract_ref`를 소문자 앵커로 통일했다
- 이번 pass에서는 모바일 원칙에 맞춰 Python/Rust/HIP/npm/CI 실행, protected evidence 재생성, release/solver/benchmark/customer-shadow/HIP claim 승격을 하지 않음

## 완료 보고 포맷 (모바일웹 개발환경용)

- Done
  - (이번 PR에서 변경한 문서/코드)
- Next-3
  1) (실행 없는 즉시 구현 항목)
  2) ...
  3) ...
- Later-3
  1) ...
  2) ...
  3) ...
- Risks
  - (실 producer/실 CI 미연결로 인한 제한) -> (해소 조건)
- Gate target
  - "문서 계약 100% 반영 + 정적검증 통과"를 기본 게이트로 사용

## 이번 기준 추천 Next-3
1) `phase1_ci_gate.py` 입력 검증 강화(스키마/범위 체크) 구현
2) `implementation/phase1/README.md`에 strict probe 실제 producer 연결 템플릿 추가
3) `lf_to_gnn_e2e_smoke.py`/`gnn_residual_model.py` 인터페이스 문서화 및 reason_code 표준 추가

## 이번 pass 이후 추천 Next-3
1) `phase1_ci_gate.py::_validate_inputs()`가 `step5_rca_contract.validate_step5_rca_summary()`를 직접 호출하거나 같은 helper를 inline해서 `missing_fields`/`invalid_fields`를 top-level gate details에 보존하도록 반영
2) `tests/test_phase1_ci_gate.py`에 `host_copy_share < 0`, `host_copy_share > 1`, `NaN/inf timing`, `missing timing subfield` 케이스를 추가
3) LF→GNN smoke fallback 경로에 대한 workstation test를 추가해 모델 import/runtime 실패 시 `fallback_used=true`, `model_module=python_fallback`, `standard_reason_code=ERR_LF_GNN_ACCURACY_BELOW_TARGET`가 보존되는지 확인

## 이번 기준 추천 Later-3
1) Krylov adaptive 재직교화 정책표(구간별 pass 증가) 반영
2) material rule table 운영 메타 필드 확장
3) fallback policy fingerprint를 Gate report에 표준화
