# Developer Preview Final Gate Action Register

- Date: 2026-07-18
- Source status: `implementation/phase1/release_evidence/productization/developer_preview_rc_status.json`
- Current RC result: deliverables `10/10`, final gates `5/9`, status `blocked`
- Claim boundary: this register is an owner handoff. It does not create benchmark, Windows, or human-observation evidence and does not promote Developer Preview, Commercial Release, G1, customer shadow, external benchmark, license, SLA, or GitHub sync readiness.

## Nearest A/B/F Slice

| Slice | Gate | Current state | Evidence | Next owner action |
|---|---|---|---|---|
| A | `benchmark_results_clean_checkout_regenerated` | Ready | `phase3_benchmark_factory_seed_clean_checkout_reproduction.json`, `phase3_benchmark_factory_seed_git_clean_clone_reproduction.json`, `phase6_clean_checkout_status.json` | Keep the clean-checkout and git-clean-clone receipts fresh when source or required inputs change. |
| B | `silent_import_loss_zero` | Blocked: selected contracts `10/10`, acquired/checksummed/executed evidence `0/10` | `phase3_ifc_import_health_execution_receipt.json`, `phase3_buildingsmart_ifc_acquisition_receipt.json`, `phase3_buildingsmart_dirty_ifc_acquisition_receipt.json`, `phase3_ifc_source_license_receipt.json`, `phase6_silent_import_loss_status.json` | Acquire and checksum all selected clean/dirty IFC files, run import-health and negative silent-loss contracts, and regenerate the Phase 3/6 receipts. Keep product/license credit blockers separate from this DP technical gate. |
| F | `new_user_core_workflow_observation_passed` | Blocked | `ux_new_user_observation_report.json`, `ux_new_user_observation_intake_packet.json`, `phase6_ux_observation_status.json` | Attach a real human new-user observation record for the five-step sample workflow, with timezone-aware start/end timestamps, completion minutes `<= 30`, `blocker_count=0`, non-template evidence reference, and accepted release decision. |

## Remaining Blocked Final Gates

| Gate | Current blocker shape | Required owner evidence | Verification |
|---|---|---|---|
| `selected_medium_models_pass_or_approved_review` | Valid scientific PASS/REVIEW rows `0/5`; the older `3/5` value is parser-ready candidate count, not benchmark credit. See `docs/medium-benchmark-corpus-and-acceptance.md` and `medium_benchmark_corpus_plan.json`. | Product/legal license approval, five diverse medium structural model cases, two independent reference-solver families including OpenSees, complete comparison artifact chains, and per-case PASS or scoped engineer-approved REVIEW decisions. | `python3 scripts/build_medium_benchmark_corpus_plan.py --check`, `python3 scripts/build_phase3_medium_model_scorecard_readiness_receipt.py --check`, `python3 scripts/build_phase6_benchmark_scale_status.py --check`, `python3 scripts/build_developer_preview_rc_status.py --check` |
| `silent_import_loss_zero` | Clean/dirty selection contracts total `10/10`, but source acquisition, checksums, import-health execution, visible-entity accounting, and negative silent-loss gate evidence are `0/10`. | Acquired and SHA256-bound selected IFC files plus executed Phase 3 import-health and negative/import-hardening receipts showing explicit entity accounting and zero silent loss. | `python3 scripts/build_phase3_ifc_import_health_execution_receipt.py --check`, `python3 scripts/build_phase6_silent_import_loss_status.py --check`, `python3 scripts/build_developer_preview_rc_status.py --check` |
| `linux_windows_reproducibility_confirmed` | Windows platform replay receipt missing. | `implementation/phase1/release_evidence/productization/phase6_windows_platform_replay_receipt.json` from the same tracked source state, with clean worktree, platform metadata, stable checksums, and the required replay commands returning `0`. | `python3 scripts/build_phase6_linux_windows_parity_status.py --check`, `python3 scripts/build_developer_preview_rc_status.py --check` |
| `new_user_core_workflow_observation_passed` | Observation file missing; `0/5` human-observed workflow steps passed. Automated browser smoke is ready but does not replace human observation. | Populate a non-template `ux_new_user_observation.json` from a first-time or pilot user covering Import, Model Health, Analysis Setup, Run & Monitor, and Compare & Report within 30 minutes. | `python3 scripts/build_ux_new_user_observation_report.py --out implementation/phase1/release_evidence/productization/ux_new_user_observation_report.json`, `python3 scripts/build_ux_new_user_observation_intake_packet.py --out implementation/phase1/release_evidence/productization/ux_new_user_observation_intake_packet.json`, `python3 scripts/build_developer_preview_rc_status.py --check` |

## Do Not Promote From

- Parser-only medium topology evidence.
- Selected IFC case contracts without acquired/checksummed files and executed import evidence.
- Linux-only replay evidence copied as Windows parity.
- GUI shell or Playwright smoke evidence without a real human new-user observation.
- Template UX observation JSON, self-referential evidence refs, or placeholder owner inputs.
- Product/legal/license credit rows as Developer Preview final-gate closure unless the referenced DP gate explicitly consumes them.
