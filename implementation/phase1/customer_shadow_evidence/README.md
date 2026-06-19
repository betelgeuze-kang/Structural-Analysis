# Customer Shadow Evidence Landing Zone

This directory is for derived customer shadow evidence metadata JSON only.

Do not commit customer raw models, drawings, solver exports, PDFs, spreadsheets, private project names, or other raw customer data here. Each committed JSON file must be derived metadata that passes:

```bash
python3 implementation/phase1/validate_customer_shadow_evidence.py --evidence <metadata.json> --json --fail-blocked
```

Required policy:

- `project_status` must be `completed`
- `raw_data_retained_by_customer` must be `true`
- `redistribution_allowed` must be `false`
- `reference_output_checksum` must be a SHA256 reference to customer-retained output
- `our_engine_commit` must identify the engine commit used for comparison
- `delta_metrics.max_relative_error_pct` and `residual_metrics.normalized_equilibrium_residual` must be numeric
