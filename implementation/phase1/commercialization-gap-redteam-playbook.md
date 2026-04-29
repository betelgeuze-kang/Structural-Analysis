# 상용화 레벨 갭 분석/실행 플레이북 (Red Team)

이 문서는 현재 아키텍처의 상용화 차단 요소(P0), 신뢰성 갭(P1), 품질 강화 항목(P2)을
작업 가능한 형태로 고정한 기준 문서다.  
향후 구현은 본 문서를 단일 기준으로 삼아 진행하며, 각 우선순위는 닫히는 즉시 다음 단계로 이동한다.

## 0) 운영 원칙

- 우선순위: `P0 -> P1 -> P2`
- 실행 원칙: 각 항목의 `Exit Gate`가 닫히면 다음 항목으로 이동
- 수행 단위: 1개 워크스트림(에이전트 역할)씩 닫고 다음으로 이동
- 완료 정의: 각 워크스트림의 `Exit Gate`를 만족하고 CI/정적검증 리포트에 반영
- 증빙 원칙: 모든 결과는 `implementation/phase1/*_report.json` 산출물로 남김

### 0-2) Snapshot / release hygiene

- 전체 `pytest` 직후에는 `python3 scripts/check_generated_worktree_clean.py --show-ok`로 `generated worktree clean`을 확인한다. `implementation/phase1/open_data/`, `implementation/phase1/stress/`, `implementation/phase1/panel_zone_solver_verified_*.json`가 dirty면 feature/test 커밋과 섞지 말고 `test side-effect bug`, `legitimate artifact refresh`, `stale local state`로 분류한다.
- generated 변경은 `legitimate artifact refresh`, `test side-effect bug`, `stale local state`의 3가지로 분류한다.
- `test side-effect bug`는 테스트 isolation으로 고치고 generated 파일을 무작정 커밋하지 않는다.
- `legitimate artifact refresh`는 검증 결과와 함께 별도 커밋으로 관리한다.
- `stale local state`는 release artifact refresh 작업과 분리한다.
- snapshot drift cleanup은 테스트 기대값을 현재 deterministic product state에 맞추고, assert는 제거하지 않으며, enum/status는 명시적으로 검증한다.
- `scripts/verify_release_artifacts_manifest.py`는 `--artifact-root` 없이 로컬 `implementation/phase1/release/` 트리를 검증하면 실제 SHA/bytes를 비교하므로 stale local release bundle로는 실패할 수 있다. 이 검증은 clean clone/CI 또는 fresh GitHub Release asset root에서만 하고, 로컬 번들 refresh는 별도 release artifact refresh 작업으로 분리한다.

## 0-1) 실행 맵 (12개 백로그)

1. `[P0] 릴리즈/심의 체인 안정화`
2. `[P0] MIDAS exact roundtrip`
3. `[P0] KDS load-combination engine`
4. `[P0] MIDAS-KDS exact geometry bridge`
5. `[P0] RC constitutive library`
6. `[P0] Steel/composite constitutive library`
7. `[P0] Beam-column / fiber engine`
8. `[P0] Shell / wall / slab engine`
9. `[P1] Foundation / contact / device library`
10. `[P1] Nonlinear solver control`
11. `[P1] Benchmark / validation breadth`
12. `[P2] Design report / results explorer / batch ops`

- 이 12개 항목이 실제 실행 순서이며, 앞 항목이 닫혀야 다음 항목을 시작한다.
- `P0` 범위가 닫히기 전에는 `P1`/`P2`를 승격하지 않는다.

## 1) 에이전트 호출 규약

여기서 "에이전트"는 역할별 최적화 워크스트림 실행자(명령 집합)이다.

1. `Engine Agent`: Rust/HIP 커널/성능 경로
2. `Benchmark Agent`: 공개 벤치마크/정량 검증
3. `Model Agent`: GNN/T-GNN 정확도 향상
4. `Quality Agent`: 테스트/입력검증/로깅
5. `Fallback Agent`: 물리 위반 시 HF 재해석 루프
6. `Docs Agent`: ADD/README/API 문서
7. `Platform Agent`: 패키징/배포/재현성/UI 통합

## 2) 우선순위 상세 카드 (0-1 실행 맵의 하위 정의)

- 아래 상세 카드는 `0-1` 실행 맵의 근거를 설명하는 하위 정의다.

