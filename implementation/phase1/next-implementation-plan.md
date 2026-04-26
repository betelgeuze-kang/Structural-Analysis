# Phase 1 이후 연속 구현 계획 (O(N) 철학 고정)


## 0) 1순위 착수 완료: 잔차 공간 직교사영 업데이트

- 구현 파일: `orthogonal_projection_update.py`
- 핵심 수식: `P = B(B^TB)^(-1)B^T`, `U_final = U_LF - alpha * P * R`
- 다음 액션: 직교 기저 `B`를 Rust/HIP LF 출력(또는 Krylov basis)로 교체

본 계획은 "로컬 환경 O(N) + 잔차보정" 원칙을 유지하면서 다음 구현 단계를 바로 실행하기 위한 작업표입니다.

철도/터널 복합 동역학 확장 작업은 별도 계획서
`implementation/phase1/railway_tunnel_dynamics_reinforcement_plan.md`를 기준으로 진행합니다.

## 1) FIRE/CG 정적 평형 루프 실장 (Rust/HIP)

### 작업 항목
- `add_external_force` 커널 분리 (Dead/Wind/Seismic)
- `compute_unbalanced_force_norm` 커널 추가
- `fire_step`(또는 `cg_step`) 업데이트 커널 추가
- 수렴 조건: `force_norm < tol` 또는 `max_steps`

### 완료 기준
- 최소 3개 테스트 케이스에서 수렴 재현
- 반복 실행 시 수렴 step 변동률 ±5% 이내
- LF 출력의 `meta.converged=true`, `meta.steps` 정상 기록

## 2) 포스필드 매퍼 구현 (E, A, I, L0 -> Kb, Kθ)

### 작업 항목
- 축강성/휨강성 치환 함수 구현
- 단위계 변환 레이어(SI / N-mm / kN-m)
- 입력 파서(부재/단면/재료 CSV 또는 JSON)

### 완료 기준
- 단위 테스트: 치환식 스냅샷 검증
- 단위계가 달라도 동일 물리량 결과 일치

## 3) 비선형 힌지/접촉 Piecewise 법칙 구현

### 작업 항목
- 항복 전/후 접선강성 함수
- `yield_index` 산출 로직
- 압축-인장 비대칭 접촉(면진/SSI) 법칙

### 완료 기준
- 간단 보/프레임 벤치에서 항복점 전후 곡선 변화 재현
- LF edge 출력에 `yield_index` 포함 및 검증 통과

## 4) Exporter 확장 (JSON + Parquet)

### 작업 항목
- 현재 JSON 계약(`lf_output_schema.json`) 유지
- `ulf_nodes.parquet`, `ulf_edges.parquet`, `ulf_meta.json` 동시 출력
- JSON-Parquet 정합성 체크 스크립트 추가

### 완료 기준
- GNN dataloader에서 parquet 바로 ingest 가능
- 동일 샘플에 대해 JSON/Parquet 핵심 통계량 일치

## 5) O(N) 실측 가드레일을 실엔진 훅으로 교체

### 작업 항목
- `complexity_profile.py`의 synthetic workload를 Rust/HIP 실행 훅으로 교체
- N 스케일 구간별 wall-time/VRAM 기록
- `complexity_report.json`에 slope + 메모리 추세 추가

### 완료 기준
- 실측 slope `0.85 <= p <= 1.15` 유지
- VRAM 증가율도 선형/준선형 범위 유지

## 6) Gate 제안 (다음 단계 진입 조건)

- **Gate-1 (LF 안정화):** 수렴/출력계약/단위계 테스트 100% 통과
- **Gate-2 (복잡도):** 실측 O(N) slope 가드레일 통과
- **Gate-3 (연동):** LF -> GNN 입력 파이프라인 E2E 1회 성공

## 권장 실행 순서

1. FIRE/CG 루프
2. 포스필드 매퍼
3. 비선형 힌지/접촉
4. Parquet exporter
5. O(N) 실측 훅
6. Gate 판정


## 추가 진행 현황 (요청 1,2,3)

- 1) Zero-copy 통신 스텁/프로토콜 확정 (`zero_copy_bridge_stub.py`)
- 2) 역행렬 없는 Krylov 직교사영 스캐폴드 (`orthogonal_krylov_projection.py`)
- 3) KBC<->MD 물성치 파서 스캐폴드 (`kbc_md_material_parser.py`)

- 통합 실행기: `run_priority3_modules.py`로 1,2,3 모듈 일괄 검증

## 우선순위 리스크 대응(완료 반영)

