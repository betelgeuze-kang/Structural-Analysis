# Phase 1 실행 산출물: LF 출력 스키마/검증

Section 11-5에서 정의한 LF → GNN 연동 계약을 실제 파일 스키마로 구체화했습니다.

## 포함 파일

- `lf_output_schema.json`: LF 출력 JSON 스키마
- `generate_lf_sample.py`: 샘플 LF 결과 생성기
- `validate_lf_output.py`: LF 출력 계약 검증기
- `complexity_profile.py`: O(N) 선형성 가드레일 점검기 (`complexity_report.json` 생성)

## 철도/터널 확장 마스터 플랜

- `railway_tunnel_dynamics_reinforcement_plan.md`
- 건축 + 철도(궤도/터널) 복합 동역학 확장 로드맵(Phase A~E), 검증계획, 리스크 대응, 우선순위를 정의합니다.

## 상용화 갭 분석/실행 플레이북 (Red Team)

- `commercialization-gap-redteam-playbook.md`
- P0/P1/P2 상용화 갭, 12개 우선순위 백로그, 에이전트(역할)별 실행 규약, Exit Gate, 표준 실행 명령을 정의합니다.
- `agent-invocation-log.md`
- 실제 에이전트(역할) 호출 기록과 실행 결과를 누적합니다.
- `commercial_tool_replacement_roadmap.md`
- 내부 게이트 녹색 상태 이후에도, MIDAS 대체 로드맵과 Abaqus/OpenSees gap map을 닫힘 기준으로 어떻게 단계적으로 대체할지 정리한 로드맵입니다.
- `validate_midas_section_library_artifacts.py`
- canonical MIDAS JSON에 `model.metadata.section_library`가 실제로 들어 있는지 검사하는 스모크 검증기입니다.
- `backfill_midas_section_library_metadata.py`
- 기존 MIDAS JSON에 embedded section-library 메타데이터를 다시 써 넣는 운영 도구입니다.
- `MIDAS Section Library` 패널의 `open representative member`
- section row를 누르면 대표 부재를 열고, 같은 section을 쓰는 baseline 부재를 함께 강조합니다.
- `design_optimization/README.md`
- 설계 최적화 계층의 bounded refactor namespace, 공통 artifact path, entrypoint 정리 방향을 설명합니다.
- `design_optimization/bounded_refactor_plan.md`
- 대규모 이동 없이 어떤 경계만 먼저 고정할지에 대한 제한적 리팩토링 계획입니다.
- `design_optimization/major_refactor_entry_criteria.md`
- 언제 repo-wide 대규모 리팩토링으로 넘어가도 되는지에 대한 진입 기준입니다.

## 실행 기준

- 이 디렉터리의 상용화 문서는 달력표가 아니라 `닫힘 기준`으로 연결됩니다.
- `commercialization-gap-redteam-playbook.md`는 12개 백로그와 Exit Gate를 정의합니다.
- `commercial_tool_replacement_roadmap.md`는 MIDAS 대체 로드맵과 Abaqus/OpenSees gap map을 축 1~5로 압축합니다.
- `docs/architecture-definition-document.md`는 달력 주차가 아니라 closure-based execution order를 유지합니다.

## MIDAS Section Library 운영 노트

- canonical MIDAS JSON 3개는 `model.metadata.section_library`를 embedded metadata로 포함합니다.
- validator와 CI gate는 `MIDAS section-library: ok | 182/183 used | 183 templates | source=...` 형식의 한 줄 요약을 같이 남깁니다.
- nightly `nightly_release_gate_report.json` summary cards와 release gap / committee dashboard, external validation one-page도 같은 section-library 요약을 그대로 소비합니다.
- dashboard summary와 `Selected Member` 패널은 같은 section을 쓰는 baseline 부재 수를 함께 노출합니다.
- summary에는 `same section N baseline members`, `1/N representative linked`, `related M` 형태의 metric이 보입니다.
- 확인 명령:

```bash
python implementation/phase1/validate_midas_section_library_artifacts.py --require
python implementation/phase1/phase1_ci_gate.py
```

```bash
python implementation/phase1/generate_structural_optimization_visualization_viewer.py
python implementation/phase1/generate_release_gap_report.py
python implementation/phase1/generate_committee_review_package.py
python -m pytest -q tests/test_generate_structural_optimization_visualization_viewer.py tests/test_phase1_ci_gate.py tests/test_validate_midas_section_library_artifacts.py
```

- viewer의 `MIDAS Section Library` 패널에서 `open representative member`를 누르면 대표 부재와 같은 section을 쓰는 baseline 부재가 함께 강조됩니다.

## Viewer Reading Mode

- `Core workflow`는 화면 상단의 핵심 동선입니다. 처음 보는 사람은 여기서 `Interactive 3D -> Baseline -> Changed Overlay -> Story-Zone Map -> MIDAS libraries -> Results` 순서로 보면 됩니다.
- `Core only`는 핵심 surface만 남기고, `Show all`은 release viewer의 고급 surface까지 다시 펼칩니다.
- 현재 구현된 URL 공유 방식은 `?view=core`와 `?view=all`입니다. 같은 HTML을 열더라도 이 파라미터로 기본 읽기 모드를 고정할 수 있습니다.
- 향후 role-based preset이 더 늘어나면 같은 `view=` 패턴을 재사용하는 쪽이 가장 단순합니다. 예를 들어 `review`, `midas`, `compare`처럼 역할별 preset을 추가해도 공유 규칙은 그대로 유지하는 편이 좋습니다.
- 추천 공유 예시:

```text
.../structural_optimization_viewer.html?view=core
.../structural_optimization_viewer.html?view=all
```

## MIDAS/KDS Geometry Bridge 운영 노트