### P0 — 상용화 차단 요소

#### P0-1 Rust/HIP 실엔진 연동 부재
- 현상: Pure Python + NumPy 중심, Rust/HIP 커널 미구현
- 영향: 실시간 성능 불가 (상용 해석기 대비 100~1000x 열세 가능)
- Agent: `Engine Agent`
- Implementation Scope:
  - FIRE/CG HIP 커널
  - Timoshenko Beam Rust 커널
  - Zero-copy DLPack 실경로 검증
- Exit Gate:
  - `strict_rust_hip_pass == true`
  - `host_copy_share <= 0.2`
  - HIP 커널 기준 성능 리포트 생성

#### P0-2 실 벤치마크/검증 데이터 부재
- 현상: Synthetic 중심, MIDAS/SAP2000/실험값 대비 정량 검증 부족
- 영향: MAPE <= 5% KPI 미증명
- Agent: `Benchmark Agent`
- Implementation Scope:
  - 공개 벤치마크 3개 이상 연동
  - RWTH Zenodo 기반 HF 기준셋 구축
  - 대조 리포트 자동 생성
- Exit Gate:
  - 각 도메인 MAPE <= 5%
  - `hf_benchmark_report*.json`에 케이스/출처/오차 명시

#### P0-3 GNN 모델 정확도 미검증
- 현상: MAE gate가 건축 20%, 터널 90%로 완화됨
- 영향: 실무 활용 불가
- Agent: `Model Agent`
- Implementation Scope:
  - 데이터 규모 확대 + hard case mining
  - 모델 구조 개선(T-GNN/Simplicial/Operator)
  - gate 기준 상향
- Exit Gate:
  - 건축/궤도/터널 val MAPE <= 5%
  - rollout phase/time-lag gate 추가 통과

### P1 — 신뢰성/안정성

#### P1-4 단위 테스트 체계 부재
- Agent: `Quality Agent`
- Scope: pytest 단위 테스트 100+ (수렴/정확도/에지)
- Exit Gate: `pytest -q` 통과 + 핵심 모듈 커버리지 리포트

#### P1-5 입력 검증 미흡
- Agent: `Quality Agent`
- Scope: 모든 솔버 진입점에 jsonschema 런타임 검증
- Exit Gate: 잘못된 입력에 대해 명확한 에러 코드/메시지 반환

#### P1-6 에러 핸들링/로깅 미흡
- Agent: `Quality Agent`
- Scope: `except Exception` 축소, 구조화 로깅 도입
- Exit Gate: 워크스트림별 에러 분류코드 + 로그 필드 표준화

#### P1-7 Fallback 정책 실행 미검증
- Agent: `Fallback Agent`
- Scope: 물리 잔차 초과 -> 서브그래프 선별 -> HF 재해석 자동화
- Exit Gate: fallback E2E 시나리오 리포트 + 수렴 보장 증빙

### P2 — 품질 강화

#### P2-8 ADD 철도/터널 통합 미반영
- Agent: `Docs Agent`
- Scope: ADD §1/2/3/6/11/12에 통합 반영
- Exit Gate: 섹션별 diff + 리뷰 체크리스트 PASS

#### P2-9 API/CLI 표준화
- Agent: `Platform Agent`
- Scope: 패키지화, 함수형 API, REST/gRPC 옵션 설계
- Exit Gate: 단일 진입점 + 하위 호환 CLI 유지

#### P2-10 문서/사용자 가이드 미비
- Agent: `Docs Agent`
- Scope: 설치/튜토리얼/API/아키텍처 문서
- Exit Gate: 신규 사용자 온보딩 문서 1회 실행 검증

#### P2-11 패키지/배포 체계 부재
- Agent: `Platform Agent`
- Scope: `pyproject.toml`, 의존성/빌드/배포 정리
- Exit Gate: 깨끗한 설치/빌드/테스트 자동화

#### P2-12 환경 재현성
- Agent: `Platform Agent`
- Scope: 버전 고정, lock, Docker 표준 이미지
- Exit Gate: 클린 환경 재현 실행 성공

#### P2-13 웹 UI 통합 완성도
- Agent: `Platform Agent`
- Scope: `src/app.tsx` <-> 백엔드 해석 파이프라인 연동
- Exit Gate: 실시간 결과 시각화 + 실패/지연 핸들링

