# Hardest External Benchmark Case KPI Receipt

- `case_id`: `tc204_excavation_tunnel`
- `case_label`: `TC204 Excavation and Adjacent Tunnel`
- `benchmark_family`: `excavation_tunnel_ground_interaction`
- `hazard_family`: `excavation_settlement`
- `topology_family`: `deep_excavation_adjacent_tunnel`
- `load_path_family`: `soil_tunnel_surface_sequence`
- `primary_report`: `implementation/phase1/tunnel_dynamics_dataset_report.json`

## KPI Rows

| KPI | Value | Source |
|---|---|---|
| production_seed_success_count | 96 | primary.production_seed_success_count |
| dataset_case_count | 96 | primary.outputs.case_count |
| max_equilibrium_residual | 0.3860107162910485 | primary.metrics.max_equilibrium_residual |
| mean_displacement_m | 0.00883114351722574 | primary.metrics.mean_displacement_m |
| soil_tunnel_interaction_count | 84 | supporting.surface_interaction.summary.interaction_family_group_ready_counts.soil_tunnel |
| foundation_member_type_count | 76 | supporting.foundation_soil_link.summary.foundation_member_type_count |

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
