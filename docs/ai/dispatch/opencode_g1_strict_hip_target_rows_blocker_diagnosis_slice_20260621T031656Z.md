# OpenCode worker slice: G1 strict HIP target_rows blocker diagnosis

Goal:
- Diagnose the next concrete blocker for G1 consistent Newton after `target_rows` row-support selection has been routed through the controllers.
- Keep the scope on ROCm/HIP residual replay, not CPU fallback closure.

Scope:
- Inspect current code and receipts only as needed:
  - `implementation/phase1/run_mgt_direct_residual_newton_probe.py`
  - `implementation/phase1/run_mgt_shell_material_rowcorr_budget_controller.py`
  - `implementation/phase1/run_mgt_g1_alternating_newton_controller.py`
  - `tests/test_mgt_direct_residual_newton_probe.py`
  - `tests/test_mgt_shell_material_rowcorr_budget_controller.py`
  - `tests/test_mgt_g1_alternating_newton_controller.py`
  - recent `implementation/phase1/release_evidence/productization/mgt_shell_material_rowcorr_budget_controller_followup*.json`
  - recent `implementation/phase1/release_evidence/productization/mgt_g1_followup*.json`

Work requested:
- Identify whether a strict HIP row lane with finite-difference `target_rows` can run without CPU fallback/claim-boundary regression.
- If a small code or test fix is clearly needed, implement it.
- Do not regenerate PM release evidence.
- Do not claim G1 closure.

Verification criteria:
- Report changed files only.
- Report exact tests run and failing test names if any.
- Summarize the next blocker in terms of fallback-zero, HIP residual contract, material Newton claim boundary, or runtime unavailable state.
