# Hardest External Benchmark Case KPI Receipt

- `case_id`: `oc3_oc4_offshore_monopile`
- `case_label`: `OC3 / OC4 Offshore Monopile`
- `benchmark_family`: `offshore_multiphysics_ssi`
- `hazard_family`: `wave_wind_soil_sequence`
- `topology_family`: `offshore_monopile_foundation`
- `load_path_family`: `multiphysics_ssi_fatigue`
- `primary_report`: `implementation/phase1/foundation_soil_link_gate_report.json`

## KPI Rows

| KPI | Value | Source |
|---|---|---|
| foundation_member_type_count | 76 | primary.summary.foundation_member_type_count |
| optimized_foundation_group_count | 2 | primary.summary.optimized_foundation_group_count |
| foundation_link_model_types | ['bearing_bilinear', 'compression_only_penalty', 'coulomb_friction', 'kelvin_voigt_pounding', 'normal_gap_unilateral', 'uplift_seat_unilateral'] | primary.summary.foundation_link_model_types |
| soil_profile | dense_sand | supporting.ssi_boundary.summary.soil_profile |
| dominant_frequency_hz | 3.566666666666667 | supporting.ssi_boundary.summary.dominant_frequency_hz |
| footing_soil_interaction_count | 62 | supporting.surface_interaction.summary.interaction_family_group_ready_counts.footing_soil |
