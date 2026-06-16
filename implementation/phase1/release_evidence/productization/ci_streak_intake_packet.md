# CI Streak Intake Packet

- `contract_pass`: `False`
- `reason_code`: `ERR_CI_STREAK_EVIDENCE_INCOMPLETE`
- `ci_consecutive_pass_manifest`: `implementation/phase1/release_evidence/productization/ci_consecutive_pass_manifest.json`
- `github_actions_ci_streak_evidence`: `implementation/phase1/release_evidence/productization/github_actions_ci_streak_evidence.json`

| Lane | Streak | Missing | Source | Workflow Registered | Pass | Owner Action |
|---|---:|---:|---|---|---|---|
| `pr` | `0/30` | `30` | `missing_tracked_ci_evidence` | `True` | `False` | Collect 30 additional consecutive successful PR CI run(s); keep the pull_request CI lane green and refresh github_actions_ci_streak_evidence before release signoff. |
| `nightly` | `0/30` | `30` | `github_actions_workflow_not_registered` | `False` | `False` | Register or enable the nightly GitHub Actions workflow, then collect 30 additional consecutive successful nightly CI run(s) before release signoff. Local workflow file is present, so merge/register it in GitHub Actions first. |

## Validation Commands

- `python3 scripts/build_github_actions_ci_streak_evidence.py --out implementation/phase1/release_evidence/productization/github_actions_ci_streak_evidence.json`
- `python3 scripts/build_ci_consecutive_pass_manifest.py --out implementation/phase1/release_evidence/productization/ci_consecutive_pass_manifest.json`
- `python3 scripts/build_ci_streak_intake_packet.py --out implementation/phase1/release_evidence/productization/ci_streak_intake_packet.json`
- `python3 scripts/report_pm_release_gate.py  --out implementation/phase1/release_evidence/productization/pm_release_gate_report.json --out-md implementation/phase1/release_evidence/productization/pm_release_gate_report.md`
- `python3 scripts/build_pm_release_blocker_action_register.py  --out implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.json --out-md implementation/phase1/release_evidence/productization/pm_release_blocker_action_register.md`
