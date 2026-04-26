# Hardest External Benchmark Case KPI Receipt

- `case_id`: `iass_dome_snapthrough`
- `case_label`: `IASS Dome Snap-through`
- `benchmark_family`: `buckling_snapthrough`
- `hazard_family`: `buckling_instability`
- `topology_family`: `shell_dome_large_deformation`
- `load_path_family`: `limit_point_snapthrough`
- `primary_report`: `implementation/phase1/buckling_contract_report.json`

## KPI Rows

| KPI | Value | Source |
|---|---|---|
| critical_load_factor | 2.242 | primary.critical_load_factor |
| mode_count | 2 | primary.mode_count |
| selected_mode | 1 | primary.selected_mode |
| layered_family_count | 6 | supporting.nonlinear_generalization.summary.layered_family_count |

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