1. **Zero-copy 실연동 기준 강화**
   - `zero_copy_bridge_stub.py`에 `--producer-cmd` 추가
   - pass 조건: `roundtrip_success && shared_storage && host_copy_bytes==0`
2. **Step5 실엔진 계측 강제 옵션**
   - `run_phase1_steps.py`에 `--require-runtime-hook` 추가
   - Gate-2: `within_guardrail && vram_trend_ok && host_copy_bytes_budget_ok`
3. **Krylov 품질 기준 강화**
   - `orthogonal_krylov_projection.py`에 `--operator-source hook`, `--operator-cmd`
   - `projection_quality.threshold_pass` 기준 적용
4. **Material parser 규정 매핑 확장**
   - `material_type`, `regulation`, `temperature_factor`, `time_factor` 입력 지원
   - `regulation_mapping_pass` 필드 추가


## 다음 개선 제시 (Markdown 기준 우선순위)

### P1) White-box Validation 자동화
- 해야 할 일
  - LF/GNN vs HF FEM 비교 리포트 자동 생성 스크립트 추가
  - 변위/응력/반력/평형잔차 오차표를 공통 포맷(JSON+MD)으로 출력
- 완료 기준
  - 기준 케이스 3종(캔틸레버/라멘/트러스)에서 리포트 자동 생성 100%

### P2) 실 DLPack Zero-copy 실증
- 해야 할 일
  - `zero_copy_bridge_stub.py --producer-cmd`에 실제 Rust HIP producer 연결
  - 포인터 동일성/host_copy_bytes 로그를 CI 아티팩트로 저장
- 완료 기준
  - `roundtrip_success=true`, `shared_storage=true`, `host_copy_bytes=0`

### P3) O(N) 계측 세분화
- 해야 할 일
  - Step5 리포트에 compute/host-copy/serialization 시간 분해 추가
  - 구조 규모별 VRAM budget table과 초과 대응(subgraph 분할) 정책 반영
- 완료 기준
  - Gate-2 통과 + 병목 항목 RCA 자동 출력

### P4) Material parser 신뢰성 고도화
- 해야 할 일
  - 규정 룰셋(versioned rule table) 분리
  - `parser_warnings`를 critical/warn/info 등급화
- 완료 기준
  - `regulation_mapping_pass=true` + critical warning 0건

### P5) LF→GNN E2E CI smoke
- 해야 할 일
  - `ulf_nodes/edges/meta`를 dataloader ingestion 후 단일 배치 추론까지 CI에서 실행
- 완료 기준
  - CI에서 E2E smoke 성공 및 아티팩트 저장


### 진행 반영 (최근 구현)
- `whitebox_validation_report.py` 추가: 3개 기준 케이스의 LF/GNN vs HF 비교 리포트(JSON+MD) 자동 생성
- `kbc_md_material_parser.py` 고도화: versioned rule table(`material_rule_table.json`) 기반 매핑 + warning severity + `parser_quality_pass`
- `run_priority3_modules.py` 판정 강화: parser는 `parser_quality_pass` 기준으로 통합 PASS 처리


## A/B 진행 상태
- **A단계(P5)**: `lf_to_gnn_e2e_smoke.py`로 LF→GNN one-batch smoke 자동화 구현
- **B단계(P2)**: `zero_copy_real_probe.py`로 producer 계약/준비상태 검증 구현 (현재 stub 기준 PASS, `--require-rust-hip`로 실환경 엄격검증 지원)
- **A2 개선**: batch/gain 파라미터 추가, dataloader 형태 배치 반복 경로 도입
- **P3 연계 개선**: Step5에 compute/host-copy/serialization 시간 분해 지표 반영
- **P3 RCA 자동요약**: Step5 리포트에 `rca_summary`(dominant_stage/action_hint) 추가


## 완료 보고 운영 규칙 (요청 반영)

앞으로는 **매 작업 완료 시점마다** 아래 형식으로 다음 구현/개선 요소를 항상 함께 보고한다.

1. 이번 완료 범위 (Done)
2. 즉시 다음 작업 3개 (Next-3)
3. 차순위 작업 3개 (Later-3)
4. 차단 리스크와 해소 조건
5. 다음 보고 시점의 Gate 목표

### 다음 보고 템플릿

- Done:
  - (완료 항목 1)
  - (완료 항목 2)
- Next-3:
  1) (즉시 착수)
  2) (즉시 착수)
  3) (즉시 착수)
- Later-3:
  1) (후속)
  2) (후속)
  3) (후속)
- Risks:
  - (리스크) -> (해소 조건)
