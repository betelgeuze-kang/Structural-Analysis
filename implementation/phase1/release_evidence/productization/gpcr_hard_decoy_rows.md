# GPCR Hard-Decoy ChEMBL Activity Rows

- `status`: `raw_activity_rows_ready`
- `contract_pass`: `True`
- `raw_rows_ready`: `True`
- `actual_closure_ready`: `False`
- `row_count`: `96`

| Target | Positives | Decoys | Total |
|---|---:|---:|---:|
| `DRD2` | 12 | 20 | 32 |
| `HTR2A` | 12 | 20 | 32 |
| `OPRM1` | 12 | 20 | 32 |

This artifact materializes source-attached GPCR ranking rows from official ChEMBL activity snapshots. It enables importer and suite verification, but does not by itself change the default GPCR suite report or promote broad GPCR hard-decoy closure.
