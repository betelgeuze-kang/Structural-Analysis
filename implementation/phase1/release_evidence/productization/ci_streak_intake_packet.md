# CI Streak Intake Packet

- `summary_line`: `CI streak intake: BLOCKED | lanes=0/2 | pr_missing=30 | nightly_missing=30 | blockers=11 | runner=blocked`
- `status`: `blocked`
- `contract_pass`: `False`
- `reason_code`: `ERR_CI_STREAK_SOURCE_EVIDENCE_INCOMPLETE`
- `release_area`: `basic_ci`
- `current_blocker_count`: `11`
- `blocker_id_count`: `13`
- `evidence_intake_artifact_count`: `6`
- `ci_consecutive_pass_manifest`: `implementation/phase1/release_evidence/productization/ci_consecutive_pass_manifest.json`
- `github_actions_ci_streak_evidence`: `implementation/phase1/release_evidence/productization/github_actions_ci_streak_evidence.json`

| Lane | Observed Streak | Missing | Source | Workflow Registered | Pass | Owner Action |
|---|---:|---:|---|---|---|---|
| `pr` | `0/30` | `30` | `no_pull_request_run_source` | `True` | `False` | No pull_request-triggered CI runs have been observed for the CI workflow (500 run(s) queried, all from non-PR events). Open a pull request for this branch or add `pull_request` to the CI workflow triggers, then collect 30 additional consecutive successful PR CI run(s) before release signoff. |
| `nightly` | `0/30` | `30` | `github_actions_job_start_blocked` | `True` | `False` | Resolve the nightly GitHub Actions job-start blocker shown in github_actions_ci_streak_evidence.json, rerun the workflow, and then collect 30 additional consecutive successful CI run(s) before release signoff. |

## Runner Precondition

| Path | Status | Online Matching | Ready | Pass | Owner Action |
|---|---|---:|---:|---:|---|
| `implementation/phase1/release_evidence/productization/github_actions_self_hosted_runner_status.json` | `blocked` | `0/1` | `0` | `False` | Bring at least one GitHub Actions self-hosted runner online with labels self-hosted, linux, x64, then refresh github_actions_self_hosted_runner_status.json and github_actions_ci_streak_evidence.json before collecting the 30-run streak. |

## Job Start Blocker Queue

| Lane | Count | Reason Codes | First Run | Owner Action |
|---|---:|---|---|---|
| `nightly` | `1` | `github_actions_self_hosted_runner_queued_timeout` | `28680698586` | Resolve the nightly GitHub Actions job-start blocker, bring the required self-hosted runner online, rerun the workflow, then collect 30 consecutive successful run(s). |

## Workflow Queue Backlog

| Workflow | Event | Counted Lane | Queued Minutes | Run | Owner Action |
|---|---|---|---:|---|---|
| `Nightly Full Quality` | `schedule` | `nightly` | `790.4` | `28680698586` | Bring the required self-hosted runner online, let queued Nightly Full Quality runs start, then refresh github_actions_ci_streak_evidence.json before collecting release streak credit. |

## Validation Commands

- `python3 scripts/check_github_actions_self_hosted_runner_status.py --out implementation/phase1/release_evidence/productization/github_actions_self_hosted_runner_status.json`
- `python3 scripts/build_github_actions_ci_streak_evidence.py --out implementation/phase1/release_evidence/productization/github_actions_ci_streak_evidence.json`
- `python3 scripts/build_ci_consecutive_pass_manifest.py --out implementation/phase1/release_evidence/productization/ci_consecutive_pass_manifest.json`
- `python3 scripts/build_ci_streak_intake_packet.py --out implementation/phase1/release_evidence/productization/ci_streak_intake_packet.json`
- `python3 scripts/report_pm_release_gate.py  --out implementation/phase1/release_evidence/productization/pm_release_gate_report.json --out-md implementation/phase1/release_evidence/productization/pm_release_gate_report.md`
- `python3 scripts/build_pm_release_blocker_action_register.py  --out implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.json --out-md implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.md`

## Blocker IDs

- `pm_release::basic_ci::pr_ci_30_consecutive_pass_evidence_missing`
- `pm_release::basic_ci::nightly_ci_30_consecutive_pass_evidence_missing`
- `ci_streak::pr:pr_pull_request_run_source_absent`
- `ci_streak::pr:pr_ci_30_consecutive_pass_evidence_missing`
- `ci_streak::pr:github_actions_lane_threshold_not_pass`
- `ci_streak::pr:github_actions_lane_streak_below_threshold`
- `ci_streak::pr:github_actions_filtered_run_count_below_threshold`
- `ci_streak::nightly:nightly_github_actions_job_start_blocked`
- `ci_streak::nightly:nightly_ci_30_consecutive_pass_evidence_missing`
- `ci_streak::nightly:github_actions_lane_threshold_not_pass`
- `ci_streak::nightly:github_actions_lane_streak_below_threshold`
- `ci_streak::nightly:github_actions_filtered_run_count_below_threshold`
- `ci_streak::runner:self_hosted_runner_matching_labels_not_online`

