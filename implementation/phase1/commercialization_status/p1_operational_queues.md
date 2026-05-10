# P1 Operational Queues

- `contract_pass`: `True`
- `reason_code`: `PASS`
- `external_submission_queue_count`: `4`
- `residual_holdout_work_item_count`: `3`
- `residual_holdout_open_count`: `3`
- `residual_holdout_closure_evidence_pending_count`: `3`
- `full_commercial_replacement_ready`: `False`

## External Benchmark Submission

| Work Item | Queue | Submission ID | Owner | Status | Lifecycle | Receipt Status | Receipt URL | Receipt Template | Owner Action |
|---|---|---|---|---|---|---|---|---|---|
| EB-001 | hardest_external_10case | p1-hardest-external-10case | benchmark_program_owner | ready_for_full_submission | ready_to_submit | pending_external_submission_receipt | pending | implementation/phase1/commercialization_status/external_benchmark_submission_queue/EB-001.receipt_template.json | submit_external_benchmark_package_and_attach_receipt |
| EB-002 | tpu_hffb | p1-tpu-hffb | wind_benchmark_owner | ready_for_full_submission | ready_to_submit | pending_external_submission_receipt | pending | implementation/phase1/commercialization_status/external_benchmark_submission_queue/EB-002.receipt_template.json | submit_external_benchmark_package_and_attach_receipt |
| EB-003 | peer_spd_hinge | p1-peer-spd-hinge | pbd_benchmark_owner | ready_for_full_submission | ready_to_submit | pending_external_submission_receipt | pending | implementation/phase1/commercialization_status/external_benchmark_submission_queue/EB-003.receipt_template.json | submit_external_benchmark_package_and_attach_receipt |
| EB-004 | korean_public_structures | p1-korean-public-structures | korean_source_owner | ready_for_full_submission | ready_to_submit | pending_external_submission_receipt | pending | implementation/phase1/commercialization_status/external_benchmark_submission_queue/EB-004.receipt_template.json | submit_external_benchmark_package_and_attach_receipt |

## Residual Holdout

| Work Item | Category | Owner | Queue Status | SLA | Due | Closure Evidence | Last Checked | Packet Template | Owner Action |
|---|---|---|---|---|---|---|---|---|---|
| RH-001 | licensed_engineer_review_required | licensed_engineer | pending_review | 72h | assignment_plus_3_business_days | signed_engineer_review_packet (pending: pending) | 2026-05-05T05:05:53Z | implementation/phase1/commercialization_status/residual_holdout_queue/RH-001.closure_packet_template.json | complete_engineer_review_and_attach_signed_packet |
| RH-002 | legacy_tool_cross_validation_required | legacy_tool_owner | pending_cross_validation | 120h | assignment_plus_5_business_days | legacy_tool_cross_validation_report (pending: pending) | 2026-05-05T05:05:53Z | implementation/phase1/commercialization_status/residual_holdout_queue/RH-002.closure_packet_template.json | run_legacy_tool_cross_validation_and_attach_report |
| RH-003 | legal_authority_signoff_required | authority_workflow_owner | pending_signoff | 168h | authority_submission_window | authority_signoff_receipt_or_formal_hold (pending: pending) | 2026-05-05T05:05:53Z | implementation/phase1/commercialization_status/residual_holdout_queue/RH-003.closure_packet_template.json | collect_authority_signoff_or_formal_hold_receipt |
