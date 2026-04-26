# Wind Data

- `across_wind_10h_dt1s.csv`: long-duration across-wind load series (10h, dt=1s).
- `across_wind_10h_dt1s.manifest.json`: provenance/hash contract for gate input.
- `tpu_hffb_seed_manifest.json`: next-step official TPU wind-tunnel benchmark seed selection for diversifying raw HFFB mapping validation.
- `tpu_hffb_benchmark_gate_report.json`: TPU official raw HFFB diversified benchmark gate. This is intentionally separate from the 10h `across_wind_force_kN` gate.

TPU raw CSV를 manifest로 정리하려면:

```bash
python3 implementation/phase1/prepare_tpu_hffb_seed.py \
  --seed-id tpu_hffb_isolated_highrise_seed_01 \
  --raw-wind path/to/raw.csv
```

TPU case page에서 `.mat`를 받아 CSV까지 만들려면:

```bash
python3 implementation/phase1/fetch_tpu_case_mat.py \
  --case-id 1202

python3 implementation/phase1/convert_tpu_mat_to_csv.py \
  --input-mat implementation/phase1/open_data/wind/tpu/1202.mat
```

한 번에 seed까지 materialize하려면:

```bash
python3 implementation/phase1/materialize_tpu_hffb_seed.py \
  --seed-id tpu_hffb_isolated_highrise_seed_01 \
  --case-id 1202 \
  --dataset-key pressure \
  --time-key time
```

실제 공식 TPU probe 결과도 남겨뒀습니다.

1. `case=616`
   - [case_616_materialized.materialize_report.json](/home/betelgeuze/건축구조분석/implementation/phase1/open_data/wind/tpu/case_616_materialized.materialize_report.json)
   - 현재 결과: `PASS`
   - final manifest: [tpu_hffb_isolated_highrise_seed_01.source_manifest.json](/home/betelgeuze/건축구조분석/implementation/phase1/open_data/wind/tpu/case_616_materialized/tpu_hffb_isolated_highrise_seed_01.source_manifest.json)
2. `case=1202`
   - [case_1202_probe.materialize_report.json](/home/betelgeuze/건축구조분석/implementation/phase1/open_data/wind/tpu/case_1202_probe.materialize_report.json)
   - 현재 결과: `ERR_FETCH_STEP`
   - fetch 상세: [tpu_hffb_isolated_highrise_seed_01.fetch_report.json](/home/betelgeuze/건축구조분석/implementation/phase1/open_data/wind/tpu/case_1202_probe/tpu_hffb_isolated_highrise_seed_01.fetch_report.json)
   - 핵심 원인: 첫 후보 MAT가 `size_bytes=0`
3. `case=917`
   - [case_917_materialized.materialize_report.json](/home/betelgeuze/건축구조분석/implementation/phase1/open_data/wind/tpu/case_917_materialized.materialize_report.json)
   - 현재 결과: `PASS`
   - final manifest: [tpu_hffb_interference_highrise_seed_01.source_manifest.json](/home/betelgeuze/건축구조분석/implementation/phase1/open_data/wind/tpu/case_917_materialized/tpu_hffb_interference_highrise_seed_01.source_manifest.json)

TPU diversified raw HFFB gate를 다시 만들려면:

```bash
python3 implementation/phase1/run_tpu_hffb_benchmark_gate.py
```

현재 live report는 여기 있습니다.

- [tpu_hffb_benchmark_gate_report.json](/home/betelgeuze/건축구조분석/implementation/phase1/open_data/wind/tpu_hffb_benchmark_gate_report.json)

TPU usable case pool을 다시 probe하려면:

```bash
python3 implementation/phase1/probe_tpu_hffb_case_pool.py \
  --case-id 917 \
  --case-id 918 \
  --case-id 919 \
  --case-id 1279 \
  --case-id 1280 \
  --case-id 1202
```

local wind benchmark asset registry를 다시 만들려면:

```bash
python3 implementation/phase1/build_wind_benchmark_asset_registry.py
```
