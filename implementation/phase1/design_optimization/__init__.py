"""Bounded refactor namespace for design-optimization paths and entrypoints.

This package intentionally does not move the existing flat runner scripts.
It provides a stable import surface for shared paths, artifact groups, and
entrypoint metadata while preserving current CLI compatibility.
"""

from .artifacts import (
    COMMITTEE_REVIEW_DIR,
    DESIGN_OPT_RELEASE_DIR,
    EXTERNAL_LIGHT_ARTIFACTS_DESIGN_OPT,
    EXTERNAL_FULL_ARTIFACTS_DESIGN_OPT,
    PBD_REVIEW_DIR,
    artifact_path,
)
from .artifact_writers import (
    write_blocked_action_artifacts,
    write_candidate_explain_artifacts,
    write_cost_reduction_support_artifacts,
    write_design_optimization_report,
    write_design_change_artifacts,
    write_stage_report,
)
from .io import entrypoint_group_rows, entrypoint_status_rows, load_design_opt_reports
from .entrypoints import ENTRYPOINTS, entrypoint_rows

__all__ = [
    "COMMITTEE_REVIEW_DIR",
    "DESIGN_OPT_RELEASE_DIR",
    "ENTRYPOINTS",
    "EXTERNAL_FULL_ARTIFACTS_DESIGN_OPT",
    "EXTERNAL_LIGHT_ARTIFACTS_DESIGN_OPT",
    "PBD_REVIEW_DIR",
    "artifact_path",
    "write_blocked_action_artifacts",
    "write_candidate_explain_artifacts",
    "write_cost_reduction_support_artifacts",
    "write_design_optimization_report",
    "write_design_change_artifacts",
    "write_stage_report",
    "entrypoint_rows",
    "entrypoint_group_rows",
    "entrypoint_status_rows",
    "load_design_opt_reports",
]
