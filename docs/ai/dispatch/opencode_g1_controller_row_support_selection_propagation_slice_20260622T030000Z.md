# OpenCode slice: G1 controller row support-selection propagation

Goal:
- Propagate direct-probe `current_tangent_residual_row_support_selection=target_rows` through G1 row-correction controllers.

Scope:
- `implementation/phase1/run_mgt_shell_material_rowcorr_budget_controller.py`
- `implementation/phase1/run_mgt_g1_alternating_newton_controller.py`
- Tests:
  - `tests/test_mgt_shell_material_rowcorr_budget_controller.py`
  - `tests/test_mgt_g1_alternating_newton_controller.py`

Implementation intent:
- Add `row_support_selection` parameter/CLI where row FD support selection is passed to `run_mgt_direct_residual_newton_probe.py`.
- Preserve existing defaults (`row_strongest`).
- Allow `target_rows` so HIP-required finite-difference row-correction lanes can use stiffness-free support selection.
- Record the selected support mode in controller payloads/rows.

Verification criteria:
- Focused tests prove child command includes `--current-tangent-residual-row-support-selection target_rows`.
- Existing G1/HIP focused suite remains green.
