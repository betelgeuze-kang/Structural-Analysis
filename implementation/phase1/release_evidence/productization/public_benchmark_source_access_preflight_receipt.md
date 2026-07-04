# Public Benchmark Source Access Preflight Receipt

- `status`: `network_probe_required`
- `contract_pass`: `True`
- `network_probe_performed`: `False`
- `source_access_probe_row_count`: `6`
- `reachable_count`: `0`
- `blocked_count`: `0`
- `not_run_count`: `6`

## Probe Rows

| Source | Status | Primary Status | Fallback Status | Blockers |
|---|---|---|---|---|
| `pdbbind_plus_casf` | `network_probe_not_run` | `not_run` (0) | `not_run` (0) | `source_access_network_probe_not_run` |
| `dud_e` | `network_probe_not_run` | `not_run` (0) | `not_run` (0) | `source_access_network_probe_not_run` |
| `lit_pcba` | `network_probe_not_run` | `not_run` (0) | `not_run` (0) | `source_access_network_probe_not_run` |
| `autodock_vina` | `network_probe_not_run` | `not_run` (0) | `not_run` (0) | `source_access_network_probe_not_run` |
| `gnina` | `network_probe_not_run` | `not_run` (0) | `not_run` (0) | `source_access_network_probe_not_run` |
| `posebusters` | `network_probe_not_run` | `not_run` (0) | `not_run` (0) | `source_access_network_probe_not_run` |

## Command

- `network_probe_command`: `python3 scripts/build_public_benchmark_source_access_preflight_receipt.py --source-plan implementation/phase1/release_evidence/productization/public_benchmark_phase2_source_acquisition_plan.json --out implementation/phase1/release_evidence/productization/public_benchmark_source_access_preflight_receipt.json --out-md implementation/phase1/release_evidence/productization/public_benchmark_source_access_preflight_receipt.md --probe-network`

This receipt performs HEAD-only source access preflight checks. It does not download, redistribute, checksum, license, or prove raw benchmark payloads, and it does not close Public Benchmark Phase 2.
