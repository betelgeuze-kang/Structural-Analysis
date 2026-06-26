# UX New-User Observation Report

- `summary_line`: `UX new-user observation: BLOCKED | completion=missing/30.0 min | elapsed=missing/30.0 min | workflow=0/5 | blockers=11`
- `contract_pass`: `False`
- `observation_path`: `implementation/phase1/release_evidence/productization/ux_new_user_observation.json`

## Timing Checks

- `declared_completion_minutes`: `None`
- `elapsed_minutes`: `None`
- `max_completion_minutes`: `30.0`
- `timestamp_tolerance_minutes`: `1.0`
- `completion_minutes_elapsed_match_pass`: `False`

## Workflow Checks

- `workflow_step_pass_count`: `0`
- `required_workflow_step_count`: `5`
- `all_required_workflow_steps_observed`: `False`
- `all_required_workflow_steps_passed`: `False`
- `missing_workflow_steps`: `['import', 'model_health', 'analysis_setup', 'run_monitor', 'compare_report']`
- `not_passed_workflow_steps`: `[]`

## Required Fields

- `contract_pass`
- `participant_role`
- `new_to_product`
- `sample_project_id`
- `workflow_scope`
- `workflow_steps`
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
