# Evidence Console Scope Status

- `summary_line`: `Evidence Console scope: BLOCKED | features=7/7 | deferred_gui=5/5 | prerequisites=4/5`
- `scope_contract_pass`: `True`
- `launch_ready`: `False`

| Evidence Console Feature | Pass |
|---|---|
| `case_list` | `True` |
| `source_provenance_inspector` | `True` |
| `reference_vs_engine_comparison` | `True` |
| `residual_audit` | `True` |
| `worst_member_story` | `True` |
| `reviewer_decision` | `True` |
| `reproduce_bundle_export` | `True` |

| Deferred GUI Surface | Visible |
|---|---|
| `full_project_dashboard` | `True` |
| `model_editor` | `True` |
| `accounts_permissions` | `True` |
| `collaboration` | `True` |
| `licensing` | `True` |

| Launch Prerequisite | Pass |
|---|---|
| `p0_closed` | `True` |
| `p1_readiness_unblocked` | `True` |
| `p1_benchmark_breadth_ready` | `True` |
| `real_project_measured_status_pass` | `True` |
| `customer_shadow_completed_project_cases_ready` | `False` |

## Blockers

- `launch_prerequisite_blocked:customer_shadow_completed_project_cases_ready`