- 현재 canonical MIDAS 3개는 `kds_geometry_bridge` 계약을 embedded metadata로 포함하며, `mapped_review_ids=12/12`, `exact=12/12`, `heuristic=0/12`입니다.
- validator/workflow/CI/release/committee surface는 이제 같은 full-crosswalk closure를 공유하며 `full_member_crosswalk=242/242 PASS`, `full_section_crosswalk=200/200 PASS`, `full_load_crosswalk=51/51 PASS`, `geometry_diff=36/36 PASS`로 닫혔습니다. reviewer-verified exact bridge는 더 이상 pending이 아니라 closed baseline입니다.
- `midas_kds_geometry_bridge_full_crosswalk_depth=36`는 `load_crosswalk`와 `semantic_crosswalk`의 최소 깊이로, CI/release/committee가 같은 exact bridge depth를 공유하도록 정규화하는 중입니다.
- live CI/release/committee surface에는 `support_search=9 | node_surface_proxy=5 | support_depth=21`도 함께 올라가서 foundation/device/contact 신호를 같은 summary stream에서 읽을 수 있습니다.
- live NDTHA summary에는 `ndtha_material_depth=3 | material_model=rc_composite`도 함께 올라가서 step-series depth와 material-depth를 같이 볼 수 있습니다.
- exact registry 생성물: `implementation/phase1/open_data/midas/kds_geometry_bridge_registry.exact.json`
- heuristic registry 생성물: `implementation/phase1/open_data/midas/kds_geometry_bridge_registry.heuristic.json` (legacy fallback)
- 운영자 관점에서 이 값은 `브리지 계약은 존재하고, KDS semantic review id와 MIDAS baseline geometry의 exact 1:1 crosswalk가 닫혔다`를 뜻합니다.
- 따라서 지금의 `MIDAS kds-geometry-bridge: ok`는 매핑 완료를 의미합니다. `검증기와 게이트, 대시보드는 exact bridge PASS를 확인했다`로 읽어야 합니다.
- exact baseline member focus는 exact bridge가 잡힌 경우에만 자동으로 열리고, 그렇지 않으면 `bridge unavailable` 경로로 명시됩니다.
- 운영 명령:

```bash
python implementation/phase1/validate_midas_kds_geometry_bridge_artifacts.py --require
python implementation/phase1/phase1_ci_gate.py
python implementation/phase1/generate_release_gap_report.py
python implementation/phase1/generate_committee_review_package.py
```

- 현재 필요한 후속 작업은 exact registry를 canonical corpus와 함께 유지/확장하는 것이며, 다음 활성 타겟은 core engine depth이고 첫 활성 closure step은 `contact-material integration`입니다. geometry bridge는 `traceable-but-closed` baseline으로 읽어야 합니다.

## MIDAS Exact Roundtrip 운영 노트

- `run_midas_native_roundtrip_gate.py`는 native write-back exact roundtrip gate입니다. `midas_native_corpus_manifest.json`과 `midas_native_writeback_diff_receipts_report.json`을 함께 읽고, `contract_pass=True`일 때만 현재 exact-closure target scope가 닫혔다고 봅니다. 이 scope에는 실제 native roundtrip evidence만 넣고, intentional optimized writeback 산출물과 parser-drop fixture는 closure evidence에서 제외합니다.
- `PASS`는 corpus가 존재한다는 뜻이 아니라, target scope 안에서 topology/load/loadcomb 안정성, receipt coverage, zero unknown rows, taxonomy, exact queue/promotion evidence가 모두 맞았다는 뜻입니다. 현재 canonical exact roundtrip closure scope는 닫혀 있고, `load-combination engine`, `MIDAS-KDS exact geometry bridge`, `structural contact`, `workflow/interoperability productization`, `RC constitutive`, `steel/composite constitutive`가 canonical evidence 기준 `PASS`이므로 다음 활성 게이트는 core engine depth의 `contact-material integration`입니다.
- raw-recovery artifact가 내려오면, 그 안에서만 minimal structured loads backfill을 적용합니다. 이후 artifact가 재생성되더라도 같은 조건부 규칙을 그대로 따릅니다.
- `reason_code`는 운영적으로 `PASS`, `ERR_CORPUS`, `ERR_RECEIPTS`, `ERR_WRITEBACK`만 보면 됩니다. `ERR_RECEIPTS`는 diff receipt coverage 부족, `ERR_WRITEBACK`은 ready case 중 exact fidelity 또는 topology/load/loadcomb 안정성 실패로 해석하면 됩니다.
- `summary_line`의 `exact_queue`, `korean_reconstruction`, `korean_promotions`는 backlog 상태입니다. `exact_queue>0`이어도 gate가 `PASS`일 수 있고, 이는 아직 promote되지 않은 후보가 남아 있다는 뜻이지 실패가 아닙니다.
- `run_midas_interoperability_gate.py`는 roundtrip보다 넓은 preview/export evidence gate입니다. 여기서는 `exact_entry_row_min`이 현재 bounded subset의 핵심 fidelity signal이고, `PASS`는 bounded subset의 preview/export evidence가 충분하다는 의미입니다.
- `run_load_combination_engine_gate.py`는 canonical evidence 기준 `PASS`입니다.
- `ndtha_step_series_depth=2400`은 현재 CI/release/committee에 surfacing되는 max completed step-series depth입니다.

```bash
python implementation/phase1/run_midas_native_roundtrip_gate.py \
  --corpus-manifest implementation/phase1/open_data/midas/midas_native_corpus_manifest.json \
  --diff-receipts-report implementation/phase1/release/midas_native_roundtrip/midas_native_writeback_diff_receipts_report.json

python implementation/phase1/run_midas_interoperability_gate.py \
  --out implementation/phase1/midas_interoperability_gate_report.json

python implementation/phase1/run_load_combination_engine_gate.py \
  --out implementation/phase1/load_combination_engine_gate_report.json
```

## Phase3 실데이터 하드닝 실행 (METIS + Adaptive Newton)

## 실험파일 정리 정책

- 주요 러너(`run_phase3_megastructure_pipeline.py`, `run_partitioned_scaleout.py`, `run_scaleout_io_profile.py`, `run_noise_convergence_gate.py`, `run_noise_sensitivity_stress.py`, `run_nightly_release_gate.py`)는 실행 종료 시 산출물을 자동으로 `experiments/by_test/<test>/<timestamp>/`로 아카이브합니다.
- 최신 아카이브 포인터는 `experiments/by_test/<test>/latest_manifest.json`에 기록됩니다.
- 과거 `sample/seed` 계열 파일 정리는 아래 명령으로 수행합니다.

```bash
python3 implementation/phase1/experiment_artifact_archive.py --cleanup-legacy
```

## Global Authority (SAC/OpenSees/NHERI) 게이트

```bash
# OpenSees + SAC + NHERI authority track (catalog의 holdout 케이스 포함)
python implementation/phase1/run_global_authority_gate.py \
  --catalog implementation/phase1/open_data/global_authority/authority_source_catalog.json \
  --out implementation/phase1/global_authority_gate_report.json

# strict 강제 실행 (SAC/NHERI 포함)
python implementation/phase1/run_global_authority_gate.py \
  --catalog implementation/phase1/open_data/global_authority/authority_source_catalog.json \
  --require-sac \
  --require-nheri \
  --out implementation/phase1/global_authority_gate_report.json

# 원시 CSV로 권위 메트릭 자동 생성 후 검증 (옵션)
python implementation/phase1/run_global_authority_gate.py \
  --catalog implementation/phase1/open_data/global_authority/authority_source_catalog.json \
  --require-sac \
  --require-nheri \
  --auto-generate-metrics \
  --out implementation/phase1/global_authority_gate_report.json
```

