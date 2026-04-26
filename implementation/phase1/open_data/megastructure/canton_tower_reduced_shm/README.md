# Canton Tower Reduced SHM Landing Root

이 디렉터리는 공개 `Canton Tower / Guangzhou TV Tower` reduced-order SHM benchmark의 local landing root입니다.

권장 흐름:

1. 공식 benchmark 페이지를 probe 해서 공개 링크를 고정
2. 최소 패키지를 이 디렉터리에 저장
3. source manifest를 생성
4. 기존 megastructure intake 체인으로 변환

공식 source probe:

```bash
python3 implementation/phase1/probe_canton_tower_reduced_shm_sources.py \
  --out implementation/phase1/open_data/megastructure/canton_tower_reduced_shm.download_probe.json
```

최소 패키지를 자동 다운로드하려면:

```bash
python3 implementation/phase1/fetch_canton_tower_reduced_shm_package.py \
  --probe-json implementation/phase1/open_data/megastructure/canton_tower_reduced_shm.download_probe.json \
  --out-dir implementation/phase1/open_data/megastructure/canton_tower_reduced_shm
```

권장 최소 패키지:

1. `system_matrices.mat`
2. `Phase_I_measurement_description.pdf`
3. `Phase_I_FE_model_description.pdf`
4. `Phase_I_data_all.zip`

raw txt bundle을 generic converter가 읽을 수 있는 CSV로 정규화하려면:

```bash
python3 implementation/phase1/normalize_canton_tower_reduced_shm_package.py \
  --zip-path implementation/phase1/open_data/megastructure/canton_tower_reduced_shm/Phase_I_data_all.zip \
  --out-dir implementation/phase1/open_data/megastructure/canton_tower_reduced_shm/normalized_csv \
  --report-out implementation/phase1/open_data/megastructure/canton_tower_reduced_shm/canton_tower_normalization_report.json \
  --hour-count 1
```

패키지를 여기에 넣은 뒤 source manifest 생성:

```bash
python3 implementation/phase1/prepare_canton_tower_reduced_shm_source_manifest.py \
  --input-root implementation/phase1/open_data/megastructure/canton_tower_reduced_shm \
  --out implementation/phase1/open_data/megastructure/canton_tower_reduced_shm.source_manifest.json
```

그 다음 기존 generic converter 실행:

```bash
python3 implementation/phase1/build_cases_from_megastructure_open.py \
  --candidate-id canton_tower_reduced_shm_benchmark \
  --input-path implementation/phase1/open_data/megastructure/canton_tower_reduced_shm \
  --catalog implementation/phase1/open_data/megastructure/mega_structure_catalog.json \
  --require-source-manifest \
  --source-manifest-out implementation/phase1/open_data/megastructure/canton_tower_conversion_report.source_manifest.json \
  --dynamic-out implementation/phase1/spatiotemporal_data/canton_tower_dynamic_cases.jsonl \
  --benchmark-out implementation/phase1/commercial_benchmark_cases.canton_tower_open.json \
  --report-out implementation/phase1/open_data/megastructure/canton_tower_conversion_report.json \
  --case-id-prefix canton_tower_reduced_shm
```
