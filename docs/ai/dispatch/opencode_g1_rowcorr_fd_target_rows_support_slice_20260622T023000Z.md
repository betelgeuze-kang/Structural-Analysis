# OpenCode slice: G1 row-correction finite-difference target-row support mode

Goal:
- Add a finite-difference-only row-correction support selection mode that does not depend on CPU tangent/stiffness rows for support columns.

Scope:
- Candidate file: `implementation/phase1/run_mgt_direct_residual_newton_probe.py`
- Candidate test: `tests/test_mgt_direct_residual_newton_probe.py`
- Focus on `current_tangent_residual_row_support_selection`, row pass `k_ff/support_graph`, and FD support column trimming.

Implementation intent:
- Add `target_rows` support selection mode.
- Only allow it with `current_tangent_residual_row_jacobian_mode=finite_difference`.
- In this mode, support columns are the selected target residual rows (plus optional node-block expansion), no `k_ff`/`support_graph` support selection is used, and FD replay supplies the actual Jacobian.
- Record receipt metadata that support selection was stiffness-free.

Verification criteria:
- Parser accepts `--current-tangent-residual-row-support-selection target_rows`.
- Focused HIP-required FD row-correction test shows `support_selection=target_rows`, FD HIP batch replay, and stiffness-free support metadata.
- Current-tangent behavior remains unchanged.
