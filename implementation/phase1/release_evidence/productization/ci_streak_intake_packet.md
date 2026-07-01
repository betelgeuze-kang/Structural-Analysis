# CI Streak Intake Packet

- `contract_pass`: `False`
- `reason_code`: `ERR_CI_STREAK_SOURCE_EVIDENCE_INCOMPLETE`
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

## Validation Commands

- `python3 scripts/check_github_actions_self_hosted_runner_status.py --out implementation/phase1/release_evidence/productization/github_actions_self_hosted_runner_status.json`
- `python3 scripts/build_github_actions_ci_streak_evidence.py --out implementation/phase1/release_evidence/productization/github_actions_ci_streak_evidence.json`
- `python3 scripts/build_ci_consecutive_pass_manifest.py --out implementation/phase1/release_evidence/productization/ci_consecutive_pass_manifest.json`
- `python3 scripts/build_ci_streak_intake_packet.py --out implementation/phase1/release_evidence/productization/ci_streak_intake_packet.json`
- `python3 scripts/report_pm_release_gate.py  --out implementation/phase1/release_evidence/productization/pm_release_gate_report.json --out-md implementation/phase1/release_evidence/productization/pm_release_gate_report.md`
- `python3 scripts/build_pm_release_blocker_action_register.py  --out implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.json --out-md implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.md`

## Source Evidence

| Path | Schema | Fresh | Age Hours | Pass |
|---|---|---:|---:|---:|
| `implementation/phase1/release_evidence/productization/github_actions_ci_streak_evidence.json` | `github-actions-ci-streak-evidence.v1` | `True` | `7.702` | `False` |
