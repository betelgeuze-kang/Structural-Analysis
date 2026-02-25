# Phase 1 실행 산출물: LF 출력 스키마/검증

Section 11-5에서 정의한 LF → GNN 연동 계약을 실제 파일 스키마로 구체화했습니다.

## 포함 파일

- `lf_output_schema.json`: LF 출력 JSON 스키마
- `generate_lf_sample.py`: 샘플 LF 결과 생성기
- `validate_lf_output.py`: LF 출력 계약 검증기
- `complexity_profile.py`: O(N) 선형성 가드레일 점검기 (`complexity_report.json` 생성)

## 단계 1~6 일괄 실행

```bash
python implementation/phase1/run_phase1_steps.py --out-dir implementation/phase1/step_outputs --repeats 3 --strict
```

실엔진 계측 강제 모드:

```bash
python implementation/phase1/run_phase1_steps.py \
  --out-dir implementation/phase1/step_outputs \
  --repeats 3 --strict --require-runtime-hook \
  --engine-hook-cmd "python implementation/phase1/engine_hook_stub.py" \
  --runtime-hook-cmd "python implementation/phase1/engine_hook_stub.py"
```

- `--require-runtime-hook`를 켜면 runtime hook이 없을 때 실패합니다.
- Step5는 `peak_vram_bytes`, `host_copy_bytes`를 받아 Gate-2에서 함께 판정합니다.

## 1순위 구현 (직교사영 잔차 보정 스캐폴드)

```bash
python implementation/phase1/orthogonal_projection_update.py \
  --out implementation/phase1/projection_update_report.json --alpha 0.35
```

## 우선순위 1/2/3/4 실행

### 1) Zero-copy bridge 검증 (외부 producer 명령 지원)
```bash
python implementation/phase1/zero_copy_bridge_stub.py \
  --out implementation/phase1/zero_copy_bridge_report.json \
  --producer-cmd "python implementation/phase1/engine_hook_stub.py"
```

### 2) 역행렬 없는 Krylov 직교사영 (외부 A·v 연산자 훅)
```bash
python implementation/phase1/orthogonal_krylov_projection.py \
  --out implementation/phase1/krylov_projection_report.json \
  --alpha 0.35 --m 4 --operator-source hook \
  --operator-cmd "python implementation/phase1/engine_hook_stub.py" \
  --reduction-threshold 0.98 \
  --orthogonality-threshold 1e-6
```

- `projection_quality.reason_code` / `suggested_reorth_pass`로 재직교화 정책을 정적으로 확인할 수 있습니다.

### 3) KBC/IBC ↔ 2-Bead MD 물성치 파서 확장
```bash
python implementation/phase1/kbc_md_material_parser.py \
  --input implementation/phase1/material_input_sample.csv \
  --out implementation/phase1/material_map_report.json
```

### 통합 실행 (권장)

```bash
python implementation/phase1/run_priority3_modules.py --out-dir implementation/phase1 --alpha 0.35 --m 4
```

- `priority3_summary.json`에서 통합 PASS/FAIL을 확인합니다.
- pass 조건:
  - zero-copy: `roundtrip_success && shared_storage && host_copy_bytes == 0`
  - krylov: `projection_quality.threshold_pass && projection_quality.orthogonality_pass`
  - parser: `parser_quality_pass` (unit/regulation/critical-warning 동시 통과)


### 4) White-box Validation 자동 리포트
```bash
python implementation/phase1/whitebox_validation_report.py \
  --out-json implementation/phase1/whitebox_validation_report.json \
  --out-md implementation/phase1/whitebox_validation_report.md \
  --acceptance-rel-err 0.03 \
  --acceptance-abs-residual 0.01
```

- HF FEM 기준 대비 LF/GNN 상대오차를 케이스별로 자동 비교하고 PASS/FAIL을 출력합니다.


### 5) Priority-A: LF→GNN E2E smoke
```bash
python implementation/phase1/lf_to_gnn_e2e_smoke.py \
  --nodes implementation/phase1/step_outputs/ulf_nodes.csv \
  --edges implementation/phase1/step_outputs/ulf_edges.csv \
  --meta implementation/phase1/step_outputs/ulf_meta.json \
  --batch-size 2 --gain 0.001 \
  --out implementation/phase1/lf_to_gnn_e2e_smoke_report.json
```

