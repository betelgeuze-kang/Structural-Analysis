# PBD Hinge Benchmark Seeds

이 디렉터리는 projected hinge refresh를 실험 기반 family로 넓히기 위한 외부 benchmark seed를 담습니다.

현재 첫 seed는 아래 파일입니다.

- `peer_spd_column_seed_manifest.json`

의도는 간단합니다.

1. PEER SPD 계열에서 RC column cyclic response를 몇 건 고릅니다.
2. geometry / rebar / axial load / hysteresis를 최소 공통 형식으로 정리합니다.
3. 그 데이터를 `hinge refresh` calibration / holdout fixture로 씁니다.

처음에는 어떤 slice를 받을지와 어떤 holdout split으로 쓸지를 고정하는 manifest만 있었지만,
지금은 official PEER SPD source에서 실제 raw hysteresis와 normalized hinge fixture까지 생성됩니다.

raw specimen JSON을 fixture로 바꾸려면:

```bash
python3 implementation/phase1/normalize_peer_spd_column_seed.py \
  --seed-id peer_spd_rc_column_rebar_sensitive_seed_01 \
  --raw-specimen-json path/to/specimen.json
```

공식 PEER SPD properties table을 먼저 받아 두려면:

```bash
python3 implementation/phase1/fetch_peer_spd_properties_tables.py
```

그 다음 seed preselection을 properties 기반으로 먼저 만들 수 있습니다:

```bash
python3 implementation/phase1/build_peer_spd_column_seed_candidates.py
```

현재 live 산출물:

- [peer_spd_fetch_report.json](/home/betelgeuze/건축구조분석/implementation/phase1/open_data/pbd_hinge/peer_spd_fetch_report.json)
- [peer_spd_column_seed_candidates.json](/home/betelgeuze/건축구조분석/implementation/phase1/open_data/pbd_hinge/peer_spd_column_seed_candidates.json)
- [peer_spd_specimen_pages_report.json](/home/betelgeuze/건축구조분석/implementation/phase1/open_data/pbd_hinge/peer_spd_specimen_pages_report.json)
- [peer_spd_hysteresis_resources_report.json](/home/betelgeuze/건축구조분석/implementation/phase1/open_data/pbd_hinge/peer_spd_hysteresis_resources_report.json)
- [peer_spd_column_materialize_report.json](/home/betelgeuze/건축구조분석/implementation/phase1/open_data/pbd_hinge/peer_spd_column_materialize_report.json)
- [pbd_hinge_benchmark_asset_registry.json](/home/betelgeuze/건축구조분석/implementation/phase1/open_data/pbd_hinge/pbd_hinge_benchmark_asset_registry.json)
- [peer_spd_hinge_benchmark_gate_report.json](/home/betelgeuze/건축구조분석/implementation/phase1/open_data/pbd_hinge/peer_spd_hinge_benchmark_gate_report.json)

selected specimen page를 내려서 raw page/resource bundle을 만들려면:

```bash
python3 implementation/phase1/fetch_peer_spd_specimen_pages.py
```

이미 받아둔 HTML cache만으로 report를 재생성하려면:

```bash
python3 implementation/phase1/fetch_peer_spd_specimen_pages.py --prefer-cache
```

selected specimen page의 txt resource를 내려서 raw specimen JSON을 만들려면:

```bash
python3 implementation/phase1/fetch_peer_spd_hysteresis_resources.py
```

이미 받아둔 txt cache만으로 raw specimen JSON/report를 재생성하려면:

```bash
python3 implementation/phase1/fetch_peer_spd_hysteresis_resources.py --prefer-cache
```

raw specimen JSON부터 hinge fixture까지 한 번에 materialize하려면:

```bash
python3 implementation/phase1/materialize_peer_spd_column_seed.py --prefer-cache
```

현재 properties-based preselection으로 고른 specimen은 아래 5건입니다.

1. `peer_spd_rc_column_rectangular_seed_01` -> `121` `Galeota et al. 1996, AB1`
2. `peer_spd_rc_column_rectangular_seed_02` -> `29` `Nagasaka 1982, HPRC19-32`
3. `peer_spd_rc_column_spiral_seed_01` -> `276` `Ang et al. 1985, No. 10`
4. `peer_spd_rc_column_rebar_sensitive_seed_01` -> `121` `Galeota et al. 1996, AB1`
5. `peer_spd_rc_column_holdout_seed_01` -> `299` `Petrovski and Ristic 1984, M1E1`

현재 specimen page 단계 상태:

1. `selected_seed_count = 5`
2. `fetch_pass_count = 5`
3. `parse_pass_count = 5`
4. `resource_link_count_total = 7`
5. `hysteresis_link_candidate_count_total = 7`

