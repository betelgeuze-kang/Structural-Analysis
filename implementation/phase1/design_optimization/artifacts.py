"""Shared artifact paths for bounded design-optimization refactor.

The goal is to remove repeated hard-coded release paths from multiple runner
scripts without moving the existing CLI entrypoints yet.
"""

from __future__ import annotations

from pathlib import Path


PHASE1_DIR = Path(__file__).resolve().parent.parent
RELEASE_DIR = PHASE1_DIR / "release"
DESIGN_OPT_RELEASE_DIR = RELEASE_DIR / "design_optimization"
COMMITTEE_REVIEW_DIR = RELEASE_DIR / "committee_review"
PBD_REVIEW_DIR = RELEASE_DIR / "pbd_review"


def artifact_path(filename: str, *, root: Path = DESIGN_OPT_RELEASE_DIR) -> str:
    return str(root / filename)


DATASET_NPZ = artifact_path("design_optimization_dataset.npz")
DATASET_REPORT_JSON = artifact_path("design_optimization_dataset_report.json")
SOLVER_LOOP_REPORT_JSON = artifact_path("design_optimization_solver_loop_report.json")
SOLVER_LOOP_STATE_NPZ = artifact_path("design_optimization_solver_loop_state.npz")
SOLVER_LOOP_LONG_REPORT_JSON = artifact_path("design_optimization_solver_loop_long_report.json")
SOLVER_LOOP_LONG_STATE_NPZ = artifact_path("design_optimization_solver_loop_long_state.npz")
BASELINE_REPORT_JSON = artifact_path("design_optimization_baseline_report.json")
BUDGETED_REPORT_JSON = artifact_path("design_optimization_budgeted_report.json")
BUDGETED_STATE_NPZ = artifact_path("design_optimization_budgeted_state.npz")
STAGE_A_REPORT_JSON = artifact_path("design_optimization_stage_a_report.json")
STAGE_B_REPORT_JSON = artifact_path("design_optimization_stage_b_report.json")
STAGE_C_REPORT_JSON = artifact_path("design_optimization_stage_c_report.json")
ABLATION_REPORT_JSON = artifact_path("design_optimization_ablation_report.json")
ABLATION_CACHE_DIR = artifact_path("ablation_cache")
OBJECTIVE_CALIBRATION_REPORT_JSON = artifact_path("design_objective_calibration_report.json")
OBJECTIVE_PROFILE_REPORT_JSON = artifact_path("design_objective_profile_report.json")
COST_REDUCTION_REPORT_JSON = artifact_path("design_optimization_cost_reduction_report.json")
COST_REDUCTION_SMOKE_REPORT_JSON = artifact_path("design_optimization_cost_reduction_smoke_report.json")
COST_REDUCTION_SMOKE_HISTORY_JSON = artifact_path("design_optimization_cost_reduction_smoke_history.json")
COST_REDUCTION_CHANGES_JSON = artifact_path("design_optimization_cost_reduction_changes.json")
COST_REDUCTION_CHANGES_CSV = artifact_path("design_optimization_cost_reduction_changes.csv")
COST_REDUCTION_CHANGES_SUMMARY_JSON = artifact_path("design_optimization_cost_reduction_changes_summary.json")
COST_REDUCTION_CHANGES_SUMMARY_CSV = artifact_path("design_optimization_cost_reduction_changes_summary.csv")
COST_REDUCTION_BLOCKED_ACTIONS_JSON = artifact_path("design_optimization_cost_reduction_blocked_actions.json")
COST_REDUCTION_BLOCKED_ACTIONS_CSV = artifact_path("design_optimization_cost_reduction_blocked_actions.csv")
COST_REDUCTION_NO_GAIN_GROUPS_JSON = artifact_path("design_optimization_cost_reduction_no_cost_gain_groups.json")
COST_REDUCTION_NO_GAIN_GROUPS_CSV = artifact_path("design_optimization_cost_reduction_no_cost_gain_groups.csv")
COST_REDUCTION_NO_GAIN_EXPLAIN_JSON = artifact_path("design_optimization_cost_reduction_no_cost_gain_explain.json")
COST_REDUCTION_NO_GAIN_EXPLAIN_CSV = artifact_path("design_optimization_cost_reduction_no_cost_gain_explain.csv")
ACCEPTED_CANDIDATE_EXPLAIN_JSON = artifact_path("design_optimization_cost_reduction_accepted_candidate_explain.json")
ACCEPTED_CANDIDATE_EXPLAIN_CSV = artifact_path("design_optimization_cost_reduction_accepted_candidate_explain.csv")
COST_REDUCTION_REVERSE_SYNC_JSON = artifact_path("design_optimization_cost_reduction_reverse_sync_table.json")
COST_REDUCTION_REVERSE_SYNC_CSV = artifact_path("design_optimization_cost_reduction_reverse_sync_table.csv")
CANDIDATE_EXPLAIN_V2_JSON = artifact_path("design_optimization_candidate_explain_v2.json")
CANDIDATE_EXPLAIN_V2_CSV = artifact_path("design_optimization_candidate_explain_v2.csv")
REJECTED_CANDIDATE_EXPLAIN_V2_JSON = artifact_path("design_optimization_rejected_candidate_explain_v2.json")
REJECTED_CANDIDATE_EXPLAIN_V2_CSV = artifact_path("design_optimization_rejected_candidate_explain_v2.csv")


