# P1 Evidence Sidecar Intake Preflight

- `contract_pass`: `False`
- `reason_code`: `ERR_P1_EVIDENCE_SIDECAR_INTAKE_PENDING`
- `external_receipt_attached_count`: `0/4`
- `external_closure_evidence_attached_count`: `0/4`
- `residual_closed_count`: `0/3`
- `residual_closure_evidence_attached_count`: `0/3`
- `blockers`: `external_receipt_or_closure_pending:hardest_external_10case, external_receipt_or_closure_pending:tpu_hffb, external_receipt_or_closure_pending:peer_spd_hinge, external_receipt_or_closure_pending:korean_public_structures, residual_closure_pending:RH-001, residual_closure_pending:RH-002, residual_closure_pending:RH-003`

## External Benchmark Submission

| Queue | Receipt Status | Receipt Evidence | Closure Status | Missing |
|---|---|---|---|---|
| hardest_external_10case | pending_external_submission_receipt | pending | pending | receipt_status_attached, receipt_url_or_evidence_path, closure_evidence_status_attached |
| tpu_hffb | pending_external_submission_receipt | pending | pending | receipt_status_attached, receipt_url_or_evidence_path, closure_evidence_status_attached |
| peer_spd_hinge | pending_external_submission_receipt | pending | pending | receipt_status_attached, receipt_url_or_evidence_path, closure_evidence_status_attached |
| korean_public_structures | pending_external_submission_receipt | pending | pending | receipt_status_attached, receipt_url_or_evidence_path, closure_evidence_status_attached |

## Residual Holdout

| Work Item | Status | Closure Evidence | Missing |
|---|---|---|---|
| RH-001 | open | pending (pending) | status_closed, closure_evidence_status_attached, closure_evidence_path_exists |
| RH-002 | open | pending (pending) | status_closed, closure_evidence_status_attached, closure_evidence_path_exists |
| RH-003 | open | pending (pending) | status_closed, closure_evidence_status_attached, closure_evidence_path_exists |
