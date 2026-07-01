# License Status Intake Packet

- `summary_line`: `License status intake: BLOCKED | fields=0/16 | blockers=10`
- `status`: `blocked`
- `contract_pass`: `False`
- `gate_unblock_plan_count`: `6`
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
| `evidence_ref_not_self_reference` | `` | evidence_ref must not point back to license_status.json | `evidence_ref_not_self_reference_pass` = `False` |
| `evidence_ref_not_template_reference` | `` | evidence_ref must not point to the license status template | `evidence_ref_not_template_reference_pass` = `False` |
| `evidence_ref_not_template_artifact` | `` | evidence_ref must not point to docs/templates or a .template.* artifact | `evidence_ref_not_template_artifact_pass` = `False` |

## Gate Unblock Plan

- `attach_license_status_record`
  - status is active, approved, or valid
  - tier is paid-pilot or limited-commercial
  - license_id, issuer_or_approver, approver_role, approval_ref, and approved_at_utc are populated
  - template placeholders such as LICENSE-ID or OWNER_INPUT_REQUIRED are absent
- `prove_product_legal_approval`
  - approver_role is product_owner, legal_counsel, product_and_legal, or delegated_product_owner
  - approved_at_utc is timezone-aware and not in the future
  - approval_ref names the product/legal decision record
  - approval_ref differs from license_id
- `prove_scope_and_tier_boundary`
  - product_scope includes review-assist
  - product_scope includes specified-structure-families
  - product_scope includes specified-workflows
  - product_scope includes engine-and-reviewer-evidence-package
- `prove_validity_window_or_perpetual_approval`
  - expires_at_utc is timezone-aware and in the future
  - or perpetual=true is explicitly approved
  - approved_at_utc is not later than expires_at_utc when an expiry exists
- `attach_distinct_retrievable_evidence_reference`
  - evidence_ref is a ticket/jira/legal/docusign reference, https URL, or existing local evidence path
  - evidence_ref is not license_status.json itself
  - evidence_ref is not docs/templates or a .template artifact
- `regenerate_release_gate_evidence`
  - license_status_closure_report.json contract_pass=true
  - license_status_intake_packet.json contract_pass=true
  - PM release security area no longer blocks license_status_not_configured

## Validation Commands

- `python3 scripts/build_license_status_closure_report.py --out implementation/phase1/release_evidence/productization/license_status_closure_report.json`
- `python3 scripts/build_license_status_intake_packet.py --out implementation/phase1/release_evidence/productization/license_status_intake_packet.json --out-md implementation/phase1/release_evidence/productization/license_status_intake_packet.md`
- `python3 scripts/report_pm_release_gate.py  --out implementation/phase1/release_evidence/productization/pm_release_gate_report.json --out-md implementation/phase1/release_evidence/productization/pm_release_gate_report.md`
- `python3 scripts/build_pm_release_blocker_action_register.py  --out implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.json --out-md implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.md`