EXTERNAL_FULL_ARTIFACTS_DESIGN_OPT = [
    SOLVER_LOOP_LONG_REPORT_JSON,
    SOLVER_LOOP_LONG_STATE_NPZ,
    BUDGETED_REPORT_JSON,
    STAGE_A_REPORT_JSON,
    STAGE_B_REPORT_JSON,
    STAGE_C_REPORT_JSON,
    ABLATION_REPORT_JSON,
    OBJECTIVE_PROFILE_REPORT_JSON,
    COST_REDUCTION_REPORT_JSON,
    COST_REDUCTION_CHANGES_JSON,
    COST_REDUCTION_CHANGES_CSV,
    COST_REDUCTION_BLOCKED_ACTIONS_JSON,
    COST_REDUCTION_BLOCKED_ACTIONS_CSV,
    COST_REDUCTION_NO_GAIN_GROUPS_JSON,
    COST_REDUCTION_NO_GAIN_GROUPS_CSV,
    COST_REDUCTION_NO_GAIN_EXPLAIN_JSON,
    COST_REDUCTION_NO_GAIN_EXPLAIN_CSV,
    COST_REDUCTION_REVERSE_SYNC_JSON,
    COST_REDUCTION_REVERSE_SYNC_CSV,
    CANDIDATE_EXPLAIN_V2_JSON,
    CANDIDATE_EXPLAIN_V2_CSV,
    REJECTED_CANDIDATE_EXPLAIN_V2_JSON,
    REJECTED_CANDIDATE_EXPLAIN_V2_CSV,
]

EXTERNAL_LIGHT_ARTIFACTS_DESIGN_OPT = [
    SOLVER_LOOP_LONG_REPORT_JSON,
    BUDGETED_REPORT_JSON,
    ABLATION_REPORT_JSON,
    OBJECTIVE_PROFILE_REPORT_JSON,
    COST_REDUCTION_REPORT_JSON,
    COST_REDUCTION_CHANGES_CSV,
    COST_REDUCTION_BLOCKED_ACTIONS_CSV,
    COST_REDUCTION_NO_GAIN_GROUPS_CSV,
    COST_REDUCTION_NO_GAIN_EXPLAIN_CSV,
    COST_REDUCTION_REVERSE_SYNC_CSV,
    CANDIDATE_EXPLAIN_V2_CSV,
    REJECTED_CANDIDATE_EXPLAIN_V2_CSV,
]