- 전략 문서: `implementation/phase1/global_authority_two_track.md`
- 카탈로그: `implementation/phase1/open_data/global_authority/authority_source_catalog.json`
- 기본 최소 케이스 정책: `SAC >= 3`, `NHERI >= 3` (미달 시 gate fail)
- 누수 방지 정책: `split_manifest_path`에 등록된 `holdout` 케이스만 권위 게이트 허용

## 벤치마크 다양화

- 계획 문서: `implementation/phase1/open_data/BENCHMARK_DIVERSIFICATION_PLAN.md`
- 후보 카탈로그: `implementation/phase1/open_data/benchmark_diversification_catalog.json`
- 목적: 현재 반복적으로 쓰는 단일 MIDAS 설계 파일 편향을 줄이고, `wind / hinge / foundation / panel` holdout에 직접 먹히는 공식 benchmark source를 우선 확장합니다.
- TPU wind seed manifest materializer:
  `python implementation/phase1/prepare_tpu_hffb_seed.py --seed-id tpu_hffb_isolated_highrise_seed_01 --raw-wind path/to/raw.csv`
- PEER SPD hinge fixture normalizer:
  `python implementation/phase1/normalize_peer_spd_column_seed.py --seed-id peer_spd_rc_column_rebar_sensitive_seed_01 --raw-specimen-json path/to/specimen.json`

```bash
# PR gate (1M/3M + noise seeds 11/23/47 + GPU strict)
python implementation/phase1/run_phase3_megastructure_pipeline.py \
  --candidate-id zenodo_atwood_highrise_shm_2025 \
  --input-path implementation/phase1/open_data/megastructure \
  --opensees-model implementation/phase1/open_data/megastructure/opensees/SCBF16B_shell_beam_mix.tcl \
  --download-if-missing \
  --require-real-source \
  --require-real-topology \
  --require-shell-beam-mix \
  --gpu-strict \
  --ci-mode pr \
  --scale-levels-pr 1000000,3000000 \
  --noise-seeds 11,23,47 \
  --noise-stiffness-levels-pct 5,10 \
  --noise-min-seed-count 3 \
  --summary-out implementation/phase1/phase3_megastructure_pipeline_report.json

# Nightly gate (adds 10M DOF)
python implementation/phase1/run_phase3_megastructure_pipeline.py \
  --candidate-id zenodo_atwood_highrise_shm_2025 \
  --input-path implementation/phase1/open_data/megastructure \
  --opensees-model implementation/phase1/open_data/megastructure/opensees/SCBF16B_shell_beam_mix.tcl \
  --download-if-missing \
  --require-real-source \
  --require-real-topology \
  --require-shell-beam-mix \
  --gpu-strict \
  --ci-mode nightly \
  --scale-levels-nightly 1000000,3000000,10000000 \
  --noise-seeds 11,23,47 \
  --noise-stiffness-levels-pct 5,10 \
  --noise-min-seed-count 3 \
  --summary-out implementation/phase1/phase3_megastructure_pipeline_report.json

# Optional: attach MIDAS .mgt coarsened graph (rigid-link resolution) as partition source
python implementation/phase1/run_phase3_megastructure_pipeline.py \
  --candidate-id zenodo_atwood_highrise_shm_2025 \
  --input-path implementation/phase1/open_data/megastructure \
  --opensees-model implementation/phase1/open_data/megastructure/opensees/SCBF16B_shell_beam_mix.tcl \
  --mgt-model implementation/phase1/open_data/midas/midas_generator_33.mgt \
  --mgt-report-out implementation/phase1/midas_mgt_conversion_report.json \
  --mgt-json-out implementation/phase1/open_data/midas/midas_generator_33.json \
  --mgt-npz-out implementation/phase1/open_data/midas/midas_generator_33.npz \
  --mgt-edge-list-out implementation/phase1/open_data/midas/midas_generator_33_edges.json \
  --prefer-mgt-for-partition \
  --require-shell-beam-mix \
  --gpu-strict \
  --ci-mode pr \
  --scale-levels-pr 1000000,3000000 \
  --noise-seeds 11,23,47 \
  --noise-stiffness-levels-pct 5,10 \
  --noise-min-seed-count 3 \
  --summary-out implementation/phase1/phase3_megastructure_pipeline_report.json
```

추가 산출물:
- `opensees_topology_report.json`
- `partitioned_scaleout_report.json`
- `sync_stress_gate_report.json`
- `noise_convergence_gate_report.json`
- `open_data/megastructure/atwood_conversion_report.source_manifest.json`

## Nightly 자동화 + 릴리즈 승격

