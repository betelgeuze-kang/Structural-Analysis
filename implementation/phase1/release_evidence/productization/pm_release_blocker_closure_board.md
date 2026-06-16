# PM Release Blocker Closure Board

- `summary_line`: `PM release blocker closure board: BLOCKED | open=5 | external_owner_ready=5 | handoff_not_ready=0`
- `pm_summary_line`: `PM release gate: LIMITED_READY | release_areas=BLOCKED | paid_pilot_candidate=True | milestones=5/5 | release_areas_green=11/14 | measured_cases=304`
- `contract_pass`: `False`
- `open_blocker_count`: `5`
- `all_open_blockers_have_handoff`: `True`

| Blocker | Owner | Closure State | Evidence State | Next Action |
|---|---|---|---|---|
| `basic_ci::pr_ci_30_consecutive_pass_evidence_missing` | `release_ci_owner` | `external_owner_input_ready` | `no_pull_request_run_source` | No pull_request-triggered CI runs have been observed for the CI workflow (100 run(s) queried, all from non-PR events). Open a pull request for this branch or add `pull_request` to the CI workflow triggers, then collect 30 additional consecutive successful PR CI run(s) before release signoff. |
| `basic_ci::nightly_ci_30_consecutive_pass_evidence_missing` | `release_ci_owner` | `external_owner_input_ready` | `missing_tracked_ci_streak_evidence` | Register or enable the nightly GitHub Actions workflow, then collect 30 additional consecutive successful nightly CI run(s) before release signoff. Local workflow file is present, so merge/register it in GitHub Actions first. |
| `ux::human_new_user_observation_missing_or_failed` | `ux_research_owner` | `external_owner_input_ready` | `missing_human_new_user_observation` | Attach a human new-user observation record for the sample project workflow, including participant status, observer, timezone-aware start/end timestamps, wall-clock completion minutes, blocker count, evidence reference, and accepted release decision. |
| `ux::human_new_user_30min_sample_evidence_missing` | `ux_research_owner` | `external_owner_input_ready` | `missing_human_new_user_completion_evidence` | Attach a human new-user observation record for the sample project workflow, including participant status, observer, timezone-aware start/end timestamps, wall-clock completion minutes, blocker count, evidence reference, and accepted release decision. |
| `security::license_status_not_configured` | `product_legal_owner` | `external_owner_input_ready` | `not_configured` | Populate license_status.json from an approved product/legal decision, replacing all template placeholders with real approval evidence before release-area security can pass. |

This closure board is an owner-handoff and daily closure artifact. It does not convert missing CI streak, human UX observation, license, or other external evidence into a release pass.
