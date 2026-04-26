# Hardest External Benchmark Case KPI Receipt

- `case_id`: `nist_fema_progressive_collapse`
- `case_label`: `NIST / FEMA Progressive Collapse`
- `benchmark_family`: `progressive_collapse`
- `hazard_family`: `local_damage_sequence`
- `topology_family`: `frame_column_removal`
- `load_path_family`: `path_dependent_collapse`
- `primary_report`: `implementation/phase1/nonlinear_pushover_stress_report.json`

## KPI Rows

| KPI | Value | Source |
|---|---|---|
| case_count | 3 | primary.summary.case_count |
| first_yield_load_factor_mean | 1.0 | primary.summary.first_yield_load_factor_mean |
| peak_plastic_story_count_mean | 21.666666666666668 | primary.summary.peak_plastic_story_count_mean |
| drift_amplification_mean | 2.0895684797416756 | primary.summary.drift_amplification_mean |
| ndtha_residual_drift_ratio_pct_max_abs | 1.9136000000000006 | supporting.ndtha.summary.residual_drift_ratio_pct_max_abs |
| material_family_count | {'concrete_damage': 48, 'cyclic_degradation': 46, 'bond_interface': 48, 'creep_shrinkage': 7, 'soil_boundary_nonlinear': 11, 'device_dissipation': 10, 'foundation_impedance_nonlinear': 19, 'contact_link_hysteresis': 15, 'panel_zone_joint_response': 12, 'wind_dynamic_response': 16, 'track_support_viscoelasticity': 11, 'vehicle_track_transient_coupling': 19, 'tunnel_soil_wave_attenuation': 13, 'serviceability_velocity_response': 8, 'construction_stage_redistribution': 6, 'joint_constraint_transfer': 5, 'aeroelastic_serviceability': 7, 'heterogeneous_soil_adaptation': 5, 'segment_joint_softening': 5, 'longitudinal_wave_strain_transfer': 5, 'raw_pressure_field_mapping': 5, 'phase_assimilation_correction': 5, 'multiscale_streaming_refinement': 5, 'integrated_vibration_transfer': 5, 'resilience_ood_recovery': 5, 'boundary_absorption_nonlinear': 6, 'attention_load_localization': 6, 'residual_energy_stabilization': 7, 'phase_latency_projection': 5, 'cache_window_adaptation': 5, 'whitebox_feedback_stitching': 5, 'recovery_residual_relock': 5, 'rail_support_contact_modulation': 5, 'tunnel_lining_interface_recovery': 5, 'panel_feedback_residual_transfer': 5, 'wind_pressure_coupled_transfer': 5} | supporting.material_constitutive.summary.calibration_matrix_family_counts |
