# UX New-User Observation Report

- `summary_line`: `UX new-user observation: BLOCKED | completion=missing/30.0 min | blockers=1`
- `contract_pass`: `False`
- `observation_path`: `implementation/phase1/release_evidence/productization/ux_new_user_observation.json`

## Required Fields

- `contract_pass`
- `participant_role`
- `new_to_product`
- `sample_project_id`
- `workflow_scope`
- `observer`
- `started_at_utc`
- `completed_at_utc`
- `completion_minutes`
- `blocker_count`
- `evidence_ref`
- `approval_decision`

## Validation Commands

- `python3 scripts/build_ux_new_user_observation_report.py --out implementation/phase1/release_evidence/productization/ux_new_user_observation_report.json`
- `python3 scripts/build_ux_new_user_observation_intake_packet.py --out implementation/phase1/release_evidence/productization/ux_new_user_observation_intake_packet.json`
- `python3 scripts/report_pm_release_gate.py --out implementation/phase1/release_evidence/productization/pm_release_gate_report.json --out-md implementation/phase1/release_evidence/productization/pm_release_gate_report.md`
