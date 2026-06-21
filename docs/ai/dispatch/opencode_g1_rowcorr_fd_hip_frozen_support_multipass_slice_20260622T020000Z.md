# OpenCode slice: G1 row-correction HIP FD multipass with frozen support scaffold

Goal:
- Allow HIP-required row-correction multipass to continue without CPU tangent refresh when `current_tangent_residual_row_jacobian_mode=finite_difference`.

Scope:
- Candidate file: `implementation/phase1/run_mgt_direct_residual_newton_probe.py`
- Candidate test: `tests/test_mgt_direct_residual_newton_probe.py`
- Focus on row-correction promotion after accepted HIP residual candidate.

Implementation intent:
- If accepted row candidate was evaluated by HIP residual replay and the row Jacobian mode is finite-difference, keep the accepted HIP residual/free/rhs.
- Do not call CPU `assemble_residual` for tangent refresh.
- Continue the next row pass using the previous stiffness/support graph only as a support-selection scaffold, while the actual row Jacobian remains finite-difference residual replay.
- Record metadata that the support graph is frozen/stale and only valid as a scaffold.
- Current-tangent mode should still stop after accepted HIP residual promotion if HIP tangent refresh is unavailable.

Verification criteria:
- Focused tests prove finite-difference HIP-required row-correction can attempt a second pass without CPU residual/tangent refresh blockers.
- Current-tangent HIP-required path still stops after first promotion without CPU fallback.
- Do not claim G1 closure.
