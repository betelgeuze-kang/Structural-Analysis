# PM Release Gate Reviewer Handoff

- `summary_line`: `PM release gate reviewer handoff: PASS | open_blockers=5 | incomplete=0`
- `pm_summary_line`: `PM release gate: LIMITED_READY | release_areas=BLOCKED | paid_pilot_candidate=True | milestones=5/5 | release_areas_green=11/14 | measured_cases=304`
- `contract_pass`: `True`

| Blocker | Owner | Closure | Verdict Change Conditions |
|---|---|---|---|
| `basic_ci::pr_ci_30_consecutive_pass_evidence_missing` | `release_ci_owner` | `external_owner_input_ready` | `release_area.basic_ci` status is `pass` in `pm_release_gate_completion_audit.json`<br>`basic_ci::pr_ci_30_consecutive_pass_evidence_missing` is absent from `pm_release_gate_report.json.release_area_blockers`<br>`release_area.basic_ci::pr_ci_30_run_streak_pass` is `true` in `pm_release_gate_report.json`<br>Current false audit check(s): `ci_streak_intake_contract_pass`, `ci_streak_source_evidence_pass`, `nightly_ci_30_run_streak_pass`, `pr_ci_30_run_streak_pass` |
| `basic_ci::nightly_ci_30_consecutive_pass_evidence_missing` | `release_ci_owner` | `external_owner_input_ready` | `release_area.basic_ci` status is `pass` in `pm_release_gate_completion_audit.json`<br>`basic_ci::nightly_ci_30_consecutive_pass_evidence_missing` is absent from `pm_release_gate_report.json.release_area_blockers`<br>`release_area.basic_ci::nightly_ci_30_run_streak_pass` is `true` in `pm_release_gate_report.json`<br>Current false audit check(s): `ci_streak_intake_contract_pass`, `ci_streak_source_evidence_pass`, `nightly_ci_30_run_streak_pass`, `pr_ci_30_run_streak_pass` |
| `ux::human_new_user_observation_missing_or_failed` | `ux_research_owner` | `external_owner_input_ready` | `release_area.ux` status is `pass` in `pm_release_gate_completion_audit.json`<br>`ux::human_new_user_observation_missing_or_failed` is absent from `pm_release_gate_report.json.release_area_blockers`<br>`release_area.ux::human_new_user_observation_pass` is `true` in `pm_release_gate_report.json`<br>Current false audit check(s): `human_new_user_observation_pass`, `human_new_user_sample_30min_evidence_present`, `human_new_user_sample_30min_pass` |
| `ux::human_new_user_30min_sample_evidence_missing` | `ux_research_owner` | `external_owner_input_ready` | `release_area.ux` status is `pass` in `pm_release_gate_completion_audit.json`<br>`ux::human_new_user_30min_sample_evidence_missing` is absent from `pm_release_gate_report.json.release_area_blockers`<br>`release_area.ux::human_new_user_sample_30min_evidence_present` is `true` in `pm_release_gate_report.json`<br>`release_area.ux::human_new_user_sample_30min_pass` is `true` in `pm_release_gate_report.json`<br>Current false audit check(s): `human_new_user_observation_pass`, `human_new_user_sample_30min_evidence_present`, `human_new_user_sample_30min_pass` |
| `security::license_status_not_configured` | `product_legal_owner` | `external_owner_input_ready` | `release_area.security` status is `pass` in `pm_release_gate_completion_audit.json`<br>`security::license_status_not_configured` is absent from `pm_release_gate_report.json.release_area_blockers`<br>`release_area.security::license_status_configured_pass` is `true` in `pm_release_gate_report.json`<br>`release_area.security::license_status_closure_report_present` is `true` in `pm_release_gate_report.json`<br>Current false audit check(s): `license_status_configured_pass` |

## Blocker Details

### `basic_ci::pr_ci_30_consecutive_pass_evidence_missing`

