# Public Benchmark Source Access Preflight Receipt

- `status`: `reachable`
- `contract_pass`: `True`
- `network_probe_performed`: `True`
- `source_access_probe_row_count`: `6`
- `reachable_count`: `6`
- `blocked_count`: `0`
- `not_run_count`: `0`
- `known_content_length_probe_count`: `2`
- `total_known_content_length_gib`: `0.0`
- `largest_known_payload_source_id`: `lit_pcba`

## Probe Rows

| Source | Status | Size Bytes | Primary Status | Fallback Status | Blockers |
|---|---|---:|---|---|---|
| `pdbbind_plus_casf` | `primary_reachable` | `664` | `reachable` (200) | `reachable` (200) |  |
| `dud_e` | `primary_reachable` | `0` | `reachable` (200) | `reachable` (200) |  |
| `lit_pcba` | `primary_reachable` | `49064` | `reachable` (200) | `reachable` (200) |  |
| `autodock_vina` | `primary_reachable` | `0` | `reachable` (200) | `reachable` (200) |  |
| `gnina` | `primary_reachable` | `0` | `reachable` (200) | `reachable` (200) |  |
| `posebusters` | `primary_reachable` | `0` | `reachable` (200) | `reachable` (200) |  |

## Command

- `network_probe_command`: `python3 scripts/build_public_benchmark_source_access_preflight_receipt.py --source-plan implementation/phase1/release_evidence/productization/public_benchmark_phase2_source_acquisition_plan.json --out implementation/phase1/release_evidence/productization/public_benchmark_source_access_preflight_receipt.json --out-md implementation/phase1/release_evidence/productization/public_benchmark_source_access_preflight_receipt.md --probe-network`

This receipt performs HEAD-only source access preflight checks. It does not download, redistribute, checksum, license, or prove raw benchmark payloads, and it does not close Public Benchmark Phase 2.