### 6) Priority-B: Zero-copy real producer probe
```bash
python implementation/phase1/zero_copy_real_probe.py \
  --producer-cmd "python implementation/phase1/engine_hook_stub.py" \
  --out implementation/phase1/zero_copy_real_probe_report.json
```

- 실제 Rust/HIP producer 연결 시 `--require-rust-hip` 옵션으로 엄격 판정을 켤 수 있습니다.
- 실 producer 커맨드 템플릿: `implementation/phase1/strict-producer-command-template.md`

- `zero_copy_real_probe_report.json`에서 `strict_rust_hip_pass`를 확인해 실 Rust/HIP 연결 준비도를 판정합니다.
- `step5_runtime_hook_profile.json`에 `rca_summary`(병목 단계/개선 힌트)가 포함됩니다.


Rust/HIP strict probe 예시(모의 producer):
```bash
python implementation/phase1/zero_copy_real_probe.py \
  --producer-cmd "python implementation/phase1/rust_hip_mock_producer.py" \
  --require-rust-hip \
  --out implementation/phase1/zero_copy_real_probe_report_strict.json
```
- Step5 실행 시 `step_outputs/step5_rca_summary.json`도 함께 생성됩니다.


CI Gate 실행 예시:
```bash
python implementation/phase1/phase1_ci_gate.py \
  --strict-probe implementation/phase1/zero_copy_real_probe_report_strict.json \
  --rca implementation/phase1/step_outputs/step5_rca_summary.json \
  --max-host-copy-share 0.2 \
  --out implementation/phase1/ci_gate_report.json \
  --manifest implementation/phase1/ci_artifact_manifest.json
```

## LF→GNN smoke 계약(모바일 개발용 정적 기준)

### 입력 필수
- nodes CSV: `node_id, ux, uy, uz, f_norm`
- edges CSV: 최소 1행 이상
- meta JSON: `unit_system` 필수

### 출력 핵심 필드
- `pass` (bool)
- `reason_code` / `reason`
- `inference.backend` (`torch` 또는 `python`)

### `reason_code` 표준
- `PASS`
- `ERR_EMPTY_NODES`
- `ERR_EMPTY_EDGES`
- `ERR_META_UNIT`
- `ERR_EMPTY_CORRECTION`

## CI Gate 입력 계약(모바일 개발용 정적 기준)

- strict probe report: `strict_rust_hip_pass` 포함
- RCA summary: `timing_breakdown_seconds.compute/host_copy/serialization` 포함
- schema 참고: `implementation/phase1/step5_rca_summary_schema.json`
- fallback policy 연동: `step6_gate_report.json`의 `fallback_policy_version`/`fallback_policy_fingerprint` 확인

fallback 정책 스펙: `implementation/phase1/fallback-policy-spec.md`

## 모바일 환경용 정적 아티팩트 검증

런타임 의존성 없이 현재 보고서 파일들의 계약 일치 여부를 점검합니다.

```bash
python implementation/phase1/validate_phase1_artifacts.py \
  --smoke implementation/phase1/lf_to_gnn_e2e_smoke_report.json \
  --ci implementation/phase1/ci_gate_report.json \
  --rca implementation/phase1/step_outputs/step5_rca_summary.json \
  --physics-residual implementation/phase1/physics_residual_contract_report.json \
  --meta-learning implementation/phase1/meta_learning_task_report.json \
  --out implementation/phase1/static_artifact_validation_report.json
```


## 모바일웹 개발환경 가이드 (실행 테스트 제외)

실제 런타임 테스트가 어려운 환경에서는 아래 백로그를 기준으로 문서/계약/정적검증 중심 개발을 진행합니다.

- `implementation/phase1/mobile-web-dev-only-backlog.md`
- `implementation/phase1/mobile-next-steps-report.md`
- `implementation/phase1/high-fidelity-gap-analysis.md`
- 권장 순서: CI gate 입력검증 강화 -> strict producer 연결 템플릿 문서화 -> LF→GNN 인터페이스 계약 표준화