- Owner: `release_ci_owner`
- Release area status: `blocked_external_owner_input_ready`
- Closure state: `external_owner_input_ready`
- Evidence state: `no_pull_request_run_source`
- External input required: `True`
- Owner input required: `True`
- Next action: No pull_request-triggered CI runs have been observed for the CI workflow (100 run(s) queried, all from non-PR events). Open a pull request for this branch or add `pull_request` to the CI workflow triggers, then collect 30 additional consecutive successful PR CI run(s) before release signoff.

Acceptance criteria:
- `pr_pass_streak_count >= 30` in `pm_release_gate_report.json`
- `ci_streak_intake_packet.json.contract_pass == true`
- `basic_ci::pr_ci_30_consecutive_pass_evidence_missing` absent from `release_area_blockers`
- `github_actions_ci_streak_evidence.json` refreshed for the release signoff window

Evidence artifact paths:
- `ci_streak_intake_packet`: `implementation/phase1/release_evidence/productization/ci_streak_intake_packet.json`
- `ci_streak_manifest`: `implementation/phase1/release_evidence/productization/ci_consecutive_pass_manifest.json`
- `github_actions_ci_streak_evidence`: `implementation/phase1/release_evidence/productization/github_actions_ci_streak_evidence.json`
- `nightly_ci`: `implementation/phase1/ci_gate_report.nightly.json`
- `pm_release_gate_report`: `implementation/phase1/release_evidence/productization/pm_release_gate_report.json`
- `pr_ci`: `implementation/phase1/ci_gate_report.pr.json`

Reproduction commands:
- `python3 scripts/build_github_actions_ci_streak_evidence.py --out implementation/phase1/release_evidence/productization/github_actions_ci_streak_evidence.json`
- `python3 scripts/build_ci_consecutive_pass_manifest.py --out implementation/phase1/release_evidence/productization/ci_consecutive_pass_manifest.json`
- `python3 scripts/build_ci_streak_intake_packet.py --out implementation/phase1/release_evidence/productization/ci_streak_intake_packet.json`
- `python3 scripts/report_pm_release_gate.py --out implementation/phase1/release_evidence/productization/pm_release_gate_report.json --out-md implementation/phase1/release_evidence/productization/pm_release_gate_report.md`
- `python3 scripts/build_pm_release_blocker_action_register.py --out implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.json --out-md implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.md`

Verification commands:
- `python3 scripts/build_ci_streak_intake_packet.py --out implementation/phase1/release_evidence/productization/ci_streak_intake_packet.json --fail-blocked`
- `python3 scripts/build_pm_release_blocker_action_register.py --out implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.json --out-md implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.md --fail-blocked`

Verdict change conditions:
- `release_area.basic_ci` status is `pass` in `pm_release_gate_completion_audit.json`
- `basic_ci::pr_ci_30_consecutive_pass_evidence_missing` is absent from `pm_release_gate_report.json.release_area_blockers`
- `release_area.basic_ci::pr_ci_30_run_streak_pass` is `true` in `pm_release_gate_report.json`
- Current false audit check(s): `ci_streak_intake_contract_pass`, `ci_streak_source_evidence_pass`, `nightly_ci_30_run_streak_pass`, `pr_ci_30_run_streak_pass`

### `basic_ci::nightly_ci_30_consecutive_pass_evidence_missing`

- Owner: `release_ci_owner`
- Release area status: `blocked_external_owner_input_ready`
- Closure state: `external_owner_input_ready`
- Evidence state: `missing_tracked_ci_streak_evidence`
- External input required: `True`
- Owner input required: `True`
- Next action: Register or enable the nightly GitHub Actions workflow, then collect 30 additional consecutive successful nightly CI run(s) before release signoff. Local workflow file is present, so merge/register it in GitHub Actions first.

Acceptance criteria:
- `nightly_pass_streak_count >= 30` in `pm_release_gate_report.json`
- `ci_streak_intake_packet.json.contract_pass == true`
- `basic_ci::nightly_ci_30_consecutive_pass_evidence_missing` absent from `release_area_blockers`
- `github_actions_ci_streak_evidence.json` refreshed for the release signoff window

