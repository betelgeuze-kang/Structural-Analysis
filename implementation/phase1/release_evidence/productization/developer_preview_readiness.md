# Open Benchmark Developer Preview Readiness

- `status`: `blocked`
- `developer_preview_ready`: `False`
- `commercial_release_ready`: `False`
- `blocker_count`: `63`
- `future_commercial_blocker_count`: `23`
- `source_commit_sha`: `d33a7132976afce8a56aa4cc8e10d26b7285010b`

## Blocker Categories

| Category | Count | Developer Preview Blocking |
|---|---:|---|
| numerical | 32 | yes |
| benchmark | 13 | yes |
| software product | 18 | yes |
| future commercial | 23 | no, future commercial only |

## Included Scope

- IFC/MGT/neutral JSON import for public or locally acquired benchmark models
- linear static, modal, buckling, and validated bounded nonlinear static paths
- residual, reaction, energy, provenance, and reproducibility audit reports
- Open benchmark scorecards and commercial-tool comparison imports
- local desktop/web GUI review workflow for benchmark evidence

## Excluded Scope

- permit or code-compliance automation
- structural engineer replacement
- customer SLA or production support commitment
- multi-tenant SaaS, account, permission, or license-server operation
- customer shadow evidence as a Developer Preview blocker
- product/legal commercial license approval as a Developer Preview blocker
- 30-run commercial CI streak or external approval receipts as Developer Preview blockers
- AI/GNN predictions as independent truth before deterministic solver closure

## Freeze Policy

- `new_feature_development`: `frozen_until_developer_preview_baseline_is_clean`
- `ai_training`: `frozen_until_deterministic_reference_solver_and_benchmark_truth_are_fixed`
- `gpu_hip`: `performance_track_after_cpu_reference_parity`

## Claim Boundary

Developer Preview is an open benchmark workstation preview, not a commercial structural solver beta. Customer shadow, commercial license/legal approval, commercial SLA, 30-run CI streak, and external approval receipts remain visible as future Commercial Release blockers but do not block Developer Preview.
