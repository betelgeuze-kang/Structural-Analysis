# OpenCode slice: G1 shell row-correction HIP backend rejection

Goal:
Make the shell-material row-correction budget controller reject
`row_require_hip_batch_replay=True` when the selected row batch replay backend is
CPU, matching the stricter G1 HIP residual boundary used by the direct probe and
adaptive global controller.

Scope:
- `implementation/phase1/run_mgt_shell_material_rowcorr_budget_controller.py`
- `tests/test_mgt_shell_material_rowcorr_budget_controller.py`

Context:
- The controller currently blocks all HIP-required shell-material row work before
  child launch because the shell-material tangent HIP batch backend is not
  available.
- That preserves the claim boundary, but `row_require_hip_batch_replay=True` with
  backend `cpu` is still accepted as a controller preflight blocker rather than
  rejected as an invalid strict-HIP configuration.
- Direct probe and adaptive global controller now raise/return CLI errors for the
  equivalent Python API and CLI invalid CPU-backend state.

Implementation requirements:
- Normalize `row_batch_replay_backend` early in
  `run_shell_material_rowcorr_budget_controller(...)`.
- If `row_require_hip_batch_replay=True` and normalized backend is `cpu`, raise
  `ValueError` before reading seed/checkpoint or creating child launch state.
- In `main(...)`, return code `2` with a clear stderr message for the same invalid
  CLI combination.
- Preserve the existing preflight-blocker receipt for valid HIP backends where
  the HIP shell-material tangent backend is unavailable.
- Preserve non-HIP CPU diagnostic behavior.
- Do not edit PM evidence, ledgers, or support bundles.

Verification:
- Add tests:
  - Python API rejects `row_require_hip_batch_replay=True` with backend `cpu`.
  - CLI rejects `--row-require-hip-batch-replay` without a HIP row backend.
  - Existing valid-HIP-backend preflight-blocker test still passes.
- Run:
  - `python3 -m pytest -q tests/test_mgt_shell_material_rowcorr_budget_controller.py`
  - `python3 -m py_compile implementation/phase1/run_mgt_shell_material_rowcorr_budget_controller.py`

Output summary only:
- changed files
- test commands/results
- blockers, if any