Evidence artifact paths:
- `ci_streak_intake_packet`: `implementation/phase1/release_evidence/productization/ci_streak_intake_packet.json`
- `ci_streak_manifest`: `implementation/phase1/release_evidence/productization/ci_consecutive_pass_manifest.json`
- `github_actions_ci_streak_evidence`: `implementation/phase1/release_evidence/productization/github_actions_ci_streak_evidence.json`
- `nightly_ci`: `implementation/phase1/ci_gate_report.nightly.json`
- `pm_release_gate_report`: `implementation/phase1/release_evidence/productization/pm_release_gate_report.json`
- `pr_ci`: `implementation/phase1/ci_gate_report.pr.json`

Reproduction commands:
- `python3 scripts/build_github_actions_ci_streak_evidence.py --out implementation/phase1/release_evidence/productization/github_actions_ci_streak_evidence.json`
- `python3 scripts/build_ci_consecutive_pass_manifest.py --out implementation/phase1/release_evidence/productization/ci_consecutive_pass_manifest.json`
- `python3 scripts/build_ci_streak_intake_packet.py --out implementation/phase1/release_evidence/productization/ci_streak_intake_packet.json`
- `python3 scripts/report_pm_release_gate.py --out implementation/phase1/release_evidence/productization/pm_release_gate_report.json --out-md implementation/phase1/release_evidence/productization/pm_release_gate_report.md`
- `python3 scripts/build_pm_release_blocker_action_register.py --out implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.json --out-md implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.md`

Verification commands:
- `python3 scripts/build_ci_streak_intake_packet.py --out implementation/phase1/release_evidence/productization/ci_streak_intake_packet.json --fail-blocked`
- `python3 scripts/build_pm_release_blocker_action_register.py --out implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.json --out-md implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.md --fail-blocked`

Verdict change conditions:
- `release_area.basic_ci` status is `pass` in `pm_release_gate_completion_audit.json`
- `basic_ci::nightly_ci_30_consecutive_pass_evidence_missing` is absent from `pm_release_gate_report.json.release_area_blockers`
- `release_area.basic_ci::nightly_ci_30_run_streak_pass` is `true` in `pm_release_gate_report.json`
- Current false audit check(s): `ci_streak_intake_contract_pass`, `ci_streak_source_evidence_pass`, `nightly_ci_30_run_streak_pass`, `pr_ci_30_run_streak_pass`

### `ux::human_new_user_observation_missing_or_failed`

- Owner: `ux_research_owner`
- Release area status: `blocked_external_owner_input_ready`
- Closure state: `external_owner_input_ready`
- Evidence state: `missing_human_new_user_observation`
- External input required: `True`
- Owner input required: `True`
- Next action: Attach a human new-user observation record for the sample project workflow, including participant status, observer, timezone-aware start/end timestamps, wall-clock completion minutes, blocker count, evidence reference, and accepted release decision.

Acceptance criteria:
- `ux_new_user_observation_report.json.contract_pass == true`
- `human_new_user_sample_30min_pass == true` in `pm_release_gate_report.json`
- `ux::human_new_user_observation_missing_or_failed` absent from `release_area_blockers`

Evidence artifact paths:
- `pm_release_gate_report`: `implementation/phase1/release_evidence/productization/pm_release_gate_report.json`
- `ux_new_user_observation`: `implementation/phase1/release_evidence/productization/ux_new_user_observation_report.json`
- `ux_new_user_observation_intake_packet`: `implementation/phase1/release_evidence/productization/ux_new_user_observation_intake_packet.json`
- `ux_new_user_observation_report`: `implementation/phase1/release_evidence/productization/ux_new_user_observation_report.json`
- `ux_release_readiness`: `implementation/phase1/release_evidence/productization/ux_release_readiness_report.json`
- `viewer_performance_budget`: `implementation/phase1/structure_viewer_performance_budget_manifest.json`
- `viewer_quality`: `implementation/phase1/commercialization_status/real_drawing_viewer_quality_gate.json`

