# Benchmark Diversification Plan

현재 반복적으로 많이 타는 입력은 사실상 [midas_generator_33.mgt](/home/betelgeuze/건축구조분석/implementation/phase1/open_data/midas/midas_generator_33.mgt) 하나에 크게 의존합니다.

이 상태는 parser / optimization / nightly smoke에는 좋지만, 아래 리스크가 남습니다.

1. 특정 건물 형상과 naming style에 과적합됩니다.
2. `panel / hinge / foundation / wind` holdout을 각기 다른 권위 데이터로 눌러보지 못합니다.
3. live release가 green이어도 “실은 같은 파일을 다른 각도에서만 검증했다”는 비판을 받기 쉽습니다.

## 권장 방향

좋은 방향입니다. 다만 무작정 많이 모으는 것보다, 현재 commercialization holdout에 바로 먹히는 축으로 먼저 넓히는 게 맞습니다.

우선순위는 아래 순서가 좋습니다.

1. `wind`: TPU wind database 계열
2. `hinge`: PEER SPD RC column 계열
3. `foundation`: DesignSafe pile / liquefaction / SSI 계열
4. `panel`: PEER beam-column joint 계열
5. `measured dynamic holdout`: USGS NSMP structural arrays

세부 카탈로그는 [benchmark_diversification_catalog.json](/home/betelgeuze/건축구조분석/implementation/phase1/open_data/benchmark_diversification_catalog.json) 에 정리했습니다.

## 왜 이 순서인가

### 1. Wind

가장 ROI가 좋습니다.

- 현재 wind는 `raw_hffb_node_pressure_mapping`까지는 닫혔지만, source diversity는 얕습니다.
- TPU 계열은 바로 `raw pressure / force -> node/floor mapping` 검증으로 이어집니다.
- isolated tower와 interference case를 같이 넣으면 지금보다 훨씬 강해집니다.

### 2. Hinge

`hinge_refresh_projected_from_optimization_changes`에서 한 단계 더 가려면 실험 기반 hysteresis family가 필요합니다.

- PEER SPD column data는 `geometry + rebar + axial load + cyclic response`가 같이 있어 member-local hinge refresh 검증에 적합합니다.
- 특히 현재 projected refresh를 실험 반응으로 눌러볼 수 있다는 점이 큽니다.

### 3. Foundation

foundation은 현재 live green이지만, provenance가 아직 풍부하지 않습니다.

- measured pile/soil interaction이 들어와야 “below-grade geometry promotion”만으로 닫은 게 아니라는 설명이 됩니다.
- DesignSafe pile / liquefaction 계열과 SimCenter pile-group synthetic family를 같이 쓰면 measured + parametric 두 축이 생깁니다.

### 4. Panel

panel은 마지막까지 남은 진짜 blocker입니다.

- 지금은 `topology_projected_midas_panel_bridge`까지는 왔지만 `solver_verified 3D clash`는 아닙니다.
- PEER joint literature/data는 바로 clash row를 주는 건 아니어도, row schema와 failure mode labeling을 권위 있게 고정하는 데 가장 좋습니다.

### 5. Measured Dynamic Holdout

Atwood 하나에 measured holdout이 너무 쏠려 있습니다.

- USGS NSMP structural arrays를 넣으면 “다른 계측 구조물에서도 통하느냐”를 물을 수 있습니다.
- 이건 특히 committee/external validation 방어력이 좋아집니다.

## 바로 할 실무 단위

다음 배치는 이 정도가 적당합니다.

1. `wind`: TPU isolated high-rise 1건 + interference 1건
2. `hinge`: PEER SPD RC column 3~5건
3. `foundation`: DesignSafe measured pile case 1건 + SimCenter synthetic pile family 1건

이렇게만 들어와도 현재 벤치마크 편향은 꽤 줄어듭니다.

바로 쓸 수 있는 seed manifest도 추가했습니다.

1. [tpu_hffb_seed_manifest.json](/home/betelgeuze/건축구조분석/implementation/phase1/open_data/wind/tpu_hffb_seed_manifest.json)
2. [peer_spd_column_seed_manifest.json](/home/betelgeuze/건축구조분석/implementation/phase1/open_data/pbd_hinge/peer_spd_column_seed_manifest.json)

그리고 raw 데이터를 받으면 바로 쓸 수 있는 ingest stub도 추가했습니다.