## 3) 실행 순서 (권장, 12개 백로그 압축본)

- 아래 5개 묶음은 위 12개 백로그를 실행 묶음으로 압축한 것이다.

1. `P0-1 Engine Agent`
2. `P0-2 Benchmark Agent`
3. `P0-3 Model Agent`
4. `P1-4~P1-7 Quality/Fallback Agent`
5. `P2-8~P2-13 Docs/Platform Agent`

## 4) 에이전트별 표준 실행 명령

### Engine Agent
```bash
python3 implementation/phase1/zero_copy_real_probe.py \
  --producer-cmd "<rust_hip_producer_cmd>" \
  --require-rust-hip \
  --out implementation/phase1/zero_copy_real_probe_report_strict.json
```

### Benchmark Agent
```bash
python3 implementation/phase1/build_cases_from_rwth_zenodo.py \
  --out implementation/phase1/commercial_benchmark_cases.rwth_zenodo.json
python3 implementation/phase1/run_real_accuracy_validation.py \
  --out implementation/phase1/real_accuracy_validation_report.json
```

### Model Agent
```bash
python3 implementation/phase1/run_phased_multidomain_modules.py \
  --out implementation/phase1/phased_multidomain_summary_report.json
python3 implementation/phase1/run_99_9_architecture_pipeline.py \
  --out implementation/phase1/spatiotemporal_data/roadmap_99_9_pipeline_report.json
```

### Quality Agent
```bash
pytest -q
python3 implementation/phase1/validate_phase1_artifacts.py \
  --out implementation/phase1/static_artifact_validation_report.json
```

### Fallback Agent
```bash
python3 implementation/phase1/run_productization_gate.py \
  --out implementation/phase1/spatiotemporal_data/productization_gate_report.json
```

### Docs/Platform Agent
```bash
python3 implementation/phase1/phase1_ci_gate.py \
  --strict-probe implementation/phase1/zero_copy_real_probe_report_strict.json \
  --rca implementation/phase1/step_outputs/step5_rca_summary.json \
  --priority3 implementation/phase1/priority3_summary.json \
  --out implementation/phase1/ci_gate_report.json \
  --manifest implementation/phase1/ci_artifact_manifest.json
```

## 5) 현재 상태(초기값)

- `P0`: Open
- `P1`: Open
- `P2`: Open

업데이트 규칙: 각 작업 완료 시 본 문서의 해당 항목에 `Done + 증빙 파일 경로`를 기록한다.

## 6) 진행 현황 업데이트 (2026-02-27)

### P0-1 Rust/HIP 실엔진 연동
- 상태: `In Progress` (Rust 실커널 경로 + zero-copy 증거 경로 구현)
- 반영 파일:
  - `implementation/phase1/rust_hip_md3bead_hook/src/lib.rs` (신규, Rust CG/Timoshenko 커널 + in-place scale 커널)
  - `implementation/phase1/rust_hip_md3bead_hook/Cargo.toml` (`cdylib` 타겟 추가)
  - `implementation/phase1/rust_track_lf_bridge.py` (신규, ctypes FFI 브리지)
  - `implementation/phase1/rust_hip_md3bead_hook.py` (dlpack probe action을 Rust FFI 실호출 경로로 연결)
  - `implementation/phase1/zero_copy_real_probe.py` (challenge-response + host_copy_share 검증 강화)
  - `implementation/phase1/profile_p0_engine_path.py` (신규, P0 엔진 경로 성능 프로파일 리포트)
  - `implementation/phase1/track_lf_solver.py` (`--engine auto|python|rust` + rust_kernel_used 계약 필드)
  - `implementation/phase1/zero_copy_real_probe_report_strict.json` (재생성)
  - `implementation/phase1/track_lf_solver_report.json` (재생성)
- 적용 내용:
  - Python NumPy-only 경로 외에 Rust 커널 직접 호출 경로를 추가
  - 포인터 동일성/체크섬 기반 in-place zero-copy 증거를 strict probe 리포트에 기록
  - B1 트랙 솔버에서 Rust 커널 사용 여부를 계약 필드로 명시
  - 트랙 솔버 이론별 실행시간/처리율(`elapsed_seconds`, `node_updates_per_second`)을 리포트에 기록
  - P0 파이프라인에서 엔진 성능 프로파일(`p0_engine_perf_report.json`)을 함께 생성/검증

