# Developer Preview Final Gate Action Register

- Date: 2026-07-01
- Source status: `implementation/phase1/release_evidence/productization/developer_preview_rc_status.json`
- Current RC result: deliverables `10/10`, final gates `6/9`, status `blocked`
- Claim boundary: this register is an owner handoff. It does not create benchmark, Windows, or human-observation evidence and does not promote Developer Preview, Commercial Release, G1, customer shadow, external benchmark, license, SLA, or GitHub sync readiness.

## Nearest A/B/F Slice

| Slice | Gate | Current state | Evidence | Next owner action |
|---|---|---|---|---|
| A | `benchmark_results_clean_checkout_regenerated` | Ready | `phase3_benchmark_factory_seed_clean_checkout_reproduction.json`, `phase3_benchmark_factory_seed_git_clean_clone_reproduction.json`, `phase6_clean_checkout_status.json` | Keep the clean-checkout and git-clean-clone receipts fresh when source or required inputs change. |
| B | `silent_import_loss_zero` | Ready for the DP technical gate | `phase3_ifc_import_health_execution_receipt.json`, `phase3_buildingsmart_ifc_acquisition_receipt.json`, `phase3_buildingsmart_dirty_ifc_acquisition_receipt.json`, `phase3_ifc_source_license_receipt.json`, `phase6_silent_import_loss_status.json` | Keep product/license credit blockers separate from this DP technical gate; do not treat IFC quantity/license credit as full product release closure. |
| F | `new_user_core_workflow_observation_passed` | Blocked | `ux_new_user_observation_report.json`, `ux_new_user_observation_intake_packet.json`, `phase6_ux_observation_status.json` | Attach a real human new-user observation record for the five-step sample workflow, with timezone-aware start/end timestamps, completion minutes `<= 30`, `blocker_count=0`, non-template evidence reference, and accepted release decision. |

## Remaining Blocked Final Gates

| Gate | Current blocker shape | Required owner evidence | Verification |
|---|---|---|---|
| `selected_medium_models_pass_or_approved_review` | Valid PASS/approved-review rows `0/5`; candidate cases are not enough without license, reference output, normalization, and scorecard receipts. | Product/legal license approval, five selected medium structural model cases, reference outputs or approved REVIEW baselines, normalization receipts, and per-case scorecard receipts with PASS or APPROVED_REVIEW decisions. | `python3 scripts/build_phase3_medium_model_scorecard_readiness_receipt.py --check`, `python3 scripts/build_phase6_benchmark_scale_status.py --check`, `python3 scripts/build_developer_preview_rc_status.py --check` |
| `linux_windows_reproducibility_confirmed` | Windows platform replay receipt missing. | `implementation/phase1/release_evidence/productization/phase6_windows_platform_replay_receipt.json` from the same tracked source state, with clean worktree, platform metadata, stable checksums, and the required replay commands returning `0`. | `python3 scripts/build_phase6_linux_windows_parity_status.py --check`, `python3 scripts/build_developer_preview_rc_status.py --check` |
| `new_user_core_workflow_observation_passed` | Observation file missing; `0/5` human-observed workflow steps passed. Automated browser smoke is ready but does not replace human observation. | Populate a non-template `ux_new_user_observation.json` from a first-time or pilot user covering Import, Model Health, Analysis Setup, Run & Monitor, and Compare & Report within 30 minutes. | `python3 scripts/build_ux_new_user_observation_report.py --out implementation/phase1/release_evidence/productization/ux_new_user_observation_report.json`, `python3 scripts/build_ux_new_user_observation_intake_packet.py --out implementation/phase1/release_evidence/productization/ux_new_user_observation_intake_packet.json`, `python3 scripts/build_developer_preview_rc_status.py --check` |

## Do Not Promote From

- Parser-only medium topology evidence.
- Linux-only replay evidence copied as Windows parity.
- GUI shell or Playwright smoke evidence without a real human new-user observation.
- Template UX observation JSON, self-referential evidence refs, or placeholder owner inputs.
- Product/legal/license credit rows as Developer Preview final-gate closure unless the referenced DP gate explicitly consumes them.
