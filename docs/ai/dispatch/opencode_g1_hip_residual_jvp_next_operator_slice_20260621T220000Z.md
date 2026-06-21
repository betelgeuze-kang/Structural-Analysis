# OpenCode Worker Slice: G1 HIP Residual JVP Next Operator

Goal:
- Find the next implementation step that moves G1 from CPU-diagnostic Newton/Krylov toward an actual ROCm/HIP residual/JVP operator path.

Scope:
- `implementation/phase1/mgt_hip_full_residual_backend.py`
- `implementation/phase1/run_mgt_direct_residual_newton_probe.py`
- `implementation/phase1/run_mgt_direct_residual_adaptive_preconditioned_global_newton.py`
- `implementation/phase1/run_mgt_shell_material_rowcorr_budget_controller.py`
- Relevant tests under `tests/test_mgt_*hip*`, `tests/test_mgt_direct_residual_*`, and controller tests.

Questions:
- Where does the current HIP backend stop at residual replay only, and where does matrix-free JVP/global Krylov still rely on CPU/current-tangent pieces?
- Is there a small implementation step to make HIP batch replay metadata stricter or to expose a reusable HIP residual-JVP candidate generator without claiming closure?
- Can strict HIP mode avoid CPU current-tangent preconditioner while still testing a HIP-residual-only JVP path with auditable blockers when runtime is unavailable?

Constraints:
- Do not claim G1 closure.
- Do not promote CPU-diagnostic evidence.
- Keep full-load/full-mesh/material Newton blockers visible.
- Prefer focused tests with monkeypatch/fake receipts over long solver runs.

Output summary only:
- Candidate change.
- Files touched.
- Tests run.
- Blockers.
