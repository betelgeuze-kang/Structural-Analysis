# UX New-User Observation Intake Packet

- `summary_line`: `UX new-user observation intake: BLOCKED | fields=0/12 | blockers=8`
- `contract_pass`: `False`
- `observation_path`: `implementation/phase1/release_evidence/productization/ux_new_user_observation.json`
- `template_path`: `docs/templates/ux_new_user_observation.template.json`
- `owner_action`: Attach a human new-user observation record for the sample project workflow, including participant status, observer, timestamps, completion minutes, blocker count, evidence reference, and accepted release decision.

| Field | Current | Template | Required | Report Check |
|---|---|---|---|---|
| `contract_pass` | `` | `false` | true | `contract_signal_pass` = `False` |
| `participant_role` | `` | `OWNER_INPUT_REQUIRED: new_user \| first_time_user \| pilot_user` | new_user \| first_time_user \| pilot_user | `participant_role_new_user_pass` = `False` |
| `new_to_product` | `` | `OWNER_INPUT_REQUIRED: true` | true | `new_to_product_pass` = `False` |
| `sample_project_id` | `` | `OWNER_INPUT_REQUIRED: sample project identifier` | sample project identifier used in the observed workflow | `required_fields_present` = `False` |
| `workflow_scope` | `` | `OWNER_INPUT_REQUIRED: open sample project, inspect engine/reviewer evidence package, export reviewer report` | observed workflow steps, including reviewer package/report export | `required_fields_present` = `False` |
| `observer` | `` | `OWNER_INPUT_REQUIRED: UX research owner or human observer` | human observer or UX research owner | `required_fields_present` = `False` |
| `started_at_utc` | `` | `OWNER_INPUT_REQUIRED: 2026-06-16T09:00:00+00:00` | observation start timestamp | `required_fields_present` = `False` |
| `completed_at_utc` | `` | `OWNER_INPUT_REQUIRED: 2026-06-16T09:24:00+00:00` | observation completion timestamp | `required_fields_present` = `False` |
| `completion_minutes` | `` | `OWNER_INPUT_REQUIRED: numeric minutes <= 30.0` | <= 30.0 | `completion_30min_pass` = `False` |
| `blocker_count` | `` | `OWNER_INPUT_REQUIRED: 0` | 0 | `blocker_count_zero_pass` = `False` |
| `evidence_ref` | `` | `OWNER_INPUT_REQUIRED: observation note, ticket, recording, or signed evidence bundle` | non-placeholder evidence reference | `required_fields_present` = `False` |
| `approval_decision` | `` | `OWNER_INPUT_REQUIRED: accepted \| approved \| pass \| signed \| approved_for_release` | accepted \| approved \| pass \| signed \| approved_for_release | `approval_decision_pass` = `False` |

## Validation Commands

- `python3 scripts/build_ux_new_user_observation_report.py --out implementation/phase1/release_evidence/productization/ux_new_user_observation_report.json`
- `python3 scripts/build_ux_new_user_observation_intake_packet.py --out implementation/phase1/release_evidence/productization/ux_new_user_observation_intake_packet.json`
- `python3 scripts/report_pm_release_gate.py --out implementation/phase1/release_evidence/productization/pm_release_gate_report.json --out-md implementation/phase1/release_evidence/productization/pm_release_gate_report.md`
- `python3 scripts/build_pm_release_blocker_action_register.py --out implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.json --out-md implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.md`
