# Kiro Design Slice

You are Kiro running as a design-only architect on model `opus-4.8`. Codex owns the active goal, acceptance criteria, verification planning, claim-boundary review, and final acceptance.

Do not edit files. Do not claim readiness closure. Do not produce a long design document.

## Task

Goal: Design the smallest safe G1 diagnostic slice for testing shell geometry-normal plus bending row-family targeting at the latest followup431 frontier checkpoint.

Current blocker: G1 remains partial. Followups 432-437 show no accepted descent from the followup431 `1.3092276661494922 N` frontier for support widening, target retuning, shell bending/drilling rows, shell normal rows, and shell geometry-normal rows. The supported target mode `residual_shell_geometry_normal_bending_rows` has not yet been status-bound at that same latest checkpoint.

Scope: Plan only one bounded CPU-diagnostic controller launch from `mgt_shell_material_rowcorr_budget_controller_followup431_target128_support8_cpu_continuation_compact_checkpoint.npz` using target128/support8, `current_tangent`, `row_strongest`, alpha `0.015625`, and `residual_shell_geometry_normal_bending_rows`. Treat any result as boundary evidence unless it produces a completed child receipt with residual descent. Do not propose readiness closure.

Candidate files:

- `scripts/build_mgt_g1_shell_material_budgeted_continuation_status.py`
- `tests/test_build_mgt_g1_shell_material_budgeted_continuation_status.py`
- `docs/commercial-structural-solver-product-gap-ledger.md`
- `docs/structural-analysis-ai-engine-gap-ledger.md`
- `implementation/phase1/release_evidence/productization/`

Verification criteria:

- Kiro launch receipt proves `opus-4.8` prompt validation, no-edit boundary, and no-closure boundary.
- Controller receipt records child base/final residual and row-correction stop reason.
- If no descent, status builder records followup438 as non-promoting and keeps latest frontier at `1.3092276661494922 N`.
- Commercial and AI ledgers preserve G1 partial and do not promote G6/G7 or autonomous AI readiness.
- Focused pytest and readiness/status/audit checks pass.

## Return Format

Return only these sections:

- Design summary
- Implementation order
- Candidate files
- Verification plan
- Risks and claim boundary
- Cursor handoff prompt
