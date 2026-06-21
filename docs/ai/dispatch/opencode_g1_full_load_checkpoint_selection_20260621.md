# G1 full-load HIP checkpoint selection slice

Goal: make `scripts/run_g1_full_load_hip_newton_lane.py` select the best available checkpoint candidate from existing G1 frontier/status evidence, without promoting sub-full-load evidence as closure.

Scope:
- `scripts/run_g1_full_load_hip_newton_lane.py`
- `tests/test_run_g1_full_load_hip_newton_lane.py`
- Existing evidence shape references:
  - `implementation/phase1/release_evidence/productization/g1_checkpoint_retention_manifest.json`
  - `implementation/phase1/release_evidence/productization/mgt_g1_followup387_shell_material_budgeted_continuation_status.json`

Requirements:
- Preserve explicit `--checkpoint-npz` override behavior.
- If no explicit checkpoint is supplied, scan configured status/manifest JSON files for `.npz` checkpoint paths, read each checkpoint load scale, and select the highest-load candidate.
- If a full-load candidate exists, the lane may proceed to dry-run/child execution as today, still requiring child HIP/material/fallback safety gates.
- If only sub-full-load candidates exist, select the highest-load candidate but keep `checkpoint_load_scale_below_required_full_load` blocked before child execution.
- Add receipt-visible selection metadata such as source paths, candidate count, highest observed load scale, and selection reason.
- Do not mark G1 closure, do not synthesize receipts, do not relax thresholds, and do not change child safety requirements.

Tests:
- Full-load candidate in a status/manifest source is selected when no explicit checkpoint is supplied.
- Highest sub-full-load candidate is selected and still blocked.
- Explicit `checkpoint_npz` overrides source-based selection.

Deliverable:
- Implement the smallest safe code/test change.
- Run focused pytest for `tests/test_run_g1_full_load_hip_newton_lane.py`.
- Summarize changed files, tests, and any blockers only.