```bash
# nightly end-to-end: commercial csv gate -> phase3 nightly -> scaleout -> ci -> static validate -> freeze -> promote
python implementation/phase1/run_nightly_release_gate.py \
  --candidate-id zenodo_atwood_highrise_shm_2025 \
  --input-path implementation/phase1/open_data/megastructure \
  --opensees-model implementation/phase1/open_data/megastructure/opensees/SCBF16B_shell_beam_mix.tcl \
  --mgt-input implementation/phase1/open_data/midas/midas_generator_33.mgt \
  --mgt-json-out implementation/phase1/open_data/midas/midas_generator_33.json \
  --mgt-npz-out implementation/phase1/open_data/midas/midas_generator_33.npz \
  --mgt-require-shell-beam-mix \
  --download-if-missing \
  --gpu-strict \
  --require-real-topology \
  --require-shell-beam-mix \
  --scale-levels-nightly 1000000,3000000,10000000 \
  --scale-levels-io 1000000,3000000 \
  --noise-seeds 11,23,47 \
  --noise-stiffness-levels-pct 5,10 \
  --noise-min-seed-count 3 \
  --out implementation/phase1/release/nightly_release_gate_report.json

# MIDAS .mgt -> AI-friendly JSON/NPZ (single-file parser)
# (optional) re-download bundled open sample from upstream GitHub raw URL
python implementation/phase1/fetch_open_mgt_sample.py \
  --out implementation/phase1/open_data/midas/midas_generator_33.mgt \
  --manifest-out implementation/phase1/open_data/midas/midas_generator_33.source_manifest.json

# convert .mgt to parser artifacts
python implementation/phase1/parse_midas_mgt_to_json_npz.py \
  --mgt /path/to/project_model.mgt \
  --json-out implementation/phase1/open_data/midas/project_model.json \
  --npz-out implementation/phase1/open_data/midas/project_graph.npz \
  --edge-list-out implementation/phase1/open_data/midas/project_edges.json \
  --report-out implementation/phase1/midas_mgt_conversion_report.json \
  --resolve-rigid-links \
  --rigid-stiffness-threshold 1e5 \
  --drop-unreferenced-nodes \
  --require-shell-beam-mix

# optional: unknown section을 경고만 남기고 통과(기본)
# strict 모드에서는 알 수 없는 섹션 발견 시 즉시 FAIL
python implementation/phase1/parse_midas_mgt_to_json_npz.py \
  --mgt /path/to/project_model.mgt \
  --json-out implementation/phase1/open_data/midas/project_model.json \
  --npz-out implementation/phase1/open_data/midas/project_graph.npz \
  --report-out implementation/phase1/midas_mgt_conversion_report.json \
  --strict-unknown-sections

# bundled public sample (.mgt) from open GitHub repository
python implementation/phase1/parse_midas_mgt_to_json_npz.py \
  --mgt implementation/phase1/open_data/midas/midas_generator_33.mgt \
  --json-out implementation/phase1/open_data/midas/midas_generator_33.json \
  --npz-out implementation/phase1/open_data/midas/midas_generator_33.npz \
  --edge-list-out implementation/phase1/open_data/midas/midas_generator_33_edges.json \
  --report-out implementation/phase1/midas_mgt_conversion_report.json \
  --forbid-synthetic-source \
  --resolve-rigid-links \
  --rigid-stiffness-threshold 1e5 \
  --drop-unreferenced-nodes \
  --require-shell-beam-mix

# Optional: skip artifact archive when nightly archive copy becomes too heavy
python implementation/phase1/run_nightly_release_gate.py \
  --skip-archive \
  --out implementation/phase1/release/nightly_release_gate_report.json

# Cleanup local Python caches only (safe, non-contract files)
find implementation/phase1 tests -type d -name '__pycache__' -prune -exec rm -rf {} +

# bundle: MIDAS parser + Top-k + NDTHA comparison summary
python implementation/phase1/run_midas_topk_ndtha_comparison.py \
  --cases implementation/phase1/commercial_benchmark_cases.from_csv.json \
  --midas-conversion-report implementation/phase1/midas_mgt_conversion_report.json \
  --ground-motion-csv implementation/phase1/open_data/seismic/el_centro_like_60s_dt0p01.csv \
  --topk-seeds 11,23,47 \
  --topk-out implementation/phase1/topk_precision_suite_report.midas_bundle.json \
  --ndtha-out implementation/phase1/nonlinear_ndtha_stress_report.midas_bundle.json \
  --out implementation/phase1/midas_topk_ndtha_comparison_report.json

# commercial csv gate + member-force(축력) soft-accept gate 포함 실행
python implementation/phase1/run_commercial_csv_gate.py \
  --hf-csv implementation/phase1/commercial_hf_export_sample.csv \
  --lf-csv implementation/phase1/commercial_lf_export_sample.csv \
  --run-member-force-gate \
  --require-member-force \
  --member-force-hf-column axial_force_kN \
  --member-force-lf-column axial_force_kN \
  --out implementation/phase1/commercial_csv_gate_report.json

# 심의 제출용 KDS 포맷 패키지(md/csv/pdf/json)
python implementation/phase1/generate_kds_compliance_report.py \
  --pbd-review-package implementation/phase1/release/pbd_review/pbd_review_package_report.json \
  --commercial-csv-gate implementation/phase1/commercial_csv_gate_report.json \
  --member-force-gate implementation/phase1/member_force_soft_accept_report.json \
  --out-dir implementation/phase1/release/kds_compliance

# 풍하중(장시간 Across-wind) 검증 게이트
python implementation/phase1/run_wind_time_history_gate.py \
  --cases implementation/phase1/commercial_benchmark_cases.from_csv.json \
  --target-split all \
  --wind-csv implementation/phase1/open_data/wind/across_wind_10h_dt1s.csv \
  --source-manifest implementation/phase1/open_data/wind/across_wind_10h_dt1s.manifest.json \
  --min-duration-hours 10 \
  --out implementation/phase1/wind_time_history_gate_report.json

# SSI(p-y/t-z 비선형 경계조건) 검증 게이트
python implementation/phase1/run_ssi_boundary_gate.py \
  --cases implementation/phase1/commercial_benchmark_cases.from_csv.json \
  --target-split all \
  --ground-motion-csv implementation/phase1/open_data/seismic/el_centro_like_60s_dt0p01.csv \
  --soil-profile dense_sand \
  --out implementation/phase1/ssi_boundary_gate_report.json

# 특수 댐퍼(NHERI 파형) 검증 게이트
python implementation/phase1/run_damper_validation_gate.py \
  --catalog implementation/phase1/open_data/global_authority/nheri/damped_frame_catalog.json \
  --out implementation/phase1/damper_validation_gate_report.json

# 시공단계해석(크리프/건조수축/부등축소) 게이트
python implementation/phase1/run_construction_sequence_gate.py \
  --cases implementation/phase1/commercial_benchmark_cases.from_csv.json \
  --target-split all \
  --stage-count 24 \
  --construction-years 4.0 \
  --out implementation/phase1/construction_sequence_gate_report.json

# 유연 다이아프램(shell-beam mix) 게이트
python implementation/phase1/run_flexible_diaphragm_gate.py \
  --cases implementation/phase1/commercial_benchmark_cases.from_csv.json \
  --opensees-model implementation/phase1/open_data/megastructure/opensees/SCBF16B_shell_beam_mix.tcl \
  --target-split all \
  --out implementation/phase1/flexible_diaphragm_gate_report.json

# 법적 재현성/버전락(해시+시드 고정) 게이트
python implementation/phase1/run_reproducibility_version_lock_gate.py \
  --cases implementation/phase1/commercial_benchmark_cases.from_csv.json \
  --target-split all \
  --seed 23 \
  --replay-runs 3 \
  --model-artifacts implementation/phase1/winning_ticket_backprop_report.json,implementation/phase1/nonlinear_frame_engine_report.json \
  --lock-manifest-out implementation/phase1/release/version_lock_manifest.json \
  --out implementation/phase1/reproducibility_version_lock_report.json
```

## 10M 비선형 NDTHA 통합 스트레스 (풀 60초)

