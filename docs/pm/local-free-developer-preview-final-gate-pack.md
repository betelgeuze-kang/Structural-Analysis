# Local-free Developer Preview final-gate pack

Purpose: prepare the remaining Developer Preview RC final gates for closure without running local solver jobs, Windows replay, or human UX observation.

This packet is **non-promoting**. It does not make Developer Preview ready, does not attach benchmark outputs, and does not create human or Windows evidence.

## Current state

- Deliverables: `10/10`
- Final gates: `5/9`
- Developer Preview ready: false
- Developer Preview release candidate ready: false

Open final gates:

1. `selected_medium_models_pass_or_approved_review`
2. `silent_import_loss_zero`
3. `linux_windows_reproducibility_confirmed`
4. `new_user_core_workflow_observation_passed`

Authoritative artifacts:

- `implementation/phase1/release_evidence/productization/developer_preview_rc_status.json`
- `implementation/phase1/release_evidence/productization/developer_preview_readiness.json`
- `implementation/phase1/release_evidence/productization/developer_preview_final_gate_owner_packet.json`
- `implementation/phase1/release_evidence/productization/phase6_linux_windows_parity_status.json`
- `implementation/phase1/release_evidence/productization/ux_new_user_observation_report.json`

## Gate A — selected medium models PASS or approved REVIEW

Known blocker shape:

- parser-ready medium candidates: `3/5` (scientific benchmark credit remains `0/5`)
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

The authoritative scientific contract is `docs/medium-benchmark-corpus-and-acceptance.md`; the generated non-promoting plan is `implementation/phase1/release_evidence/productization/medium_benchmark_corpus_plan.json`. The legacy minimum fields above are insufficient by themselves without the metric-specific comparison and decision artifact chain required there.

## Gate B — IFC silent-import-loss technical evidence

Current evidence is fail-closed: selected clean/dirty contracts are `10/10`, while
acquired files, attached checksums, import-health execution, visible-entity accounting,
and negative silent-loss gate passes are `0/10`.

Required evidence:

- Acquire the selected clean and dirty IFC source files through the approved process.
- Bind every selected file to its SHA256 value.
- Execute the import-health and dirty/negative import contracts.
- Retain visible entity accounting and explicit unsupported-entity outcomes.
- Regenerate the Phase 3 import-health and Phase 6 silent-import-loss receipts.

The selected-case count is a plan/input contract only and is not execution evidence.
Product/legal quantity credit remains a separate release requirement.

## Gate C — Linux/Windows reproducibility

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

## Gate D — human new-user workflow observation

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
4. Acquire/checksum the selected IFC files and execute the import-health and negative
   silent-loss contracts.
5. Regenerate the Phase 3 IFC and Phase 6 silent-import-loss receipts.
6. Run Linux replay.
7. Run Windows replay on actual Windows runner/PC.
8. Conduct human UX observation.
9. Regenerate UX observation report.
10. Regenerate Linux/Windows parity status.
11. Regenerate Developer Preview RC status.
12. Regenerate Developer Preview readiness.
13. Regenerate product readiness snapshot in check mode.

## Acceptance criteria

Developer Preview RC becomes ready only when:

- final gates are `9/9`;
- all deliverables remain `10/10`;
- medium model pass/review count reaches required threshold;
- acquired/checksummed IFC files and executed import-health/silent-loss evidence pass;
- Windows and Linux replay receipts pass;
- human new-user observation passes;
- known limitations still preserve claim boundaries.

## Claim boundary

Allowed current claim:

> Developer Preview deliverables are packaged, but final gates remain open for selected medium models, IFC import-health/silent-loss execution evidence, Linux/Windows reproducibility, and human new-user observation.

Forbidden current claim:

- Developer Preview ready
- Developer Preview RC ready
- commercial solver beta
- customer-validated release
- Windows parity proven without Windows receipt
- human UX proven by automated browser smoke
