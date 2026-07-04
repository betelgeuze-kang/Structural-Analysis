# Public Benchmark Source Access Preflight Receipt

- `status`: `reachable`
- `contract_pass`: `True`
- `network_probe_performed`: `True`
- `source_access_probe_row_count`: `6`
- `reachable_count`: `6`
- `blocked_count`: `0`
- `not_run_count`: `0`

## Probe Rows

| Source | Status | Primary Status | Fallback Status | Blockers |
|---|---|---|---|---|
| `pdbbind_plus_casf` | `primary_reachable` | `reachable` (200) | `reachable` (200) |  |
| `dud_e` | `primary_reachable` | `reachable` (200) | `reachable` (200) |  |
| `lit_pcba` | `primary_reachable` | `reachable` (200) | `reachable` (200) |  |
| `autodock_vina` | `primary_reachable` | `reachable` (200) | `reachable` (200) |  |
| `gnina` | `primary_reachable` | `reachable` (200) | `reachable` (200) |  |
| `posebusters` | `primary_reachable` | `reachable` (200) | `reachable` (200) |  |

## Command

- `network_probe_command`: `python3 scripts/build_public_benchmark_source_access_preflight_receipt.py --source-plan implementation/phase1/release_evidence/productization/public_benchmark_phase2_source_acquisition_plan.json --out implementation/phase1/release_evidence/productization/public_benchmark_source_access_preflight_receipt.json --out-md implementation/phase1/release_evidence/productization/public_benchmark_source_access_preflight_receipt.md --probe-network`

This receipt performs HEAD-only source access preflight checks. It does not download, redistribute, checksum, license, or prove raw benchmark payloads, and it does not close Public Benchmark Phase 2.
