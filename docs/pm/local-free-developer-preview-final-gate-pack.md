# Local-free Developer Preview final-gate pack

Purpose: prepare the remaining Developer Preview RC final gates for closure without running local solver jobs, Windows replay, or human UX observation.

This packet is **non-promoting**. It does not make Developer Preview ready, does not attach benchmark outputs, and does not create human or Windows evidence.

## Current state

- Deliverables: `10/10`
- Final gates: `6/9`
- Developer Preview ready: false
- Developer Preview release candidate ready: false

Open final gates:

1. `selected_medium_models_pass_or_approved_review`
2. `linux_windows_reproducibility_confirmed`
3. `new_user_core_workflow_observation_passed`

Authoritative artifacts:

- `implementation/phase1/release_evidence/productization/developer_preview_rc_status.json`
- `implementation/phase1/release_evidence/productization/developer_preview_readiness.json`
- `implementation/phase1/release_evidence/productization/developer_preview_final_gate_owner_packet.json`
- `implementation/phase1/release_evidence/productization/phase6_linux_windows_parity_status.json`
- `implementation/phase1/release_evidence/productization/ux_new_user_observation_report.json`

## Gate A — selected medium models PASS or approved REVIEW

Known blocker shape:

- medium structural models below required count: `3/5`
- medium model pass/review below required count: `0/5`
- scorecard execution missing for the required medium lane

Required evidence:

- Five selected medium structural models are present.
- Each model has PASS or approved REVIEW receipt.
- Reference/source/license requirements are recorded.
- Scorecard execution is attached.
- Review decision is explicit and does not promote unsupported solver claims.

Suggested medium-model receipt minimum fields:

- `case_id`
- `source_family`
- `model_scale`
- `license_or_rights_status`
- `reference_result_source`
- `execution_command`
- `scorecard_path`
- `decision`: `pass` or `approved_review`
- `reviewer`
- `reviewed_at_utc`
- `claim_boundary`

## Gate B — Linux/Windows reproducibility

Required evidence:

- Linux replay receipt is present and valid.
- Windows replay receipt is present and valid.
- Both replay receipts reference the same artifact set or explicitly documented equivalent artifact set.
- Working tree is clean during replay.
- Required commands return zero.
- Checksums for stable artifacts are recorded.

Disallowed shortcuts:

- Copying Linux receipt as Windows receipt.
- Marking Windows pass without actual Windows run.
- Omitting stable artifact checksums.
- Attaching dirty worktree receipts.

## Gate C — human new-user workflow observation

Required evidence:

- Real participant is a new/first-time/pilot user.
- Observer is a human observer or UX research owner.
- Participant completes required steps within 30 minutes:
  - Import
  - Model Health
  - Analysis Setup
  - Run & Monitor
  - Compare & Report
- Blocking usability issues are absent or explicitly accepted.
- Evidence reference is separate from generated gate artifacts.
- Approval decision is accepted/pass/signed/approved_for_release.

## Recommended execution sequence

1. Finalize five medium model candidates and rights/source status.
2. Execute medium model scorecards.
3. Attach PASS/approved REVIEW decisions.
4. Run Linux replay.
5. Run Windows replay on actual Windows runner/PC.
6. Conduct human UX observation.
7. Regenerate UX observation report.
8. Regenerate Linux/Windows parity status.
9. Regenerate Developer Preview RC status.
10. Regenerate Developer Preview readiness.
11. Regenerate product readiness snapshot in check mode.

## Acceptance criteria

Developer Preview RC becomes ready only when:

- final gates are `9/9`;
- all deliverables remain `10/10`;
- medium model pass/review count reaches required threshold;
- Windows and Linux replay receipts pass;
- human new-user observation passes;
- known limitations still preserve claim boundaries.

## Claim boundary

Allowed current claim:

> Developer Preview deliverables are packaged, but final gates remain open for selected medium models, Linux/Windows reproducibility, and human new-user observation.

Forbidden current claim:

- Developer Preview ready
- Developer Preview RC ready
- commercial solver beta
- customer-validated release
- Windows parity proven without Windows receipt
- human UX proven by automated browser smoke
