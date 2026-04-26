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
