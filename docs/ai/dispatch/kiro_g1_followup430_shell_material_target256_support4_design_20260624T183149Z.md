# Kiro Design Slice

You are Kiro running as a design-only architect on model `opus-4.8`. Codex owns the active goal, acceptance criteria, verification planning, claim-boundary review, and final acceptance. Cursor `composer-2.5` may implement approved scoped local edits, but this slice is evidence generation and status refresh only.

Do not edit files. Do not claim readiness closure. Do not produce a long design document.

## Task

Goal: Design the next bounded G1 shell-material CPU diagnostic continuation after followup429.

Current blocker: G1 remains partial. Followup429 lowered the counted frontier to `1.3277400507770736 N` but target128/support4 ended with `row_correction_stop_reason=no_residual_descent` after three promotions. The latest residual is still about `2.66e3x` above the `5e-4 N` direct-residual gate; full-load/full-mesh/material Newton/production ROCm-HIP gates remain open.

Scope: Recommend whether Codex should try one bounded changed-operator child using target256/support4 current-tangent row correction from the followup429 compact checkpoint, or choose a different immediate operator-change diagnostic. Keep the result CPU-diagnostic only. Do not propose broad refactors, external submissions, readiness closure, or edits outside receipt/status/ledger refreshes.

Candidate files:

- `implementation/phase1/release_evidence/productization/mgt_shell_material_rowcorr_budget_controller_followup429_target128_support4_cpu_continuation_compact_checkpoint.npz`
- `scripts/run_mgt_shell_material_rowcorr_budget_controller.py`
- `scripts/build_mgt_g1_shell_material_budgeted_continuation_status.py`
- `docs/commercial-structural-solver-product-gap-ledger.md`
- `docs/structural-analysis-ai-engine-gap-ledger.md`

Verification criteria:

- New receipt, if run, must include direct residual, compact checkpoint, promotion count, residual gate status, and claim boundary.
- Status reporter must continue to mark G1 partial unless all full-load/full-mesh/material Newton/production ROCm-HIP gates are proven.
- If target256/support4 improves, count it as the latest CPU-diagnostic frontier; if it does not, record it as non-promoting boundary evidence without replacing followup429.
- Commercial and AI ledgers must describe the new evidence as CPU-diagnostic frontier or boundary evidence only.
- Run focused reporter tests, orchestration preflight, readiness consistency checks, release freshness, `./scripts/ai-verify.sh`, and `git diff --check`.

## Return Format

Return only these sections:

- Design summary
- Implementation order
- Candidate files
- Verification plan
- Risks and claim boundary
- Cursor handoff prompt
