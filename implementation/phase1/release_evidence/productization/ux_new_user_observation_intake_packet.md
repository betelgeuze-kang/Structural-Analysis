# UX New-User Observation Intake Packet

- `summary_line`: `UX new-user observation intake: BLOCKED | fields=0/12 | blockers=8`
- `contract_pass`: `False`
- `observation_path`: `implementation/phase1/release_evidence/productization/ux_new_user_observation.json`
- `template_path`: `docs/templates/ux_new_user_observation.template.json`
- `owner_action`: Attach a human new-user observation record for the sample project workflow, including participant status, observer, timestamps, completion minutes, blocker count, evidence reference, and accepted release decision.

| Field | Current | Template | Required | Report Check |
|---|---|---|---|---|
| `contract_pass` | `` | `true` | true | `contract_signal_pass` = `False` |
| `participant_role` | `` | `new_user` | new_user \| first_time_user \| pilot_user | `participant_role_new_user_pass` = `False` |
| `new_to_product` | `` | `true` | true | `new_to_product_pass` = `False` |
| `sample_project_id` | `` | `SAMPLE-PROJECT-ID` | sample project identifier used in the observed workflow | `required_fields_present` = `False` |
| `workflow_scope` | `` | `open sample project, inspect engine/reviewer evidence package, export reviewer report` | observed workflow steps, including reviewer package/report export | `required_fields_present` = `False` |
| `observer` | `` | `UX-RESEARCH-OWNER` | human observer or UX research owner | `required_fields_present` = `False` |
| `started_at_utc` | `` | `2026-06-16T09:00:00+00:00` | observation start timestamp | `required_fields_present` = `False` |
| `completed_at_utc` | `` | `2026-06-16T09:24:00+00:00` | observation completion timestamp | `required_fields_present` = `False` |
| `completion_minutes` | `` | `24.0` | <= 30.0 | `completion_30min_pass` = `False` |
| `blocker_count` | `` | `0` | 0 | `blocker_count_zero_pass` = `False` |
| `evidence_ref` | `` | `UX-OBSERVATION-EVIDENCE-REF` | non-placeholder evidence reference | `required_fields_present` = `False` |
| `approval_decision` | `` | `accepted` | accepted \| approved \| pass \| signed \| approved_for_release | `approval_decision_pass` = `False` |

## Validation Commands

- `python3 scripts/build_ux_new_user_observation_report.py --out implementation/phase1/release_evidence/productization/ux_new_user_observation_report.json`
- `python3 scripts/build_ux_new_user_observation_intake_packet.py --out implementation/phase1/release_evidence/productization/ux_new_user_observation_intake_packet.json`
- `python3 scripts/report_pm_release_gate.py --out implementation/phase1/release_evidence/productization/pm_release_gate_report.json --out-md implementation/phase1/release_evidence/productization/pm_release_gate_report.md`
- `python3 scripts/build_pm_release_blocker_action_register.py --out implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.json --out-md implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.md`