현재 hysteresis/text resource 단계 상태:

1. `selected_seed_count = 5`
2. `fetch_pass_count = 5`
3. `parse_pass_count = 5`
4. `raw_json_written_count = 5`

현재 materialization 단계 상태:

1. `selected_seed_count = 5`
2. `normalized_seed_count = 5`

현재 registry / gate 상태:

1. `benchmark_ready_asset_count = 5`
2. `train_count = 2`
3. `val_count = 2`
4. `holdout_count = 1`
5. `rebar_sensitive_count = 1`
6. `confinement_sensitive_count = 1`
7. `peer_spd_hinge_benchmark_gate = PASS`

즉 지금은

1. 공식 specimen table에서 후보 ID를 고르고
2. `specimen_display_url`과 specimen page snapshot을 고정하고
3. txt resource를 실제로 내려받아 `raw specimen json`을 만들고
4. 그 raw를 `hinge fixture`로 정규화하고
5. train / val / holdout diversified benchmark pool로 registry/gate까지 검증하는

usable benchmark 단계까지 올라온 상태입니다.

준비 단계입니다.

## E-Defense / PEER blind prediction scaffold

다음 frontier용 scaffold도 추가했습니다.

- seed manifest:
  [edefense_peer_blind_prediction_seed_manifest.json](/home/betelgeuze/건축구조분석/implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_manifest.json)
- source manifest helper:
  [prepare_edefense_peer_blind_prediction_source_manifest.py](/home/betelgeuze/건축구조분석/implementation/phase1/prepare_edefense_peer_blind_prediction_source_manifest.py)

권장 local landing root:

- `implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01/`

필수 artifact group:

1. geometry/model
2. material/section properties
3. excitation history
4. measured response

local package를 받은 뒤 source manifest를 만들려면:

```bash
python3 implementation/phase1/prepare_edefense_peer_blind_prediction_source_manifest.py \
  --input-root implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01 \
  --out implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.source_manifest.json
```

이 `source_manifest`가 blind-prediction onboarding의 provenance anchor입니다.
이후 public-input bundle report, measured-response landing status, input contract, prebenchmark scaffold는 모두 이 manifest를 기준으로 현재 completeness를 읽습니다.

source discovery와 public fetch를 먼저 고정하려면:

```bash
python3 implementation/phase1/probe_edefense_peer_blind_prediction_sources.py \
  --out implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.download_probe.json

python3 implementation/phase1/fetch_edefense_peer_blind_prediction_seed_package.py \
  --probe-json implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.download_probe.json \
  --out-dir implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01
```

이 단계의 provenance chain은 아래 순서입니다.

1. `download_probe.json`
   public page에서 직접 보이는 파일 링크 inventory
2. `fetch_report.json`
   실제 landing root에 내려받은 파일과 existing/downloaded 상태
3. `source_manifest.json`
   blind-prediction required group 4개 중 어디까지 닫혔는지 판정하는 기준

주의:

- `E-Defense 2009` 자체는 현재도 article PDF 중심이라 manual landing helper가 맞습니다.
- 반면 `PEER blind prediction contest` input-data page는 `Materials.zip`, `GMs.xlsx`, drawing PDF들이 직접 공개돼 있어 자동 fetch가 가능합니다.
- 현재 live 상태는 `geometry/material/excitation`까지는 public path로 닫히고, `measured response`는 아직 별도 확보가 필요합니다.

현재 live artifact:

- [edefense_peer_blind_prediction_seed_01.download_probe.json](/home/betelgeuze/건축구조분석/implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.download_probe.json)
- [edefense_peer_blind_prediction_seed_01.fetch_report.json](/home/betelgeuze/건축구조분석/implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.fetch_report.json)
- [edefense_peer_blind_prediction_seed_01.source_manifest.json](/home/betelgeuze/건축구조분석/implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.source_manifest.json)

현재 live state 요약:

1. `download_probe`: `page_count=4`, `direct_download_count=17`
2. `fetch_report`: `downloaded=8`, `existing=9`
3. `source_manifest`: `required_group_pass_count=3/4`
   geometry / material / excitation은 public bundle로 닫혔고, measured response만 비어 있습니다.

public input bundle을 구조화된 normalization-prep report로 요약하려면:

```bash
python3 implementation/phase1/prepare_peer_blind_prediction_public_input_bundle.py \
  --root implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01 \
  --source-manifest implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.source_manifest.json \
  --out implementation/phase1/open_data/pbd_hinge/peer_blind_prediction_public_input_bundle_report.json
```

measured response manual landing provenance를 canonical manifest로 고정하려면:

