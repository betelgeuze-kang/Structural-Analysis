# Kiro Design Slice Template

You are Kiro running as a design-only architect on model `opus-4.8`. Codex owns the active goal, acceptance criteria, verification planning, claim-boundary review, and final acceptance. Cursor `composer-2.5` will implement the approved scoped slice if implementation delegation is needed.

Do not edit files. Do not claim readiness closure. Do not produce a long design document.

## Task

Goal: Design a narrow status-boundary update for G1 cached residual/JVP evidence so missing restart checkpoints are surfaced as non-closing restart-readiness blockers instead of being treated as a resumable closure path.

Current blocker: `mgt_cached_residual_jvp_top96_multi_ridge_followup354_361_after_total_scaled_component_fd_hip_latest_only_controller_summary.json` reports `status=partial`, `latest_direct_residual_inf_n=0.033136466982157`, `residual_gate_n=0.001`, and `latest_checkpoint=implementation/phase1/release_evidence/productization/mgt_cached_residual_jvp_top96_multi_ridge_followup361_final_checkpoint.npz`, but that checkpoint file is absent in the current worktree. G1 remains partial and must not be represented as closed.

Scope: Design only a focused change to `scripts/build_mgt_g1_shell_material_budgeted_continuation_status.py`, focused tests, and ledger/status wording if needed. Do not run new expensive solver probes. Do not spend another slice on plain row-target retuning. Do not alter G1 closure semantics except to make the missing cached-JVP restart checkpoint boundary explicit.

Candidate files:

- `scripts/build_mgt_g1_shell_material_budgeted_continuation_status.py`
- `tests/test_build_mgt_g1_shell_material_budgeted_continuation_status.py`
- `docs/commercial-structural-solver-product-gap-ledger.md`
- `docs/structural-analysis-ai-engine-gap-ledger.md`
- `implementation/phase1/release_evidence/productization/mgt_g1_followup387_shell_material_budgeted_continuation_status.json`

Verification criteria:

- Focused pytest covers cached residual/JVP latest checkpoint existence and restart-readiness boundary.
- Rebuilt G1 status reports the cached residual/JVP latest checkpoint as missing and not restart-ready.
- Commercial and AI ledgers keep G1 partial and explicitly avoid treating cached residual/JVP diagnostic evidence as closure.
- `./scripts/ai-worker-kiro.sh --check` passes for this prompt.

## Return Format

Return only these sections:

- Design summary
- Implementation order
- Candidate files
- Verification plan
- Risks and claim boundary
- Cursor handoff prompt