```bash
python implementation/phase1/run_mega_ndtha_partitioned_stress.py \
  --partitioned-scaleout implementation/phase1/partitioned_scaleout_report.json \
  --topology-report implementation/phase1/opensees_topology_report.json \
  --ground-motion-csv implementation/phase1/open_data/seismic/el_centro_like_60s_dt0p01.csv \
  --target-dof 10000000 \
  --partitions 16 \
  --halo-coupling-gain 1.0 \
  --min-halo-coupling-gain 1.0 \
  --pdelta-factor 1.0 \
  --collapse-drift-threshold-pct 10.0 \
  --rayleigh-alpha 0.03 \
  --rayleigh-beta 1e-6 \
  --require-full-duration \
  --max-steps 0 \
  --out implementation/phase1/mega_ndtha_partitioned_stress_report.json
```

주요 체크:
- `shell_beam_mix_pass=true`
- `real_topology_pass=true`
- `ground_motion_step_count_used == ground_motion_step_count_full` (컷아웃 금지)
- `pdelta_enabled_pass=true`
- `all_steps_converged=true`
- `plasticity_triggered_all_partitions=true`

수동 분리 실행:

```bash
# freeze snapshot only
python implementation/phase1/freeze_release_snapshot.py \
  --out implementation/phase1/release/freeze_release_report.json

# promote release candidate (dual-green policy: nightly snapshot + current pr ci)
python implementation/phase1/promote_release_candidate.py \
  --pr-ci implementation/phase1/ci_gate_report.json \
  --out implementation/phase1/release/release_candidate_promotion_report.json
```

## 메가스트럭처 상용수준 판정 (7축 게이트)

```bash
python implementation/phase1/run_megastructure_commercial_readiness.py \
  --model-cases implementation/phase1/commercial_benchmark_cases.rwth_zenodo.json,implementation/phase1/commercial_benchmark_cases.from_csv.json \
  --target-split all \
  --noise-seeds 11,23,47 \
  --convergence-seeds 11,23,47 \
  --noise-stiffness-levels-pct 0,10 \
  --convergence-stiffness-levels-pct 10 \
  --ci-mode nightly \
  --forbid-toy-cases \
  --require-gpu-strict \
  --out implementation/phase1/commercial_readiness_report.json
```

```bash
# Multi real-source integrity gate (RWTH + commercial export)
python implementation/phase1/run_real_source_multi_gate.py \
  --cases implementation/phase1/commercial_benchmark_cases.rwth_zenodo.json,implementation/phase1/commercial_benchmark_cases.from_csv.json \
  --forbid-toy-markers \
  --out implementation/phase1/real_source_multi_gate_report.json

# Nightly 10M reproducibility gate (repeat runs + variance check)
python implementation/phase1/run_nightly_10m_repro_gate.py \
  --runs 3 \
  --dof-levels 1000000,3000000,10000000 \
  --gpu-strict \
  --out implementation/phase1/nightly_10m_repro_report.json
```

주요 산출물:
- `commercial_readiness_report.json`
- `stress/commercial_readiness/` (모델별 benchmark/noise/convergence 중간 리포트)
- `experiments/by_test/megastructure_commercial_readiness/` (자동 아카이브)

등급 판정:
- `Research`: 실데이터/정확도 축 통과
- `Pre-Commercial`: Research + 노이즈 강건성 + 수렴성 + 스케일/운영 축 통과
- `Commercial`: Pre-Commercial + 위상 동역학 + OOD 안전축 통과

## Phase A 계약팩 생성/검증

```bash
python3 implementation/phase1/generate_dynamics_boundary_contract.py \
  --out implementation/phase1/dynamics_boundary_report.json

python3 implementation/phase1/generate_phasea_contract_report.py \
  --out implementation/phase1/phasea_contract_report.json
```

- 생성 결과:
  - `dynamics_boundary_report.building.json`
  - `dynamics_boundary_report.track.json`
  - `dynamics_boundary_report.tunnel.json`
  - `dynamics_boundary_report.coupled.json`
  - `phasea_contract_report.json`

## Phase B 궤도 동역학 실행

```bash
python3 implementation/phase1/run_phaseb_track_modules.py \
  --out implementation/phase1/phaseb_track_summary_report.json
```

- 산출물:
  - `track_lf_solver_report.json` (B1: Timoshenko/Euler + Winkler/Pasternak)
  - `moving_load_integrator_report.json` (B2: Newmark 이동하중)
  - `vti_coupled_solver_report.json` (B3: 차량-궤도 연성 반복)
  - `track_irregularity_report.json` + `open_data/track/irregularity_profile.csv` (B4: PSD 불규칙도)

## Phase C 터널 동역학 실행

```bash
python3 implementation/phase1/run_phasec_tunnel_modules.py \
  --out implementation/phase1/phasec_tunnel_summary_report.json
```

- 산출물:
  - `tunnel_graph_converter_report.json` + `tunnel_graph.json` (C1)
  - `tunnel_segment_joint_report.json` (C2)
  - `soil_tunnel_ssi_report.json` (C3)
  - `train_passage_load_report.json` + `open_data/tunnel/train_passage_load.csv` (C4)
  - `tunnel_seismic_longitudinal_report.json` (C5)

## Phase D 멀티도메인 잔차학습 실행

```bash
python3 implementation/phase1/run_phased_multidomain_modules.py \
  --device cuda \
  --out implementation/phase1/phased_multidomain_summary_report.json
```

- 산출물:
  - `track_dynamics_dataset_report.json` + `spatiotemporal_data/track_dynamic_cases.jsonl` (D1)
  - `tunnel_dynamics_dataset_report.json` + `spatiotemporal_data/tunnel_dynamic_cases.jsonl` (D2)
  - `tgnn_multidomain_report.json` + `spatiotemporal_data/tgnn_multidomain.pt` (D3)
  - `moving_load_attention_report.json` (D4)

## 단계 1~6 일괄 실행

```bash
python implementation/phase1/run_phase1_steps.py --out-dir implementation/phase1/step_outputs --repeats 3 --strict
```

- `step1_fire_loop.json`은 mock decay 루프가 아니라 `md3bead_soa.py`의 3-Bead(CA/SC/CB) 포스필드 완화 계산 결과를 기록합니다.
- 주요 물리지표: `max_unbalanced_force`, `kinetic_energy`, `system_temperature`, `model=3bead_ca_sc_cb`

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

## 우선순위 1/2/3/4 실행 (닫힘 기반)

- 앞 단계의 Exit Gate가 닫힌 뒤에만 다음 단계로 이동합니다.

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
- CPU backend가 필수인 프로브만 `--allow-cpu-required`를 추가합니다.
- GPU가 가능한 환경에서 CPU fallback(`cpu_fallback_used=true`)은 금지입니다.
- Step5 실행 시 `step_outputs/step5_rca_summary.json`도 함께 생성됩니다.


