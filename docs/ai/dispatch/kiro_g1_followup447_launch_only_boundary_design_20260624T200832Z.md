# Kiro Design Slice Template

You are Kiro running as a design-only architect on model `opus-4.8`. Codex owns the active goal, acceptance criteria, verification planning, claim-boundary review, and final acceptance. Cursor `composer-2.5` will implement the approved scoped slice if implementation delegation is needed.

Do not edit files. Do not claim readiness closure. Do not produce a long design document.

## Task

Goal: Design a narrow status-boundary update for `mgt_shell_material_rowcorr_budget_controller_followup447_fd_target_rows_support8_cpu_continuation_candidate1_target128_support8.json`, which is currently a launch-only child receipt.

Current blocker: The followup447 child receipt has schema `mgt-shell-material-rowcorr-child-launch.v1`, `status=in_progress`, target mode `largest_rows`, row Jacobian `finite_difference`, support selection `target_rows`, and a claim boundary saying a completed child direct-residual receipt is required before claiming residual progress. It must not be counted as residual descent, row-mode exhaustion, or G1 closure evidence.

Scope: Design only a focused change that makes this pending launch-only receipt visible in the G1 shell-material status and ledger wording. Do not run the child solver. Do not claim readiness closure. Do not alter G1 closure semantics.

Candidate files:

- `scripts/build_mgt_g1_shell_material_budgeted_continuation_status.py`
- `tests/test_build_mgt_g1_shell_material_budgeted_continuation_status.py`
- `docs/commercial-structural-solver-product-gap-ledger.md`
- `docs/structural-analysis-ai-engine-gap-ledger.md`
- `implementation/phase1/release_evidence/productization/mgt_g1_followup387_shell_material_budgeted_continuation_status.json`

Verification criteria:

- Status receipt exposes followup447 as pending launch-only and non-counted.
- Followup447 does not affect latest frontier, direct residual gate, row-target exhaustion, or G1 blockers.
- Ledger wording states followup447 is launch-only/in-progress and cannot claim residual progress.
- Focused pytest passes.
- `./scripts/ai-worker-kiro.sh --check` passes for this prompt.

## Return Format

Return only these sections:

- Design summary
- Implementation order
- Candidate files
- Verification plan
- Risks and claim boundary
- Cursor handoff prompt
