# Hardest External Benchmark Case KPI Receipt

- `case_id`: `caarc_wind_standard_tower`
- `case_label`: `CAARC Wind Standard Tower`
- `benchmark_family`: `wind_time_history`
- `hazard_family`: `wind_dynamic`
- `topology_family`: `aeroelastic_tall_tower`
- `load_path_family`: `pressure_series_mapping`
- `primary_report`: `implementation/phase1/wind_time_history_gate_report.json`

## KPI Rows

| KPI | Value | Source |
|---|---|---|
| selected_case_count | 4 | primary.summary.selected_case_count |
| duration_hours | 10.0 | primary.summary.duration_hours |
| load_reversal_count | 7560 | primary.summary.load_reversal_count |
| dominant_frequency_hz | 0.105 | primary.summary.dominant_frequency_hz |
| max_drift_ratio_pct_all_cases | 0.000806268371805018 | primary.summary.max_drift_ratio_pct_all_cases |
| residual_drift_pct_max_abs | 0.00011317580211746988 | primary.summary.residual_drift_pct_max_abs |

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