CI Gate 실행 예시:
```bash
python implementation/phase1/phase1_ci_gate.py \
  --strict-probe implementation/phase1/zero_copy_real_probe_report_strict.json \
  --rca implementation/phase1/step_outputs/step5_rca_summary.json \
  --phase3-pipeline implementation/phase1/phase3_megastructure_pipeline_report.json \
  --partitioned-scaleout implementation/phase1/partitioned_scaleout_report.json \
  --noise-convergence implementation/phase1/noise_convergence_gate_report.json \
  --pbd-review-package implementation/phase1/release/pbd_review/pbd_review_package_report.json \
  --ci-mode pr \
  --require-gpu-strict \
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
  --pbd-review-package implementation/phase1/release/pbd_review/pbd_review_package_report.json \
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

python implementation/phase1/benchmark_kpi_contract.py \
  --cases implementation/phase1/commercial_benchmark_cases.json \
  --comparison-out implementation/phase1/topk_comparison_experiment_report.json \
  --top-k 3 --branches 8 --epochs 180 \
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

### 상용 해석기 export -> 비교실험 연결 (strict, no fallback)

```bash
python implementation/phase1/build_cases_from_commercial_exports.py \
  --hf-csv implementation/phase1/commercial_hf_export_sample.csv \
  --lf-csv implementation/phase1/commercial_lf_export_sample.csv \
  --out implementation/phase1/commercial_benchmark_cases.from_csv.json

python implementation/phase1/benchmark_kpi_contract.py \
  --cases implementation/phase1/commercial_benchmark_cases.from_csv.json \
  --top-k 3 --branches 8 --epochs 180 \
  --require-direct-metrics \
  --accepted-metric-sources engine_export_direct,commercial_solver_export \
  --out implementation/phase1/hf_benchmark_report.json \
  --comparison-out implementation/phase1/topk_comparison_experiment_report.json

python implementation/phase1/run_topk_precision_experiments.py \
  --cases implementation/phase1/commercial_benchmark_cases.from_csv.json \
  --seeds 11,17,23,31,47 \
  --top-k 3 --branches 8 --epochs 180 \
  --require-direct-metrics \
  --accepted-metric-sources engine_export_direct,commercial_solver_export \
  --out implementation/phase1/topk_precision_suite_report.json
```

### 실험 아티팩트 번들링 (baseline/top-k 분리)

```bash
python implementation/phase1/organize_benchmark_artifacts.py \
  --cases implementation/phase1/commercial_benchmark_cases.from_csv.json \
  --benchmark implementation/phase1/hf_benchmark_report.json \
  --comparison implementation/phase1/topk_comparison_experiment_report.json \
  --suite implementation/phase1/topk_precision_suite_report.json \
  --ci implementation/phase1/ci_gate_report.json \
  --validation implementation/phase1/static_artifact_validation_report.json \
  --out-root implementation/phase1/experiments
```

### 원커맨드 재현 파이프라인 (config lock + manifest)

```bash
python implementation/phase1/run_phase1_topk_pipeline.py \
  --out-config-lock implementation/phase1/pipeline_config.lock.json \
  --out-manifest implementation/phase1/pipeline_manifest.json
```

- 파이프라인 기본 런타임 훅은 `rust_hip_md3bead_hook.py`를 사용하며, `step1_case/step5_profile`가 Rust 3-Bead SoA 경로로 실행됩니다.
- `rust_md3bead_parity_report.json`이 생성되며, Python 참조모델과 Rust 훅의 1:1 동치 여부를 CI gate에서 함께 판정합니다.

### Rust 3-Bead 훅 단독 동치 검증

```bash
python implementation/phase1/validate_md3bead_rust_parity.py \
  --rust-hook-cmd "python3 implementation/phase1/rust_hip_md3bead_hook.py" \
  --out implementation/phase1/rust_md3bead_parity_report.json
```

### 비선형 Lennard-Jones 맵핑 커널 검증

```bash
python implementation/phase1/validate_nonlinear_lj_mapping.py \
  --out implementation/phase1/nonlinear_lj_mapping_report.json
```

- 항복점 검출, 항복 후 연화(softening), 에너지 소산(pass/fail)을 계약 형태로 검증합니다.

### 동적 시간이력(Newmark-β + Rayleigh) 검증

```bash
python implementation/phase1/dynamic_time_history_contract_stub.py \
  --ground-motion-csv implementation/phase1/open_data/seismic/el_centro_like_60s_dt0p01.csv \
  --auto-generate-input \
  --out implementation/phase1/dynamic_time_history_report.json
```

- 지진파 입력 기반으로 동적 응답 안정성, 평형 잔차, 에너지 균형 계약을 검증합니다.

### branches=64 마이크로배칭 + 6900XT 캐시 프로파일

```bash
python implementation/phase1/profile_branch64_microbatch_cache.py \
  --runtime-hook-cmd "python3 implementation/phase1/rust_hip_md3bead_hook.py" \
  --branches 64 \
  --chunk-candidates 64,32,16,8,4 \
  --node-count 100000 \
  --cache-mb 128 \
  --out implementation/phase1/branch64_microbatch_profile_report.json
```

- full-batch(64) 캐시 미스 여부와 cache-safe micro-batch 추천 chunk를 함께 출력합니다.

### P0 엔진 경로 성능 프로파일 (zero-copy + Rust/Python 비교)

```bash
python implementation/phase1/profile_p0_engine_path.py \
  --producer-cmd "python3 implementation/phase1/rust_hip_md3bead_hook.py" \
  --allow-cpu-required \
  --out implementation/phase1/p0_engine_perf_report.json
```

- `p0_engine_perf_report.json`에 zero-copy timing breakdown, Rust/Python LF solver 이론별 elapsed/speedup을 기록합니다.

### HIP 커널 스모크 (실제 hipcc 컴파일/실행)

```bash
python implementation/phase1/run_hip_kernel_smoke.py \
  --source implementation/phase1/hip_kernels/axpy_kernel.hip.cpp \
  --binary implementation/phase1/hip_kernels/axpy_kernel_smoke \
  --n 1048576 --reps 30 \
  --strict \
  --out implementation/phase1/hip_kernel_smoke_report.json
```

- Rust FFI 경로와 별도로 HIP 커널 본체가 실제 빌드/실행되는지 검증합니다.
- `run_p0_core_gap_pipeline.py --require-hip-kernel`로 P0 게이트에 강제할 수 있습니다.

### RC/복합재 비선형 재료모델 활성화 (균열/크리프/bond-slip)

```bash
python implementation/phase1/run_nonlinear_ndtha_stress.py \
  --cases implementation/phase1/commercial_benchmark_cases.from_csv.json \
  --target-split test \
  --material-model rc_composite \
  --rc-cracking-strain 2.2e-4 \
  --rc-creep-rate-per-hour 0.008 \
  --rc-bond-slip-ratio-ref 0.003 \
  --out implementation/phase1/nonlinear_ndtha_stress_report.json