```bash
python3 implementation/phase1/prepare_edefense_peer_measured_response_landing_manifest.py \
  --source-manifest implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.source_manifest.json \
  --input-root implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01 \
  --out implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.measured_response_landing_manifest.json
```

새 live artifact:

- [peer_blind_prediction_public_input_bundle_report.json](/home/betelgeuze/건축구조분석/implementation/phase1/open_data/pbd_hinge/peer_blind_prediction_public_input_bundle_report.json)
- [edefense_peer_blind_prediction_seed_01.measured_response_landing_manifest.json](/home/betelgeuze/건축구조분석/implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.measured_response_landing_manifest.json)

현재 live state:

1. `peer_blind_prediction_public_input_bundle_report`:
   `PASS_INPUT_READY_MEASURED_PENDING`
   `geometry_docs=6 | materials=yes | gm_workbook=yes | measured_response=pending`
2. `edefense_peer_blind_prediction_seed_01.measured_response_landing_manifest`:
   `ERR_MEASURED_RESPONSE_PENDING_MANUAL_LANDING`
   `matched=0 | csv=0 | accel_candidates=0 | drift_candidates=0 | sensors=0`

public input를 실제 normalize contract로 고정하려면:

```bash
python3 implementation/phase1/prepare_peer_blind_prediction_input_contract.py \
  --bundle-report implementation/phase1/open_data/pbd_hinge/peer_blind_prediction_public_input_bundle_report.json \
  --source-manifest implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.source_manifest.json \
  --measured-status implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.measured_response_landing_status.json \
  --measured-landing-manifest implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.measured_response_landing_manifest.json \
  --out implementation/phase1/open_data/pbd_hinge/peer_blind_prediction_input_contract.json
```

measured response 수동 landing을 위한 accepted pattern / bundle layout template를 만들려면:

```bash
python3 implementation/phase1/prepare_edefense_peer_measured_response_landing_template.py \
  --source-manifest implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.source_manifest.json \
  --input-contract implementation/phase1/open_data/pbd_hinge/peer_blind_prediction_input_contract.json \
  --out implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.measured_response_template.json
```

public input ready 상태를 `benchmark_case -> compare_report -> viewer_entry` 전 단계 scaffold로 고정하려면:

```bash
python3 implementation/phase1/build_peer_blind_prediction_prebenchmark_scaffold.py \
  --input-contract implementation/phase1/open_data/pbd_hinge/peer_blind_prediction_input_contract.json \
  --measured-status implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.measured_response_landing_status.json \
  --out implementation/phase1/open_data/pbd_hinge/peer_blind_prediction_prebenchmark_scaffold.json
```

추가 live artifact:

- [peer_blind_prediction_input_contract.json](/home/betelgeuze/건축구조분석/implementation/phase1/open_data/pbd_hinge/peer_blind_prediction_input_contract.json)
- [edefense_peer_blind_prediction_seed_01.measured_response_template.json](/home/betelgeuze/건축구조분석/implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.measured_response_template.json)
- [peer_blind_prediction_prebenchmark_scaffold.json](/home/betelgeuze/건축구조분석/implementation/phase1/open_data/pbd_hinge/peer_blind_prediction_prebenchmark_scaffold.json)

현재 live state:

1. `peer_blind_prediction_input_contract`:
   `PASS_INPUT_CONTRACT_READY_MEASURED_PENDING`
   `gm_cases=10 | groups=3/4 | measured_response=pending`
   `landing_manifest=recorded`
2. `edefense_peer_blind_prediction_seed_01.measured_response_template`:
   `READY | expected_patterns=5 | gm_cases=10`
3. `peer_blind_prediction_prebenchmark_scaffold`:
   `PENDING | cases=10 | measured_response=pending`

landed measured response를 normalize하려면:

```bash
python3 implementation/phase1/normalize_edefense_peer_measured_response_bundle.py \
  --input-root implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01 \
  --template implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.measured_response_template.json \
  --landing-manifest implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.measured_response_landing_manifest.json \
  --out implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.measured_response_normalized.json
```

blind-prediction benchmark case scaffold를 실제 case payload로 만들려면:

```bash
python3 implementation/phase1/build_peer_blind_prediction_benchmark_cases.py \
  --input-contract implementation/phase1/open_data/pbd_hinge/peer_blind_prediction_input_contract.json \
  --measured-normalized implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.measured_response_normalized.json \
  --scaffold implementation/phase1/open_data/pbd_hinge/peer_blind_prediction_prebenchmark_scaffold.json \
  --cases-out implementation/phase1/commercial_benchmark_cases.peer_blind_prediction_open.json \
  --report-out implementation/phase1/open_data/pbd_hinge/peer_blind_prediction_case_build_report.json
```

