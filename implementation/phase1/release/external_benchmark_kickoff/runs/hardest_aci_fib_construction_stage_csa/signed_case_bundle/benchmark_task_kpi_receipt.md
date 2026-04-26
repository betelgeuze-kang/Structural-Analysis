# Hardest External Benchmark Case KPI Receipt

- `case_id`: `aci_fib_construction_stage_csa`
- `case_label`: `ACI / FIB Construction Stage CSA`
- `benchmark_family`: `construction_stage_time_dependent`
- `hazard_family`: `time_dependent_construction`
- `topology_family`: `staged_highrise_megastructure`
- `load_path_family`: `creep_shrinkage_stage_sequence`
- `primary_report`: `implementation/phase1/construction_sequence_gate_report.json`

## KPI Rows

| KPI | Value | Source |
|---|---|---|
| case_count | 4 | primary.summary.case_count |
| stage_count | 24 | primary.summary.stage_count |
| construction_years | 4.0 | primary.summary.construction_years |
| max_differential_shortening_mm | 38.33072269918383 | primary.summary.max_differential_shortening_mm |
| mean_creep_index | 0.9999996474401244 | primary.summary.mean_creep_index |
| mean_shrinkage_index | 0.6170546560702105 | primary.summary.mean_shrinkage_index |

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
