# Developer Preview Remaining Gate Owner Packet

> Status: **non-promoting PM execution handoff**  
> Scope: Open Benchmark Developer Preview only  
> This packet does **not** promote Commercial Release, paid pilot, G1, full solver readiness, autonomous AI, license server readiness, or customer-shadow readiness.

## 1. Current Developer Preview position

Current Developer Preview surface is in late pre-release state:

```text
deliverables = 10/10
final gates = 6/9
Developer Preview ready = false
```

The Developer Preview scope is a bounded open-benchmark workstation preview. It is not a commercial structural solver beta.

## 2. Already-ready deliverables

| Deliverable | Status | Notes |
|---|---|---|
| Installable Python package | ready | Package and setup surface exist. |
| CLI | ready | `structural-analysis` CLI entrypoint surface exists. |
| Local GUI surface | ready | Viewer/workbench surface exists. |
| Sample acquisition command | ready | Acquisition command surface exists without claiming external corpus closure. |
| Benchmark runner | ready | Runner surface exists. |
| Benchmark scorecard | ready | Scorecard surface exists. |
| Known limitations | ready | Limitations remain explicit. |
| Reproducibility bundle | ready | Bundle surface exists. |
| Dataset/license manifest | ready | Dataset/license manifest surface exists. |
| Commercial comparison import template | ready | Import-template surface exists. |

## 3. Gates that recently improved

| Gate | Current DP interpretation | Claim boundary |
|---|---|---|
| Silent import loss zero | passing in current README/DP surface | Does not close commercial solver truth or benchmark truth. |
| Large crash/OOM-free | passing in current README/DP surface | Does not close full Phase 3 or G1. |

These improvements move Developer Preview closer to external preview, but they do not promote release or paid pilot readiness.

## 4. Remaining gates

### Gate 1 — Selected medium models PASS or approved REVIEW

Current signal:

```text
selected_medium_models_pass_or_approved_review remains blocked
medium structural model count is below required 5/5 in the roadmap surface
```

Owner objective:

```text
selected_medium_models_pass_or_approved_review = ready
```

Required evidence:

| Evidence | Required shape |
|---|---|
| Medium model list | Five selected medium structural models with stable IDs. |
| Execution/scorecard receipt | Each selected model has PASS or approved REVIEW. |
| Review exception, if any | Human-approved REVIEW row with reason and scope boundary. |
| Known-limitations update | Any REVIEW model limitation appears in known limitations. |
| No silent import loss | Medium model import retains expected structural content. |

Suggested commands:

```bash
python3 scripts/build_phase3_medium_model_scorecard_readiness_receipt.py --json
python3 scripts/build_developer_preview_rc_status.py --json --no-write
python3 scripts/build_developer_preview_readiness.py --json --no-write
```

Acceptance criteria:

```text
medium_structural_models_current >= 5
medium_model_pass_or_review >= 5
selected_medium_models_pass_or_approved_review.status == ready
Developer Preview final gate count increments without commercial-solver promotion
```

### Gate 2 — Linux/Windows reproducibility

Current signal:

```text
Linux/Windows reproducibility remains blocked; Windows replay receipt is still missing or insufficient.
```

Owner objective:

```text
linux_windows_reproducibility_confirmed = ready
```

Required evidence:

| Evidence | Required shape |
|---|---|
| Linux replay receipt | Clean replay with source commit and checksums. |
| Windows replay receipt | Clean replay with the same source boundary. |
| Result comparison | Platform parity fields or documented acceptable deltas. |
| Dependency manifest | Python/npm/runtime versions captured. |
| Known limitations | Platform-specific gaps documented if accepted as REVIEW. |

Suggested commands:

```bash
python3 scripts/build_phase6_linux_windows_parity_status.py --json
python3 scripts/build_developer_preview_rc_status.py --json --no-write
python3 scripts/build_developer_preview_readiness.py --json --no-write
```

Acceptance criteria:

```text
Windows replay receipt present
Linux replay receipt present
Linux/Windows parity status ready
No platform-specific silent import loss
No release promotion beyond Developer Preview scope
```

### Gate 3 — Human new-user workflow observation

Current signal:

```text
human new-user workflow observation remains blocked
```

Owner objective:

```text
new_user_core_workflow_observation_passed = ready
```

Required evidence:

| Evidence | Required shape |
|---|---|
| Observation session | Real person or approved internal observer executes workflow. |
| Duration | Minimum workflow duration recorded, e.g. 30-minute sample. |
| Task list | Install/load sample/run analysis/view report/export evidence. |
| Outcome | PASS/REVIEW/FAIL decision with notes. |
| Consent/privacy | No private customer raw data included. |

Suggested commands:

```bash
python3 scripts/build_ux_new_user_observation_intake_packet.py --json
python3 scripts/build_ux_new_user_observation_report.py --json
python3 scripts/build_phase6_ux_observation_status.py --json
python3 scripts/build_developer_preview_rc_status.py --json --no-write
```

Acceptance criteria:

```text
new_user_core_workflow_observation_passed == true
observation artifact exists
known limitations updated for any REVIEW items
Developer Preview remains bounded to open benchmark workstation preview
```

## 5. Recommended execution order

| Priority | Gate | Why first |
|---:|---|---|
| 1 | Selected medium models | Most concrete DP evidence gap; improves product credibility. |
| 2 | Linux/Windows reproducibility | Required for external preview trust and installation confidence. |
| 3 | Human new-user workflow observation | Converts technical readiness into usability evidence. |

## 6. Owner checklist

| Checklist item | Owner | Status |
|---|---|---|
| Identify five selected medium structural models | PM + CTO | TODO |
| Execute or review medium model scorecard | CTO / Codex / local runner | TODO |
| Generate Windows replay receipt | Release owner | TODO |
| Compare Linux/Windows replay | Release owner | TODO |
| Run human new-user workflow | PM / observer | TODO |
| Update known limitations | PM | TODO |
| Rebuild Developer Preview RC status | Release owner | TODO |
| Rebuild Developer Preview readiness | Release owner | TODO |

## 7. Non-promoting guardrails

Closing Developer Preview gates does not close:

```text
G1 full nonlinear full-mesh/material Newton
Commercial Release
paid pilot
customer shadow
external benchmark receipts
autonomous AI/GNN/surrogate truth
license server operation
commercial SLA
```

Allowed claim after all gates close:

```text
Open Benchmark Workstation Developer Preview ready
```

Disallowed claim:

```text
Commercial structural solver beta
Engineer replacement
Permit automation
Full autonomous optimization/design approval
```
