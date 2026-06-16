# License Status Intake Packet

- `contract_pass`: `False`
- `reason_code`: `ERR_LICENSE_STATUS_OWNER_INPUT_REQUIRED`
- `license_status_path`: `implementation/phase1/release/support_bundle/license_status.json`
- `template_path`: `docs/templates/license_status.template.json`
- `owner_action`: Populate license_status.json from an approved product/legal decision, replacing all template placeholders with real approval evidence before release-area security can pass.

| Field | Current | Required | Closure Check |
|---|---|---|---|
| `status` | `not_configured` | active | approved | valid | `status_active_pass` = `False` |
| `tier` | `` | commercial tier, for example limited-commercial | `tier_present_pass` = `False` |
| `license_id` | `` | non-placeholder license or approval identifier | `license_id_present_pass` = `False` |
| `issuer_or_approver` | `` | product/legal owner or approval authority | `issuer_or_approver_present_pass` = `False` |
| `approval_ref` | `` | legal/product approval reference | `approval_reference_present_pass` = `False` |
| `product_scope` | `` | one or more approved product-scope entries | `product_scope_present_pass` = `False` |
| `expiry_or_perpetual` | `` | future expiry timestamp or perpetual=true | `expiry_valid_pass` = `False` |

## Validation Commands

- `python3 scripts/build_license_status_closure_report.py --out implementation/phase1/release_evidence/productization/license_status_closure_report.json`
- `python3 scripts/report_pm_release_gate.py  --out implementation/phase1/release_evidence/productization/pm_release_gate_report.json --out-md implementation/phase1/release_evidence/productization/pm_release_gate_report.md`
- `python3 scripts/build_pm_release_blocker_action_register.py  --out implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.json --out-md implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.md`