```

- `run_nonlinear_pushover_stress.py`에도 동일 옵션을 적용할 수 있습니다.
- 리포트에 `material_effect_rows`와 `material_indices`가 기록됩니다.

### Solver-wide HIP E2E 계약 (메인 루프 GPU residency 공개)

```bash
python implementation/phase1/run_solver_hip_e2e_contract.py \
  --strict-probe implementation/phase1/zero_copy_real_probe_report_strict.json \
  --out implementation/phase1/solver_hip_e2e_contract_report.json
```

- `hip_kernel_smoke`와 별개로 `nonlinear frame / NDTHA / track LF` 메인 루프가 실제 GPU main-loop telemetry를 내는지 검사합니다.
- 현재 CPU FFI가 남아 있으면 의도적으로 `FAIL` 하며, 이 리포트는 P0 commercialization gap의 직접 증거로 사용됩니다.

### RC benchmark-lock 게이트 (cracking / bond-slip / creep)

```bash
python implementation/phase1/run_rc_benchmark_lock_gate.py \
  --cases implementation/phase1/open_data/rc/rc_benchmark_lock_cases.json \
  --out implementation/phase1/rc_benchmark_lock_report.json
```

- 공개 실험 전체를 대체하는 것은 아니지만, 현재 RC 재료모델이 고정된 benchmark slice를 벗어나지 않는지 지속적으로 검증합니다.

### 품질 보장 MIDAS corpus 수집

```bash
python implementation/phase1/collect_mgt_quality_corpus.py \
  --catalog implementation/phase1/open_data/midas/quality_mgt_source_catalog.json \
  --out-dir implementation/phase1/open_data/midas/quality_corpus \
  --report-out implementation/phase1/open_data/midas/quality_corpus_report.json
```

- strict provenance + shell-beam mix 조건을 만족하는 `.mgt`만 보존합니다.
- `quality_corpus_report.json`에 accepted source 수, 누적 node/element 수, typed/unknown row 요약을 남깁니다.

### Phase1 워크스페이스 정리 (비파괴 복사)

```bash
python implementation/phase1/organize_phase1_workspace.py \
  --root implementation/phase1 \
  --workspace implementation/phase1/workspace \
  --clean
```

- `workspace/catalog/scripts/scripts_by_group.json`: 스크립트 분류 인덱스
- `workspace/catalog/report_catalog.json`: 결과/입력 파일 카탈로그 + 해시
- 루트의 결과 파일을 실제로 정리(이동)하려면 `--move-reports` 옵션을 추가하세요.

### 상용 export CSV 절대경로로 원커맨드 재실행 (CI/정적검증 포함)

```bash
python implementation/phase1/run_phase1_topk_pipeline.py \
  --hf-csv /ABS/PATH/to/commercial_hf_export.csv \
  --lf-csv /ABS/PATH/to/commercial_lf_export.csv \
  --metric-source commercial_solver_export \
  --artifact-label commercial_direct_b64_dyn \
  --out-config-lock implementation/phase1/release/pipeline_config.commercial_direct_b64_dyn.lock.json \
  --out-manifest implementation/phase1/release/pipeline_manifest.commercial_direct_b64_dyn.json
```

- 이 실행에는 `dynamic_time_history_report.json`, `branch64_microbatch_profile_report.json`이 CI gate 필수 항목으로 포함됩니다.

### 99.9 로드맵 단계 1~5 실행 파이프라인

```bash
python implementation/phase1/run_99_9_architecture_pipeline.py \
  --out implementation/phase1/spatiotemporal_data/roadmap_99_9_pipeline_report.json
```

- Step1: `generate_spatiotemporal_bigdata.py` (Active Learning 기반 시공간 데이터 생성)
- Step2: `train_tgnn_baseline.py` (T-GNN baseline)
- Step3: `train_simplicial_tgnn.py` (Simplicial/Cellular 확장)
- Step4: `train_neural_operator_surrogate.py` (Neural Operator 보조 트랙)
- Step5: `run_productization_gate.py` (Deterministic fallback + 코드체크 게이트)

주요 산출물:
- `implementation/phase1/spatiotemporal_data/bigdata_generation_report.json`
- `implementation/phase1/spatiotemporal_data/tgnn_baseline_report.json`
- `implementation/phase1/spatiotemporal_data/simplicial_tgnn_report.json`
- `implementation/phase1/spatiotemporal_data/neural_operator_report.json`
- `implementation/phase1/spatiotemporal_data/productization_gate_report.json`
- `implementation/phase1/spatiotemporal_data/roadmap_99_9_pipeline_report.quick.json`

### PINN + 스트리밍 + 능동학습 (데이터 1/1000 전략)

```bash
python implementation/phase1/train_pinn_streaming_active.py \
  --out implementation/phase1/spatiotemporal_data/pinn_streaming_active_report.json \
  --ckpt implementation/phase1/spatiotemporal_data/pinn_streaming_active.pt
