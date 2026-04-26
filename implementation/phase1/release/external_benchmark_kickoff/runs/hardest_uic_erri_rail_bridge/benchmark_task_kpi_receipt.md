# Hardest External Benchmark Case KPI Receipt

- `case_id`: `uic_erri_rail_bridge`
- `case_label`: `UIC / ERRI Railway Bridge`
- `benchmark_family`: `moving_load_track_bridge`
- `hazard_family`: `moving_load_dynamic`
- `topology_family`: `bridge_track_vehicle`
- `load_path_family`: `moving_axle_sequence`
- `primary_report`: `implementation/phase1/vti_coupled_solver_report.json`

## KPI Rows

| KPI | Value | Source |
|---|---|---|
| step_count | 160 | primary.metrics.step_count |
| converged_ratio | 0.99375 | primary.metrics.converged_ratio |
| max_track_disp_m | 6.766487425586766e-08 | primary.metrics.max_track_disp_m |
| max_contact_force_n | 6.522349912820334 | primary.metrics.max_contact_force_n |
| max_acceleration_mps2 | 47.77269653518046 | supporting.moving_load.metrics.max_acceleration_mps2 |
| energy_balance_relative_error | 0.023668310639223332 | supporting.moving_load.metrics.energy_balance_relative_error |

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