1. `python3 implementation/phase1/prepare_tpu_hffb_seed.py --seed-id tpu_hffb_isolated_highrise_seed_01 --raw-wind path/to/raw.csv`
2. `python3 implementation/phase1/normalize_peer_spd_column_seed.py --seed-id peer_spd_rc_column_rebar_sensitive_seed_01 --raw-specimen-json path/to/specimen.json`

TPU는 이제 one-shot materialization도 가능합니다.

1. `python3 implementation/phase1/fetch_tpu_case_mat.py --case-id 1202`
2. `python3 implementation/phase1/convert_tpu_mat_to_csv.py --input-mat path/to/case.mat`
3. `python3 implementation/phase1/materialize_tpu_hffb_seed.py --seed-id tpu_hffb_isolated_highrise_seed_01 --case-id 1202 --dataset-key pressure --time-key time`

즉 지금은 `fetch -> convert -> prepare` 경로가 코드와 테스트 기준으로 닫혀 있습니다.

그리고 TPU 쪽은 이제 한 단계 더 갔습니다.

1. 공식 source 기준 `case=616` isolated materialization `PASS`
2. 공식 source 기준 `case=917` interference materialization `PASS`
3. [tpu_hffb_benchmark_gate_report.json](/home/betelgeuze/건축구조분석/implementation/phase1/open_data/wind/tpu_hffb_benchmark_gate_report.json) 에서 `isolated + interference` diversified raw HFFB benchmark gate도 `PASS`

중요한 점은 이 gate가 기존 `10h across_wind_force_kN` gate를 대체하는 건 아니라는 점입니다.

- TPU asset은 `raw HFFB mapping` benchmark로는 usable
- 하지만 현재 `wind_time_history_gate` 기준으로는 `missing_across_wind_force_kN_column` 이므로 별도 gate로 관리해야 함

PEER SPD도 이제 `seed 후보 선정 -> specimen page -> txt hysteresis -> normalized hinge fixture` 단계까지 실제 official source 기준으로 올라왔습니다.

1. [peer_spd_fetch_report.json](/home/betelgeuze/건축구조분석/implementation/phase1/open_data/pbd_hinge/peer_spd_fetch_report.json) 에서 rectangular/spiral properties table fetch `PASS`
2. [peer_spd_column_seed_candidates.json](/home/betelgeuze/건축구조분석/implementation/phase1/open_data/pbd_hinge/peer_spd_column_seed_candidates.json) 에서 `5개 seed 모두 matched`
3. [peer_spd_specimen_pages_report.json](/home/betelgeuze/건축구조분석/implementation/phase1/open_data/pbd_hinge/peer_spd_specimen_pages_report.json) 에서 selected specimen page fetch/parse `PASS`
4. [peer_spd_hysteresis_resources_report.json](/home/betelgeuze/건축구조분석/implementation/phase1/open_data/pbd_hinge/peer_spd_hysteresis_resources_report.json) 에서 txt hysteresis resource fetch/parse `PASS`
5. [peer_spd_column_materialize_report.json](/home/betelgeuze/건축구조분석/implementation/phase1/open_data/pbd_hinge/peer_spd_column_materialize_report.json) 에서 `normalized_seed_count = 5`
6. [pbd_hinge_benchmark_asset_registry.json](/home/betelgeuze/건축구조분석/implementation/phase1/open_data/pbd_hinge/pbd_hinge_benchmark_asset_registry.json) 기준 `benchmark_ready_asset_count = 5`
7. [peer_spd_hinge_benchmark_gate_report.json](/home/betelgeuze/건축구조분석/implementation/phase1/open_data/pbd_hinge/peer_spd_hinge_benchmark_gate_report.json) 기준 diversified hinge benchmark gate `PASS`

## 추가 온보딩: 세 가지 후보 트랙

아래 3개는 현재 repo의 강점을 기준으로 `immediate / next / deferred` 순서로 붙이는 게 가장 자연스럽습니다.

### 1. Immediate: E-Defense / PEER blind prediction