- Gate target:
  - (다음 리포트까지 통과할 Gate)

### 현재 기준 다음 구현/개선 요소 (지속 갱신)

- Next-3 (즉시)
  1) `zero_copy_real_probe.py --require-rust-hip` 실제 Rust/HIP producer 연결 검증 (strict gate 스크립트 연결 완료, 실 producer 전환 남음)
  2) `lf_to_gnn_e2e_smoke.py`를 실제 dataloader 경로와 1-batch 추론으로 교체 (project-style GNN 시그니처 연동 완료)
  3) Step5에 compute/host-copy/serialization 시간 분해 지표 추가 (RCA summary + CI fail-rule 반영 완료)

- Later-3 (차순위)
  1) Krylov `orthogonality_error` 임계치 기반 재직교화 자동화
  2) material rule table 버전(예: kbc_2024/ibc_2024) 확장
  3) fallback 정책 파일(`fallback_policy.json`) 분리 및 Gate 연동


- Later-3 1) 진행: Krylov orthogonality threshold + reorthogonalization passes를 projection gate에 연결

- Later-3 3) 진행: `fallback_policy.json` 분리 및 run_phase1_steps Gate 출력에 policy 로드 상태 반영


## 모바일웹 개발환경 우선 전략 (실행 테스트 제외)

모바일웹/저사양 환경에서는 실제 엔진 실행 대신, 문서/계약/스키마/정적 검증 중심으로 진행한다.

- 상세 백로그: `implementation/phase1/mobile-web-dev-only-backlog.md`
- 운영 원칙:
  - 런타임 실행/성능 실측/실 producer 호출은 CI 또는 고성능 환경으로 이관
  - 로컬에서는 인터페이스 명세, 입력 검증, 리포트 스키마, 실패 코드 표준화를 우선 구현

### 즉시 Next-3 (실행 없는 개발 항목)
1) `phase1_ci_gate.py` 입력 유효성 검증 강화(누락 키/범위 오류/NaN 방어)
2) strict rust-hip 실 producer 커맨드 템플릿과 체크리스트 문서화
3) LF→GNN 인터페이스 계약 표와 reason_code 표준화

### 모바일웹 진행 반영 (정적 개발)
- `phase1_ci_gate.py` 입력 검증/`reason_code` 체계를 추가해, 실행 없이도 실패 원인을 판독 가능하도록 개선
- `step5_rca_summary_schema.json` 추가로 RCA 입력 계약을 고정
- `strict-producer-command-template.md` 추가로 실 Rust/HIP 연결 전 문서 기반 준비 작업을 완료
- `lf_to_gnn_e2e_smoke.py` 보고서에 `reason_code`를 추가해 모바일 환경 리뷰 품질을 높임

## 모바일 환경 기준 최신 보고서
- 다음 진행 항목 보고서: `implementation/phase1/mobile-next-steps-report.md`
- 본 보고서는 실행 테스트 없이 진행 가능한 작업만 포함한다.


## 모바일 정적 백로그 진행 상태

- 완료: N1/N2/N3 (reason codebook, interface version policy, material rule changelog template)
- 다음: N4/N5/N6


## 실무권장순서 1~5 진행 상태

1) 동역학/경계조건 계약: `generate_dynamics_boundary_contract.py` + schema 추가
2) PG-GAT 입력 계약: `pg_gat_contract_stub.py` 추가
3) 분할 직교사영 스켈레톤: `subgraph_projection_stub.py` 추가
4) SoA-DLPack 브릿지 스펙: `soa-dlpack-bridge-spec.md` + 계약 리포트 생성기 추가
5) 정적 게이트 연동: `phase1_ci_gate.py`/`validate_phase1_artifacts.py`에 계약 아티팩트 검증 추가


## 다음 구현점 (요청 반영)

- N7/N8/N9: 리포트 공통 메타 필드 강제 및 버전 규약 고도화

- N8/N9 완료: 계약 리포트 메타 정합화 + 버전 규약 문서화

- priority3 메타 정합화 완료: 공통 메타 필드 + metadata mismatch reason_code 반영

- 남은 핵심 3가지 완료: gate2 진단 보강 + ci_gate priority3 병합 + priority3 샘플/fixture 추가


## 최근 반영 (정적 환경 고도화)

- 물리 정합성 계약 추가: `physics_residual_contract_stub.py`
- 잔차/메타학습 task pack 계약 추가: `meta_learning_task_schema.json`, `meta_learning_task_stub.py`
- CI/정적 validator에 신규 계약 아티팩트 연동 완료
