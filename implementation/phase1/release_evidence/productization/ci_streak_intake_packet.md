# CI Streak Intake Packet

- `summary_line`: `CI streak intake: BLOCKED | lanes=0/2 | pr_missing=30 | nightly_missing=30 | blockers=10 | runner=blocked`
- `status`: `blocked`
- `contract_pass`: `False`
- `reason_code`: `ERR_CI_STREAK_SOURCE_EVIDENCE_INCOMPLETE`
- `release_area`: `basic_ci`
- `current_blocker_count`: `10`
- `blocker_id_count`: `12`
- `evidence_intake_artifact_count`: `6`
- `ci_consecutive_pass_manifest`: `implementation/phase1/release_evidence/productization/ci_consecutive_pass_manifest.json`
- `github_actions_ci_streak_evidence`: `implementation/phase1/release_evidence/productization/github_actions_ci_streak_evidence.json`

| Lane | Observed Streak | Missing | Source | Workflow Registered | Pass | Owner Action |
|---|---:|---:|---|---|---|---|
| `pr` | `0/30` | `30` | `github_actions_job_start_blocked` | `True` | `False` | Resolve the pr GitHub Actions job-start blocker shown in github_actions_ci_streak_evidence.json, rerun the workflow, and then collect 30 additional consecutive successful CI run(s) before release signoff. |
| `nightly` | `0/30` | `30` | `github_actions_job_start_blocked` | `True` | `False` | Resolve the nightly GitHub Actions job-start blocker shown in github_actions_ci_streak_evidence.json, rerun the workflow, and then collect 30 additional consecutive successful CI run(s) before release signoff. |

## Runner Precondition

| Path | Status | Online Matching | Ready | Pass | Owner Action |
|---|---|---:|---:|---:|---|
| `implementation/phase1/release_evidence/productization/github_actions_self_hosted_runner_status.json` | `blocked` | `0/1` | `0` | `False` | Bring at least one GitHub Actions self-hosted runner online with labels self-hosted, linux, x64, then refresh github_actions_self_hosted_runner_status.json and github_actions_ci_streak_evidence.json before collecting the 30-run streak. |

## Job Start Blocker Queue

| Lane | Count | Reason Codes | First Run | Owner Action |
|---|---:|---|---|---|
| `pr` | `5` | `github_actions_self_hosted_runner_queued_timeout` | `28481977838` | Resolve the pr GitHub Actions job-start blocker, bring the required self-hosted runner online, rerun the workflow, then collect 30 consecutive successful run(s). |
| `nightly` | `1` | `github_actions_self_hosted_runner_queued_timeout` | `28473310506` | Resolve the nightly GitHub Actions job-start blocker, bring the required self-hosted runner online, rerun the workflow, then collect 30 consecutive successful run(s). |

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
- `ci_streak::pr:pr_github_actions_job_start_blocked`
- `ci_streak::pr:pr_ci_30_consecutive_pass_evidence_missing`
- `ci_streak::pr:github_actions_lane_threshold_not_pass`
- `ci_streak::pr:github_actions_lane_streak_below_threshold`
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
| `implementation/phase1/release_evidence/productization/github_actions_ci_streak_evidence.json` | `github-actions-ci-streak-evidence.v1` | `True` | `14.974` | `False` |
