# OpenCode slice: G1 strict HIP claim-boundary audit

Goal:
Make `run_mgt_g1_alternating_newton_controller.py` reject child receipts in
strict HIP residual mode when the child receipt still declares itself
CPU-diagnostic or still says official ROCm/HIP closure is required, even if the
child reports `fallback_zero_passed=true`.

Scope:
- `implementation/phase1/run_mgt_g1_alternating_newton_controller.py`
- `tests/test_mgt_g1_alternating_newton_controller.py`

Context:
- Direct/adaptive/shell controllers now reject HIP-required CPU backends and
  preflight HIP-required runtime paths.
- The top-level strict audit currently inspects `gate_assessment`,
  `controller.preflight_blockers`, and strict-looking top-level blockers.
- A child receipt can still include a claim boundary such as
  `{"cpu_diagnostic_only": true, "official_rocm_hip_closure_required": true}`.
  In strict HIP residual mode, that receipt must not be promotable.

Implementation requirements:
- Extend `_strict_fallback_zero_audit(...)` to inspect each receipt's
  `claim_boundary`.
- If `claim_boundary` is a dict and includes `cpu_diagnostic_only: true`, add a
  blocker.
- If `claim_boundary` is a dict and includes
  `official_rocm_hip_closure_required: true`, add a blocker.
- If `claim_boundary` is a string containing CPU/host/fallback/ROCm-HIP-required
  strict-boundary wording, add a blocker.
- Ensure nested child receipts referenced from accepted rows/promoted rows are
  checked the same way.
- Do not edit PM evidence, ledgers, or support bundles.

Verification:
- Add a focused test where a child receipt has `fallback_zero_passed=true` and
  `claim_boundary.cpu_diagnostic_only=true`; strict audit must fail and the
  controller must not promote the child.
- Existing strict positive-path tests should still pass when the fake child
  receipt does not carry CPU-diagnostic claim boundaries.
- Run:
  - `python3 -m pytest -q tests/test_mgt_g1_alternating_newton_controller.py`
  - `python3 -m py_compile implementation/phase1/run_mgt_g1_alternating_newton_controller.py`

Output summary only:
- changed files
- test commands/results
- blockers, if any