- 왜 지금인가: 현재 repo는 `NDTHA`, `results explorer`, `selection-set compare console`, `row provenance`, `release / committee package`가 이미 살아 있어서, blind prediction의 핵심인 `사전 제출 -> 사후 측정 비교 -> scorecard review`를 바로 돌릴 수 있습니다.
- 들어와야 할 intake artifacts: 문제정의서, specimen geometry, 경계조건, 입력 지진/가진 이력, blind submission 템플릿, measured response table, 공식 scoring sheet, post-test summary report.
- 현재 repo와의 접점: `run_nonlinear_ndtha_stress.py`, `generate_structural_optimization_visualization_viewer.py`, `charts.html`, `optimization_history.html`.
- 온보딩 이유: dynamic holdout을 가장 빠르게 넓히면서도 provenance/compare surface를 검증할 수 있어서 immediate가 맞습니다.

### 2. Next: Canton Tower megastructure

- 왜 다음인가: 현재 repo는 large-model instancing, contour, story clip, picking, SVG review surface를 갖고 있어서 megatall SHM/response 패킷을 수용할 준비가 되어 있습니다. 다만 실제 Canton Tower용 intake는 geometry와 monitoring metadata가 더 풍부해야 하므로 immediate보다는 다음 단계가 맞습니다.
- 들어와야 할 intake artifacts: tower geometry, story / elevation metadata, section schedule, sensor layout, modal identification summary, wind 또는 earthquake response histories, SHM snapshot, model-updating note.
- 현재 repo와의 접점: `index.html` 대형 모델 경로, `charts.html` time-history / envelope, `structural_svg_generator.py`, megastructure open-data pipeline.
- 온보딩 이유: 현재 뷰어/검토 체인으로 큰 형상을 다룰 수 있지만, Canton Tower는 실제 megatall SHM 패킷이 필요해서 immediate보다 한 단계 뒤가 적절합니다.

### 3. Deferred: Nuclear containment / SSI

- 왜 deferred인가: repo에는 SSI / contact / foundation / boundary gate가 이미 있지만, containment-specific geometry, basemat/liner/interface, safety-case package까지 포함한 benchmark intake는 아직 부족합니다. 즉 현재 plumbing은 있으나 authority packet이 아직 얇습니다.
- 들어와야 할 intake artifacts: containment geometry, basemat 및 soil profile, SSI spring 또는 FE soil model, ground motions, liner / contact assumptions, pressure / temperature history, benchmark report 또는 design note bundle.
- 현재 repo와의 접점: `run_ssi_boundary_gate.py`, `run_general_fe_contact_benchmark_gate.py`, `run_foundation_soil_link_gate.py`, `material_constitutive_gate.py`.
- 온보딩 이유: SSI 자체는 소화 가능하지만 nuclear containment은 benchmark 권위 패키지와 도메인 특화 intake가 더 필요하므로 deferred가 맞습니다.

이 3개를 넣으면 현재의 `wind / hinge / foundation / panel` 축에 더해 `blind prediction / megatall / nuclear SSI`가 분리되어, benchmark 다양화 의도가 더 명확해집니다.

## 운영 원칙

새 벤치마크는 아래 기준으로만 받는 게 좋습니다.

1. 공식/권위 출처 링크가 있어야 함
2. source manifest를 남겨야 함
3. holdout split을 먼저 정의해야 함
4. “왜 이 케이스가 필요한지”가 현재 gap과 연결돼야 함
5. 단순 fixture가 아니라 release-facing summary까지 provenance가 올라가야 함

## 결론

좋은 생각이고, 지금 시점에 꼭 해야 합니다.

다만 “설계도 파일을 더 많이 모으자”보다는:

1. `wind`
2. `hinge`
3. `foundation`
4. `panel`

이 네 축을 직접 넓히는 공식 benchmark source를 먼저 넣는 게 맞습니다.

## Next Frontier Benchmark Tracks

위 우선순위는 `현재 commercialization holdout`을 가장 빠르게 넓히는 실무 배치입니다.  
그 다음 단계에서 바로 검토할 만한 대형/고난도 benchmark 트랙은 아래 3개입니다.

### 1. Immediate Next: Canton Tower megastructure SHM benchmark

이 저장소 기준으로는 가장 먼저 붙이기 좋은 `next frontier` 후보입니다.

- 공식/public source는 PolyU benchmark 페이지 쪽이 가장 강합니다.
- 다만 이 benchmark는 `full-order native FE`라기보다 `reduced-order SHM benchmark`로 보는 게 정확합니다.
- 즉 “상용 FE 모델 통째 ingestion”보다 `measured megatall response + reduced system matrices + viewer/review chain` 검증에 적합합니다.