### P0-2 실 벤치마크/검증 데이터
- 상태: `In Progress` (RWTH 공개데이터 기반 HF 기준 케이스 고정 + gate 추가)
- 반영 파일:
  - `implementation/phase1/build_cases_from_rwth_zenodo.py`
  - `implementation/phase1/run_real_accuracy_validation.py`
  - `implementation/phase1/run_p0_core_gap_pipeline.py` (신규)
  - `implementation/phase1/commercial_benchmark_cases.rwth_zenodo.json` (재생성, public_benchmark_cases 포함)
  - `implementation/phase1/real_accuracy_validation_report.json` (재생성)
  - `implementation/phase1/p0_core_gap_report.json` (신규)
- 적용 내용:
  - HF case payload에 DOI/출처(member) 메타데이터를 추가
  - `public_benchmark_cases`(최소 3개) 강제 생성 및 검증
  - metric source 기본값을 `open_data_measurement`로 상향
  - P0-1+P0-2를 단일 러너에서 재현하는 파이프라인 추가

### P0-3 GNN 모델 정확도/게이트 강화
- 상태: `In Progress` (5% 게이트 상향 + CPU fallback 금지 정책 반영)
- 반영 파일:
  - `implementation/phase1/train_tgnn_baseline.py`
  - `implementation/phase1/run_phased_multidomain_modules.py`
  - `implementation/phase1/phase1_ci_gate.py`
  - `implementation/phase1/no-cpu-fallback-policy.md` (신규)
- 적용 내용:
  - Phase-D 기본 임계치를 `20/20/90`에서 `5/5/5`로 상향
  - `rollout_val_gate_pass`를 계약 필드로 추가
  - `cpu_fallback_used == false`를 CI gate 조건으로 강제
  - 가속기 부재 상황에서 CPU 실행은 `--allow-cpu-required` 명시 시에만 허용

### P1-5 입력 검증 미흡
- 상태: `In Progress` (핵심 솔버/러너 적용 완료)
- 반영 파일:
  - `implementation/phase1/runtime_contracts.py`
  - `implementation/phase1/track_lf_solver.py`
  - `implementation/phase1/moving_load_integrator.py`
  - `implementation/phase1/vti_coupled_solver.py`
  - `implementation/phase1/track_irregularity_generator.py`
  - `implementation/phase1/tunnel_graph_converter.py`
  - `implementation/phase1/tunnel_segment_joint_nonlinear.py`
  - `implementation/phase1/soil_tunnel_ssi.py`
  - `implementation/phase1/train_passage_load_generator.py`
  - `implementation/phase1/tunnel_seismic_longitudinal.py`
  - `implementation/phase1/run_phaseb_track_modules.py`
  - `implementation/phase1/run_phasec_tunnel_modules.py`
- 적용 내용:
  - 각 CLI 진입점에 JSON Schema 기반 런타임 입력 검증 추가
  - 계약 위반 시 `ERR_INVALID_INPUT`로 일관된 리포트 생성

### P1-6 에러 핸들링/로깅 미흡
- 상태: `In Progress` (구조화 로그 표준 도입 완료)
- 반영 파일:
  - `implementation/phase1/runtime_contracts.py`
  - 상기 P1-5 반영 모듈 전체
  - `implementation/phase1/run_p0_core_gap_pipeline.py`
  - `implementation/phase1/run_real_accuracy_validation.py`
  - `implementation/phase1/run_phased_multidomain_modules.py`
- 적용 내용:
  - `log_event()` 기반 JSON-line 로그(`start/completed/invalid_input/internal_error`) 추가
  - 기존 broad `except Exception`의 분기 전처리로 입력 오류와 내부 오류를 구분 로깅

### P1-4 단위 테스트 체계
- 상태: `In Progress` (기초 단위 테스트 확장)
- 반영 파일:
  - `tests/test_runtime_contracts.py` (신규)
- 증빙:
  - `python3 -m pytest -q` -> `73 passed`

## 7) Real Project Corpus P0/P1/P2 Closeout Track (2026-04-27)

