# Cursor worker task: UX duplicate blocker audit

Goal: Audit whether `pm_release::ux::*` blockers duplicate the same missing human observation already represented by `human_ux::*` blockers in Developer Preview readiness.

Scope:
- Read `/home/betelgeuze/.codex/attachments/98075342-506d-4368-9755-b528a830c410/goal-objective.md`.
- Read `.betelgeuze/intent_spec.md` and `.betelgeuze/project_contract.yaml`.
- Inspect only:
  - `scripts/build_product_readiness_snapshot.py`
  - `scripts/build_developer_preview_readiness.py`
  - `scripts/report_pm_release_gate.py`
  - `implementation/phase1/release_evidence/productization/ux_new_user_observation_report.json`
  - `implementation/phase1/release_evidence/productization/pm_release_gate_report.json`
  - related tests if needed

Question:
- Are `pm_release::ux::human_new_user_30min_sample_evidence_missing` and `pm_release::ux::human_new_user_observation_missing_or_failed` duplicating the same evidence gap already carried by `human_ux::*` blockers?
- If yes, recommend a narrow code/test change so Developer Preview and product snapshots keep the direct `human_ux::*` blockers but do not double-count the `pm_release::ux::*` wrappers.
- Do not hide the human UX gate, do not mark UX ready, and do not change external/human final gate semantics.

Verification criteria:
- The answer must list changed files if edits are made.
- If edits are not made, list the exact recommended files and tests.
- Include only core diff summary, relevant test commands/results, and blockers.
