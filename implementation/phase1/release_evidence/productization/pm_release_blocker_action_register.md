# PM Release Blocker Action Register

- `pm_summary_line`: `PM release gate: LIMITED_READY | release_areas=BLOCKED | paid_pilot_candidate=True | milestones=5/5 | release_areas_green=12/14 | measured_cases=304`
- `contract_pass`: `False`
- `open_blocker_count`: `3`

| Blocker | Scope | Owner | Evidence Status | Next Action | Acceptance |
|---|---|---|---|---|---|
| `basic_ci::pr_ci_30_consecutive_pass_evidence_missing` | release_area | `release_ci_owner` | `missing_tracked_ci_streak_evidence` | Collect 30 additional consecutive successful PR CI run(s); keep the pull_request CI lane green and refresh github_actions_ci_streak_evidence before release signoff. | `pr_pass_streak_count >= 30` in `pm_release_gate_report.json`<br>`ci_streak_intake_packet.json.contract_pass == true`<br>`basic_ci::pr_ci_30_consecutive_pass_evidence_missing` absent from `release_area_blockers`<br>`github_actions_ci_streak_evidence.json` refreshed for the release signoff window |
| `basic_ci::nightly_ci_30_consecutive_pass_evidence_missing` | release_area | `release_ci_owner` | `missing_tracked_ci_streak_evidence` | Collect 30 additional consecutive successful nightly CI run(s); keep the scheduled/nightly lane green and refresh github_actions_ci_streak_evidence before release signoff. | `nightly_pass_streak_count >= 30` in `pm_release_gate_report.json`<br>`ci_streak_intake_packet.json.contract_pass == true`<br>`basic_ci::nightly_ci_30_consecutive_pass_evidence_missing` absent from `release_area_blockers`<br>`github_actions_ci_streak_evidence.json` refreshed for the release signoff window |
| `security::license_status_not_configured` | release_area | `product_legal_owner` | `not_configured` | Populate license_status.json from an approved product/legal decision, replacing all template placeholders with real approval evidence before release-area security can pass. | `license_status_closure_report.json.contract_pass == true`<br>`license_status` is active and populated from approved product/legal evidence<br>`security::license_status_not_configured` absent from `release_area_blockers` |
