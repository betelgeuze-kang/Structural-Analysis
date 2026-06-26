# Kiro G1 Cached JVP Regeneration Feasibility Design

You are Kiro running as a design-only architect on model `opus-4.8`. Codex owns the active goal, acceptance criteria, verification planning, claim-boundary review, and final acceptance. Cursor `composer-2.5` may implement an approved scoped slice if needed.

Do not edit files. Do not claim readiness closure. Do not produce a long design document.

## Task

Goal: Design a narrow, non-promoting G1 evidence slice that determines whether the cached residual/JVP followup354-361 restart chain can be regenerated or must remain explicitly blocked.

Current blocker: `mgt_g1_followup387_shell_material_budgeted_continuation_status.json` reports `restart_ready=false`, `latest_checkpoint_exists=false`, `controller_start_checkpoint_exists=false`, `advertised_retained_checkpoint_missing=true`, and `missing_controller_replay_artifact_count=10` for `mgt_cached_residual_jvp_top96_multi_ridge_followup354_361_after_total_scaled_component_fd_hip_latest_only_controller_summary.json`. G1 remains partial and must not be represented as closed.

Scope: Design only a feasibility and evidence-boundary slice. The slice may inspect the controller, existing receipts, required checkpoint paths, and command-line feasibility. If regeneration is attempted, it must be bounded, diagnostic-only, and must not promote G1. If regeneration is not attempted, it must improve the machine-readable blocker so future routing knows exactly why. Non-goals: no full-load closure claim, no production ROCm/HIP closure claim, no external mutation, no readiness status promotion.

Candidate files:

- `implementation/phase1/run_mgt_cached_residual_jvp_multi_ridge_controller.py`
- `implementation/phase1/run_mgt_cached_residual_jvp_batch_probe.py`
- `scripts/build_mgt_g1_shell_material_budgeted_continuation_status.py`
- `implementation/phase1/commercial_gap_ledger_status.py`
- `tests/test_build_mgt_g1_shell_material_budgeted_continuation_status.py`
- `tests/test_commercial_gap_ledger_status.py`
- `docs/commercial-structural-solver-product-gap-ledger.md`
- `docs/structural-analysis-ai-engine-gap-ledger.md`

Verification criteria:

- The resulting evidence distinguishes launch/feasibility, missing start checkpoint, missing step basis NPZs, retained latest checkpoint, and actual replay verification.
- G1 remains `partial` unless full-load, full-mesh nonlinear equilibrium, material Newton breadth, and production ROCm/HIP residency are all proven.
- Any regenerated diagnostic receipt is marked non-promoting and does not erase external or operator-corpus blockers.
- Focused tests cover any new fields, and `commercial_gap_ledger_status.json` plus dependent readiness artifacts stay consistent.

## Return Format

Return only these sections:

- Design summary
- Implementation order
- Candidate files
- Verification plan
- Risks and claim boundary
- Cursor handoff prompt
