# OpenCode Worker Slice: G1 frozen shell-material tangent HIP replay

Goal:
Move G1 residual replay away from CPU for shell-material runs by adding an explicit, non-closure HIP replay mode that uses the current accepted state's shell-material tangent CSR as a frozen HIP operator. Do not claim full material Newton closure.

Context:
- `run_mgt_direct_residual_newton_probe.py` currently disables HIP residual batch replay when `apply_shell_material_tangent=True` with reason `state_dependent_shell_material_tangent_requires_cpu_batch`.
- CPU physical residual batch recomputes shell material tangent per candidate state in `mgt_physical_residual_assembly.py`.
- Native HIP full residual backend currently evaluates frame force + shell CSR + spring CSR. It can replay a frozen shell CSR on GPU, but it does not recompute state-dependent shell material tangent per candidate.
- The user explicitly wants residual solved through ROCm/HIP rather than CPU. A frozen-current-tangent HIP replay is a useful intermediate implementation path only if the receipt keeps the material-Newton limitation visible.

Scope:
- Primary: `implementation/phase1/run_mgt_direct_residual_newton_probe.py`
- Tests: `tests/test_mgt_direct_residual_newton_probe.py`
- Optional only if required: `implementation/phase1/run_mgt_shell_material_rowcorr_budget_controller.py` and its tests

Required behavior:
- Add an explicit option/parameter, e.g. `allow_frozen_shell_material_tangent_hip_replay`, for direct residual probe.
- Default behavior stays conservative: `apply_shell_material_tangent=True` still disables HIP batch replay unless the explicit option is enabled.
- When explicit frozen mode is enabled and a HIP backend is requested:
  - build the HIP shell CSR from the current state with shell material tangents applied;
  - use HIP residual batch replay for matrix-free global Krylov and/or row correction candidates;
  - metadata must say this is `frozen_shell_material_tangent_hip_replay`, not state-dependent material Newton;
  - do not set full material Newton closure or direct residual closure unless existing residual/increment/fallback-zero gates actually pass;
  - fallback-zero audit must not record CPU fallback for this frozen HIP path if the HIP backend is actually used.
- If HIP backend preparation/evaluation fails and HIP is required, keep the existing blocker behavior and do not fall back to CPU.
- Preserve default CPU diagnostic behavior for non-HIP runs.

Tests to add/update:
- Parser/default test proves the new flag defaults false and can be enabled.
- Unit test with monkeypatched HIP backend preparation/evaluate proves `apply_shell_material_tangent=True` plus explicit frozen flag does not set `state_dependent_shell_material_tangent_requires_cpu_batch` and records frozen-HIP metadata.
- Test proves without the explicit flag the old disabled reason remains.
- Test proves HIP-required frozen path still blocks instead of CPU falling back if backend prepare/evaluate fails.

Verification:
- `python3 -m pytest -q tests/test_mgt_direct_residual_newton_probe.py`
- If shell row controller touched: `python3 -m pytest -q tests/test_mgt_shell_material_rowcorr_budget_controller.py`

Output:
- Concise summary only: changed files, tests run, failures/blockers.
- Do not include full unified diffs.
