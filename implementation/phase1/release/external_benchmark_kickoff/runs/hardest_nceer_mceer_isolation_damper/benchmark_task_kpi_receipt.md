# Hardest External Benchmark Case KPI Receipt

- `case_id`: `nceer_mceer_isolation_damper`
- `case_label`: `NCEER / MCEER Isolation-Damper`
- `benchmark_family`: `seismic_isolation_damping`
- `hazard_family`: `seismic_isolated`
- `topology_family`: `base_isolation_damper_network`
- `load_path_family`: `hysteretic_device_sequence`
- `primary_report`: `implementation/phase1/damper_validation_gate_report.json`

## KPI Rows

| KPI | Value | Source |
|---|---|---|
| case_count | 3 | primary.summary.case_count |
| waveform_corr_min | 0.962532707045799 | primary.summary.waveform_corr_min |
| phase_error_ms_max | 30.0 | primary.summary.phase_error_ms_max |
| residual_drift_mm_max | 0.66292 | primary.summary.residual_drift_mm_max |
| damping_reduction_ratio_mean | 0.0003541342972751874 | primary.summary.damping_reduction_ratio_mean |
| device_section_family_count | 4 | supporting.nonlinear_generalization.summary.device_section_family_count |

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
