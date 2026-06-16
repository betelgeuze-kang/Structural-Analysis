# License Status Intake Packet

- `contract_pass`: `False`
- `reason_code`: `ERR_LICENSE_STATUS_OWNER_INPUT_REQUIRED`
- `license_status_path`: `implementation/phase1/release/support_bundle/license_status.json`
- `template_path`: `docs/templates/license_status.template.json`
- `owner_action`: Populate license_status.json from an approved product/legal decision, including approver role, approval timestamp, retrievable evidence reference, scoped product boundary, and no template placeholders before release-area security can pass.

| Field | Current | Required | Closure Check |
|---|---|---|---|
| `status` | `not_configured` | active \| approved \| valid | `status_active_pass` = `False` |
| `tier` | `` | paid-pilot \| limited-commercial | `tier_allowed_pass` = `False` |
| `license_id` | `` | non-placeholder license or approval identifier | `license_id_present_pass` = `False` |
| `issuer_or_approver` | `` | product/legal owner or approval authority | `issuer_or_approver_present_pass` = `False` |
| `approver_role` | `` | product_owner \| legal_counsel \| product_and_legal \| delegated_product_owner | `approver_role_allowed_pass` = `False` |
| `approval_ref` | `` | legal/product approval reference | `approval_reference_present_pass` = `False` |
| `approved_at_utc` | `` | timezone-aware approval timestamp, not future | `approved_at_not_future_pass` = `False` |
| `evidence_ref` | `` | https URL, supported external ref, or existing local evidence path | `evidence_ref_resolvable_pass` = `False` |
| `product_scope` | `` | review-assist, specified-structure-families, specified-workflows, engine-and-reviewer-evidence-package | `product_scope_boundary_pass` = `False` |
| `expiry_or_perpetual` | `` | future expiry timestamp or perpetual=true | `expiry_valid_pass` = `False` |
| `approval_timeline` | `approved_at=; expires_at=` | approved_at_utc <= now and approved_at_utc <= expiry when not perpetual | `approval_timeline_pass` = `False` |
| `approval_ref_distinct` | `license_id=; approval_ref=` | approval_ref differs from license_id | `approval_ref_distinct_pass` = `False` |
| `provenance_complete` | `role=; evidence_ref=; evidence_kind=missing` | approver role, approval time, evidence ref, and distinct approval ref all pass | `provenance_complete_pass` = `False` |

## Validation Commands

- `python3 scripts/build_license_status_closure_report.py --out implementation/phase1/release_evidence/productization/license_status_closure_report.json`
- `python3 scripts/report_pm_release_gate.py  --out implementation/phase1/release_evidence/productization/pm_release_gate_report.json --out-md implementation/phase1/release_evidence/productization/pm_release_gate_report.md`
- `python3 scripts/build_pm_release_blocker_action_register.py  --out implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.json --out-md implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.md`
