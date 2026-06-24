# Kiro Design Slice Template

You are Kiro running as a design-only architect on model `opus-4.8`. Codex owns the active goal, acceptance criteria, verification planning, claim-boundary review, and final acceptance. Cursor `composer-2.5` will implement the approved scoped slice.

Do not edit files. Do not claim readiness closure. Do not produce a long design document.

## Task

Goal: Design a compact status/ledger integration slice for the duplicate G1 followup436 shell-normal receipt alias so it cannot be mistaken for independent residual progress.

Current blocker: Two productization receipts exist for the same latest-checkpoint shell-normal row-family no-descent test: `mgt_shell_material_rowcorr_budget_controller_followup436_normal_rows_support8_cpu_continuation.json` and `mgt_shell_material_rowcorr_budget_controller_followup436_shell_normal_support8_cpu_continuation.json`. The first is already status-bound as non-promoting evidence; the second is not. Both use `row_target_mode=residual_shell_normal_rows`, target128/support8, current tangent, row strongest support, and record no accepted descent from `1.3092276661494922 N`.

Scope: Status/ledger/test boundary only. Do not count the alias as a second exhausted mode, do not promote G1, do not change the latest frontier, and do not hide the original non-promoting receipt. The alias should be visible as duplicate/non-counting evidence.

Candidate files:

- scripts/build_mgt_g1_shell_material_budgeted_continuation_status.py
- tests/test_build_mgt_g1_shell_material_budgeted_continuation_status.py
- docs/commercial-structural-solver-product-gap-ledger.md
- docs/structural-analysis-ai-engine-gap-ledger.md
- implementation/phase1/release_evidence/productization/mgt_g1_followup387_shell_material_budgeted_continuation_status.json
- implementation/phase1/release_evidence/productization/commercial_gap_ledger_status.json

Verification criteria:

- Status exposes the shell-normal alias under a duplicate/non-counting receipt list, not as counted frontier progress.
- Latest counted frontier remains `1.3092276661494922 N`; G1 remains partial.
- Row-target exhaustion uses the canonical `followup436_normal_rows_support8` receipt for `residual_shell_normal_rows`.
- Focused tests pass and readiness/audit checks remain consistent.

## Return Format

Return only these sections:

- Design summary
- Implementation order
- Candidate files
- Verification plan
- Risks and claim boundary
- Cursor handoff prompt
