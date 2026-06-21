# OpenCode slice: G1 row-correction HIP-only stop after accepted residual promotion

Goal:
- For HIP-required row-correction in `run_mgt_direct_residual_newton_probe.py`, stop after an accepted HIP residual promotion when the next pass would require CPU tangent refresh.
- Preserve the accepted HIP residual and avoid CPU residual/tangent fallback.

Scope:
- Candidate file: `implementation/phase1/run_mgt_direct_residual_newton_probe.py`
- Candidate test: `tests/test_mgt_direct_residual_newton_probe.py`
- Focus on the row-correction promotion block around `hip_residual_refresh_available`.

Implementation intent:
- If `row_require_hip_batch_replay` and an accepted candidate has HIP residual replay metadata, use the accepted candidate residual/free/rhs.
- If the promotion is not terminal and no HIP tangent refresh is available, do not call CPU `assemble_residual` for tangent refresh. Instead record `accepted_state_tangent_refresh_backend=not_refreshed_hip_required_row_correction`, stop row-correction after this promotion, and keep fallback-zero CPU blockers absent.
- Do not claim G1 closure; residual/material/full-load gates still decide readiness.

Verification criteria:
- Focused tests show multipass HIP-required row-correction stops after one HIP residual promotion without CPU residual or tangent refresh blockers.
- G1/HIP focused suite remains green.