권장 source:

1. `https://polyucee.hk/ceyxia/benchmark/benchmark.htm`
2. `https://polyucee.hk/ceyxia/benchmark/tvtower.htm`
3. `https://polyucee.hk/ceyxia/benchmark/task_i.htm`

권장 intake artifact:

1. `source_manifest.json`
2. `system_matrices.mat`
3. measurement description PDF
4. selected acceleration / wind / temperature files
5. `benchmark_case.json`
6. `compare_report.json`
7. `viewer_entry.html`

repo landing point:

1. `implementation/phase1/open_data/irregular/`
2. `implementation/phase1/open_data/megastructure/`
3. `implementation/phase1/run_measured_benchmark_breadth_gate.py`

즉시 성공 기준:

1. reduced system matrices ingestion
2. measured-response case generation
3. `measured benchmark breadth`에 family 추가
4. viewer/results explorer에서 provenance drill-down 생성

### 2. Next: E-Defense / PEER blind prediction benchmark

두 번째가 맞습니다. 이유는 현재 저장소가 `PEER SPD hinge refresh`, `PBD hinge benchmark`, `member-local cyclic response` 쪽으로 이미 이어져 있기 때문입니다.

- E-Defense/PEER 계열은 `geometry + material + loading + measured response`가 함께 오는 붕괴/비선형 benchmark로 매우 가치가 큽니다.
- 다만 지금 저장소에서 가장 자연스러운 첫 진입은 `full collapse contest` 전체가 아니라 `PEER/E-Defense steel or frame blind benchmark 1건`입니다.

권장 source:

1. `https://peer.berkeley.edu/2009-blind-analysis-contest-e-defense`
2. `https://peer.berkeley.edu/sites/default/files/news_e-defense_blind_analysis_2009-article.pdf`
3. `https://peer.berkeley.edu/nees-tipse-defense-announce-blind-analysis-contest-seismic-isolation-test`

권장 intake artifact:

1. source manifest
2. specimen / frame geometry metadata
3. material / member property table
4. excitation / loading history
5. measured response target set
6. holdout split manifest
7. compare / calibration report

repo landing point:

1. `implementation/phase1/open_data/pbd_hinge/`
2. `implementation/phase1/open_data/rc/`
3. `implementation/phase1/run_peer_spd_hinge_benchmark_gate.py`
4. `implementation/phase1/run_rc_benchmark_lock_gate.py`

즉시 성공 기준:

1. one blind benchmark family ingested with official provenance
2. member-local hysteresis or frame response target generated
3. compare/report/viewer drill-down closed

### 3. Deferred: Nuclear containment / SSI benchmark

가치는 크지만 지금 당장 1차 타깃으로는 비추천입니다.

- 공식 benchmark 문서와 SSI reference는 찾을 수 있지만, `즉시 ingestion 가능한 공개 raw FE mesh/model package`는 상대적으로 불확실합니다.
- 현재 저장소의 SSI/foundation/contact breadth는 꽤 올라왔지만, 아직 `licensing-grade nuclear SSI`를 대표 트랙으로 삼기엔 이릅니다.

권장 source:

1. `https://ww2.nrc.gov/reading-rm/doc-collections/nuregs/contract/cr5679/index`
2. `https://www.osti.gov/biblio/1097517`

권장 intake artifact:

1. source manifest
2. benchmark report/PDF
3. response target abstraction
4. impedance / transfer-function compare receipt
5. SSI boundary benchmark sidecar

repo landing point:

1. `implementation/phase1/open_data/reference/`
2. `implementation/phase1/run_ssi_boundary_gate.py`
3. `implementation/phase1/run_foundation_soil_link_gate.py`

착수 기준:

1. trusted public model/mesh or benchmark package 확보
2. current SSI gate outputs와 직접 연결 가능한 target signal 정의
3. solver breadth에서 thick shell / stronger soil-contact evidence 보강

## Recommended order after current holdout batch

현재 `wind / hinge / foundation / panel` diversification이 계속 우선입니다.  
그 다음 배치 순서는 아래가 가장 안전합니다.

1. `Canton Tower` megastructure reduced-order SHM benchmark
2. `E-Defense / PEER` blind benchmark one family
3. `nuclear containment / SSI` only after a stronger public benchmark package is secured
