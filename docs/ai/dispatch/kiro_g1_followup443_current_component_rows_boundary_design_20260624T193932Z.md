# Kiro Design Slice

You are Kiro running as a design-only architect on model `opus-4.8`. Codex owns the active goal, acceptance criteria, verification planning, claim-boundary review, and final acceptance. Cursor `composer-2.5` may implement the approved scoped slice if implementation edits are needed.

Do not edit files. Do not claim readiness closure. Do not produce a long design document.

## Task

Goal: Design the smallest safe way to convert the existing G1 followup443 `current_component_rows` launch-only child receipt into completed, status-bound boundary evidence, or explicitly classify it as launch-only if completion is not possible.

Current blocker: G1 remains partial. The latest counted shell-material frontier is `1.3092276661494922 N` from followup431 target128/support8, still far above the `5e-4 N` direct-residual gate. Followups 440-442 are non-promoting no-descent boundary receipts. The current worktree contains only a followup443 child launch receipt under `implementation/phase1/release_evidence/productization/mgt_shell_material_rowcorr_budget_controller_followup443_current_component_rows_support8_cpu_continuation_children/`; no parent controller summary is status-bound yet.

Scope: Design only a bounded CPU-diagnostic followup443 completion using `scripts/run_mgt_shell_material_rowcorr_budget_controller.py` / `implementation/phase1/run_mgt_shell_material_rowcorr_budget_controller.py` from the followup431 compact checkpoint, target mode `current_component_rows`, target rows `128`, support columns `8`, alpha `0.015625`, max four row promotions, compact child checkpoint, and all output under `implementation/phase1/release_evidence/productization/`. Non-goals: no full-load/full-mesh/material Newton/production ROCm-HIP closure claim, no G6/G7 claim changes, no broad refactor, no use of parent top-level residual as counted frontier when child receipt disagrees.

Candidate files:

- `implementation/phase1/run_mgt_shell_material_rowcorr_budget_controller.py`
- `scripts/build_mgt_g1_shell_material_budgeted_continuation_status.py`
- `tests/test_build_mgt_g1_shell_material_budgeted_continuation_status.py`
- `docs/commercial-structural-solver-product-gap-ledger.md`
- `docs/structural-analysis-ai-engine-gap-ledger.md`
- `implementation/phase1/release_evidence/productization/mgt_shell_material_rowcorr_budget_controller_followup431_target128_support8_cpu_continuation_compact_checkpoint.npz`
- `implementation/phase1/release_evidence/productization/mgt_shell_material_rowcorr_budget_controller_followup443_current_component_rows_support8_cpu_continuation_children/mgt_shell_material_rowcorr_budget_controller_followup443_current_component_rows_support8_cpu_continuation_candidate1_target128_support8.json`

Verification criteria:

- Wrapper receipt confirms Kiro `opus-4.8` prelaunch validation, design-only no-edit boundary, and no-readiness-closure boundary.
- A completed followup443 parent/child receipt is produced or the existing launch-only receipt is explicitly classified as non-counted launch evidence.
- G1 status remains `partial` and does not hide `direct_residual_gate_not_closed`, `full_mesh_nonlinear_equilibrium_not_closed`, `production_rocm_hip_residual_row_backend_not_closed`, or `consistent_residual_jacobian_newton_not_closed`.
- If followup443 completes, both commercial and AI ledgers describe it as boundary evidence only and avoid closure language.
- Focused tests and readiness/status checks pass.

## Return Format

Return only these sections:

- Design summary
- Implementation order
- Candidate files
- Verification plan
- Risks and claim boundary
- Cursor handoff prompt