나라장터(KONEPS) 턴키/기술제안 설계도서와 PEER TBI 초고층 benchmark는 상용툴 대체성 검증을 위한 real-project corpus track으로 관리한다. 이 track은 무작정 다운로드/크롤링하지 않고 `provenance -> parser/benchmark coverage -> P1-3 row provenance -> automation/release` 순서로 닫는다. P1-3 gate는 parser/benchmark row가 source family, access policy, checksum-or-withheld reason, file inventory status, parser contract, row pointer, release-surface eligibility를 갖춰야 P2로 올라간다는 뜻이다. CLI는 `implementation/phase1/build_real_project_row_provenance_report.py`, generated output은 `implementation/phase1/real_project_row_provenance_report.json`이다. 세부 운영 기준은 [Real Project Corpus closeout guide](../../docs/real-project-corpus.md)에 맞춘다. 아직 파일명이 확정되지 않은 구현은 파일명보다 역할 기준으로 적는다: manifest, validator, parser matrix, benchmark record, crawler, redaction, release viewer, report surface. PEER TBI는 citation-first benchmark family이며, raw model/input deck redistribution은 document-level review가 끝나기 전에는 금지다.

### P0-RP. Provenance / license / security / checksum / manual-review gate
- 상태: `In Progress`
- 반영 범위:
  - corpus manifest/schema
  - seed manifest
  - validation script
  - targeted test
- Exit Gate:
  - KONEPS source family는 public metadata, announcement/notice, attachment access, retrieved file, redistributable artifact를 구분한다.
  - PEER TBI source family는 citation-first benchmark family로 취급하고, citation과 benchmark metric record를 먼저 고정한다. raw model/input deck redistribution은 document-level review가 끝나기 전에는 금지다.
  - 각 source family가 official entrypoint, jurisdiction, access policy, target file type, P0 exit gate를 가진다.
  - `restricted`, `unknown`, `redacted` source/artifact는 `redistribution_allowed=true`가 될 수 없다.
  - `downloaded` artifact는 `sha256`, `bytes`, `file_inventory`, manual-review 결과 없이는 통과하지 않는다.
  - CI에서 seed manifest validation과 targeted test가 통과한다.

### P1-3. Real-Project Row Provenance
- 상태: `In Progress` (seed report generator/test 구현, generated JSON은 local/CI 산출물)
- P1-3 gate:
  - parser/benchmark row가 source family, access policy, checksum-or-withheld reason, file inventory status, parser contract, row pointer, release-surface eligibility를 모두 갖춘 경우에만 P2로 승격한다.
  - KONEPS는 public metadata, announcement/notice, attachment access와 redistributable artifact를 구분한다.
  - PEER TBI는 citation-first benchmark record는 허용하되 raw model/input deck redistribution은 document-level review 전 금지다.
  - CLI는 `implementation/phase1/build_real_project_row_provenance_report.py`, generated output은 `implementation/phase1/real_project_row_provenance_report.json`이다.

### P1-RP. Parser coverage / benchmark metric gate
- 상태: `In Progress` (P1 parser/benchmark coverage matrix seed 및 PEER TBI metric record seed 구현)
- PEER TBI metric record는 P1의 active gate다. citation-linked benchmark record가 고정되어야 P2 crawler/redaction/report surface로 넘어갈 수 있다.
- 반영 범위:
  - parser/benchmark coverage matrix generator
  - deterministic coverage matrix JSON
  - PEER TBI benchmark metric record generator
  - deterministic PEER TBI benchmark metric record JSON
  - targeted test
- Exit Gate:
  - KONEPS 후보는 `.mgt/.ifc/.dwg/.dxf/.pdf/.xlsx` 추출 coverage와 `typed/raw-preserved/excluded/blocked` classification을 낸다.
  - PEER TBI 후보는 `citation`, `period`, `base_shear`, `story_drift`, `nonlinear_response`를 citation-linked benchmark record로 고정한다. raw model/input deck redistribution은 document-level review가 끝나기 전에는 금지다.
  - P1-3 row provenance gate를 통과한 parser/benchmark row만 release/report surface로 올린다.

### P2-RP. Automation / redaction / delivery surface gate
- 상태: `Pending after P1-RP`
- Exit Gate:
  - crawler refresh가 rate-limit, robots/terms, checksum, manual-review 상태를 보존한다.
  - redaction policy가 보안/재배포 제한 artifact를 release package에서 제외한다.
  - viewer/report/release registry에 corpus source, checksum, benchmark status가 표시된다.
  - release surface는 source ingestion과 redacted delivery artifact를 분리해서 보여준다.
