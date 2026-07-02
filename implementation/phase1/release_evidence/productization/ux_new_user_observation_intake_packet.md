# UX New-User Observation Intake Packet

- `summary_line`: `UX new-user observation intake: BLOCKED | fields=0/24 | blockers=12`
- `contract_pass`: `False`
- `release_area`: `ux`
- `blocker_ids`: `27`
- `gate_unblock_plan_count`: `5`
- `observation_path`: `implementation/phase1/release_evidence/productization/ux_new_user_observation.json`
- `template_path`: `docs/templates/ux_new_user_observation.template.json`
- `owner_action`: Attach a human new-user observation record for the sample project workflow, including an anonymized participant_ref, participant status, observer, all five workflow steps (Import, Model Health, Analysis Setup, Run & Monitor, Compare & Report), timezone-aware start/end timestamps, wall-clock completion minutes, blocker count, evidence reference, and accepted release decision.

## Blocker IDs

- `pm_release::ux::human_new_user_observation_missing_or_failed`
- `pm_release::ux::human_new_user_30min_sample_evidence_missing`
- `developer_preview_rc::new_user_core_workflow_observation_passed`
- `human_ux::observation_file_missing`
- `human_ux::contract_signal_not_pass`
- `human_ux::required_fields_missing`
- `human_ux::participant_not_new_user`
- `human_ux::new_to_product_not_confirmed`
- `human_ux::completion_minutes_missing`
- `human_ux::workflow_steps_missing`
- `human_ux::required_workflow_steps_missing`
- `human_ux::required_workflow_step_not_passed`
- `human_ux::blocking_usability_issue_present`
- `human_ux::evidence_ref_missing`
- `human_ux::approval_decision_not_accepted`
- `ux_new_user_observation::observation_file_missing`
- `ux_new_user_observation::contract_signal_not_pass`
- `ux_new_user_observation::required_fields_missing`
- `ux_new_user_observation::participant_not_new_user`
- `ux_new_user_observation::new_to_product_not_confirmed`
- `ux_new_user_observation::completion_minutes_missing`
- `ux_new_user_observation::workflow_steps_missing`
- `ux_new_user_observation::required_workflow_steps_missing`
- `ux_new_user_observation::required_workflow_step_not_passed`
- `ux_new_user_observation::blocking_usability_issue_present`
- `ux_new_user_observation::evidence_ref_missing`
- `ux_new_user_observation::approval_decision_not_accepted`

## Evidence Intake Artifacts

- `docs/templates/ux_new_user_observation.template.json`
- `implementation/phase1/release_evidence/productization/ux_new_user_observation.json`
- `implementation/phase1/release_evidence/productization/ux_new_user_observation_report.json`
- `implementation/phase1/release_evidence/productization/ux_new_user_observation_intake_packet.json`
- `implementation/phase1/release_evidence/productization/phase6_ux_observation_status.json`
- `implementation/phase1/release_evidence/productization/pm_release_gate_report.json`
- `implementation/phase1/release_evidence/productization/product_readiness_snapshot.json`
- `implementation/phase1/release_evidence/productization/developer_preview_rc_status.json`

## Human Observation Evidence Policy

- `closure_rule`: The UX PM release area and Developer Preview UX final gate close only after ux_new_user_observation_report.json and phase6_ux_observation_status.json both pass from a real human 30-minute new-user sample.
- `accepted_evidence`: human-observed 30-minute new-user workflow record with anonymized participant_ref; observer-owned note, ticket, recording reference, or signed evidence bundle; timezone-aware started_at_utc/completed_at_utc plus matching completion_minutes <= 30; all five required workflow steps observed with passing outcomes; approval_decision explicitly accepted for release evidence
- `rejected_substitutes`: automated browser smoke or task-based UX rehearsal without human observation; generated UX/PM/DP/readiness gate reports used as evidence_ref; docs/templates or *.template.* files; the observation JSON self-referencing itself as separate evidence; operator/expert rehearsal that is not a new-user observation

