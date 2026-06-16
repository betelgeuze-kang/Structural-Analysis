# PM Owner Evidence Request Packet

- `summary_line`: `PM owner evidence request packet: PASS | owners=3 | open_blockers=5 | incomplete=0`
- `pm_summary_line`: `PM release gate: LIMITED_READY | release_areas=BLOCKED | paid_pilot_candidate=True | milestones=5/5 | release_areas_green=11/14 | measured_cases=304`
- `contract_pass`: `True`

| Owner | State | Blockers | Next Actions | Expected Intake |
|---|---|---|---|---|
| `release_ci_owner` | `ready_for_owner_input` | `basic_ci::pr_ci_30_consecutive_pass_evidence_missing`<br>`basic_ci::nightly_ci_30_consecutive_pass_evidence_missing` | No pull_request-triggered CI runs have been observed for the CI workflow (100 run(s) queried, all from non-PR events). Open a pull request for this branch or add `pull_request` to the CI workflow triggers, then collect 30 additional consecutive successful PR CI run(s) before release signoff.<br>Register or enable the nightly GitHub Actions workflow, then collect 30 additional consecutive successful nightly CI run(s) before release signoff. Local workflow file is present, so merge/register it in GitHub Actions first. | `implementation/phase1/release_evidence/productization/ci_streak_intake_packet.json` |
| `ux_research_owner` | `ready_for_owner_input` | `ux::human_new_user_observation_missing_or_failed`<br>`ux::human_new_user_30min_sample_evidence_missing` | Attach a human new-user observation record for the sample project workflow, including participant status, observer, timezone-aware start/end timestamps, wall-clock completion minutes, blocker count, evidence reference, and accepted release decision. | `implementation/phase1/release_evidence/productization/ux_new_user_observation_intake_packet.json` |
| `product_legal_owner` | `ready_for_owner_input` | `security::license_status_not_configured` | Populate license_status.json from an approved product/legal decision, including approver role, approval timestamp, retrievable evidence reference, scoped product boundary, and no template placeholders before release-area security can pass. | `implementation/phase1/release_evidence/productization/license_status_intake_packet.json` |

This packet groups open PM blocker evidence requests by owner. It does not create or replace tracked CI streaks, human UX observations, product/legal license approval, or any other external release evidence, and it does not convert missing evidence into a release pass.