results explorer compare lane용 summary report를 만들려면:

```bash
python3 implementation/phase1/run_peer_blind_prediction_compare_report.py \
  --cases implementation/phase1/commercial_benchmark_cases.peer_blind_prediction_open.json \
  --build-report implementation/phase1/open_data/pbd_hinge/peer_blind_prediction_case_build_report.json \
  --measured-normalized implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.measured_response_normalized.json \
  --out implementation/phase1/release/benchmark_expansion/peer_blind_prediction_compare_report.json
```

추가 live artifact:

- [edefense_peer_blind_prediction_seed_01.measured_response_normalized.json](/home/betelgeuze/건축구조분석/implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.measured_response_normalized.json)
- [commercial_benchmark_cases.peer_blind_prediction_open.json](/home/betelgeuze/건축구조분석/implementation/phase1/commercial_benchmark_cases.peer_blind_prediction_open.json)
- [peer_blind_prediction_case_build_report.json](/home/betelgeuze/건축구조분석/implementation/phase1/open_data/pbd_hinge/peer_blind_prediction_case_build_report.json)
- [peer_blind_prediction_compare_report.json](/home/betelgeuze/건축구조분석/implementation/phase1/release/benchmark_expansion/peer_blind_prediction_compare_report.json)

지금 live 상태는 `compare pending`이지만, measured response bundle만 landing되면 `benchmark_case -> compare_report -> viewer lane`이 그대로 compare-ready로 전환됩니다.

sample measured-response landing으로 compare path를 end-to-end 검증하려면:

```bash
python3 implementation/phase1/materialize_peer_blind_prediction_sample_measured_response.py \
  --input-contract implementation/phase1/open_data/pbd_hinge/peer_blind_prediction_input_contract.json \
  --out-root implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01_sample_measured_response \
  --report-out implementation/phase1/open_data/pbd_hinge/peer_blind_prediction_sample_measured_response_report.json

python3 implementation/phase1/normalize_edefense_peer_measured_response_bundle.py \
  --input-root implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01_sample_measured_response \
  --template implementation/phase1/open_data/pbd_hinge/edefense_peer_blind_prediction_seed_01.measured_response_template.json \
  --out implementation/phase1/open_data/pbd_hinge/peer_blind_prediction_sample_measured_response_normalized.json

python3 implementation/phase1/build_peer_blind_prediction_benchmark_cases.py \
  --input-contract implementation/phase1/open_data/pbd_hinge/peer_blind_prediction_input_contract.json \
  --measured-normalized implementation/phase1/open_data/pbd_hinge/peer_blind_prediction_sample_measured_response_normalized.json \
  --scaffold implementation/phase1/open_data/pbd_hinge/peer_blind_prediction_prebenchmark_scaffold.json \
  --cases-out implementation/phase1/commercial_benchmark_cases.peer_blind_prediction_sample_ready.json \
  --report-out implementation/phase1/open_data/pbd_hinge/peer_blind_prediction_sample_case_build_report.json

python3 implementation/phase1/run_peer_blind_prediction_compare_report.py \
  --cases implementation/phase1/commercial_benchmark_cases.peer_blind_prediction_sample_ready.json \
  --build-report implementation/phase1/open_data/pbd_hinge/peer_blind_prediction_sample_case_build_report.json \
  --measured-normalized implementation/phase1/open_data/pbd_hinge/peer_blind_prediction_sample_measured_response_normalized.json \
  --out implementation/phase1/release/benchmark_expansion/peer_blind_prediction_sample_compare_report.json
```

sample live artifact:

- [peer_blind_prediction_sample_measured_response_report.json](/home/betelgeuze/건축구조분석/implementation/phase1/open_data/pbd_hinge/peer_blind_prediction_sample_measured_response_report.json)
- [peer_blind_prediction_sample_measured_response_normalized.json](/home/betelgeuze/건축구조분석/implementation/phase1/open_data/pbd_hinge/peer_blind_prediction_sample_measured_response_normalized.json)
- [commercial_benchmark_cases.peer_blind_prediction_sample_ready.json](/home/betelgeuze/건축구조분석/implementation/phase1/commercial_benchmark_cases.peer_blind_prediction_sample_ready.json)
- [peer_blind_prediction_sample_case_build_report.json](/home/betelgeuze/건축구조분석/implementation/phase1/open_data/pbd_hinge/peer_blind_prediction_sample_case_build_report.json)
- [peer_blind_prediction_sample_compare_report.json](/home/betelgeuze/건축구조분석/implementation/phase1/release/benchmark_expansion/peer_blind_prediction_sample_compare_report.json)
