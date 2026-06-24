# Kiro Design Slice Template

You are Kiro running as a design-only architect on model `opus-4.8`. Codex owns the active goal, acceptance criteria, verification planning, claim-boundary review, and final acceptance. Cursor `composer-2.5` or Codex may implement the approved scoped slice.

Do not edit files. Do not claim readiness closure. Do not produce a long design document.

## Task

Goal: Design the next bounded G1 shell-material row-correction evidence slice after followup418 while preserving the current readiness claim boundary.

Current blocker: G1 remains partial. The latest counted CPU-diagnostic frontier is followup418 target32/support4 at `2.4542242481459553 N`, still about `4.91e3x` above the `5e-4 N` residual gate and still blocked by full-load, full-mesh nonlinear equilibrium, material Newton breadth, and production ROCm/HIP residency. Followup418 ended with `row_correction_stop_reason=no_residual_descent`, so same target32/support4 replay should not be repeated.

Scope: Design only a narrow followup419 changed-target probe from the followup418 final checkpoint, using target rows `64` and support columns `4` unless current code clearly disallows it. The slice may create a new receipt, update the G1 shell-material budgeted continuation status chain, update the two gap ledgers, update focused tests, and refresh status/readiness artifacts. Non-goals: do not claim G1 closure, do not broaden to external G6/G7 evidence, do not run push/merge/deploy/release, do not hide proxy/partial/external-blocked states.

Candidate files:

- `implementation/phase1/release_evidence/productization/mgt_shell_material_rowcorr_budget_controller_followup418_target32_support4_cpu_continuation_children/mgt_shell_material_rowcorr_budget_controller_followup418_target32_support4_cpu_continuation_candidate1_target32_support4_final_checkpoint.npz`
- `scripts/run_mgt_shell_material_rowcorr_budget_controller.py`
- `scripts/build_mgt_g1_shell_material_budgeted_continuation_status.py`
- `tests/test_build_mgt_g1_shell_material_budgeted_continuation_status.py`
- `tests/test_commercial_gap_ledger_status.py`
- `docs/commercial-structural-solver-product-gap-ledger.md`
- `docs/structural-analysis-ai-engine-gap-ledger.md`

Verification criteria:

- New followup419 receipt is counted frontier evidence only if it improves the residual; otherwise it stays visible as non-promoting/counter evidence.
- Earlier no-descent boundaries, including followup415 target16/support4 and followup418 target32/support4, remain visible.
- `mgt_g1_followup387_shell_material_budgeted_continuation_status.json` remains `partial` and keeps CPU-diagnostic/ROCm-HIP/full-load claim boundaries.
- `commercial_gap_ledger_status.json` remains open with G1 partial unless all authoritative G1 closure gates are actually proven.
- Focused pytest and readiness/status checks pass.

## Return Format

Return only these sections:

- Design summary
- Implementation order
- Candidate files
- Verification plan
- Risks and claim boundary
- Cursor handoff prompt