Reproduction commands:
- `python3 scripts/build_ux_new_user_observation_report.py --out implementation/phase1/release_evidence/productization/ux_new_user_observation_report.json`
- `python3 scripts/build_ux_new_user_observation_intake_packet.py --out implementation/phase1/release_evidence/productization/ux_new_user_observation_intake_packet.json`
- `python3 scripts/report_pm_release_gate.py --out implementation/phase1/release_evidence/productization/pm_release_gate_report.json --out-md implementation/phase1/release_evidence/productization/pm_release_gate_report.md`
- `python3 scripts/build_pm_release_blocker_action_register.py --out implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.json --out-md implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.md`

Verification commands:
- `python3 scripts/build_ux_new_user_observation_report.py --out implementation/phase1/release_evidence/productization/ux_new_user_observation_report.json --fail-blocked`
- `python3 scripts/build_ux_new_user_observation_intake_packet.py --out implementation/phase1/release_evidence/productization/ux_new_user_observation_intake_packet.json --fail-blocked`
- `python3 scripts/build_pm_release_blocker_action_register.py --out implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.json --out-md implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.md --fail-blocked`

Verdict change conditions:
- `release_area.ux` status is `pass` in `pm_release_gate_completion_audit.json`
- `ux::human_new_user_observation_missing_or_failed` is absent from `pm_release_gate_report.json.release_area_blockers`
- `release_area.ux::human_new_user_observation_pass` is `true` in `pm_release_gate_report.json`
- Current false audit check(s): `human_new_user_observation_pass`, `human_new_user_sample_30min_evidence_present`, `human_new_user_sample_30min_pass`

### `ux::human_new_user_30min_sample_evidence_missing`

- Owner: `ux_research_owner`
- Release area status: `blocked_external_owner_input_ready`
- Closure state: `external_owner_input_ready`
- Evidence state: `missing_human_new_user_completion_evidence`
- External input required: `True`
- Owner input required: `True`
- Next action: Attach a human new-user observation record for the sample project workflow, including participant status, observer, timezone-aware start/end timestamps, wall-clock completion minutes, blocker count, evidence reference, and accepted release decision.

Acceptance criteria:
- `ux_new_user_observation_report.json.contract_pass == true`
- `human_new_user_sample_30min_pass == true` in `pm_release_gate_report.json`
- `ux::human_new_user_30min_sample_evidence_missing` absent from `release_area_blockers`

Evidence artifact paths:
- `pm_release_gate_report`: `implementation/phase1/release_evidence/productization/pm_release_gate_report.json`
- `ux_new_user_observation`: `implementation/phase1/release_evidence/productization/ux_new_user_observation_report.json`
- `ux_new_user_observation_intake_packet`: `implementation/phase1/release_evidence/productization/ux_new_user_observation_intake_packet.json`
- `ux_new_user_observation_report`: `implementation/phase1/release_evidence/productization/ux_new_user_observation_report.json`
- `ux_release_readiness`: `implementation/phase1/release_evidence/productization/ux_release_readiness_report.json`
- `viewer_performance_budget`: `implementation/phase1/structure_viewer_performance_budget_manifest.json`
- `viewer_quality`: `implementation/phase1/commercialization_status/real_drawing_viewer_quality_gate.json`

Reproduction commands:
- `python3 scripts/build_ux_new_user_observation_report.py --out implementation/phase1/release_evidence/productization/ux_new_user_observation_report.json`
- `python3 scripts/build_ux_new_user_observation_intake_packet.py --out implementation/phase1/release_evidence/productization/ux_new_user_observation_intake_packet.json`
- `python3 scripts/report_pm_release_gate.py --out implementation/phase1/release_evidence/productization/pm_release_gate_report.json --out-md implementation/phase1/release_evidence/productization/pm_release_gate_report.md`
- `python3 scripts/build_pm_release_blocker_action_register.py --out implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.json --out-md implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.md`

