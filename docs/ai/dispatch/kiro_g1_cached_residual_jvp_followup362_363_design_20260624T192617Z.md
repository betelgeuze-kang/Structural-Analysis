# Kiro Design Slice

You are Kiro running as a design-only architect on model `opus-4.8`. Codex owns the active goal, acceptance criteria, verification planning, claim-boundary review, and final acceptance.

Do not edit files. Do not claim readiness closure. Do not produce a long design document.

## Task

Goal: Design the smallest safe continuation slice for G1 cached residual/JVP multi-ridge diagnostics after followup361.

Current blocker: G1 remains partial. The latest status-bound cached residual/JVP summary is `mgt_cached_residual_jvp_top96_multi_ridge_followup354_361_after_total_scaled_component_fd_hip_latest_only_controller_summary.json`, with latest residual `0.033136466982157 N`, remaining margin `0.032136466982157 N`, and gate `0.001 N`. It explicitly disclaims residual gate closure and production ROCm/HIP residency.

Scope: Plan one bounded continuation using `implementation/phase1/run_mgt_cached_residual_jvp_multi_ridge_controller.py` from `mgt_cached_residual_jvp_top96_multi_ridge_followup361_final_checkpoint.npz`, start followup index `362`, max steps `2`, existing HIP full residual batch replay settings, retain latest checkpoint only, and `--allow-cpu-diagnostic`. Treat any result as diagnostic evidence only.

Candidate files:

- `implementation/phase1/run_mgt_cached_residual_jvp_multi_ridge_controller.py`
- `scripts/build_mgt_g1_shell_material_budgeted_continuation_status.py`
- `tests/test_build_mgt_g1_shell_material_budgeted_continuation_status.py`
- `docs/commercial-structural-solver-product-gap-ledger.md`
- `docs/structural-analysis-ai-engine-gap-ledger.md`
- `implementation/phase1/release_evidence/productization/`

Verification criteria:

- New summary records followup362-363 results or a bounded no-promotion/timeout boundary.
- If residual improves, status report exposes the new latest cached residual/JVP receipt and keeps G1 partial.
- If residual does not improve, receipt remains non-closing diagnostic evidence.
- Commercial and AI ledgers do not promote G1/G6/G7 or autonomous AI readiness.
- Focused tests, readiness/status/audit checks, `ai-preflight`, and `ai-verify` pass.

## Return Format

Return only these sections:

- Design summary
- Implementation order
- Candidate files
- Verification plan
- Risks and claim boundary
- Cursor handoff prompt