## Evidence Intake Artifacts

- `implementation/phase1/release_evidence/productization/ci_consecutive_pass_manifest.json`
- `implementation/phase1/release_evidence/productization/github_actions_ci_streak_evidence.json`
- `implementation/phase1/release_evidence/productization/github_actions_self_hosted_runner_status.json`
- `implementation/phase1/release_evidence/productization/ci_streak_intake_packet.json`
- `implementation/phase1/release_evidence/productization/pm_release_gate_report.json`
- `implementation/phase1/release_evidence/productization/product_readiness_snapshot.json`

## Streak Requirements

- `required_lanes`: `['pr', 'nightly']`
- `required_consecutive_pass_count`: `30`
- `source_schema_version`: `github-actions-ci-streak-evidence.v1`
- `max_source_evidence_age_hours`: `168`
- `runner_class`: `self-hosted linux x64`

## Required Fields

| Field | Current | Required | Pass |
|---|---|---|---:|
| `github_actions_ci_streak_evidence.schema_version` | `github-actions-ci-streak-evidence.v1` | `github-actions-ci-streak-evidence.v1` | `True` |
| `github_actions_ci_streak_evidence.generated_at` | `2026-07-04T09:02:06.092465+00:00` | `timezone-aware timestamp no older than 168 hours` | `True` |
| `github_actions_ci_streak_evidence.threshold` | `30` | `30` | `True` |
| `lanes.pr.consecutive_pass_count` | `0` | `>= 30` | `False` |
| `lanes.pr.threshold_pass` | `False` | `true` | `False` |
| `lanes.pr.pull_request_run_source_present` | `False` | `true` | `False` |
| `lanes.pr.workflow_registered_active` | `registered=True; state=active` | `registered=true and state=active` | `True` |
| `lanes.nightly.consecutive_pass_count` | `0` | `>= 30` | `False` |
| `lanes.nightly.threshold_pass` | `False` | `true` | `False` |
| `lanes.nightly.workflow_registered_active` | `registered=True; state=active` | `registered=true and state=active` | `True` |
| `lanes.nightly.schedule_or_dispatch_trigger_present` | `['schedule', 'workflow_dispatch']` | `schedule or workflow_dispatch trigger present` | `True` |
| `lanes.pr.local_self_hosted_runner_default` | `True` | `true` | `True` |
| `lanes.nightly.local_self_hosted_runner_default` | `True` | `true` | `True` |

## Derived Checks

| Check | Current | Required | Pass |
|---|---|---|---:|
| `source_manifest_threshold_consistency` | `source=30; required=30` | `source threshold equals release threshold` | `True` |
| `source_evidence_freshness` | `age_hours=0.002` | `freshness_pass=true` | `True` |
| `pr_trigger_and_source` | `triggers=['pull_request', 'push', 'workflow_dispatch']; pull_request_source=False` | `pull_request trigger and pull_request source runs present` | `False` |
| `nightly_trigger_source` | `triggers=['schedule', 'workflow_dispatch']` | `schedule or workflow_dispatch trigger present` | `True` |
| `self_hosted_runner_precondition` | `evaluated=True; online=0; ready=0` | `at least one required self-hosted runner online when evaluated` | `False` |
| `github_hosted_runner_defaults_absent` | `False` | `false` | `True` |
| `job_start_blockers_absent` | `1` | `0` | `False` |
| `release_area_blockers_absent` | `['pm_release::basic_ci::pr_ci_30_consecutive_pass_evidence_missing', 'pm_release::basic_ci::nightly_ci_30_consecutive_pass_evidence_missing']` | `[]` | `False` |

## Gate Unblock Plan

- `restore_self_hosted_runner_precondition`
- `resolve_github_actions_job_start_blockers`
- `collect_pr_30_consecutive_passes`
- `collect_nightly_30_consecutive_passes`
- `refresh_ci_streak_source_evidence`
- `regenerate_release_gate_evidence`

## CI Release Credit Policy

- `accepted_source`: `tracked GitHub Actions PR and nightly consecutive-pass evidence`
- `required_consecutive_pass_count`: `30`
- rejected substitutes:
  - local PR or nightly gate artifacts counted as release streak credit
  - manifest-only consecutive-pass claims without source evidence
  - queued/job-start-blocked workflow runs
  - github-hosted runner defaults when self-hosted labels are required

## Source Evidence

| Path | Schema | Fresh | Age Hours | Pass |
|---|---|---:|---:|---:|
| `implementation/phase1/release_evidence/productization/github_actions_ci_streak_evidence.json` | `github-actions-ci-streak-evidence.v1` | `True` | `0.002` | `False` |