Verification commands:
- `python3 scripts/build_ux_new_user_observation_report.py --out implementation/phase1/release_evidence/productization/ux_new_user_observation_report.json --fail-blocked`
- `python3 scripts/build_ux_new_user_observation_intake_packet.py --out implementation/phase1/release_evidence/productization/ux_new_user_observation_intake_packet.json --fail-blocked`
- `python3 scripts/build_pm_release_blocker_action_register.py --out implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.json --out-md implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.md --fail-blocked`

Verdict change conditions:
- `release_area.ux` status is `pass` in `pm_release_gate_completion_audit.json`
- `ux::human_new_user_30min_sample_evidence_missing` is absent from `pm_release_gate_report.json.release_area_blockers`
- `release_area.ux::human_new_user_sample_30min_evidence_present` is `true` in `pm_release_gate_report.json`
- `release_area.ux::human_new_user_sample_30min_pass` is `true` in `pm_release_gate_report.json`
- Current false audit check(s): `human_new_user_observation_pass`, `human_new_user_sample_30min_evidence_present`, `human_new_user_sample_30min_pass`

### `security::license_status_not_configured`

- Owner: `product_legal_owner`
- Release area status: `blocked_external_owner_input_ready`
- Closure state: `external_owner_input_ready`
- Evidence state: `not_configured`
- External input required: `True`
- Owner input required: `True`
- Next action: Populate license_status.json from an approved product/legal decision, including approver role, approval timestamp, retrievable evidence reference, scoped product boundary, and no template placeholders before release-area security can pass.

Acceptance criteria:
- `license_status_closure_report.json.contract_pass == true`
- `license_status` is active and populated from approved product/legal evidence
- `security::license_status_not_configured` absent from `release_area_blockers`

Evidence artifact paths:
- `frontend_dependency_audit`: `implementation/phase1/release_evidence/productization/frontend_dependency_audit_report.json`
- `license_status`: `implementation/phase1/release/support_bundle/license_status.json`
- `license_status_closure`: `implementation/phase1/release_evidence/productization/license_status_closure_report.json`
- `license_status_intake_packet`: `implementation/phase1/release_evidence/productization/license_status_intake_packet.json`
- `pm_release_gate_report`: `implementation/phase1/release_evidence/productization/pm_release_gate_report.json`
- `reproducibility_lock`: `implementation/phase1/reproducibility_version_lock_report.json`
- `runtime_sbom`: `implementation/phase1/runtime_sbom.json`
- `security_runbook`: `docs/production-ops-security.md`

Reproduction commands:
- `python3 scripts/build_license_status_intake_packet.py --out implementation/phase1/release_evidence/productization/license_status_intake_packet.json`
- `python3 scripts/build_license_status_closure_report.py --out implementation/phase1/release_evidence/productization/license_status_closure_report.json`
- `python3 scripts/report_pm_release_gate.py --out implementation/phase1/release_evidence/productization/pm_release_gate_report.json --out-md implementation/phase1/release_evidence/productization/pm_release_gate_report.md`
- `python3 scripts/build_pm_release_blocker_action_register.py --out implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.json --out-md implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.md`

Verification commands:
- `python3 scripts/build_license_status_closure_report.py --out implementation/phase1/release_evidence/productization/license_status_closure_report.json --fail-blocked`
- `python3 scripts/build_pm_release_blocker_action_register.py --out implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.json --out-md implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.md --fail-blocked`

Verdict change conditions:
- `release_area.security` status is `pass` in `pm_release_gate_completion_audit.json`
- `security::license_status_not_configured` is absent from `pm_release_gate_report.json.release_area_blockers`
- `release_area.security::license_status_configured_pass` is `true` in `pm_release_gate_report.json`
- `release_area.security::license_status_closure_report_present` is `true` in `pm_release_gate_report.json`
- Current false audit check(s): `license_status_configured_pass`

This reviewer handoff packages PM blocker review actions and verdict-change conditions. It does not convert missing tracked CI streak, human UX observation, license approval, or other external evidence into a release pass.