| Field | Current | Template | Required | Report Check |
|---|---|---|---|---|
| `contract_pass` | `` | `false` | true | `contract_signal_pass` = `False` |
| `participant_ref` | `` | `OWNER_INPUT_REQUIRED: anonymized participant or session reference, e.g. ux-participant-001` | stable anonymized participant reference | `required_fields_present` = `False` |
| `participant_role` | `` | `OWNER_INPUT_REQUIRED: new_user \| first_time_user \| pilot_user` | new_user \| first_time_user \| pilot_user | `participant_role_new_user_pass` = `False` |
| `new_to_product` | `` | `OWNER_INPUT_REQUIRED: true` | true | `new_to_product_pass` = `False` |
| `sample_project_id` | `` | `OWNER_INPUT_REQUIRED: sample project identifier` | sample project identifier used in the observed workflow | `required_fields_present` = `False` |
| `workflow_scope` | `` | `OWNER_INPUT_REQUIRED: Import, Model Health, Analysis Setup, Run & Monitor, Compare & Report` | observed workflow scope covering the full five-step workflow | `required_fields_present` = `False` |
| `workflow_steps` | `` | `[{"id": "import", "label": "Import", "outcome": "OWNER_INPUT_REQUIRED: pass"}, {"id": "model_health", "label": "Model Health", "outcome": "OWNER_INPUT_REQUIRED: pass"}, {"id": "analysis_setup", "label": "Analysis Setup", "outcome": "OWNER_INPUT_REQUIRED: pass"}, {"id": "run_monitor", "label": "Run & Monitor", "outcome": "OWNER_INPUT_REQUIRED: pass"}, {"id": "compare_report", "label": "Compare & Report", "outcome": "OWNER_INPUT_REQUIRED: pass"}]` | all five steps observed and passed: Import, Model Health, Analysis Setup, Run & Monitor, Compare & Report | `all_required_workflow_steps_passed` = `False` |
| `observer` | `` | `OWNER_INPUT_REQUIRED: UX research owner or human observer` | human observer or UX research owner | `required_fields_present` = `False` |
| `started_at_utc` | `` | `OWNER_INPUT_REQUIRED: timezone-aware ISO timestamp, e.g. 2026-06-16T09:00:00Z` | timezone-aware ISO-8601 observation start timestamp | `started_at_utc_valid` = `False` |
| `completed_at_utc` | `` | `OWNER_INPUT_REQUIRED: timezone-aware ISO timestamp, e.g. 2026-06-16T09:24:00Z` | timezone-aware ISO-8601 observation completion timestamp | `completed_at_utc_valid` = `False` |
| `completion_minutes` | `` | `OWNER_INPUT_REQUIRED: wall-clock minutes matching completed_at_utc - started_at_utc, numeric <= 30.0` | <= 30.0 and matches timestamp elapsed minutes | `completion_30min_pass` = `False` |
| `blocker_count` | `` | `OWNER_INPUT_REQUIRED: 0` | 0 | `blocker_count_zero_pass` = `False` |
| `evidence_ref` | `` | `OWNER_INPUT_REQUIRED: observation note, ticket, recording, or signed evidence bundle` | non-placeholder evidence reference | `required_fields_present` = `False` |
| `approval_decision` | `` | `OWNER_INPUT_REQUIRED: accepted \| approved \| pass \| signed \| approved_for_release` | accepted \| approved \| pass \| signed \| approved_for_release | `approval_decision_pass` = `False` |
| `timestamp_order` | `` | `derived from observation timestamps` | completed_at_utc >= started_at_utc | `timestamp_order_pass` = `False` |
| `elapsed_minutes` | `` | `derived from observation timestamps` | <= 30.0 from completed_at_utc - started_at_utc | `elapsed_30min_pass` = `False` |
| `completion_minutes_elapsed_match` | `declared=None; elapsed=None; tolerance=1.0` | `derived from observation timestamps` | completion_minutes equals elapsed_minutes within tolerance | `completion_minutes_elapsed_match_pass` = `False` |
| `workflow_step_coverage` | `pass=0/5; missing=['import', 'model_health', 'analysis_setup', 'run_monitor', 'compare_report']` | `derived from observation timestamps` | required workflow observed count == 5/5 | `all_required_workflow_steps_observed` = `False` |
| `workflow_step_placeholders` | `[]` | `derived from observation timestamps` | no placeholder workflow step labels or outcomes | `workflow_step_placeholders_absent` = `False` |
| `evidence_ref_resolvable` | `ref=; kind=missing; resolved=` | `derived from observation timestamps` | https URL, ticket/jira/ux/user-study reference, or existing local evidence path | `evidence_ref_resolvable_pass` = `False` |
| `evidence_ref_not_self_reference` | `` | `derived from observation timestamps` | evidence_ref must not point back to the observation JSON itself | `evidence_ref_not_self_reference_pass` = `False` |
| `evidence_ref_not_template_reference` | `` | `derived from observation timestamps` | evidence_ref must not point to the UX observation template | `evidence_ref_not_template_reference_pass` = `False` |
| `evidence_ref_not_template_artifact` | `` | `derived from observation timestamps` | evidence_ref must not point to docs/templates or a .template.* artifact | `evidence_ref_not_template_artifact_pass` = `False` |
| `evidence_ref_not_generated_gate_artifact` | `` | `derived from observation timestamps` | evidence_ref must not point to generated UX/PM/DP/readiness gate or automated browser-rehearsal artifacts | `evidence_ref_not_generated_gate_artifact_pass` = `False` |

## Gate Unblock Plan

- `attach_observation_record`
- `observe_required_workflow_steps`
- `prove_30_minute_timing`
- `attach_separate_evidence_reference`
- `regenerate_release_gate_evidence`

## Validation Commands

- `python3 scripts/build_ux_new_user_observation_report.py --out implementation/phase1/release_evidence/productization/ux_new_user_observation_report.json`
- `python3 scripts/build_ux_new_user_observation_intake_packet.py --out implementation/phase1/release_evidence/productization/ux_new_user_observation_intake_packet.json`
- `python3 scripts/build_phase6_ux_observation_status.py --out implementation/phase1/release_evidence/productization/phase6_ux_observation_status.json`
- `python3 scripts/build_developer_preview_rc_status.py --out implementation/phase1/release_evidence/productization/developer_preview_rc_status.json`
- `python3 scripts/report_pm_release_gate.py --out implementation/phase1/release_evidence/productization/pm_release_gate_report.json --out-md implementation/phase1/release_evidence/productization/pm_release_gate_report.md`
- `python3 scripts/build_pm_release_blocker_action_register.py --out implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.json --out-md implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.md`
- `python3 scripts/build_product_readiness_snapshot.py --out implementation/phase1/release_evidence/productization/product_readiness_snapshot.json`