```

- 학습 배치를 디스크 적재 없이 on-the-fly 생성합니다.
- Loss에 동역학 방정식 잔차(`M*u_ddot + C*u_dot + K*u - f_ext`)를 직접 포함합니다.
- Active Learning 루프가 고오차 케이스를 hard pool로 재주입합니다.
- `--move-reports` 사용 시 결과 JSON/CSV/Parquet는 `workspace/reports/*`로 이동됩니다.

### 3-Bead 캐시 예산 분석 (128MB Infinity Cache 기준)

```bash
python implementation/phase1/three_bead_cache_budget.py \
  --node-count 100000 --branches-list 10,64 \
  --out implementation/phase1/three_bead_cache_budget_report.json
```

- `10` branches 시나리오가 캐시에 들어오는지, `64` branches 시 micro-batch 권장 크기를 자동 계산합니다.

### RWTH Zenodo 오픈데이터 -> 비교실험 연결 (strict, no fallback)

Zenodo record: `14173245`  
Dataset zip: `Data_v1.0.0.zip`

```bash
mkdir -p implementation/phase1/open_data/rwth_zenodo_14173245
curl -L --fail --retry 3 \
  -o implementation/phase1/open_data/rwth_zenodo_14173245/Data_v1.0.0.zip \
  https://zenodo.org/api/records/14173245/files/Data_v1.0.0.zip/content

python implementation/phase1/build_cases_from_rwth_zenodo.py \
  --zip implementation/phase1/open_data/rwth_zenodo_14173245/Data_v1.0.0.zip \
  --out implementation/phase1/commercial_benchmark_cases.rwth_zenodo.json

python implementation/phase1/benchmark_kpi_contract.py \
  --cases implementation/phase1/commercial_benchmark_cases.rwth_zenodo.json \
  --top-k 3 --branches 10 --epochs 220 \
  --lr 0.055 --epsilon 0.11 --temperature 0.32 \
  --target-split test \
  --out implementation/phase1/hf_benchmark_report.rwth_zenodo.json \
  --comparison-out implementation/phase1/topk_comparison_experiment_report.rwth_zenodo.json

python implementation/phase1/run_topk_precision_experiments.py \
  --cases implementation/phase1/commercial_benchmark_cases.rwth_zenodo.json \
  --seeds 11,17,23,31,47 \
  --top-k 3 --branches 10 --epochs 220 \
  --lr 0.055 --epsilon 0.11 --temperature 0.32 \
  --target-split test \
  --out implementation/phase1/topk_precision_suite_report.rwth_zenodo.json
```

### 야생형 스트레스 테스트 (노이즈 + 1M DOF 스케일아웃)

```bash
python implementation/phase1/run_noise_sensitivity_stress.py \
  --cases implementation/phase1/commercial_benchmark_cases.rwth_zenodo.json \
  --target-split test \
  --required-case-count 4 \
  --sensor-noise-levels-pct 0,1,3,5 \
  --stiffness-noise-levels-pct 0,5,10 \
  --seeds 11,23,47 \
  --out implementation/phase1/noise_sensitivity_stress_report.json

python implementation/phase1/run_scaleout_io_profile.py \
  --runtime-hook-cmd "python3 implementation/phase1/rust_hip_md3bead_hook.py" \
  --producer-cmd "python3 implementation/phase1/rust_hip_md3bead_hook.py" \
  --dof-levels 100000,300000,1000000,3000000 \
  --allow-cpu-required \
  --out implementation/phase1/scaleout_io_profile_report.json
```

### 10M DOF 장시간 NDTHA 연속 프로파일 자동화

```bash
python implementation/phase1/run_10m_ndtha_long_profile.py \
  --runs 2 \
  --partitioned-scaleout implementation/phase1/partitioned_scaleout_report.json \
  --topology-report implementation/phase1/opensees_topology_report.json \
  --ground-motion-csv implementation/phase1/open_data/seismic/el_centro_like_60s_dt0p01.csv \
  --target-dof 10000000 --partitions 16 \
  --halo-coupling-gain 1.0 \
  --out implementation/phase1/ndtha_long_profile_report.json
```

- 연속 런 분산(COV)까지 함께 점검합니다.
- nightly 자동화에서는 `run_nightly_release_gate.py --enable-ndtha-long-profile`로 호출됩니다.

주요 산출물:
- `implementation/phase1/noise_sensitivity_stress_report.json`
- `implementation/phase1/scaleout_io_profile_report.json`
- `implementation/phase1/open_data/megastructure/mega_structure_catalog.json`

메가스트럭처 대체 오픈소스 후보:
- `implementation/phase1/open_data/megastructure/README.md`

오픈 메가스트럭처 변환/파이프라인:
```bash
# 1) Open dataset -> dynamic_cases + benchmark_cases 변환
python implementation/phase1/build_cases_from_megastructure_open.py \
  --candidate-id zenodo_atwood_highrise_shm_2025 \
  --input-path implementation/phase1/open_data/megastructure \
  --download-if-missing \
  --dynamic-out implementation/phase1/spatiotemporal_data/atwood_dynamic_cases.jsonl \
  --benchmark-out implementation/phase1/commercial_benchmark_cases.atwood_open.json \
  --report-out implementation/phase1/open_data/megastructure/atwood_conversion_report.json

# 2) phase3 통합 실행 (변환 -> top-k benchmark -> noise -> scaleout 옵션)
python implementation/phase1/run_phase3_megastructure_pipeline.py \
  --candidate-id zenodo_atwood_highrise_shm_2025 \
  --input-path implementation/phase1/open_data/megastructure \
  --download-if-missing \
  --benchmark-epochs 160 \
  --run-noise \
  --run-scaleout \
  --allow-cpu-required \
  --summary-out implementation/phase1/phase3_megastructure_pipeline_report.json
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

# top-k weighted targeted backprop on physically-admissible branches
python implementation/phase1/winning_ticket_backprop.py   --branches 16 --top-k 3 --temperature 0.25   --out implementation/phase1/winning_ticket_backprop_report.json
```

CI gate / static validation now also consume these artifacts.


## PBD 심의용 패키지 (7 지진파)

다음 스크립트는 7개 지진파 NDTHA 결과를 기반으로 심의용 산출물을 생성합니다.

- `drift_envelope_7eq.png`
- `core_wall_hysteresis.png`
- `pbd_killshot_metrics.json/.csv`
- `pbd_review_report.md`
- `pbd_review_report.pdf`

```bash
python implementation/phase1/generate_pbd_review_package.py \
  --run-ndtha \
  --cases-json implementation/phase1/commercial_benchmark_cases.opstool_nightly.json \
  --target-split all \
  --earthquake-count 7 \
  --ground-motion-csv implementation/phase1/open_data/seismic/el_centro_like_60s_dt0p01.csv \
  --ndtha-report implementation/phase1/nonlinear_ndtha_stress_report.pbd7.json \
  --out-dir implementation/phase1/release/pbd_review \
  --commercial-estimate-hours 336 \
  --engine-time-minutes-override 28
```

기존 NDTHA 결과를 재사용하려면:

```bash
python implementation/phase1/generate_pbd_review_package.py \
  --no-run-ndtha \
  --ndtha-report implementation/phase1/nonlinear_ndtha_stress_report.pbd7.json \
  --out-dir implementation/phase1/release/pbd_review \
  --commercial-estimate-hours 336 \
  --engine-time-minutes-override 28
```

릴리즈 기준 상용화 갭 리포트를 다시 생성하려면:

```bash
python implementation/phase1/generate_release_gap_report.py \
  --out-json implementation/phase1/release/release_gap_report.json \
  --out-md implementation/phase1/release/release_gap_report.md
```

PBD + wind/SSI/damper/시공단계/유연다이아프램/재현성/KDS를 하나의 심의 패키지로 묶으려면:

```bash
python implementation/phase1/generate_committee_review_package.py \
  --out-dir implementation/phase1/release/committee_review
```
