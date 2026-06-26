# Template Evidence Safety Report

- `summary_line`: `Template evidence safety: PASS | templates=7 | validator_probes=7 | blockers=0`
- `contract_pass`: `True`
- `template_dir`: `docs/templates`

## Templates

| Template | Template Only | Pass Signals | Placeholders | Probe | Blockers |
|---|---:|---:|---:|---:|---|
| `customer_audit_failure_bundle_sla.template.json` | `True` | `0` | `2` | `True` | `none` |
| `customer_shadow_evidence.template.json` | `True` | `0` | `2` | `True` | `none` |
| `family_validation_manual_signoff.template.json` | `True` | `0` | `2` | `True` | `none` |
| `fresh_validation_receipt.template.json` | `True` | `0` | `2` | `True` | `none` |
| `independent_vv_attestation.template.json` | `True` | `0` | `2` | `True` | `none` |
| `license_status.template.json` | `True` | `0` | `7` | `True` | `none` |
| `ux_new_user_observation.template.json` | `True` | `0` | `2` | `True` | `none` |

## Validator Probes

| Probe | Pass | Validator Pass | State | Template |
|---|---:|---:|---|---|
| `customer_shadow_evidence_template_probe` | `True` | `False` | `template_rejected_as_customer_shadow_evidence` | `docs/templates/customer_shadow_evidence.template.json` |
| `fresh_validation_receipt_template_probe` | `True` | `False` | `template_rejected_as_fresh_validation_evidence` | `docs/templates/fresh_validation_receipt.template.json` |
| `license_status_template_probe` | `True` | `False` | `template_rejected_as_license_evidence` | `docs/templates/license_status.template.json` |
| `ux_new_user_observation_template_probe` | `True` | `False` | `template_rejected_as_ux_evidence` | `docs/templates/ux_new_user_observation.template.json` |
| `independent_vv_attestation_template_probe` | `True` | `False` | `template_only_external_signoff_evidence` | `docs/templates/independent_vv_attestation.template.json` |
| `family_validation_manual_signoff_template_probe` | `True` | `False` | `template_only_external_signoff_evidence` | `docs/templates/family_validation_manual_signoff.template.json` |
| `customer_audit_failure_bundle_sla_template_probe` | `True` | `False` | `template_only_external_signoff_evidence` | `docs/templates/customer_audit_failure_bundle_sla.template.json` |
