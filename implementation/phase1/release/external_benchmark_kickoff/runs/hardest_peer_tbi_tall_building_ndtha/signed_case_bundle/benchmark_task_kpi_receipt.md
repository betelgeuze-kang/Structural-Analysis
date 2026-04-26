# Hardest External Benchmark Case KPI Receipt

- `case_id`: `peer_tbi_tall_building_ndtha`
- `case_label`: `PEER TBI Tall Building NDTHA`
- `benchmark_family`: `highrise_ndtha`
- `hazard_family`: `seismic`
- `topology_family`: `tall_building_core_outrigger`
- `load_path_family`: `ndtha_multi_record`
- `primary_report`: `implementation/phase1/nonlinear_ndtha_stress_report.json`

## KPI Rows

| KPI | Value | Source |
|---|---|---|
| case_count | 3 | primary.summary.case_count |
| max_drift_ratio_pct_max | 9.200000000000003 | primary.summary.max_drift_ratio_pct_max |
| peak_plastic_story_count_mean | 22.666666666666668 | primary.summary.peak_plastic_story_count_mean |
| avg_step_iterations_mean | 16.0 | primary.summary.avg_step_iterations_mean |
| residual_drift_ratio_pct_max_abs | 1.9136000000000006 | primary.summary.residual_drift_ratio_pct_max_abs |
| solver_hip_variants | 20 | supporting.solver_hip.summary.solver_count |

## Appendix: MIDAS Native Roundtrip / Write-Back

- `summary`: `MIDAS native write-back diff receipts: PASS | ready=14 | receipts=14/14 | topology=14/14 | load=14/14 | loadcomb=14/14 exact | types=4 | taxonomy=exact:13,canonical:1,lossy:0,unsupported:0,manual:1 | pending_review=2`
- `honest_counts`: public_native_ready=0 | public_preview_ready=0 | public_source_ready=0 | structure_types=0
- `appendix_md`: `implementation/phase1/release/midas_native_roundtrip/unsupported_lossy_card_family_appendix.md`
- `appendix_json`: `implementation/phase1/release/midas_native_roundtrip/unsupported_lossy_card_family_appendix.json`
- `structure_type_batches`:
  - `implementation/phase1/release/midas_native_roundtrip/bridge.diff_batch.md`
  - `implementation/phase1/release/midas_native_roundtrip/building.diff_batch.md`
  - `implementation/phase1/release/midas_native_roundtrip/foundation.diff_batch.md`
  - `implementation/phase1/release/midas_native_roundtrip/vertical_circulation.diff_batch.md`