## 모바일 정적 개발 문서 (추가)

- CI reason codebook: `implementation/phase1/ci-gate-reason-codebook.md`
- LF→GNN 인터페이스 버전 정책: `implementation/phase1/interface-version-policy.md`
- Material rule changelog 템플릿: `implementation/phase1/material-rule-changelog-template.md`
- Material rule changelog: `implementation/phase1/material-rule-changelog.md`


## 실무권장순서 1~5 (모바일 정적 구현)

```bash
python implementation/phase1/generate_dynamics_boundary_contract.py \
  --out implementation/phase1/dynamics_boundary_report.json

python implementation/phase1/pg_gat_contract_stub.py \
  --out implementation/phase1/pg_gat_contract_report.json

python implementation/phase1/subgraph_projection_stub.py \
  --out implementation/phase1/subgraph_projection_report.json

python implementation/phase1/generate_soa_dlpack_contract.py \
  --out implementation/phase1/soa_dlpack_contract_report.json

python implementation/phase1/physics_residual_contract_stub.py \
  --out implementation/phase1/physics_residual_contract_report.json

python implementation/phase1/meta_learning_task_stub.py \
  --out implementation/phase1/meta_learning_task_report.json

python implementation/phase1/buckling_eigen_contract_stub.py \
  --out implementation/phase1/buckling_contract_report.json

python implementation/phase1/benchmark_kpi_contract_stub.py \
  --out implementation/phase1/hf_benchmark_report.json

python implementation/phase1/phase1_ci_gate.py \
  --strict-probe implementation/phase1/zero_copy_real_probe_report_strict.json \
  --rca implementation/phase1/step_outputs/step5_rca_summary.json \
  --out implementation/phase1/ci_gate_report.json \
  --manifest implementation/phase1/ci_artifact_manifest.json

python implementation/phase1/validate_phase1_artifacts.py \
  --physics-residual implementation/phase1/physics_residual_contract_report.json \
  --meta-learning implementation/phase1/meta_learning_task_report.json \
  --buckling implementation/phase1/buckling_contract_report.json \
  --benchmark implementation/phase1/hf_benchmark_report.json \
  --out implementation/phase1/static_artifact_validation_report.json
```

참고 문서:
- `implementation/phase1/dynamics-boundary-contract.md`
- `implementation/phase1/soa-dlpack-bridge-spec.md`
- `docs/review-checklist-mobile.md`


## 다음 구현점

- 공통 메타 필드 강제: `schema_version`, `run_id`, `generated_at`
- 정적 validator에서 메타 누락 시 FAIL 처리

- 메타 버전 규약: `implementation/phase1/report-metadata-versioning-policy.md`

- `priority3_summary.json` 메타 필드(`schema_version/run_id/generated_at`) 및 `reason_code` 포함

- Priority3 샘플: `priority3_summary.pass.sample.json`, `priority3_summary.fail.sample.json`
- Mismatch fixture: `priority3_metadata_mismatch_fixture.json`
- CI gate priority3 병합 예시: `python implementation/phase1/phase1_ci_gate.py --priority3 implementation/phase1/priority3_summary.json ...`


## A→B→C 단계 구현 (미분없는 경로분기 학습/추론)

A/B/C는 **역전파 없는 학습추론**이 아니라, 요청하신 대로 **미분없는 경로분기(물리적으로 가능한 경로)** 기준으로 구현됩니다.

```bash
python implementation/phase1/run_abc_sequence.py --out-dir implementation/phase1

# or run each phase explicitly
python implementation/phase1/physics_guided_branching.py   --mode train   --out implementation/phase1/physics_branching_report.json

python implementation/phase1/bifurcation_detector_stub.py   --out implementation/phase1/bifurcation_detector_report.json

python implementation/phase1/rust_onnx_native_contract_stub.py   --out implementation/phase1/rust_onnx_native_contract_report.json

# winner-only targeted backprop on physically-admissible branch
python implementation/phase1/winning_ticket_backprop.py   --branches 16   --out implementation/phase1/winning_ticket_backprop_report.json
```

CI gate / static validation now also consume these artifacts.
