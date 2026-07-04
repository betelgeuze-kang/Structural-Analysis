# Public Benchmark Vina/GNINA Input Manifest Template Preflight

- `status`: `operator_manifest_completion_required`
- `contract_pass`: `True`
- `manifest_ready`: `False`
- `template_row_count`: `12`
- `missing_required_value_count`: `36`
- `missing_local_file_count`: `48`
- `missing_receipt_ref_count`: `60`

## Case Rows

| Case | Status | Missing Fields | Missing Files | Missing Refs |
|---|---|---|---|---|
| `casf2016_4llx` | `operator_completion_required` | `3` | `4` | `5` |
| `casf2016_5c28` | `operator_completion_required` | `3` | `4` | `5` |
| `casf2016_3uuo` | `operator_completion_required` | `3` | `4` | `5` |
| `casf2016_3ui7` | `operator_completion_required` | `3` | `4` | `5` |
| `casf2016_5c2h` | `operator_completion_required` | `3` | `4` | `5` |
| `casf2016_2v00` | `operator_completion_required` | `3` | `4` | `5` |
| `casf2016_3wz8` | `operator_completion_required` | `3` | `4` | `5` |
| `casf2016_3pww` | `operator_completion_required` | `3` | `4` | `5` |
| `casf2016_3prs` | `operator_completion_required` | `3` | `4` | `5` |
| `casf2016_3uri` | `operator_completion_required` | `3` | `4` | `5` |
| `casf2016_4m0z` | `operator_completion_required` | `3` | `4` | `5` |
| `casf2016_4m0y` | `operator_completion_required` | `3` | `4` | `5` |

## Commands

- `write_preflight`: `python3 scripts/build_public_benchmark_vina_gnina_input_manifest_template_preflight.py --out implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest_template_preflight.json --out-md implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_input_manifest_template_preflight.md`
- `rerun_execution_plan`: `python3 scripts/build_public_benchmark_vina_gnina_execution_plan.py --out implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_execution_plan.json`
- `rerun_runtime_readiness`: `python3 scripts/build_public_benchmark_vina_gnina_runtime_readiness.py --out implementation/phase1/release_evidence/productization/public_benchmark_vina_gnina_runtime_readiness.json`

This preflight audits the operator input-manifest template only. It does not promote the template to an actual manifest, verify license rights, run Vina/GNINA, create adapter rows, or close Public Benchmark Phase 2.
